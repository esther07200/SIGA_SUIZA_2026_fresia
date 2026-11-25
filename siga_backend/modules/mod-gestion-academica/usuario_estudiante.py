"""Alta de usuarios de acceso para estudiantes recién matriculados.

Regla institucional: al matricular por primera vez se crea el usuario con
rol ``estudiante``, correo ``{dni}@siga.edu`` y contraseña igual al DNI.

Se opera con SQL crudo (patrón de ``shared.identity``) porque las tablas de
identidad pertenecen al núcleo y no al Base de este módulo.
"""
import logging
from typing import Optional

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ROL_ESTUDIANTE = "estudiante"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def _obtener_o_crear_rol(db: AsyncSession, nombre: str) -> Optional[int]:
    rol_id = (await db.execute(
        text("SELECT id FROM core_roles WHERE name = :nombre"), {"nombre": nombre}
    )).scalar()
    if rol_id:
        return int(rol_id)

    rol_id = (await db.execute(
        text("""
            INSERT INTO core_roles (name, description)
            VALUES (:nombre, :descripcion)
            RETURNING id
        """),
        {"nombre": nombre, "descripcion": "Estudiante de la Institución"},
    )).scalar()
    return int(rol_id) if rol_id else None


async def asegurar_usuario_estudiante(db: AsyncSession, estudiante) -> Optional[int]:
    """Crea (si aún no existe) el usuario de acceso del estudiante.

    Devuelve el ``core_users.id`` resultante o ``None`` si no fue posible
    (p. ej. estudiante sin DNI). Nunca sobrescribe una contraseña existente.
    """
    dni = str(getattr(estudiante, "dni", "") or "").strip()
    if not dni:
        logger.warning(
            "Estudiante %s sin DNI: no se creó usuario de acceso.",
            getattr(estudiante, "id", "?"),
        )
        return None

    email = f"{dni}@siga.edu"

    try:
        usuario_id = (await db.execute(
            text("SELECT id FROM core_users WHERE lower(email) = lower(:email)"),
            {"email": email},
        )).scalar()
        if usuario_id:
            await db.commit()
            return int(usuario_id)

        nombres = str(getattr(estudiante, "nombres", "") or "").strip()
        apellidos = str(getattr(estudiante, "apellidos", "") or "").strip()
        full_name = f"{apellidos} {nombres}".strip() or f"Estudiante {dni}"

        nuevo_id = (await db.execute(
            text("""
                INSERT INTO core_users (email, full_name, hashed_password, is_active, is_superuser)
                VALUES (:email, :full_name, :hashed, TRUE, FALSE)
                ON CONFLICT (email) DO NOTHING
                RETURNING id
            """),
            {
                "email": email,
                "full_name": full_name,
                "hashed": _hash_password(dni),
            },
        )).scalar()

        if not nuevo_id:
            nuevo_id = (await db.execute(
                text("SELECT id FROM core_users WHERE lower(email) = lower(:email)"),
                {"email": email},
            )).scalar()
        if not nuevo_id:
            await db.rollback()
            return None

        rol_id = await _obtener_o_crear_rol(db, ROL_ESTUDIANTE)
        if rol_id:
            ya_asignado = (await db.execute(
                text("""
                    SELECT 1 FROM core_user_roles
                    WHERE user_id = :uid AND role_id = :rid
                    LIMIT 1
                """),
                {"uid": int(nuevo_id), "rid": rol_id},
            )).scalar()
            if not ya_asignado:
                await db.execute(
                    text("""
                        INSERT INTO core_user_roles (user_id, role_id)
                        VALUES (:uid, :rid)
                    """),
                    {"uid": int(nuevo_id), "rid": rol_id},
                )

        await db.commit()
        return int(nuevo_id)
    except Exception:
        logger.exception(
            "No se pudo crear el usuario de acceso para el estudiante %s (dni=%s).",
            getattr(estudiante, "id", "?"),
            dni,
        )
        await db.rollback()
        return None
