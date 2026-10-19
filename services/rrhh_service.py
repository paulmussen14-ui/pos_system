"""RRHH: trabajadores, adelantos/descuentos/bonificaciones y pagos (egreso de caja)."""

from datetime import datetime, date

from database.connection import get_db
from repositories.caja_repository import CajaRepository

TIPOS_PAGO = ("mensual", "quincenal", "semanal")
TIPOS_MOVIMIENTO = ("adelanto", "descuento", "bonificacion")


class RrhhError(Exception):
    pass


class RrhhService:

    def __init__(self):
        self.db = get_db()
        self.caja_repo = CajaRepository()

    # --- Trabajadores ---
    def guardar_trabajador(self, datos: dict, trabajador_id: int | None = None) -> int:
        nombre = (datos.get("nombre") or "").strip()
        if not nombre:
            raise RrhhError("El nombre es obligatorio.")
        if datos.get("tipo_pago") not in TIPOS_PAGO:
            raise RrhhError("Tipo de pago inválido.")
        if float(datos.get("monto_base") or 0) < 0:
            raise RrhhError("El sueldo no puede ser negativo.")
        campos = (nombre, (datos.get("documento") or "").strip(), (datos.get("telefono") or "").strip(),
                  (datos.get("funcion") or "").strip(), datos["tipo_pago"],
                  float(datos.get("monto_base") or 0), datos.get("fecha_ingreso") or None,
                  int(bool(datos.get("activo", True))),
                  datos.get("hora_entrada") or None, datos.get("hora_salida") or None,
                  datos.get("dias_laborales") or None)
        if campos[-3] and campos[-2] and campos[-3] >= campos[-2]:
            raise RrhhError("La hora de salida debe ser posterior a la de entrada.")
        with self.db.transaction() as cur:
            if trabajador_id:
                cur.execute("""UPDATE trabajadores SET nombre=?, documento=?, telefono=?, funcion=?,
                               tipo_pago=?, monto_base=?, fecha_ingreso=?, activo=?,
                               hora_entrada=?, hora_salida=?, dias_laborales=? WHERE id=?""",
                            campos + (trabajador_id,))
                return trabajador_id
            cur.execute("""INSERT INTO trabajadores (nombre, documento, telefono, funcion, tipo_pago,
                           monto_base, fecha_ingreso, activo, hora_entrada, hora_salida, dias_laborales)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""", campos)
            return cur.lastrowid

    def listar_trabajadores(self, solo_activos: bool = False) -> list[dict]:
        sql = """SELECT t.*,
                   COALESCE((SELECT SUM(monto) FROM trabajador_movimientos m WHERE m.trabajador_id=t.id
                             AND m.pago_id IS NULL AND m.anulado=0 AND m.tipo='adelanto'),0) AS adelantos_pend,
                   COALESCE((SELECT SUM(monto) FROM trabajador_movimientos m WHERE m.trabajador_id=t.id
                             AND m.pago_id IS NULL AND m.anulado=0 AND m.tipo='descuento'),0) AS descuentos_pend,
                   COALESCE((SELECT SUM(monto) FROM trabajador_movimientos m WHERE m.trabajador_id=t.id
                             AND m.pago_id IS NULL AND m.anulado=0 AND m.tipo='bonificacion'),0) AS bonos_pend
                 FROM trabajadores t"""
        if solo_activos:
            sql += " WHERE t.activo = 1"
        sql += " ORDER BY t.activo DESC, t.nombre"
        return [dict(r) for r in self.db.get_connection().execute(sql).fetchall()]

    # --- Movimientos ---
    def registrar_movimiento(self, trabajador_id: int, tipo: str, monto: float, motivo: str = "") -> None:
        if tipo not in TIPOS_MOVIMIENTO:
            raise RrhhError("Tipo de movimiento inválido.")
        if monto <= 0:
            raise RrhhError("El monto debe ser mayor a cero.")
        with self.db.transaction() as cur:
            cur.execute("INSERT INTO trabajador_movimientos (trabajador_id, tipo, monto, motivo) VALUES (?,?,?,?)",
                        (trabajador_id, tipo, monto, (motivo or "").strip()))

    def listar_movimientos(self, trabajador_id: int | None = None, solo_pendientes: bool = False) -> list[dict]:
        sql = """SELECT m.*, t.nombre AS trabajador FROM trabajador_movimientos m
                 JOIN trabajadores t ON t.id = m.trabajador_id WHERE m.anulado = 0"""
        params = []
        if trabajador_id:
            sql += " AND m.trabajador_id = ?"
            params.append(trabajador_id)
        if solo_pendientes:
            sql += " AND m.pago_id IS NULL"
        sql += " ORDER BY m.fecha DESC, m.id DESC LIMIT 500"
        return [dict(r) for r in self.db.get_connection().execute(sql, params).fetchall()]

    def anular_movimiento(self, movimiento_id: int) -> None:
        with self.db.transaction() as cur:
            fila = cur.execute("SELECT pago_id FROM trabajador_movimientos WHERE id = ?",
                               (movimiento_id,)).fetchone()
            if not fila:
                raise RrhhError("Movimiento no encontrado.")
            if fila["pago_id"]:
                raise RrhhError("Este movimiento ya fue liquidado en un pago.")
            cur.execute("UPDATE trabajador_movimientos SET anulado = 1 WHERE id = ?", (movimiento_id,))

    # --- Pagos ---
    def calcular_pago(self, trabajador_id: int) -> dict:
        con = self.db.get_connection()
        t = con.execute("SELECT * FROM trabajadores WHERE id = ?", (trabajador_id,)).fetchone()
        if not t:
            raise RrhhError("Trabajador no encontrado.")
        sumas = {"adelanto": 0.0, "descuento": 0.0, "bonificacion": 0.0}
        for r in con.execute("""SELECT tipo, SUM(monto) s FROM trabajador_movimientos
                                WHERE trabajador_id=? AND pago_id IS NULL AND anulado=0 GROUP BY tipo""",
                             (trabajador_id,)):
            sumas[r["tipo"]] = r["s"] or 0.0
        base = float(t["monto_base"])
        neto = round(base + sumas["bonificacion"] - sumas["descuento"] - sumas["adelanto"], 2)
        return {"base": base, "bonificaciones": sumas["bonificacion"], "descuentos": sumas["descuento"],
                "adelantos": sumas["adelanto"], "neto": neto, "tipo_pago": t["tipo_pago"],
                "trabajador": t["nombre"]}

    def registrar_pago(self, trabajador_id: int, usuario_id: int, periodo_desde: str = "",
                       periodo_hasta: str = "", notas: str = "") -> dict:
        calc = self.calcular_pago(trabajador_id)
        if calc["neto"] < 0:
            raise RrhhError("Los descuentos y adelantos superan el sueldo. Anula o ajusta algún movimiento.")
        sesion = self.caja_repo.obtener_sesion_abierta(usuario_id)
        with self.db.transaction() as cur:
            cur.execute(
                """INSERT INTO trabajador_pagos (trabajador_id, periodo_desde, periodo_hasta, base,
                       bonificaciones, descuentos, adelantos, neto, usuario_id, caja_sesion_id, notas)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (trabajador_id, periodo_desde or None, periodo_hasta or None, calc["base"],
                 calc["bonificaciones"], calc["descuentos"], calc["adelantos"], calc["neto"],
                 usuario_id, sesion.id if sesion else None, (notas or "").strip() or None))
            pago_id = cur.lastrowid
            cur.execute("""UPDATE trabajador_movimientos SET pago_id = ?
                           WHERE trabajador_id = ? AND pago_id IS NULL AND anulado = 0""",
                        (pago_id, trabajador_id))
            if sesion and calc["neto"] > 0:
                self.caja_repo.registrar_movimiento(
                    cur, sesion.id, "egreso", calc["neto"],
                    f"Pago RRHH: {calc['trabajador']}", pago_id)
        calc["pago_id"] = pago_id
        calc["en_caja"] = bool(sesion and calc["neto"] > 0)
        return calc

    def listar_pagos(self, trabajador_id: int | None = None) -> list[dict]:
        sql = """SELECT p.*, t.nombre AS trabajador FROM trabajador_pagos p
                 JOIN trabajadores t ON t.id = p.trabajador_id"""
        params = []
        if trabajador_id:
            sql += " WHERE p.trabajador_id = ?"
            params.append(trabajador_id)
        sql += " ORDER BY p.id DESC LIMIT 500"
        return [dict(r) for r in self.db.get_connection().execute(sql, params).fetchall()]


    # --- Asistencia (marcar entrada y salida) ---
    TOLERANCIA_MINUTOS = 5

    def marcar_entrada(self, trabajador_id: int, hora: str | None = None) -> dict:
        ahora = datetime.now()
        hora = hora or ahora.strftime("%H:%M")
        hoy = ahora.strftime("%Y-%m-%d")
        with self.db.transaction() as cur:
            t = cur.execute("SELECT hora_entrada FROM trabajadores WHERE id = ?", (trabajador_id,)).fetchone()
            if not t:
                raise RrhhError("Trabajador no encontrado.")
            if cur.execute("SELECT 1 FROM trabajador_asistencia WHERE trabajador_id=? AND fecha=?",
                           (trabajador_id, hoy)).fetchone():
                raise RrhhError("Ya se marcó la entrada de hoy.")
            tarde = 0
            if t["hora_entrada"]:
                tarde = self._minutos(hora) - self._minutos(t["hora_entrada"])
                tarde = tarde if tarde > self.TOLERANCIA_MINUTOS else 0
            cur.execute("""INSERT INTO trabajador_asistencia (trabajador_id, fecha, entrada, minutos_tarde)
                           VALUES (?,?,?,?)""", (trabajador_id, hoy, hora, tarde))
        return {"hora": hora, "minutos_tarde": tarde}

    def marcar_salida(self, trabajador_id: int, hora: str | None = None) -> dict:
        ahora = datetime.now()
        hora = hora or ahora.strftime("%H:%M")
        hoy = ahora.strftime("%Y-%m-%d")
        with self.db.transaction() as cur:
            fila = cur.execute("SELECT id, entrada, salida FROM trabajador_asistencia WHERE trabajador_id=? AND fecha=?",
                               (trabajador_id, hoy)).fetchone()
            if not fila:
                raise RrhhError("Primero marca la entrada de hoy.")
            if fila["salida"]:
                raise RrhhError("Ya se marcó la salida de hoy.")
            if self._minutos(hora) < self._minutos(fila["entrada"]):
                raise RrhhError("La salida no puede ser anterior a la entrada.")
            cur.execute("UPDATE trabajador_asistencia SET salida = ? WHERE id = ?", (hora, fila["id"]))
        return {"hora": hora}

    @staticmethod
    def _minutos(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    def asistencia_hoy(self) -> dict[int, dict]:
        hoy = date.today().isoformat()
        cur = self.db.get_connection().execute(
            "SELECT * FROM trabajador_asistencia WHERE fecha = ?", (hoy,))
        return {r["trabajador_id"]: dict(r) for r in cur.fetchall()}

    def listar_asistencia(self, trabajador_id: int | None = None, limite: int = 300) -> list[dict]:
        sql = """SELECT a.*, t.nombre AS trabajador FROM trabajador_asistencia a
                 JOIN trabajadores t ON t.id = a.trabajador_id"""
        params = []
        if trabajador_id:
            sql += " WHERE a.trabajador_id = ?"
            params.append(trabajador_id)
        sql += " ORDER BY a.fecha DESC, a.id DESC LIMIT ?"
        params.append(limite)
        filas = [dict(r) for r in self.db.get_connection().execute(sql, params).fetchall()]
        for f in filas:
            if f["entrada"] and f["salida"]:
                m = self._minutos(f["salida"]) - self._minutos(f["entrada"])
                f["horas"] = f"{m // 60}h {m % 60:02d}m"
            else:
                f["horas"] = ""
        return filas
