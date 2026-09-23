"""
Generación de código de recuperación de cuenta.

El código se genera con `secrets` (criptográficamente seguro), se muestra
UNA sola vez al usuario en la creación de la cuenta, y solo su HASH
(mismo esquema Argon2id que la contraseña) se guarda en la base de datos.
"""

import secrets

from config import RECOVERY_CODE_LENGTH_BYTES
from security.password_hasher import hash_password, verify_password


def generar_codigo_recuperacion() -> str:
    """
    Genera un código legible tipo XXXX-XXXX-XXXX-XXXX a partir de bytes
    criptográficamente seguros.
    """
    raw = secrets.token_hex(RECOVERY_CODE_LENGTH_BYTES).upper()  # 16 caracteres hex
    grupos = [raw[i:i + 4] for i in range(0, len(raw), 4)]
    return "-".join(grupos)


def hash_codigo_recuperacion(codigo: str) -> str:
    """Genera el hash del código de recuperación (mismo algoritmo que password)."""
    codigo_normalizado = codigo.strip().upper()
    return hash_password(codigo_normalizado)


def verificar_codigo_recuperacion(codigo_ingresado: str, codigo_hash: str) -> bool:
    """Verifica un código de recuperación ingresado contra su hash almacenado."""
    codigo_normalizado = codigo_ingresado.strip().upper()
    return verify_password(codigo_normalizado, codigo_hash)
