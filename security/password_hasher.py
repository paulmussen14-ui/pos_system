"""
Hashing seguro de contraseñas.

Usa Argon2id (librería `argon2-cffi`) como método principal.
La contraseña NUNCA se guarda ni se compara en texto plano.
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

_ph = PasswordHasher(
    time_cost=3,        # iteraciones
    memory_cost=64 * 1024,  # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Devuelve el hash Argon2id de una contraseña en texto plano."""
    if not password:
        raise ValueError("La contraseña no puede estar vacía")
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verifica una contraseña contra su hash. Nunca lanza excepción hacia afuera."""
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False
    except Exception:
        return False
