import asyncio
import logging
import os
import json
import sys

# Consolas Windows en cp1252 no pueden codificar emojis: nunca debe romper el worker
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass
from nats.aio.client import Client as NATS
from database import AsyncSessionLocal
from models import AuditLog

NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_ENABLED = os.getenv("ENABLE_NATS", "true").lower() in ("1", "true", "yes", "on")
NATS_CONNECT_TIMEOUT = float(os.getenv("NATS_CONNECT_TIMEOUT", "3"))
NATS_RETRY_SECONDS = float(os.getenv("NATS_RETRY_SECONDS", "60"))

async def process_audit_event(msg):
    try:
        data = json.loads(msg.data.decode())
        print(f"[AUDITORIA] Recibido evento: {data.get('event_type')}")
        
        async with AsyncSessionLocal() as db:
            # Check if event already processed to achieve idempotency
            from sqlalchemy import select
            existing = await db.execute(select(AuditLog).where(AuditLog.event_id == data.get("event_id")))
            if existing.scalar_one_or_none():
                print(f"[AUDITORIA] Evento {data.get('event_id')} duplicado. Ignorando.")
                return

            audit_log = AuditLog(
                event_id=data.get("event_id"),
                event_type=data.get("event_type"),
                source=data.get("source"),
                payload=data.get("data", {}),
                user_id=data.get("metadata", {}).get("user_id"),
                request_id=data.get("metadata", {}).get("request_id")
            )
            db.add(audit_log)
            await db.commit()
            print(f"[AUDITORIA] Evento {data.get('event_id')} registrado correctamente.")

    except Exception as e:
        print(f"[AUDITORIA] Error procesando evento: {e}")

async def start_listener():
    if not NATS_ENABLED:
        print("[AUDITORIA] NATS deshabilitado (ENABLE_NATS=false). Listener inactivo.")
        return

    warned = False
    while True:
        nc = NATS()
        # nats-py loggea tracebacks en ERROR durante fallos de conexión:
        # se silencia solo durante el intento.
        nats_logger = logging.getLogger("nats")
        previous_level = nats_logger.level
        nats_logger.setLevel(logging.CRITICAL)
        connected = False
        try:
            await asyncio.wait_for(
                nc.connect(
                    NATS_URL,
                    connect_timeout=NATS_CONNECT_TIMEOUT,
                    max_reconnect_attempts=1,
                    reconnect_time_wait=1,
                ),
                timeout=NATS_CONNECT_TIMEOUT + 1,
            )
            connected = True
        except Exception as e:
            if not warned:
                print(
                    f"⚠️ [AUDITORIA] NATS no disponible ({NATS_URL}): {type(e).__name__}. "
                    f"Reintentando cada {int(NATS_RETRY_SECONDS)}s sin generar errores."
                )
                warned = True
        finally:
            nats_logger.setLevel(previous_level)

        if connected:
            warned = False
            print(f"[AUDITORIA] Conectado a NATS en {NATS_URL}")
            try:
                # Suscribirse a todos los eventos (*.*.*)
                await nc.subscribe("*.*.*", cb=process_audit_event, queue="auditoria_queue")

                # Mantener el listener vivo mientras la conexión esté activa
                while nc.is_connected:
                    await asyncio.sleep(5)
            except Exception as e:
                print(f"[AUDITORIA] Error en NATS listener: {e}")
            finally:
                try:
                    await nc.close()
                except Exception:
                    pass

        await asyncio.sleep(NATS_RETRY_SECONDS)

if __name__ == "__main__":
    asyncio.run(start_listener())
