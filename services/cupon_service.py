"""Cupones de descuento: el sistema genera el código y valida su uso."""

import secrets
from datetime import date

from database.connection import get_db

# Sin 0/O/1/I para que el código se lea bien en voz alta o impreso.
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PREFIJO = "CUP"


class CuponError(Exception):
    pass


class CuponService:

    def __init__(self):
        self.db = get_db()

    def generar_codigo(self) -> str:
        con = self.db.get_connection()
        for _ in range(50):
            codigo = f"{PREFIJO}-" + "".join(secrets.choice(_ALFABETO) for _ in range(6))
            if not con.execute("SELECT 1 FROM cupones WHERE codigo = ?", (codigo,)).fetchone():
                return codigo
        raise CuponError("No se pudo generar un código único. Intenta de nuevo.")

    def crear(self, descripcion: str, tipo: str, valor: float, compra_minima: float = 0.0,
              fecha_inicio: str | None = None, fecha_fin: str | None = None,
              usos_maximos: int = 0, codigo: str | None = None) -> str:
        if tipo not in ("porcentaje", "monto"):
            raise CuponError("Tipo de cupón inválido.")
        if valor <= 0:
            raise CuponError("El valor del cupón debe ser mayor a cero.")
        if tipo == "porcentaje" and valor > 100:
            raise CuponError("El porcentaje no puede ser mayor a 100.")
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            raise CuponError("La fecha final no puede ser anterior a la inicial.")
        codigo = (codigo or "").strip().upper() or self.generar_codigo()
        with self.db.transaction() as cur:
            if cur.execute("SELECT 1 FROM cupones WHERE codigo = ?", (codigo,)).fetchone():
                raise CuponError(f"Ya existe un cupón con el código {codigo}.")
            cur.execute(
                """INSERT INTO cupones (codigo, descripcion, tipo, valor, compra_minima,
                       fecha_inicio, fecha_fin, usos_maximos)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (codigo, (descripcion or "").strip(), tipo, valor, compra_minima,
                 fecha_inicio or None, fecha_fin or None, max(int(usos_maximos), 0)),
            )
        return codigo

    def listar(self) -> list[dict]:
        cur = self.db.get_connection().execute("SELECT * FROM cupones ORDER BY id DESC")
        return [dict(r) for r in cur.fetchall()]

    def obtener_por_codigo(self, codigo: str) -> dict | None:
        fila = self.db.get_connection().execute(
            "SELECT * FROM cupones WHERE codigo = ?", ((codigo or "").strip().upper(),)).fetchone()
        return dict(fila) if fila else None

    def cambiar_activo(self, cupon_id: int, activo: bool) -> None:
        with self.db.transaction() as cur:
            cur.execute("UPDATE cupones SET activo = ? WHERE id = ?", (int(activo), cupon_id))

    def eliminar(self, cupon_id: int) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM cupones WHERE id = ?", (cupon_id,))

    # --- Validación / aplicación ---
    @staticmethod
    def _calcular(cupon: dict, subtotal: float) -> float:
        if cupon["tipo"] == "porcentaje":
            return round(subtotal * cupon["valor"] / 100, 2)
        return round(min(cupon["valor"], subtotal), 2)

    def validar(self, codigo: str, subtotal: float, cursor=None) -> dict:
        """Devuelve {'codigo', 'descuento', 'cupon'} o lanza CuponError."""
        codigo = (codigo or "").strip().upper()
        if not codigo:
            raise CuponError("Escribe un código de cupón.")
        ejecutor = cursor or self.db.get_connection()
        fila = ejecutor.execute("SELECT * FROM cupones WHERE codigo = ?", (codigo,)).fetchone()
        if not fila:
            raise CuponError("El cupón no existe.")
        cupon = dict(fila)
        hoy = date.today().isoformat()
        if not cupon["activo"]:
            raise CuponError("El cupón está desactivado.")
        if cupon["fecha_inicio"] and hoy < cupon["fecha_inicio"][:10]:
            raise CuponError(f"El cupón vale desde {cupon['fecha_inicio'][:10]}.")
        if cupon["fecha_fin"] and hoy > cupon["fecha_fin"][:10]:
            raise CuponError("El cupón está vencido.")
        if cupon["usos_maximos"] and cupon["usos"] >= cupon["usos_maximos"]:
            raise CuponError("El cupón ya alcanzó su máximo de usos.")
        if subtotal < cupon["compra_minima"]:
            raise CuponError(f"Compra mínima para este cupón: {cupon['compra_minima']:.2f}.")
        descuento = self._calcular(cupon, subtotal)
        if descuento <= 0:
            raise CuponError("El cupón no aplica a esta compra.")
        return {"codigo": codigo, "descuento": descuento, "cupon": cupon}

    def consumir(self, cursor, codigo: str) -> None:
        cursor.execute("UPDATE cupones SET usos = usos + 1 WHERE codigo = ?", (codigo,))

    def devolver_uso(self, cursor, codigo: str) -> None:
        cursor.execute("UPDATE cupones SET usos = MAX(usos - 1, 0) WHERE codigo = ?", (codigo,))
