"""Lógica de negocio de caja: apertura, movimientos manuales, cierre con cálculo de diferencia."""

from repositories.caja_repository import CajaRepository


class CajaError(Exception):
    pass


class CajaService:

    def __init__(self):
        self.caja_repo = CajaRepository()

    def estado_actual(self, usuario_id: int) -> dict:
        return self.caja_repo.estado_caja_actual(usuario_id)

    def abrir_caja(self, usuario_id: int, monto_apertura: float) -> int:
        if monto_apertura < 0:
            raise CajaError("El monto de apertura no puede ser negativo.")
        if self.caja_repo.obtener_sesion_abierta(usuario_id):
            raise CajaError("Ya existe una sesión de caja abierta.")
        return self.caja_repo.abrir_sesion(usuario_id, monto_apertura)

    def registrar_ingreso_manual(self, usuario_id: int, monto: float, descripcion: str) -> None:
        sesion = self._requerir_sesion_abierta(usuario_id)
        if monto <= 0:
            raise CajaError("El monto debe ser mayor a cero.")
        self.caja_repo.registrar_movimiento_independiente(sesion.id, "ingreso_manual", monto, descripcion)

    def registrar_egreso(self, usuario_id: int, monto: float, descripcion: str) -> None:
        sesion = self._requerir_sesion_abierta(usuario_id)
        if monto <= 0:
            raise CajaError("El monto debe ser mayor a cero.")
        self.caja_repo.registrar_movimiento_independiente(sesion.id, "egreso", monto, descripcion)

    def registrar_retiro(self, usuario_id: int, monto: float, descripcion: str) -> None:
        sesion = self._requerir_sesion_abierta(usuario_id)
        if monto <= 0:
            raise CajaError("El monto debe ser mayor a cero.")
        self.caja_repo.registrar_movimiento_independiente(sesion.id, "retiro", monto, descripcion)

    def cerrar_caja(self, usuario_id: int, monto_contado: float) -> dict:
        sesion = self._requerir_sesion_abierta(usuario_id)
        if monto_contado < 0:
            raise CajaError("El monto contado no puede ser negativo.")

        monto_esperado = self.caja_repo.calcular_monto_esperado(sesion.id)
        self.caja_repo.cerrar_sesion(sesion.id, monto_esperado, monto_contado)

        return {
            "monto_esperado": monto_esperado,
            "monto_contado": monto_contado,
            "diferencia": round(monto_contado - monto_esperado, 2),
        }

    def movimientos_sesion_actual(self, usuario_id: int) -> list[dict]:
        sesion = self.caja_repo.obtener_sesion_abierta(usuario_id)
        if not sesion:
            return []
        return self.caja_repo.listar_movimientos(sesion.id)

    def historial_sesiones(self) -> list[dict]:
        return self.caja_repo.listar_sesiones()

    def _requerir_sesion_abierta(self, usuario_id: int):
        sesion = self.caja_repo.obtener_sesion_abierta(usuario_id)
        if not sesion:
            raise CajaError("No hay una sesión de caja abierta. Abra la caja primero.")
        return sesion
