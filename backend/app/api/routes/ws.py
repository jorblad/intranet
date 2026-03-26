from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import os
import logging
from typing import Dict, Optional
import asyncio
import json
import time

from app.core.security import decode_access_token, decode_access_token_exp
from .pubsub import PubSub
from app.db.session import SessionLocal
from app.crud import create_entry as crud_create_entry, update_entry as crud_update_entry, delete_entry as crud_delete_entry, get_entry as crud_get_entry
router = APIRouter()
logger = logging.getLogger("uvicorn.error")

_PUBSUB_CHANNEL = os.getenv("PUBSUB_CHANNEL", "intranet-pubsub")
# Maps WebSocket → {"exp": float | None} where exp is the token's UTC Unix expiry.
connections: Dict[WebSocket, dict] = {}

_pubsub = PubSub(channel=_PUBSUB_CHANNEL)

# sync telemetry
_last_transform_ts: Optional[float] = None
_last_heartbeat_ts: Optional[float] = None
_heartbeat_task: Optional[asyncio.Task] = None

# In-memory recent transform cache to dedupe repeated client transforms
from collections import OrderedDict

_RECENT_TRANSFORMS: OrderedDict = OrderedDict()
_RECENT_TRANSFORMS_LOCK: asyncio.Lock = asyncio.Lock()
_RECENT_TRANSFORM_TTL: int = 300  # seconds to retain seen transform ids
_RECENT_TRANSFORMS_MAX: int = 2000  # keep at most this many ids


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

                # Check for connections whose access token has expired and notify them.
                try:
                    now = time.time()
                    expired_conns = [
                        ws for ws, meta in list(connections.items())
                        if isinstance(meta, dict)
                        and meta.get("exp") is not None
                        and now >= meta["exp"]
                    ]
                    for ws in expired_conns:
                        try:
                            await ws.send_text(json.dumps({"type": "session_expired"}))
                        except Exception:
                            # Ignore send errors; connection may already be broken.
                            pass
                        try:
                            await ws.close(code=1008)
                        except Exception:
                            # Ignore close errors; connection cleanup continues.
                            pass
                        connections.pop(ws, None)
                except Exception:
                    # Protect heartbeat loop from unexpected data in `connections`.
                    logger.exception("Error while scanning/evicting expired WebSocket connections")

                await asyncio.sleep(loop_interval)
        except asyncio.CancelledError:
            return

    _heartbeat_task = asyncio.create_task(_hb_loop())


async def _is_new_transform(transform_id: Optional[str]) -> bool:
    """Return True if the transform_id has not been seen recently.

    This keeps a small per-process in-memory cache of recent transform ids
    to avoid re-processing and re-publishing duplicate client transforms.
    """
    if not transform_id:
        return True
    try:
        async with _RECENT_TRANSFORMS_LOCK:
            now = time.time()
            # purge expired entries
            expired = [k for k, ts in _RECENT_TRANSFORMS.items() if now - ts > _RECENT_TRANSFORM_TTL]
            for k in expired:
                try:
                    _RECENT_TRANSFORMS.pop(k, None)
                except Exception:
                    pass
            if transform_id in _RECENT_TRANSFORMS:
                # refresh timestamp and move to the end
                _RECENT_TRANSFORMS[transform_id] = now
                try:
                    _RECENT_TRANSFORMS.move_to_end(transform_id)
                except Exception:
                    pass
                return False
            # record
            _RECENT_TRANSFORMS[transform_id] = now
            # enforce max size
            try:
                while len(_RECENT_TRANSFORMS) > _RECENT_TRANSFORMS_MAX:
                    _RECENT_TRANSFORMS.popitem(last=False)
            except Exception:
                pass
            return True
    except Exception:
        try:
            logger.exception("_is_new_transform failed")
        except Exception:
            pass
        # on error, be permissive and treat as new
        return True


async def _is_new_transform_global(transform_id: Optional[str]) -> bool:
    """Use valkey (if available) for cross-process dedupe, falling
    back to the in-process cache when valkey isn't usable or operations
    fail.
    """
    if not transform_id:
        return True

    # prefer valkey-aware dedupe when pubsub valkey client is available
    try:
        vk = getattr(_pubsub, "_valkey_client", None)
        if vk is None or not getattr(_pubsub, "_valkey_usable", False):
            return await _is_new_transform(transform_id)

        key = f"intranet:seen_transform:{transform_id}"
        now = str(time.time())

        # Try atomic set-if-not-exists patterns, trying several client APIs
        try:
            # common redis-like `set` with nx/ex
            if hasattr(vk, "set"):
                try:
                    maybe = vk.set(key, now, nx=True, ex=_RECENT_TRANSFORM_TTL)
                    if asyncio.iscoroutine(maybe):
                        maybe = await maybe
                    if maybe:
                        return True
                    return False
                except TypeError:
                    # signature doesn't accept nx/ex; fall through
                    pass
                except Exception:
                    # non-fatal; fall back to other methods
                    pass

            # try `put` variants that accept ttl-like arg
            if hasattr(vk, "put"):
                for attempt in (lambda: vk.put(key, now, _RECENT_TRANSFORM_TTL),
                                lambda: vk.put(key, now, ttl=_RECENT_TRANSFORM_TTL),
                                lambda: vk.put(key, now, ex=_RECENT_TRANSFORM_TTL)):
                    try:
                        maybe = attempt()
                        if asyncio.iscoroutine(maybe):
                            maybe = await maybe
                        # If put returned something truthy, treat as set-success
                        if maybe:
                            return True
                        # If put returned None/False, still attempt get check below
                        break
                    except TypeError:
                        continue
                    except Exception:
                        break

            # Fallback non-atomic: check get then set
            if hasattr(vk, "get"):
                g = vk.get(key)
                if asyncio.iscoroutine(g):
                    g = await g
                if g is not None:
                    return False
                # absent: try to put/set the key
                if hasattr(vk, "put"):
                    p = vk.put(key, now)
                    if asyncio.iscoroutine(p):
                        await p
                elif hasattr(vk, "set"):
                    s = vk.set(key, now)
                    if asyncio.iscoroutine(s):
                        await s
                # try to set expire if available
                if hasattr(vk, "expire"):
                    try:
                        e = vk.expire(key, _RECENT_TRANSFORM_TTL)
                        if asyncio.iscoroutine(e):
                            await e
                    except Exception:
                        pass
                return True
        except Exception:
            # if valkey ops fail, fall back to in-process dedupe
            try:
                logger.exception("valkey dedupe attempt failed; falling back to local dedupe")
            except Exception:
                pass
            return await _is_new_transform(transform_id)
    except Exception:
        return await _is_new_transform(transform_id)


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
        connections.pop(d, None)


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
    token_exp = None
    try:
        if token:
            token_exp = decode_access_token_exp(token)
    except Exception:
        pass
    connections[websocket] = {"exp": token_exp}
    # ensure heartbeat task is running (best-effort)
    try:
        await _start_heartbeat()
    except Exception:
        pass
    try:
        while True:
            data = await websocket.receive_text()
            try:
                truncated = (data[:200] + '...') if len(data) > 200 else data
                client_info = None
                try:
                    c = getattr(websocket, 'client', None)
                    if c and isinstance(c, (list, tuple)) and len(c) >= 2:
                        client_info = f"{c[0]}:{c[1]}"
                except Exception:
                    client_info = None
                try:
                    logger.info("WebSocket received message from %s (truncated): %s", client_info or 'unknown', truncated)
                except Exception:
                    logger.info("WebSocket received message (truncated): %s", truncated)
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
                # parse message for potential persistence work
                try:
                    parsed_for_publish = json.loads(data)
                except Exception:
                    parsed_for_publish = data

                async def _maybe_persist_transform(parsed_msg):
                    try:
                        if not isinstance(parsed_msg, dict):
                            return None
                        if parsed_msg.get('type') != 'transform':
                            return None
                        transform = parsed_msg.get('transform') or {}
                        # capture any client-provided transform id for diagnostics
                        try:
                            client_tid = transform.get('transformId') or transform.get('transform_id')
                        except Exception:
                            client_tid = None
                        op = transform.get('op')

                        # helper to normalize incoming id-array shapes
                        def _ids(arr):
                            if not arr:
                                return []
                            out = []
                            for a in arr:
                                if isinstance(a, dict):
                                    if 'value' in a:
                                        out.append(str(a.get('value')))
                                    elif 'id' in a:
                                        out.append(str(a.get('id')))
                                else:
                                    out.append(str(a))
                            return out

                        # persist create/update/delete transforms synchronously in a thread
                        def _persist():
                            session = SessionLocal()
                            try:
                                entry = transform.get('entry') or {}
                                schedule_id = transform.get('scheduleId') or transform.get('schedule_id')

                                # CREATE
                                if op == 'create':
                                    responsible_ids = _ids(entry.get('responsible_ids') or entry.get('responsible'))
                                    devotional_ids = _ids(entry.get('devotional_ids') or entry.get('devotional'))
                                    cant_come_ids = _ids(entry.get('cant_come_ids') or entry.get('cant_come'))
                                    server_entry = crud_create_entry(
                                        session,
                                        schedule_id,
                                        entry.get('date'),
                                        entry.get('start'),
                                        entry.get('end'),
                                        entry.get('name'),
                                        entry.get('description'),
                                        entry.get('notes'),
                                        bool(entry.get('public_event')),
                                        responsible_ids,
                                        devotional_ids,
                                        cant_come_ids,
                                    )
                                    return {
                                        'id': server_entry.id,
                                        'schedule_id': server_entry.schedule_id,
                                        'date': server_entry.date.isoformat() if server_entry.date else None,
                                        'start': server_entry.start.isoformat() if getattr(server_entry, 'start', None) else None,
                                        'end': server_entry.end.isoformat() if getattr(server_entry, 'end', None) else None,
                                        'name': server_entry.name,
                                        'description': server_entry.description,
                                        'notes': server_entry.notes,
                                        'public_event': server_entry.public_event,
                                        'responsible_ids': [u.id for u in server_entry.responsible_users],
                                        'devotional_ids': [u.id for u in server_entry.devotional_users],
                                        'cant_come_ids': [u.id for u in server_entry.cant_come_users],
                                    }

                                # UPDATE
                                if op == 'update':
                                    eid = entry.get('id')
                                    if not eid:
                                        return None
                                    server_entry_obj = crud_get_entry(session, eid)
                                    if not server_entry_obj:
                                        return None
                                    responsible_ids = _ids(entry.get('responsible_ids') or entry.get('responsible'))
                                    devotional_ids = _ids(entry.get('devotional_ids') or entry.get('devotional'))
                                    cant_come_ids = _ids(entry.get('cant_come_ids') or entry.get('cant_come'))
                                    server_entry = crud_update_entry(
                                        session,
                                        server_entry_obj,
                                        entry.get('date'),
                                        entry.get('start'),
                                        entry.get('end'),
                                        entry.get('name'),
                                        entry.get('description'),
                                        entry.get('notes'),
                                        bool(entry.get('public_event')) if entry.get('public_event') is not None else None,
                                        responsible_ids if responsible_ids is not None else None,
                                        devotional_ids if devotional_ids is not None else None,
                                        cant_come_ids if cant_come_ids is not None else None,
                                    )
                                    return {
                                        'id': server_entry.id,
                                        'schedule_id': server_entry.schedule_id,
                                        'date': server_entry.date.isoformat() if server_entry.date else None,
                                        'start': server_entry.start.isoformat() if getattr(server_entry, 'start', None) else None,
                                        'end': server_entry.end.isoformat() if getattr(server_entry, 'end', None) else None,
                                        'name': server_entry.name,
                                        'description': server_entry.description,
                                        'notes': server_entry.notes,
                                        'public_event': server_entry.public_event,
                                        'responsible_ids': [u.id for u in server_entry.responsible_users],
                                        'devotional_ids': [u.id for u in server_entry.devotional_users],
                                        'cant_come_ids': [u.id for u in server_entry.cant_come_users],
                                    }

                                # DELETE
                                if op == 'delete':
                                    eid = entry.get('id')
                                    if not eid:
                                        return None
                                    server_entry_obj = crud_get_entry(session, eid)
                                    if not server_entry_obj:
                                        return None
                                    crud_delete_entry(session, server_entry_obj)
                                    return {'id': eid}
                            finally:
                                session.close()

                        try:
                            server_entry = await asyncio.to_thread(_persist)
                            server_entry_id = getattr(server_entry, 'id', None) if hasattr(server_entry, 'id') else (server_entry and server_entry.get('id'))
                            logger.info('Persisted transform %s client_tid=%s -> server_entry id=%s', op, client_tid, server_entry_id)
                        except Exception:
                            logger.exception('Error while persisting transform')
                            return None

                        try:
                            # publish authoritative transform for CREATE/UPDATE/DELETE
                            if op == 'create':
                                created_transform = {'type': 'transform', 'transform': {'op': 'create', 'scheduleId': transform.get('scheduleId'), 'entry': server_entry}}
                                envelope_created = json.dumps({'__origin_pid': os.getpid(), 'payload': created_transform})
                                await _pubsub.publish(envelope_created)
                                logger.info('Published authoritative create transform for server_entry id=%s', getattr(server_entry, 'id', None))

                                local_id = (transform.get('entry') or {}).get('id')
                                if local_id:
                                    delete_transform = {'type': 'transform', 'transform': {'op': 'delete', 'scheduleId': transform.get('scheduleId'), 'entry': {'id': local_id}}}
                                    envelope_delete = json.dumps({'__origin_pid': os.getpid(), 'payload': delete_transform})
                                    await _pubsub.publish(envelope_delete)
                                    logger.info('Published delete transform for local placeholder id=%s', local_id)

                            elif op == 'update':
                                update_transform = {'type': 'transform', 'transform': {'op': 'update', 'scheduleId': transform.get('scheduleId'), 'entry': server_entry}}
                                envelope_update = json.dumps({'__origin_pid': os.getpid(), 'payload': update_transform})
                                await _pubsub.publish(envelope_update)
                                logger.info('Published authoritative update transform for server_entry id=%s', server_entry and server_entry.get('id'))

                            elif op == 'delete':
                                delete_transform = {'type': 'transform', 'transform': {'op': 'delete', 'scheduleId': transform.get('scheduleId'), 'entry': {'id': server_entry.get('id') if isinstance(server_entry, dict) else entry.get('id')}}}
                                envelope_delete = json.dumps({'__origin_pid': os.getpid(), 'payload': delete_transform})
                                await _pubsub.publish(envelope_delete)
                                logger.info('Published authoritative delete transform for server_entry id=%s', server_entry and server_entry.get('id'))
                        except Exception:
                            logger.exception('Failed to publish created/update/delete transforms')
                        return server_entry
                    except Exception:
                        logger.exception('_maybe_persist_transform failed')
                        return None

                # defensive dedupe: if this is a transform with a client-provided
                # transformId we've already seen recently, ack it but skip
                # persistence and authoritative publish so we don't republish
                # duplicates.
                try:
                    if isinstance(parsed_for_publish, dict) and parsed_for_publish.get('type') == 'transform':
                        _t = parsed_for_publish.get('transform') or {}
                        _client_tid = None
                        try:
                            _client_tid = _t.get('transformId') or _t.get('transform_id')
                        except Exception:
                            _client_tid = None
                        if _client_tid:
                            try:
                                is_new = await _is_new_transform_global(_client_tid)
                            except Exception:
                                is_new = True
                            if not is_new:
                                try:
                                    logger.info('Duplicate transform received; skipping persistence/publish for transformId=%s', _client_tid)
                                except Exception:
                                    pass
                                # send an ack so clients know the transform is accounted for
                                try:
                                    ack = {"type": "ack", "ts": time.time(), "transformId": _client_tid}
                                    entry = _t.get('entry') or {}
                                    entry_id = None
                                    if isinstance(entry, dict):
                                        entry_id = entry.get('id') or entry.get('entry_id')
                                    if entry_id and entry_id != _client_tid:
                                        ack['entryId'] = entry_id
                                    ack_env = json.dumps({"__origin_pid": os.getpid(), "payload": ack})
                                    await _pubsub.publish(ack_env)
                                except Exception:
                                    try:
                                        logger.exception('Failed to publish ack for duplicate transform')
                                    except Exception:
                                        pass
                                # skip further processing for this message
                                continue
                except Exception:
                    try:
                        logger.exception('Error while checking duplicate transforms')
                    except Exception:
                        pass

                # schedule persistence of create transforms in background so the
                # websocket loop doesn't block when many pending transforms arrive
                try:
                    asyncio.create_task(_maybe_persist_transform(parsed_for_publish))
                    logger.debug('Scheduled background persistence for incoming transform')
                except Exception:
                    logger.exception('Error scheduling pre-publish transform persistence')

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
                    connections.pop(d, None)
                continue

            # publish an ack for monitoring/debugging
            try:
                ack = {"type": "ack", "ts": time.time()}
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict) and parsed.get('type') == 'transform':
                        transform = parsed.get('transform') or {}
                        if isinstance(transform, dict):
                            # Prefer echoing a client-provided transformId when present
                            client_tid = transform.get('transformId') or transform.get('transform_id')
                            entry = transform.get('entry') or {}
                            entry_id = None
                            if isinstance(entry, dict):
                                entry_id = entry.get('id') or entry.get('entry_id')

                            if client_tid:
                                # echo back client transform id so clients can match acks precisely
                                ack['transformId'] = client_tid
                                # also include the authoritative entry id when available and different
                                if entry_id and entry_id != client_tid:
                                    ack['entryId'] = entry_id
                            elif entry_id:
                                # fall back to entry id for older clients
                                ack['transformId'] = entry_id
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
        connections.pop(websocket, None)


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
