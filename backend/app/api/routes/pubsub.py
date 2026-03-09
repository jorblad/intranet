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
        # whether we own the loop (we created it and started it in a background thread)
        self._loop_owner: bool = False

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
                # remember the loop we used to start the valkey subscribe task
                self._loop = None
                # Try to use the current running loop. If none exists (common during
                # module import / test collection), create a dedicated loop running
                # in a background thread and schedule the subscribe coroutine there.
                try:
                    cur_loop = asyncio.get_event_loop()
                    self._loop = cur_loop
                    # schedule task on the current loop
                    self._valkey_task = cur_loop.create_task(self._valkey_subscribe_loop())
                except RuntimeError:
                    # no running loop in this thread; create one and run it in a daemon thread
                    self._loop = asyncio.new_event_loop()
                    def _start_loop(loop):
                        try:
                            asyncio.set_event_loop(loop)
                            loop.run_forever()
                        except Exception:
                            logger.exception("PubSub: background loop exited unexpectedly")

                    t = threading.Thread(target=_start_loop, args=(self._loop,), daemon=True)
                    t.start()
                    self._loop_owner = True
                    # schedule coroutine onto the background loop in a thread-safe way
                    self._valkey_task = asyncio.run_coroutine_threadsafe(self._valkey_subscribe_loop(), self._loop)
                # surface client type for diagnostics
                try:
                    client_repr = f"{type(client).__module__}.{type(client).__name__}"
                except Exception:
                    client_repr = repr(client)
                logger.info("PubSub: valkey client initialized (%s); using valkey for pub/sub", client_repr)
                # if we scheduled a task above, _valkey_task is set; otherwise it's left None
            else:
                self._valkey_usable = False
                logger.warning("PubSub: valkey package found but no usable client; falling back to local pubsub")
        except ModuleNotFoundError:
            self._valkey_usable = False
            logger.info("PubSub: valkey not installed; using local in-process pubsub")

    def schedule_publish(self, message: str):
        """Schedule a publish from non-async/synchronous code (thread-safe).

        Uses the event loop that was active when PubSub initialized (if available)
        via `asyncio.run_coroutine_threadsafe`. Falls back to creating a task
        on the currently running loop if possible.
        """
        # Prefer run_coroutine_threadsafe when we have a known loop
        try:
            loop = getattr(self, "_loop", None)
            if loop is not None:
                try:
                    asyncio.run_coroutine_threadsafe(self.publish(message), loop)
                    return True
                except Exception:
                    pass
            # fallback: try scheduling on current running loop
            try:
                cur = asyncio.get_running_loop()
                cur.create_task(self.publish(message))
                return True
            except Exception:
                pass
        except Exception:
            pass
        # Last resort: run synchronously (blocking) to ensure publish happens
        try:
            asyncio.run(self.publish(message))
            return True
        except Exception:
            return False

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
                    # If the published message is an envelope with an inner payload,
                    # call local handlers with the inner payload (not the envelope)
                    # so in-process websocket clients receive the useful payload
                    # immediately. Remote processes will still receive the full
                    # envelope from valkey and will forward the payload as usual.
                    try:
                        parsed = None
                        try:
                            parsed = json.loads(message)
                        except Exception:
                            parsed = None
                        if isinstance(parsed, dict) and parsed.get('__origin_pid') is not None and 'payload' in parsed:
                            payload_text = json.dumps(parsed.get('payload'))
                            await self._call_handlers(payload_text)
                        else:
                            await self._call_handlers(message)
                    except Exception:
                        # best-effort: fall back to delivering the raw message
                        await self._call_handlers(message)
                    return
                # try common alternative
                if hasattr(self._valkey_client, "put"):
                    maybe = self._valkey_client.put(self.channel, message)
                    if asyncio.iscoroutine(maybe):
                        await maybe
                    logger.info("PubSub: valkey put succeeded; calling local handlers")
                    try:
                        parsed = None
                        try:
                            parsed = json.loads(message)
                        except Exception:
                            parsed = None
                        if isinstance(parsed, dict) and parsed.get('__origin_pid') is not None and 'payload' in parsed:
                            payload_text = json.dumps(parsed.get('payload'))
                            await self._call_handlers(payload_text)
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
            # When valkey isn't available we still want local websocket
            # clients to receive the actionable payload. If the message is
            # an envelope, deliver the inner payload locally; otherwise
            # deliver the raw message.
            parsed = None
            try:
                parsed = json.loads(message)
            except Exception:
                parsed = None
            if isinstance(parsed, dict) and parsed.get('__origin_pid') is not None and 'payload' in parsed:
                await self._call_handlers(json.dumps(parsed.get('payload')))
            else:
                await self._call_handlers(message)
        except Exception:
            # fallback to raw message if anything goes wrong
            await self._call_handlers(message)

    def register_handler(self, handler: Callable[[str], None]):
        """Register a handler called with message text when a message is published.
        Handler may be sync or async (coroutine function).
        """
        self._handlers.append(handler)

    async def close(self):
        if self._valkey_task:
            try:
                # If the task is an asyncio.Task scheduled on the current loop, cancel and await it.
                if isinstance(self._valkey_task, asyncio.Task):
                    self._valkey_task.cancel()
                    try:
                        await self._valkey_task
                    except Exception:
                        pass
                else:
                    # Assume a concurrent.futures.Future returned by run_coroutine_threadsafe.
                    try:
                        self._valkey_task.cancel()
                    except Exception:
                        pass
            except Exception:
                logger.exception("PubSub: error while closing valkey task")
        # If we created a dedicated loop in a background thread, stop it.
        if getattr(self, "_loop_owner", False) and getattr(self, "_loop", None):
            try:
                loop = self._loop
                if loop.is_running():
                    loop.call_soon_threadsafe(loop.stop)
            except Exception:
                logger.exception("PubSub: failed to stop background loop")
