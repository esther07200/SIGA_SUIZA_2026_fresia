"""Seed idempotente del catálogo oficial de 11 programas de estudio.

Fuente de verdad: docs/10-LOGICA-NEGOCIO.md §1.2 (ids 1-11, ADR-014: sin
fallback a id 99). Se ejecuta al arrancar el módulo si la tabla está vacía,
para que una limpieza de BD no rompa la ingesta de admisión
(POST /mod-gestion-academica/admision/ingesta devuelve 503 si el catálogo
está vacío).
"""
from sqlalchemy import func, select

from models import ProgramaEstudio

# (id, nombre, codigo, creditos_totales, descripcion)
CATALOGO = [
    (1, "ENFERMERÍA TÉCNICA", "ENF", 30, None),
    (2, "CONTABILIDAD", "CON", 29, None),
    (3, "MECATRÓNICA AUTOMOTRIZ", "MET", 0, "Créditos del plan de estudios PENDIENTE de validar"),
    (4, "GESTIÓN ADMINISTRATIVA", "GAS-ADM", 0, "Créditos del plan de estudios PENDIENTE de validar"),
    (5, "PRODUCCIÓN AGROPECUARIA", "PRO-AG", 0, "Créditos del plan de estudios PENDIENTE de validar"),
    (6, "CONSTRUCCIÓN CIVIL", "CON-CIV", 0, "Créditos del plan de estudios PENDIENTE de validar"),
    (7, "DESARROLLO DE SISTEMAS DE INFORMACIÓN", "DSI", 28, None),
    (8, "ELECTRICIDAD INDUSTRIAL", "ELT", 27, None),
    (9, "ADMINISTRACIÓN DE OPERACIONES TURÍSTICAS", "AOT", 0, "Créditos del plan de estudios PENDIENTE de validar"),
    (10, "MANEJO FORESTAL", "MAN-FOR", 0, "Créditos del plan de estudios PENDIENTE de validar"),
    (11, "ASISTENCIA ADMINISTRATIVA", "ASI-ADM", 0, "Créditos del plan de estudios PENDIENTE de validar"),
]


async def seed_catalogo_si_vacio(session) -> int:
    """Inserta el catálogo solo si la tabla está vacía. Devuelve filas insertadas."""
    total = (await session.execute(select(func.count(ProgramaEstudio.id)))).scalar()
    if total:
        return 0

    for pid, nombre, codigo, creditos, descripcion in CATALOGO:
        session.add(ProgramaEstudio(
            id=pid,
            nombre=nombre,
            codigo=codigo,
            descripcion=descripcion,
            duracion_periodos=6,
            creditos_totales=creditos,
            modalidad="presencial",
            estado="activo",
        ))
    await session.commit()
    return len(CATALOGO)
