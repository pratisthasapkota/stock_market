"""Small pub/sub bridge.

Workers (celery) publish JSON events to a redis channel. The API process runs a
listener that fans those out to every connected dashboard over websockets. When
redis isn't around (plain local run, INLINE_JOBS=true) publish() just returns
and the API broadcasts inline instead.
"""
import asyncio
import json
import logging

from .config import settings

log = logging.getLogger("events")

CHANNEL = "stock:updates"


class ConnectionManager:
    def __init__(self) -> None:
        self._sockets: set = set()
        self._lock = asyncio.Lock()
        # set by the API on startup so inline jobs (no redis) can still push
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws):
        await ws.accept()
        async with self._lock:
            self._sockets.add(ws)

    async def disconnect(self, ws):
        async with self._lock:
            self._sockets.discard(ws)

    async def broadcast(self, message: dict):
        text = json.dumps(message, default=str)
        dead = []
        for ws in list(self._sockets):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    @property
    def count(self) -> int:
        return len(self._sockets)


manager = ConnectionManager()


async def _listener(manager_ref: ConnectionManager):
    import redis.asyncio as aioredis

    while True:
        try:
            client = aioredis.from_url(settings.redis_url)
            pubsub = client.pubsub()
            await pubsub.subscribe(CHANNEL)
            log.info("subscribed to %s", CHANNEL)
            async for raw in pubsub.listen():
                if raw.get("type") != "message":
                    continue
                try:
                    await manager_ref.broadcast(json.loads(raw["data"]))
                except Exception:
                    log.warning("bad event payload dropped")
        except Exception as exc:
            log.warning("redis listener down (%s), retrying in 3s", exc)
            await asyncio.sleep(3)


def start_listener(manager_ref: ConnectionManager):
    return asyncio.create_task(_listener(manager_ref))


def publish(event: dict) -> None:
    """Best-effort. Called from celery workers and from the api inline path."""
    try:
        import redis

        client = redis.from_url(settings.redis_url)
        client.publish(CHANNEL, json.dumps(event, default=str))
    except Exception as exc:
        # no redis (local inline mode): hand the event to the in-process
        # manager so dashboards still update live
        log.debug("redis publish failed (%s), trying in-process broadcast", exc)
        if manager.loop and not manager.loop.is_closed():
            asyncio.run_coroutine_threadsafe(manager.broadcast(event), manager.loop)
