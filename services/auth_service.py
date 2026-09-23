"""
Lógica de negocio de autenticación.

Reglas clave:
- Solo puede existir UNA cuenta (administrador/propietario).
- La contraseña nunca se guarda en texto plano (Argon2id).
- El código de recuperación se genera una vez, se muestra una vez,
  y se invalida tras su primer uso exitoso.
"""

from repositories.usuario_repository import UsuarioRepository
from security.password_hasher import hash_password, verify_password
from security.recovery_code import (
    generar_codigo_recuperacion,
    hash_codigo_recuperacion,
    verificar_codigo_recuperacion,
)


class AuthError(Exception):
    """Error de negocio en el flujo de autenticación (mensaje apto para mostrar al usuario)."""


class AuthService:

    def __init__(self):
        self.usuario_repo = UsuarioRepository()

    def requiere_configuracion_inicial(self) -> bool:
        """True si todavía no existe la cuenta de administrador (primera ejecución)."""
        return not self.usuario_repo.existe_usuario()

    def crear_cuenta_administrador(self, nombre: str, usuario: str, password: str, confirmar_password: str) -> str:
        """
        Crea la única cuenta de administrador permitida.
        Devuelve el código de recuperación EN TEXTO PLANO para mostrarlo una sola vez.
        """
        if self.usuario_repo.existe_usuario():
            raise AuthError("Ya existe una cuenta de administrador. No se permite crear otra.")

        nombre = nombre.strip()
        usuario = usuario.strip()

        if not nombre or not usuario:
            raise AuthError("El nombre y el usuario son obligatorios.")
        if len(password) < 8:
            raise AuthError("La contraseña debe tener al menos 8 caracteres.")
        if password != confirmar_password:
            raise AuthError("Las contraseñas no coinciden.")

        password_hash = hash_password(password)
        codigo_recuperacion = generar_codigo_recuperacion()
        codigo_hash = hash_codigo_recuperacion(codigo_recuperacion)

        self.usuario_repo.crear(nombre, usuario, password_hash, codigo_hash)
        return codigo_recuperacion

    def iniciar_sesion(self, usuario: str, password: str):
        """
        Devuelve el objeto Usuario si las credenciales son correctas.
        Lanza AuthError con mensaje genérico si no (no revela si el usuario existe).
        """
        registro = self.usuario_repo.obtener_por_usuario(usuario.strip())
        if not registro or not verify_password(password, registro.password_hash):
            raise AuthError("Usuario o contraseña incorrectos.")
        return registro

    def cambiar_password(self, usuario_id: int, password_actual: str, password_nuevo: str, confirmar_nuevo: str) -> None:
        registro = self.usuario_repo.obtener_por_id(usuario_id)
        if not registro or not verify_password(password_actual, registro.password_hash):
            raise AuthError("La contraseña actual es incorrecta.")
        if len(password_nuevo) < 8:
            raise AuthError("La nueva contraseña debe tener al menos 8 caracteres.")
        if password_nuevo != confirmar_nuevo:
            raise AuthError("Las contraseñas nuevas no coinciden.")

        self.usuario_repo.actualizar_password(usuario_id, hash_password(password_nuevo))

    def validar_codigo_recuperacion(self, codigo_ingresado: str):
        """
        Devuelve el Usuario si el código es válido y no ha sido usado.
        No lo marca como usado todavía (eso ocurre al completar el reseteo).
        """
        registro = self.usuario_repo.obtener_unico()
        if not registro:
            raise AuthError("No existe una cuenta configurada.")
        if registro.recovery_code_usado:
            raise AuthError("El código de recuperación ya fue utilizado.")
        if not verificar_codigo_recuperacion(codigo_ingresado, registro.recovery_code_hash):
            raise AuthError("Código de recuperación inválido.")
        return registro

    def restablecer_password_con_codigo(self, codigo_ingresado: str, password_nuevo: str, confirmar_nuevo: str) -> str:
        """
        Verifica el código, cambia la contraseña, invalida el código usado
        y genera uno nuevo para el futuro. Devuelve el NUEVO código en texto plano.
        """
        registro = self.validar_codigo_recuperacion(codigo_ingresado)

        if len(password_nuevo) < 8:
            raise AuthError("La nueva contraseña debe tener al menos 8 caracteres.")
        if password_nuevo != confirmar_nuevo:
            raise AuthError("Las contraseñas no coinciden.")

        self.usuario_repo.actualizar_password(registro.id, hash_password(password_nuevo))

        nuevo_codigo = generar_codigo_recuperacion()
        nuevo_codigo_hash = hash_codigo_recuperacion(nuevo_codigo)
        self.usuario_repo.actualizar_codigo_recuperacion(registro.id, nuevo_codigo_hash)

        return nuevo_codigo
