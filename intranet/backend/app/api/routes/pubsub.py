import asyncio
import importlib
import logging
import os
from typing import Callable, List, Optional
import threading
import json

logger = logging.getLogger(__name__)


class PubSub:
    def __init__(self, channel: str = "intranet-ws"):
        self.channel = channel
        self._handlers: List[Callable[[str], None]] = []
        self._valkey_client = None
        # indicates whether we should attempt to use valkey for publish/subscribe
        self._valkey_usable = False
        # indicates whether we've successfully started a subscribe/listen path
        self._valkey_subscribed = False
        self._valkey_task: Optional[asyncio.Task] = None

        # try to import valkey dynamically; if not available we'll stay in local mode
        try:
            # log environment hints so operators can see what host/port/url we will try
            logger.debug(
                "PubSub: VALKEY envs: VALKEY_HOST=%s VALKEY_PORT=%s VALKEY_URL=%s",
                os.getenv("VALKEY_HOST"), os.getenv("VALKEY_PORT"), os.getenv("VALKEY_URL"),
            )

            valkey_mod = importlib.import_module("valkey")
            # try a few common names for a client constructor
            client = None
            for attr in ("Valkey", "Client", "ValkeyClient"):
                if hasattr(valkey_mod, attr):
                    client_cls = getattr(valkey_mod, attr)
                    # try a few constructor signatures to be resilient across valkey versions
                    def _try_ctor(cls):
                        # prefer explicit host/port or URL before default no-arg
                        try:
                            host = os.getenv("VALKEY_HOST", "valkey")
                            port = int(os.getenv("VALKEY_PORT", "6379"))
                            inst = cls(host=host, port=port)
                            logger.debug("PubSub: constructed valkey client via host/port kwargs")
                            return inst
                        except Exception:
                            pass
                        try:
                            host = os.getenv("VALKEY_HOST", "valkey")
                            port = int(os.getenv("VALKEY_PORT", "6379"))
                            inst = cls(host, port)
                            logger.debug("PubSub: constructed valkey client via positional host/port")
                            return inst
                        except Exception:
                            pass
                        try:
                            url = os.getenv("VALKEY_URL")
                            if url:
                                inst = cls(url)
                                logger.debug("PubSub: constructed valkey client via URL")
                                return inst
                        except Exception:
                            pass
                        # default no-arg last
                        try:
                            inst = cls()
                            logger.debug("PubSub: constructed valkey client via default no-arg")
                            return inst
                        except Exception:
                            pass
                        return None

                    client = _try_ctor(client_cls)
                    if client is not None:
                        break
            # fallback: maybe there's a client submodule
            if client is None:
                try:
                    client_mod = importlib.import_module("valkey.client")
                    for attr in ("Valkey", "Client", "ValkeyClient"):
                        if hasattr(client_mod, attr):
                            client_cls = getattr(client_mod, attr)
                            def _try_ctor2(cls):
                                try:
                                    host = os.getenv("VALKEY_HOST", "valkey")
                                    port = int(os.getenv("VALKEY_PORT", "6379"))
                                    inst = cls(host=host, port=port)
                                    logger.debug("PubSub: constructed valkey client via host/port kwargs (fallback)")
                                    return inst
                                except Exception:
                                    pass
                                try:
                                    host = os.getenv("VALKEY_HOST", "valkey")
                                    port = int(os.getenv("VALKEY_PORT", "6379"))
                                    inst = cls(host, port)
                                    logger.debug("PubSub: constructed valkey client via positional host/port (fallback)")
                                    return inst
                                except Exception:
                                    pass
                                try:
                                    url = os.getenv("VALKEY_URL")
                                    if url:
                                        inst = cls(url)
                                        logger.debug("PubSub: constructed valkey client via URL (fallback)")
                                        return inst
                                except Exception:
                                    pass
                                try:
                                    inst = cls()
                                    logger.debug("PubSub: constructed valkey client via default no-arg (fallback)")
                                    return inst
                                except Exception:
                                    pass
                                return None

                            client = _try_ctor2(client_cls)
                            if client is not None:
                                break
                except Exception:
                    client = None

            if client is not None:
                self._valkey_client = client
                self._valkey_usable = True
                # surface client type for diagnostics
                try:
                    client_repr = f"{type(client).__module__}.{type(client).__name__}"
                except Exception:
                    client_repr = repr(client)
                logger.info("PubSub: valkey client initialized (%s); using valkey for pub/sub", client_repr)
                # start background subscription task
                # start background subscription task (subscribe loop will mark _valkey_subscribed)
                loop = asyncio.get_event_loop()
                self._valkey_task = loop.create_task(self._valkey_subscribe_loop())
            else:
                self._valkey_usable = False
                logger.warning("PubSub: valkey package found but no usable client; falling back to local pubsub")
        except ModuleNotFoundError:
            self._valkey_usable = False
            logger.info("PubSub: valkey not installed; using local in-process pubsub")

    async def _valkey_subscribe_loop(self):
        """Best-effort subscription loop for valkey client. Calls registered handlers when messages arrive.
        The implementation tries to consume messages from common subscribe APIs; if none are found it exits.
        """
        client = self._valkey_client
        if client is None:
            return

        # try a few common subscribe APIs
        if hasattr(client, "subscribe"):
            try:
                async for msg in client.subscribe(self.channel):
                    text = msg if isinstance(msg, str) else getattr(msg, "data", str(msg))
                    await self._call_handlers(text)
                return
            except TypeError:
                # subscribe may be sync iterator
                try:
                    for msg in client.subscribe(self.channel):
                        text = msg if isinstance(msg, str) else getattr(msg, "data", str(msg))
                        await self._call_handlers(text)
                    return
                except Exception:
                    logger.exception("PubSub: valkey subscribe iterate failed")
                    # disable valkey usage to avoid repeated noisy errors
                    self._valkey_usable = False
            except Exception:
                logger.exception("PubSub: valkey async subscribe failed")
                self._valkey_usable = False
            else:
                # if we reached this point and subscribe yielded, mark subscribed
                self._valkey_subscribed = True

        # try a blocking pubsub() API (redis-like clients expose client.pubsub())
        if hasattr(client, "pubsub"):
            try:
                pub = client.pubsub()
                loop = asyncio.get_event_loop()

                def _pubsub_thread():
                    try:
                        for msg in pub.listen():
                            try:
                                # redis-like messages have 'data' or are raw
                                text = msg if isinstance(msg, str) else getattr(msg, "data", str(msg))
                                # schedule handler invocation on the asyncio loop
                                asyncio.run_coroutine_threadsafe(self._call_handlers(text), loop)
                            except Exception:
                                logger.exception("PubSub: exception while handling pubsub thread message")
                    except Exception:
                        logger.exception("PubSub: pubsub.listen thread exited with exception")

                t = threading.Thread(target=_pubsub_thread, daemon=True)
                t.start()
                logger.info("PubSub: valkey pubsub() listener thread started")
                self._valkey_subscribed = True
                return
            except Exception:
                logger.exception("PubSub: valkey pubsub() setup failed")
                self._valkey_usable = False

        # try a callback-style API
        if hasattr(client, "on_message"):
            try:
                def _cb(msg):
                    text = msg if isinstance(msg, str) else getattr(msg, "data", str(msg))
                    asyncio.create_task(self._call_handlers(text))

                client.on_message(self.channel, _cb)
                self._valkey_subscribed = True
                return
            except Exception:
                logger.exception("PubSub: valkey on_message registration failed")
                self._valkey_usable = False

        logger.warning("PubSub: valkey client present but no supported subscribe API found")

    async def _call_handlers(self, message: str):
        handlers = list(self._handlers)
        logger.info("PubSub: calling %d local handlers", len(handlers))
        for h in handlers:
            try:
                if asyncio.iscoroutinefunction(h):
                    await h(message)
                else:
                    # run sync handlers in default loop executor
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, h, message)
            except Exception:
                logger.exception("PubSub: handler raised exception")

    async def publish(self, message: str):
        # publish via valkey if available and usable
        if self._valkey_client is not None and self._valkey_usable:
            logger.info("PubSub: attempting publish via valkey client")
            try:
                if hasattr(self._valkey_client, "publish"):
                    maybe = self._valkey_client.publish(self.channel, message)
                    if asyncio.iscoroutine(maybe):
                        await maybe
                    # after publishing via valkey, also call local handlers immediately
                    # so in-process websocket clients receive the message without waiting
                    # for the valkey echo. The forwarder will ignore valkey-echoed
                    # messages originating from this pid to avoid duplicates.
                    logger.info("PubSub: valkey publish succeeded; calling local handlers")
                    # if the published message is an envelope with an inner payload,
                    # unwrap it before calling local handlers so the local forwarder
                    # (which ignores messages originating from this pid) will still
                    # forward the inner payload to connected websockets.
                    try:
                        parsed_msg = None
                        if isinstance(message, str):
                            parsed_msg = __import__('json').loads(message)
                        if isinstance(parsed_msg, dict) and parsed_msg.get('__origin_pid') is not None and 'payload' in parsed_msg:
                            inner = parsed_msg.get('payload')
                            await self._call_handlers(__import__('json').dumps(inner))
                        else:
                            await self._call_handlers(message)
                    except Exception:
                        # fallback to calling handlers with raw message
                        await self._call_handlers(message)
                    return
                # try common alternative
                if hasattr(self._valkey_client, "put"):
                    maybe = self._valkey_client.put(self.channel, message)
                    if asyncio.iscoroutine(maybe):
                        await maybe
                    logger.info("PubSub: valkey put succeeded; calling local handlers")
                    try:
                        parsed_msg = None
                        if isinstance(message, str):
                            parsed_msg = __import__('json').loads(message)
                        if isinstance(parsed_msg, dict) and parsed_msg.get('__origin_pid') is not None and 'payload' in parsed_msg:
                            inner = parsed_msg.get('payload')
                            await self._call_handlers(__import__('json').dumps(inner))
                        else:
                            await self._call_handlers(message)
                    except Exception:
                        await self._call_handlers(message)
                    return
            except Exception:
                # log once and disable valkey usage to avoid repeated noisy tracebacks
                logger.exception("PubSub: valkey publish failed; disabling valkey and falling back to local handlers")
                self._valkey_usable = False

        # fallback: call local handlers directly
        # Attempt to unwrap envelope messages so local forwarder still
        # receives the inner payload (important when valkey isn't available).
        logger.info("PubSub: publishing via local handlers (count=%d)", len(self._handlers))
        try:
            parsed = None
            if isinstance(message, str):
                parsed = json.loads(message)
            if isinstance(parsed, dict) and parsed.get('__origin_pid') is not None and 'payload' in parsed:
                inner = parsed.get('payload')
                await self._call_handlers(json.dumps(inner))
            else:
                await self._call_handlers(message)
        except Exception:
            # fallback to raw message if parsing/unwrapping fails
            await self._call_handlers(message)

    def register_handler(self, handler: Callable[[str], None]):
        """Register a handler called with message text when a message is published.
        Handler may be sync or async (coroutine function).
        """
        self._handlers.append(handler)

    async def close(self):
        if self._valkey_task:
            self._valkey_task.cancel()
            try:
                await self._valkey_task
            except Exception:
                pass
