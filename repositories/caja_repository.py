"""Acceso a datos de sesiones de caja y sus movimientos."""

from database.connection import get_db
from models.caja import CajaSesion
import sys, traceback
from PySide6.QtWidgets import QMessageBox

def _excepthook(tipo, valor, tb):
    texto = "".join(traceback.format_exception(tipo, valor, tb))
    print(texto, file=sys.stderr)
    QMessageBox.critical(None, "Error", f"{tipo.__name__}: {valor}")

sys.excepthook = _excepthook

class CajaRepository:

    def __init__(self):
        self.db = get_db()

    def obtener_sesion_abierta(self, usuario_id: int) -> CajaSesion | None:
        cur = self.db.get_connection().execute(
            "SELECT * FROM caja_sesiones WHERE usuario_id = ? AND estado = 'abierta' LIMIT 1",
            (usuario_id,),
        )
        row = cur.fetchone()
        return CajaSesion.from_row(row) if row else None

    def abrir_sesion(self, usuario_id: int, monto_apertura: float) -> int:
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO caja_sesiones (usuario_id, monto_apertura, estado) VALUES (?, ?, 'abierta')",
                (usuario_id, monto_apertura),
            )
            return cur.lastrowid

    def registrar_movimiento(self, cursor, caja_sesion_id: int, tipo: str, monto: float,
                              descripcion: str = "", referencia_id: int | None = None) -> None:
        cursor.execute(
            """INSERT INTO caja_movimientos (caja_sesion_id, tipo, monto, descripcion, referencia_id)
               VALUES (?, ?, ?, ?, ?)""",
            (caja_sesion_id, tipo, monto, descripcion, referencia_id),
        )

    def registrar_movimiento_independiente(self, caja_sesion_id: int, tipo: str,
                                            monto: float, descripcion: str = "") -> None:
        """Para ingresos/egresos manuales que no vienen de una venta."""
        with self.db.transaction() as cur:
            self.registrar_movimiento(cur, caja_sesion_id, tipo, monto, descripcion)

    def calcular_monto_esperado(self, caja_sesion_id: int) -> float:
        cur = self.db.get_connection().execute(
            "SELECT monto_apertura FROM caja_sesiones WHERE id = ?", (caja_sesion_id,)
        )
        apertura = cur.fetchone()["monto_apertura"]

        cur = self.db.get_connection().execute(
            """SELECT
                   COALESCE(SUM(CASE WHEN tipo IN ('venta', 'ingreso_manual') THEN monto ELSE 0 END), 0) AS ingresos,
                   COALESCE(SUM(CASE WHEN tipo IN ('egreso', 'retiro') THEN monto ELSE 0 END), 0) AS egresos
               FROM caja_movimientos WHERE caja_sesion_id = ?""",
            (caja_sesion_id,),
        )
        row = cur.fetchone()
        return apertura + row["ingresos"] - row["egresos"]

    def cerrar_sesion(self, caja_sesion_id: int, monto_esperado: float, monto_contado: float) -> None:
        diferencia = round(monto_contado - monto_esperado, 2)
        with self.db.transaction() as cur:
            cur.execute(
                """UPDATE caja_sesiones SET
                       fecha_cierre = datetime('now', 'localtime'),
                       monto_esperado = ?, monto_contado = ?, diferencia = ?, estado = 'cerrada'
                   WHERE id = ?""",
                (monto_esperado, monto_contado, diferencia, caja_sesion_id),
            )

    def listar_movimientos(self, caja_sesion_id: int) -> list[dict]:
        cur = self.db.get_connection().execute(
            "SELECT * FROM caja_movimientos WHERE caja_sesion_id = ? ORDER BY fecha DESC",
            (caja_sesion_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    def listar_sesiones(self, limite: int = 100) -> list[dict]:
        cur = self.db.get_connection().execute(
            """SELECT cs.*, u.nombre AS usuario_nombre
               FROM caja_sesiones cs JOIN usuarios u ON u.id = cs.usuario_id
               ORDER BY cs.fecha_apertura DESC LIMIT ?""",
            (limite,),
        )
        return [dict(r) for r in cur.fetchall()]

    def estado_caja_actual(self, usuario_id: int) -> dict:
        sesion = self.obtener_sesion_abierta(usuario_id)
        if not sesion:
            return {"abierta": False}
        return {
            "abierta": True,
            "sesion_id": sesion.id,
            "monto_apertura": sesion.monto_apertura,
            "monto_esperado": self.calcular_monto_esperado(sesion.id),
        }
