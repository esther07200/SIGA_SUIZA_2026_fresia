import asyncio
import json
import time
from typing import Callable, Dict, List, Optional
import logging
from nats.aio.client import Client as NATS
from nats.errors import TimeoutError, NoServersError

from ..config import settings
from .event_schemas import BaseEvent, EventFactory

logger = logging.getLogger(__name__)

class NATSEventBus:
    """Bus de eventos usando NATS para comunicación entre microservicios"""
    
    def __init__(self):
        self.nc = NATS()
        self.connected = False
        self.subscriptions: Dict[str, List[Callable]] = {}
        self._retry_after = 0.0
        self._warned = False

    async def connect(self) -> bool:
        """Conecta al servidor NATS.

        Un único intento acotado por ventana: si NATS no está disponible
        (por ejemplo en Railway) se deshabilita temporalmente sin generar
        tracebacks ni reintentos constantes.
        """
        if self.connected:
            return True
        if not settings.enable_nats:
            return False
        if time.monotonic() < self._retry_after:
            return False

        # La librería nats-py loggea tracebacks en ERROR durante los fallos
        # de conexión; se silencia solo durante el intento.
        nats_logger = logging.getLogger("nats")
        previous_level = nats_logger.level
        nats_logger.setLevel(logging.CRITICAL)
        try:
            client = NATS()
            await asyncio.wait_for(
                client.connect(
                    servers=[settings.nats_url],
                    connect_timeout=settings.nats_connect_timeout,
                    max_reconnect_attempts=1,
                    reconnect_time_wait=1
                ),
                timeout=settings.nats_connect_timeout + 1
            )
            self.nc = client
            self.connected = True
            self._warned = False
            logger.info(f"NATS Event Bus conectado a {settings.nats_url}")
            return True

        except Exception as e:
            self.connected = False
            self._retry_after = time.monotonic() + settings.nats_retry_seconds
            if not self._warned:
                logger.warning(
                    "⚠️  NATS no disponible (%s): %s. Event Bus en modo inactivo "
                    "(reintento en %ss). Define NATS_URL o ENABLE_NATS=false para omitirlo.",
                    settings.nats_url, type(e).__name__, settings.nats_retry_seconds
                )
                self._warned = True
            else:
                logger.debug(f" NATS sigue sin estar disponible: {type(e).__name__}")
            return False
        finally:
            nats_logger.setLevel(previous_level)

    async def publish(self, event: BaseEvent) -> bool:
        """Publica un evento en el bus"""
        if not self.connected and not await self.connect():
            logger.debug("⚠️  Event Bus no conectado - Evento no publicado")
            return False

        try:
            # Publicar en el subject correspondiente al tipo de evento
            subject = f"events.{event.event_type.value}"
            message = event.model_dump_json()

            await self.nc.publish(subject, message.encode())
            logger.debug(f"📨 Evento publicado: {event.event_type} -> {subject}")
            return True

        except Exception as e:
            logger.error(f"❌ Error publicando evento: {e}")
            return False

    async def publish_raw(self, subject: str, data: Dict) -> bool:
        """Publica datos crudos en un subject específico"""
        if not self.connected and not await self.connect():
            return False

        try:
            message = json.dumps(data).encode()
            await self.nc.publish(subject, message)
            return True
        except Exception as e:
            logger.error(f"❌ Error en publish_raw: {e}")
            return False

    async def subscribe(self, event_type: str, callback: Callable) -> bool:
        """Suscribe una función callback a un tipo de evento"""
        if not self.connected and not await self.connect():
            logger.debug("⚠️  Event Bus no conectado - No se puede suscribir")
            return False
            
        try:
            subject = f"events.{event_type}"
            
            # Registrar callback localmente
            if event_type not in self.subscriptions:
                self.subscriptions[event_type] = []
            self.subscriptions[event_type].append(callback)
            
            # Suscribirse en NATS
            await self.nc.subscribe(subject, cb=self._create_message_handler(event_type, callback))
            logger.debug(f"📥 Suscrito a eventos: {event_type}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error suscribiéndose a {event_type}: {e}")
            return False
    
    def _create_message_handler(self, event_type: str, callback: Callable):
        """Crea manejador de mensajes para NATS con reconstrucción de eventos"""
        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                # Intentar reconstruir el evento usando BaseEvent o clase específica si fuera necesario
                # Por ahora usamos BaseEvent ya que es la base de todos
                event = BaseEvent(**data)
                
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"❌ Error procesando mensaje en {event_type}: {e}")
        
        return message_handler
    
    async def request(self, subject: str, data: Dict, timeout: float = 5.0) -> Optional[Dict]:
        """Envía una solicitud y espera respuesta (patrón request-reply)"""
        if not self.connected:
            return None
            
        try:
            message = json.dumps(data).encode()
            response = await self.nc.request(subject, message, timeout=timeout)
            return json.loads(response.data.decode())
        except TimeoutError:
            logger.warning(f"⏰ Timeout en request: {subject}")
            return None
        except Exception as e:
            logger.error(f"❌ Error en request {subject}: {e}")
            return None
    
    async def close(self):
        """Cierra la conexión NATS"""
        if self.connected:
            await self.nc.close()
            self.connected = False
            logger.info("🔌 NATS Event Bus desconectado")

# Instancia global del Event Bus
event_bus = NATSEventBus()