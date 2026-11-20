import asyncio
import json
import logging
import os
import time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import AsyncSessionLocal, OutboxEvent

import sys

# Consolas Windows en cp1252 no pueden codificar emojis: nunca debe romper el worker
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

try:
    from nats.aio.client import Client as NATS
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False
    print("⚠️ NATS no está instalado. El Outbox Worker simulará la publicación.")

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_ENABLED = os.getenv("ENABLE_NATS", "true").lower() in ("1", "true", "yes", "on")
NATS_CONNECT_TIMEOUT = float(os.getenv("NATS_CONNECT_TIMEOUT", "3"))
NATS_RETRY_SECONDS = float(os.getenv("NATS_RETRY_SECONDS", "300"))

_nats_unavailable_warned = False


async def connect_nats():
    """Intento único y acotado a NATS: sin tracebacks ni reintentos agresivos."""
    global _nats_unavailable_warned
    if not NATS_AVAILABLE or not NATS_ENABLED:
        return None

    # nats-py loggea tracebacks en ERROR durante fallos de conexión:
    # se silencia solo durante el intento.
    nats_logger = logging.getLogger("nats")
    previous_level = nats_logger.level
    nats_logger.setLevel(logging.CRITICAL)
    try:
        nc = NATS()
        await asyncio.wait_for(
            nc.connect(
                NATS_URL,
                connect_timeout=NATS_CONNECT_TIMEOUT,
                max_reconnect_attempts=1,
                reconnect_time_wait=1,
            ),
            timeout=NATS_CONNECT_TIMEOUT + 1,
        )
        _nats_unavailable_warned = False
        print(f"✅ Outbox Worker conectado a NATS: {NATS_URL}")
        return nc
    except Exception as e:
        if not _nats_unavailable_warned:
            print(f"⚠️ NATS no disponible ({NATS_URL}): {type(e).__name__}. Outbox en modo simulado.")
            _nats_unavailable_warned = True
        return None
    finally:
        nats_logger.setLevel(previous_level)


async def outbox_worker():
    nc = await connect_nats()
    next_retry = time.monotonic() + NATS_RETRY_SECONDS

    while True:
        if nc is None or not nc.is_connected:
            if time.monotonic() >= next_retry:
                nc = await connect_nats()
                next_retry = time.monotonic() + NATS_RETRY_SECONDS

        try:
            async with AsyncSessionLocal() as db:
                # Buscar eventos no publicados
                result = await db.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.published == False)
                    .order_by(OutboxEvent.created_at.asc())
                    .limit(50)
                )
                events = result.scalars().all()

                for event in events:
                    if nc is not None and nc.is_connected:
                        try:
                            payload_bytes = json.dumps(event.payload).encode()
                            await nc.publish(event.event_type, payload_bytes)
                            event.published = True
                            await db.commit()
                        except Exception as e:
                            print(f"Error publicando evento {event.id}: {e}")
                    else:
                        print(f"🔄 [Simulado] Publicando evento {event.event_type}: {event.payload}")
                        event.published = True
                        await db.commit()
        except Exception as e:
            print(f"Error en Outbox Worker: {e}")

        await asyncio.sleep(10) # Polling interval
