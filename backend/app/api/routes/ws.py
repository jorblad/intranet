from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import os
import logging
from typing import Set, Optional
import asyncio
import json
import time

from app.core.security import decode_access_token
from .pubsub import PubSub

router = APIRouter()

# module-level logger for consistent logging across handlers
logger = logging.getLogger("uvicorn.error")

# Keep track of connected websockets in-memory for simple broadcasting.
# We use a PubSub helper that prefers valkey (if installed) for multi-process
# broadcast, and falls back to in-process handlers when valkey is not available.
connections: Set[WebSocket] = set()

# channel name used for cross-process pubsub
_PUBSUB_CHANNEL = "intranet-ws"
_pubsub = PubSub(channel=_PUBSUB_CHANNEL)

# sync telemetry
_last_transform_ts: Optional[float] = None
_last_heartbeat_ts: Optional[float] = None
_heartbeat_task: Optional[asyncio.Task] = None


async def _start_heartbeat(loop_interval: int = 10):
    global _heartbeat_task
    if _heartbeat_task is not None and not _heartbeat_task.done():
        return

    async def _hb_loop():
        global _last_heartbeat_ts
        try:
            while True:
                _last_heartbeat_ts = time.time()
                payload = json.dumps({"type": "heartbeat", "ts": _last_heartbeat_ts, "connected_clients": len(connections)})
                try:
                    await _pubsub.publish(payload)
                except Exception:
                    # swallow so heartbeat loop continues
                    pass
                await asyncio.sleep(loop_interval)
        except asyncio.CancelledError:
            return

    _heartbeat_task = asyncio.create_task(_hb_loop())


@router.get("/sync/status")
async def sync_status():
    return {
        "last_transform_ts": _last_transform_ts,
        "last_heartbeat_ts": _last_heartbeat_ts,
        "connected_clients": len(connections),
    }


# register a handler that forwards pubsub messages to all locally connected sockets
async def _forward_to_local_connections(message: str):
    dead = []
    conns = list(connections)
    try:
        logger.info("_forward_to_local_connections: forwarding message to %d connected sockets", len(conns))
    except Exception:
        # ensure logging doesn't break forwarding
        pass
    for conn in conns:
        try:
            # try to unwrap envelope if present
            send_text = message
            try:
                parsed = json.loads(message)
                if isinstance(parsed, dict) and parsed.get('__origin_pid') is not None and 'payload' in parsed:
                    # ignore messages originating from this process to avoid duplicate
                    # delivery when we also call local handlers directly in publish().
                    try:
                        origin = int(parsed.get('__origin_pid'))
                    except Exception:
                        origin = None
                    if origin == os.getpid():
                        continue
                    # re-serialize the payload for sending to websocket clients
                    send_text = json.dumps(parsed.get('payload'))
            except Exception:
                # not JSON or no envelope — send original
                pass
            try:
                preview = send_text if isinstance(send_text, str) else str(send_text)
                if len(preview) > 200:
                    preview = preview[:200] + '...'
                logger.info("_forward_to_local_connections: sending preview to conn: %s", preview)
            except Exception:
                pass
            await conn.send_text(send_text)
        except Exception as exc:
            try:
                logger.exception("_forward_to_local_connections: send_text failed for a connection")
            except Exception:
                pass
            dead.append(conn)
    if dead:
        try:
            logger.info("_forward_to_local_connections: removing %d dead connections", len(dead))
        except Exception:
            pass
    for d in dead:
        connections.discard(d)


# attach the forwarder to the pubsub so messages published through valkey
# (or the local fallback) are forwarded to this process' connected clients
_pubsub.register_handler(_forward_to_local_connections)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    logger = logging.getLogger("uvicorn.error")
    decoded = None
    try:
        if token:
            decoded = decode_access_token(token)
        logger.info("WebSocket handshake token present: %s", "yes" if token else "no")
        # log a short preview (avoid printing the full token in logs)
        if token:
            preview = token if len(token) < 80 else token[:76] + "..."
            logger.debug("WebSocket token preview: %s", preview)
        logger.info("decode_access_token -> %s", str(decoded))
    except Exception:
        logger.exception("Error while decoding websocket token")

    if not decoded:
        logger.info("WebSocket connection rejected: invalid or missing token")
        await websocket.close(code=1008)
        return

    await websocket.accept()
    # send server/process info to client so we can correlate which backend process
    # the client is connected to (useful when running with reload/workers)
    try:
        await websocket.send_text(json.dumps({"type": "server_info", "pid": os.getpid()}))
    except Exception:
        pass
    connections.add(websocket)
    # ensure heartbeat task is running (best-effort)
    try:
        await _start_heartbeat()
    except Exception:
        pass
    try:
        while True:
            data = await websocket.receive_text()
            try:
                logger.info("WebSocket received message (truncated): %s", (data[:200] + '...') if len(data) > 200 else data)
            except Exception:
                pass

            # publish incoming data via pubsub; this will either relay through
            # valkey across processes or call the local handlers which forward
            # directly to connected websockets in this process.
            logger.debug("Publishing received websocket message to PubSub channel=%s", _PUBSUB_CHANNEL)

            # update last transform timestamp for observability
            try:
                parsed = json.loads(data)
                if isinstance(parsed, dict) and parsed.get('type') == 'transform':
                    _last_transform_ts = time.time()
            except Exception:
                pass

            try:
                # wrap the original message in an envelope so receivers can ignore
                # messages originating from the same process (prevents duplicate delivery)
                try:
                    parsed_for_publish = json.loads(data)
                except Exception:
                    parsed_for_publish = data
                envelope = json.dumps({"__origin_pid": os.getpid(), "payload": parsed_for_publish})
                await _pubsub.publish(envelope)
                logger.info("_pubsub.publish returned for incoming message (enveloped)")
            except Exception:
                logger.exception("_pubsub.publish raised an exception for incoming websocket message")
                # fallback: if publish fails for any reason, still attempt local broadcast
                dead = []
                for conn in list(connections):
                    if conn is websocket:
                        continue
                    try:
                        await conn.send_text(data)
                    except Exception:
                        dead.append(conn)
                for d in dead:
                    connections.discard(d)
                continue

            # publish an ack for monitoring/debugging
            try:
                ack = {"type": "ack", "ts": time.time()}
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict) and parsed.get('type') == 'transform':
                        transform = parsed.get('transform') or {}
                        # try to include transform entry id if provided
                        if isinstance(transform, dict):
                            entry = transform.get('entry') or {}
                            if isinstance(entry, dict) and entry.get('id'):
                                ack['transformId'] = entry.get('id')
                except Exception:
                    pass
                # wrap ack as well so subscribers can correlate origin
                ack_env = json.dumps({"__origin_pid": os.getpid(), "payload": ack})
                await _pubsub.publish(ack_env)
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        connections.discard(websocket)


@router.get("/diagnostics")
async def diagnostics():
    """Return small diagnostics object useful for debugging pubsub/valkey state."""
    client = getattr(_pubsub, "_valkey_client", None)
    try:
        client_repr = f"{type(client).__module__}.{type(client).__name__}" if client is not None else None
    except Exception:
        client_repr = repr(client)

    return {
        "valkey_env": {
            "VALKEY_HOST": os.getenv("VALKEY_HOST"),
            "VALKEY_PORT": os.getenv("VALKEY_PORT"),
            "VALKEY_URL": os.getenv("VALKEY_URL"),
        },
        "pubsub": {
            "valkey_client_present": client is not None,
            "valkey_client_repr": client_repr,
            "valkey_usable": getattr(_pubsub, "_valkey_usable", False),
            "valkey_subscribed": getattr(_pubsub, "_valkey_subscribed", False),
            "local_handler_count": len(getattr(_pubsub, "_handlers", [])),
        },
        "websockets": {"connected_clients": len(connections)},
        "process": {"pid": os.getpid()},
    }
