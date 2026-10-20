"""Reservas por hora (modelo de negocio "servicios").

Una reserva puede incluir sub-servicios (costo adicional) y productos del servicio, y puede
recibir ADELANTOS: pagos parciales del monto que el negocio indique, antes de la atención.
Al cobrar solo se paga el saldo (total - adelantos). Si se cancela, el adelanto se devuelve
o se retiene, según se decida.

Una reserva ocupa un tramo de un día (hora_inicio → hora_fin) y pasa por estos estados:

    reservada  → el cliente tiene su hora apartada.
    atendida   → ya se cobró y se generó su boleta.
    no_asistio → el cliente no llegó (sigue ocupando el tramo hasta que se cancele).
    cancelada  → libera el tramo; deja de mostrarse en la agenda.

Al cobrar se registra una venta normal (con el producto oculto del servicio) para que
el ingreso aparezca en Caja y Reportes, pero la reserva guarda su PROPIA copia de los
datos de la boleta (número, total, método de pago): la limpieza de registros antiguos
borra ventas viejas y aun así la boleta debe poder volver a generarse o reenviarse.
"""

from datetime import date, timedelta

from database.connection import get_db
from repositories.caja_repository import CajaRepository
from repositories.inventario_repository import InventarioRepository
from repositories.venta_repository import VentaRepository
from services.cliente_service import ClienteService
from services.servicio_service import ServicioService
from utils.fechas import a_hhmm, a_minutos, fecha_dmy, parsear_fecha
from utils.validators import es_email_valido

SERIE_BOLETA = "B001"

ESTADO_RESERVADA = "reservada"
ESTADO_ATENDIDA = "atendida"
ESTADO_NO_ASISTIO = "no_asistio"
ESTADO_CANCELADA = "cancelada"
ESTADOS = (ESTADO_RESERVADA, ESTADO_ATENDIDA, ESTADO_NO_ASISTIO, ESTADO_CANCELADA)

# Estados que ocupan el tramo de la agenda (la cancelada lo libera).
ESTADOS_OCUPAN = (ESTADO_RESERVADA, ESTADO_ATENDIDA, ESTADO_NO_ASISTIO)


class ReservaError(Exception):
    """Error de negocio en la agenda (mensaje apto para mostrar al usuario)."""


def numero_boleta_texto(numero: int | None) -> str:
    """12 -> 'B001-000012'."""
    return f"{SERIE_BOLETA}-{int(numero):06d}" if numero else ""


class ReservaService:

    def __init__(self):
        self.db = get_db()
        self.cliente_service = ClienteService()
        self.servicio_service = ServicioService()
        self.venta_repo = VentaRepository()
        self.caja_repo = CajaRepository()
        self.inventario_repo = InventarioRepository()

    # ------------------------------------------------------ Consultas ----
    def obtener(self, reserva_id: int) -> dict | None:
        fila = self.db.get_connection().execute(
            "SELECT * FROM reservas WHERE id = ?", (reserva_id,)
        ).fetchone()
        return self._con_extras(dict(fila)) if fila else None

    @staticmethod
    def total_de(precio_base: float, items: list[dict]) -> float:
        """Total de una reserva: precio base + sub-servicios + productos cobrables."""
        return round(float(precio_base) + sum(float(i["subtotal"]) for i in items), 2)

    def listar_rango(self, desde: date, hasta: date) -> list[dict]:
        """Reservas de [desde, hasta] (ambos incluidos), sin las canceladas."""
        filas = self.db.get_connection().execute(
            """SELECT * FROM reservas
               WHERE fecha >= ? AND fecha <= ? AND estado != 'cancelada'
               ORDER BY fecha, hora_inicio""",
            (desde.isoformat(), hasta.isoformat()),
        ).fetchall()
        return [self._con_extras(dict(f)) for f in filas]

    def listar_semana(self, lunes: date) -> list[dict]:
        return self.listar_rango(lunes, lunes + timedelta(days=6))

    def resumen_del_dia(self, dia: date) -> dict:
        """Reservas del día, cuántas siguen pendientes de cobro y lo cobrado ese día."""
        reservas = self.listar_rango(dia, dia)
        return {
            "total": len(reservas),
            "pendientes": sum(1 for r in reservas if r["estado"] == ESTADO_RESERVADA),
            "atendidas": sum(1 for r in reservas if r["estado"] == ESTADO_ATENDIDA),
            "cobrado": round(sum((r["total"] or 0) for r in reservas
                                 if r["estado"] == ESTADO_ATENDIDA), 2),
        }

    def _con_extras(self, reserva: dict) -> dict:
        """Agrega a la reserva su número de boleta en texto, sus ítems y adelantos, y los
        totales: total_estimado (antes de descuento), adelanto_total (solo los vigentes)
        y saldo_estimado (lo que falta pagar)."""
        conexion = self.db.get_connection()
        reserva["boleta_texto"] = numero_boleta_texto(reserva.get("numero_boleta"))
        reserva["items"] = [dict(f) for f in conexion.execute(
            "SELECT * FROM reserva_items WHERE reserva_id = ? ORDER BY id", (reserva["id"],))]
        reserva["pagos"] = [dict(f) for f in conexion.execute(
            "SELECT * FROM reserva_pagos WHERE reserva_id = ? ORDER BY id", (reserva["id"],))]
        reserva["adelanto_total"] = round(sum(
            p["monto"] for p in reserva["pagos"] if p["estado"] == "vigente"), 2)
        reserva["total_estimado"] = self.total_de(reserva["precio"], reserva["items"])
        reserva["saldo_estimado"] = round(max(reserva["total_estimado"] - reserva["adelanto_total"], 0), 2)
        return reserva

    def _cruce(self, fecha: str, inicio: str, fin: str, excluir_id: int | None = None) -> dict | None:
        """Devuelve la reserva que se cruza con [inicio, fin) ese día, si existe."""
        marcas = ",".join("?" * len(ESTADOS_OCUPAN))
        consulta = (
            f"SELECT * FROM reservas WHERE fecha = ? AND estado IN ({marcas}) "
            "AND hora_inicio < ? AND hora_fin > ?"
        )
        params: list = [fecha, *ESTADOS_OCUPAN, fin, inicio]
        if excluir_id is not None:
            consulta += " AND id != ?"
            params.append(excluir_id)
        fila = self.db.get_connection().execute(consulta + " LIMIT 1", params).fetchone()
        return dict(fila) if fila else None

    # ------------------------------------------------ Crear / editar ----
    def _validar_datos(self, fecha: str, hora_inicio: str, duracion_min: int,
                       cliente_nombre: str, cliente_email: str, precio: float,
                       excluir_id: int | None = None) -> tuple[str, str]:
        """Valida los datos de una reserva y devuelve (hora_inicio, hora_fin) normalizadas."""
        try:
            parsear_fecha(fecha)
            inicio_min = a_minutos(hora_inicio)
        except (ValueError, AttributeError):
            raise ReservaError("La fecha o la hora no son válidas.")
        if not (cliente_nombre or "").strip():
            raise ReservaError("Escribe el nombre del cliente.")
        if cliente_email and not es_email_valido(cliente_email):
            raise ReservaError("El correo del cliente no parece válido (ej. nombre@correo.com).")
        if precio is None or precio < 0:
            raise ReservaError("El precio no puede ser negativo.")
        if int(duracion_min) < 5:
            raise ReservaError("La duración mínima es de 5 minutos.")
        fin_min = inicio_min + int(duracion_min)
        if fin_min > 24 * 60:
            raise ReservaError("La reserva no puede pasar de la medianoche.")

        hora_inicio, hora_fin = a_hhmm(inicio_min), a_hhmm(fin_min)
        cruce = self._cruce(fecha, hora_inicio, hora_fin, excluir_id)
        if cruce:
            raise ReservaError(
                f"Ese horario ya está ocupado: {cruce['cliente_nombre']} de "
                f"{cruce['hora_inicio']} a {cruce['hora_fin']}."
            )
        return hora_inicio, hora_fin

    def _resolver_cliente(self, cliente_id: int | None, nombre: str, telefono: str,
                          email: str, guardar_cliente: bool) -> int | None:
        """Devuelve el id del cliente a asociar. Si es un cliente registrado, le completa
        el teléfono y el correo que no tuviera; si es nuevo y se pidió, lo registra."""
        nombre = nombre.strip()
        if cliente_id:
            existente = self.cliente_service.obtener_por_id(cliente_id)
            if existente:
                nuevo_tel = (existente.telefono or "").strip() or (telefono or "").strip()
                nuevo_email = (existente.email or "").strip() or (email or "").strip()
                if nuevo_tel != (existente.telefono or "").strip() or \
                        nuevo_email != (existente.email or "").strip():
                    self.cliente_service.actualizar(
                        existente.id, existente.nombre, nuevo_tel,
                        existente.direccion or "", email=nuevo_email,
                    )
                return existente.id
        if guardar_cliente:
            return self.cliente_service.crear(nombre, telefono or "", "", email=email or "")
        return None

    def _items_para(self, servicio_id: int, subservicio_ids, producto_ids) -> list[dict]:
        """Ítems (sub-servicios y productos) que se copian a la reserva, con el nombre y
        precio de HOY. Los productos "incluidos" van con precio 0 (solo descuentan stock)."""
        items = []
        subservicio_ids = set(subservicio_ids or [])
        producto_ids = set(producto_ids or [])
        if subservicio_ids:
            tipos_elegidos = 0
            # Tipos: los del servicio. Efectos: todo el catálogo global (aplican a cualquier servicio).
            candidatos = [s for s in self.servicio_service.listar_subservicios(servicio_id, solo_activos=False)
                          if s.get("clase") == "tipo"]
            candidatos += [o for o in self.servicio_service.listar_opciones(solo_activas=False)
                           if o.get("clase") != "tipo"]
            for sub in candidatos:
                if sub["id"] in subservicio_ids:
                    if sub.get("clase") == "tipo":
                        tipos_elegidos += 1
                        if tipos_elegidos > 1:
                            raise ReservaError("Elige un solo tipo de servicio (los extras sí pueden ser varios).")
                    items.append({"tipo": "subservicio", "referencia_id": sub["id"], "nombre": sub["nombre"],
                                  "cantidad": 1, "precio_unitario": sub["precio"], "subtotal": sub["precio"]})
        if producto_ids:
            for prod in self.servicio_service.listar_productos(servicio_id):
                if prod["producto_id"] in producto_ids:
                    precio = float(prod["precio"]) if prod["cobrar"] else 0.0
                    items.append({"tipo": "producto", "referencia_id": prod["producto_id"],
                                  "nombre": prod["nombre"], "cantidad": prod["cantidad"],
                                  "precio_unitario": precio,
                                  "subtotal": round(precio * prod["cantidad"], 2)})
        return items

    @staticmethod
    def _guardar_items(cur, reserva_id: int, items: list[dict]) -> None:
        cur.execute("DELETE FROM reserva_items WHERE reserva_id = ?", (reserva_id,))
        for i in items:
            cur.execute(
                """INSERT INTO reserva_items (reserva_id, tipo, referencia_id, nombre, cantidad,
                                              precio_unitario, subtotal)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (reserva_id, i["tipo"], i["referencia_id"], i["nombre"], i["cantidad"],
                 i["precio_unitario"], i["subtotal"]),
            )

    def _preparar_pago(self, monto: float, metodo_pago_id: int | None, usuario_id: int | None):
        """Valida un cobro parcial (adelanto) y devuelve (nombre del método, es_efectivo, sesión de caja)."""
        if not metodo_pago_id:
            raise ReservaError("Elige el método de pago del adelanto.")
        fila = self.db.get_connection().execute(
            "SELECT nombre FROM metodos_pago WHERE id = ?", (metodo_pago_id,)).fetchone()
        if not fila:
            raise ReservaError("El método de pago ya no existe.")
        es_efectivo = bool(self.venta_repo.metodo_pago_es_efectivo(metodo_pago_id))
        sesion = self.caja_repo.obtener_sesion_abierta(usuario_id) if usuario_id else None
        if es_efectivo and not sesion:
            raise ReservaError("Abre la caja antes de recibir un adelanto en efectivo (menú Caja).")
        return fila["nombre"], es_efectivo, sesion

    def _insertar_adelanto(self, cur, reserva_id: int, cliente: str, monto: float, metodo_pago_id: int,
                           nombre_metodo: str, es_efectivo: bool, sesion) -> None:
        cur.execute(
            """INSERT INTO reserva_pagos (reserva_id, monto, metodo_pago_id, metodo_nombre, es_efectivo)
               VALUES (?, ?, ?, ?, ?)""",
            (reserva_id, round(monto, 2), metodo_pago_id, nombre_metodo, int(es_efectivo)),
        )
        if es_efectivo and sesion:
            self.caja_repo.registrar_movimiento(
                cur, sesion.id, "ingreso_manual", round(monto, 2),
                f"Adelanto reserva #{reserva_id} - {cliente}", reserva_id)

    def crear(self, fecha: str, hora_inicio: str, duracion_min: int, servicio_id: int,
              precio: float, cliente_nombre: str, cliente_telefono: str = "",
              cliente_email: str = "", notas: str = "", cliente_id: int | None = None,
              guardar_cliente: bool = True, subservicio_ids=None, producto_ids=None,
              adelanto: float = 0.0, adelanto_metodo_id: int | None = None,
              usuario_id: int | None = None) -> int:
        servicio = self.servicio_service.obtener(servicio_id)
        if not servicio or not servicio["activo"]:
            raise ReservaError("Elige un servicio disponible.")
        hora_inicio, hora_fin = self._validar_datos(
            fecha, hora_inicio, duracion_min, cliente_nombre, cliente_email, precio)

        items = self._items_para(servicio_id, subservicio_ids, producto_ids)
        total = self.total_de(precio, items)
        adelanto = round(float(adelanto or 0), 2)
        if adelanto < 0:
            raise ReservaError("El adelanto no puede ser negativo.")
        if adelanto > total:
            raise ReservaError(f"El adelanto no puede ser mayor que el total ({total:.2f}).")
        pago = self._preparar_pago(adelanto, adelanto_metodo_id, usuario_id) if adelanto > 0 else None

        cliente_id = self._resolver_cliente(
            cliente_id, cliente_nombre, cliente_telefono, cliente_email, guardar_cliente)

        with self.db.transaction() as cur:
            cur.execute(
                """INSERT INTO reservas
                   (fecha, hora_inicio, hora_fin, servicio_id, servicio_nombre, precio,
                    cliente_id, cliente_nombre, cliente_telefono, cliente_email, notas)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fecha, hora_inicio, hora_fin, servicio_id, servicio["nombre"],
                 round(float(precio), 2), cliente_id, cliente_nombre.strip(),
                 (cliente_telefono or "").strip(), (cliente_email or "").strip(),
                 (notas or "").strip()),
            )
            reserva_id = cur.lastrowid
            self._guardar_items(cur, reserva_id, items)
            if pago:
                self._insertar_adelanto(cur, reserva_id, cliente_nombre.strip(), adelanto,
                                        adelanto_metodo_id, *pago)
            return reserva_id

    def actualizar(self, reserva_id: int, fecha: str, hora_inicio: str, duracion_min: int,
                   servicio_id: int, precio: float, cliente_nombre: str,
                   cliente_telefono: str = "", cliente_email: str = "", notas: str = "",
                   cliente_id: int | None = None, guardar_cliente: bool = True,
                   subservicio_ids=None, producto_ids=None) -> None:
        actual = self.obtener(reserva_id)
        if not actual:
            raise ReservaError("La reserva ya no existe.")
        if actual["estado"] not in (ESTADO_RESERVADA, ESTADO_NO_ASISTIO):
            raise ReservaError("Solo se pueden editar reservas pendientes.")
        servicio = self.servicio_service.obtener(servicio_id)
        if not servicio:
            raise ReservaError("Elige un servicio disponible.")
        hora_inicio, hora_fin = self._validar_datos(
            fecha, hora_inicio, duracion_min, cliente_nombre, cliente_email, precio,
            excluir_id=reserva_id)

        items = self._items_para(servicio_id, subservicio_ids, producto_ids)
        total = self.total_de(precio, items)
        if total < actual["adelanto_total"]:
            raise ReservaError(
                f"El total ({total:.2f}) no puede ser menor que los adelantos ya recibidos "
                f"({actual['adelanto_total']:.2f}).")
        cliente_id = self._resolver_cliente(
            cliente_id, cliente_nombre, cliente_telefono, cliente_email, guardar_cliente)

        with self.db.transaction() as cur:
            cur.execute(
                """UPDATE reservas SET fecha = ?, hora_inicio = ?, hora_fin = ?, servicio_id = ?,
                       servicio_nombre = ?, precio = ?, cliente_id = ?, cliente_nombre = ?,
                       cliente_telefono = ?, cliente_email = ?, notas = ?
                   WHERE id = ?""",
                (fecha, hora_inicio, hora_fin, servicio_id, servicio["nombre"],
                 round(float(precio), 2), cliente_id, cliente_nombre.strip(),
                 (cliente_telefono or "").strip(), (cliente_email or "").strip(),
                 (notas or "").strip(), reserva_id),
            )
            self._guardar_items(cur, reserva_id, items)

    # ------------------------------------------------------ Adelantos ----
    def registrar_adelanto(self, reserva_id: int, monto: float, metodo_pago_id: int | None,
                           usuario_id: int) -> None:
        """Registra un pago adelantado (si es en efectivo, entra a la caja abierta)."""
        reserva = self.obtener(reserva_id)
        if not reserva:
            raise ReservaError("La reserva ya no existe.")
        if reserva["estado"] not in (ESTADO_RESERVADA, ESTADO_NO_ASISTIO):
            raise ReservaError("Solo se puede recibir adelantos de reservas pendientes.")
        monto = round(float(monto or 0), 2)
        if monto <= 0:
            raise ReservaError("El adelanto debe ser mayor a cero.")
        falta = round(reserva["total_estimado"] - reserva["adelanto_total"], 2)
        if monto > falta:
            raise ReservaError(f"El adelanto no puede superar lo que falta pagar ({falta:.2f}).")
        pago = self._preparar_pago(monto, metodo_pago_id, usuario_id)
        with self.db.transaction() as cur:
            self._insertar_adelanto(cur, reserva_id, reserva["cliente_nombre"], monto,
                                    metodo_pago_id, *pago)

    def cancelar(self, reserva_id: int, usuario_id: int, devolver_adelanto: bool = False) -> None:
        """Cancela la reserva y libera la hora. Si tenía adelantos, `devolver_adelanto`
        decide: True los devuelve (lo que fue en efectivo sale de la caja abierta),
        False los retiene el negocio."""
        reserva = self.obtener(reserva_id)
        if not reserva:
            raise ReservaError("La reserva ya no existe.")
        if reserva["estado"] == ESTADO_ATENDIDA:
            raise ReservaError("La reserva ya fue cobrada; no se puede cancelar.")

        vigentes = [p for p in reserva["pagos"] if p["estado"] == "vigente"]
        efectivo = round(sum(p["monto"] for p in vigentes if p["es_efectivo"]), 2)
        sesion = None
        if vigentes and devolver_adelanto and efectivo > 0:
            sesion = self.caja_repo.obtener_sesion_abierta(usuario_id)
            if not sesion:
                raise ReservaError("Abre la caja para devolver un adelanto que se recibió en efectivo.")

        with self.db.transaction() as cur:
            if vigentes:
                nuevo = "devuelto" if devolver_adelanto else "retenido"
                cur.execute("UPDATE reserva_pagos SET estado = ? WHERE reserva_id = ? AND estado = 'vigente'",
                            (nuevo, reserva_id))
                if sesion:
                    self.caja_repo.registrar_movimiento(
                        cur, sesion.id, "egreso", efectivo,
                        f"Devolución de adelanto reserva #{reserva_id} - {reserva['cliente_nombre']}",
                        reserva_id)
            cur.execute("UPDATE reservas SET estado = 'cancelada' WHERE id = ?", (reserva_id,))

    def cambiar_estado(self, reserva_id: int, estado: str) -> None:
        """Cancelar, marcar "no asistió" o volver a "reservada". Una reserva ya
        cobrada no cambia de estado (su boleta ya existe)."""
        if estado not in (ESTADO_RESERVADA, ESTADO_NO_ASISTIO, ESTADO_CANCELADA):
            raise ReservaError("Estado no válido.")
        actual = self.obtener(reserva_id)
        if not actual:
            raise ReservaError("La reserva ya no existe.")
        if actual["estado"] == ESTADO_ATENDIDA:
            raise ReservaError("La reserva ya fue cobrada; no se puede cambiar su estado.")
        if estado == ESTADO_CANCELADA and actual["adelanto_total"] > 0:
            raise ReservaError("Esta reserva tiene adelantos: cancélala con cancelar() para "
                               "decidir si se devuelven o se retienen.")
        if estado == ESTADO_RESERVADA:
            # Al reactivarla, el tramo no debe haberse ocupado mientras tanto.
            cruce = self._cruce(actual["fecha"], actual["hora_inicio"], actual["hora_fin"], reserva_id)
            if cruce:
                raise ReservaError(
                    f"No se puede reactivar: ese horario ya lo ocupa {cruce['cliente_nombre']}.")
        with self.db.transaction() as cur:
            cur.execute("UPDATE reservas SET estado = ? WHERE id = ?", (estado, reserva_id))

    # ------------------------------------------------------- Cobro ----
    def cobrar(self, reserva_id: int, usuario_id: int, metodo_pago_id: int | None,
               descuento: float = 0.0) -> dict:
        """Cobra la reserva: registra la venta (con el servicio, sus sub-servicios y productos),
        descuenta el stock de los productos, y le asigna el número de boleta.

        Solo se paga el SALDO: total - adelantos vigentes. Ese saldo es lo que entra a la caja
        si el método es efectivo (los adelantos en efectivo ya entraron cuando se recibieron).
        Devuelve la reserva actualizada."""
        reserva = self.obtener(reserva_id)
        if not reserva:
            raise ReservaError("La reserva ya no existe.")
        if reserva["estado"] == ESTADO_ATENDIDA:
            raise ReservaError("Esta reserva ya fue cobrada.")
        if reserva["estado"] == ESTADO_CANCELADA:
            raise ReservaError("No se puede cobrar una reserva cancelada.")

        subtotal = reserva["total_estimado"]
        descuento = round(float(descuento or 0), 2)
        if descuento < 0:
            raise ReservaError("El descuento no puede ser negativo.")
        if descuento > subtotal:
            raise ReservaError("El descuento no puede ser mayor que el total.")
        total = round(subtotal - descuento, 2)
        adelantos = reserva["adelanto_total"]
        saldo = round(total - adelantos, 2)
        if saldo < 0:
            raise ReservaError(
                f"Con ese descuento el total ({total:.2f}) queda por debajo de los adelantos "
                f"recibidos ({adelantos:.2f}). Baja el descuento o cancela y devuelve la diferencia.")

        conexion = self.db.get_connection()
        metodo_nombre = None
        pago_es_efectivo = False
        sesion_caja = None
        if saldo > 0:
            if not metodo_pago_id:
                raise ReservaError("Elige el método de pago del saldo.")
            fila = conexion.execute("SELECT nombre FROM metodos_pago WHERE id = ?", (metodo_pago_id,)).fetchone()
            metodo_nombre = fila["nombre"] if fila else None
            pago_es_efectivo = bool(self.venta_repo.metodo_pago_es_efectivo(metodo_pago_id))
            sesion_caja = self.caja_repo.obtener_sesion_abierta(usuario_id)
            if pago_es_efectivo and not sesion_caja:
                raise ReservaError("Abre la caja antes de cobrar en efectivo (menú Caja).")
        else:
            metodo_pago_id = None
            metodo_nombre = "Adelantos"

        # Stock de los productos del servicio (antes de tocar nada).
        for item in reserva["items"]:
            if item["tipo"] != "producto":
                continue
            producto = conexion.execute(
                "SELECT nombre, stock_actual FROM productos WHERE id = ?", (item["referencia_id"],)).fetchone()
            if not producto:
                raise ReservaError(f"El producto «{item['nombre']}» ya no existe.")
            if producto["stock_actual"] < item["cantidad"]:
                raise ReservaError(
                    f"Stock insuficiente de «{producto['nombre']}» (disponible: "
                    f"{producto['stock_actual']:g}, necesario: {item['cantidad']:g}). "
                    "Repón stock en Productos/Compras o quita el producto de la reserva.")

        # Si el cliente se borró después de reservar, la venta queda con su nombre escrito.
        cliente_id = reserva["cliente_id"]
        if cliente_id and not self.cliente_service.obtener_por_id(cliente_id):
            cliente_id = None

        with self.db.transaction() as cur:
            venta_id = self.venta_repo.crear_venta(
                cur, cliente_id, usuario_id, subtotal, descuento, total, metodo_pago_id,
                pago_es_efectivo, sesion_caja.id if sesion_caja else None,
                cliente_libre_nombre=None if cliente_id else reserva["cliente_nombre"],
            )
            # Servicio base
            self._linea_servicio(cur, venta_id, self._producto_del_servicio(cur, reserva),
                                 reserva["precio"])
            # Sub-servicios y productos
            for item in reserva["items"]:
                if item["tipo"] == "subservicio":
                    self._linea_servicio(cur, venta_id, self._producto_del_subservicio(cur, item),
                                         item["subtotal"])
                else:
                    self._linea_producto(cur, venta_id, item, usuario_id)

            cur.execute("SELECT COALESCE(MAX(numero_boleta), 0) + 1 AS siguiente FROM reservas")
            numero = cur.fetchone()["siguiente"]
            if pago_es_efectivo and sesion_caja and saldo > 0:
                self.caja_repo.registrar_movimiento(
                    cur, sesion_caja.id, "venta", saldo,
                    f"Boleta {numero_boleta_texto(numero)} - {reserva['servicio_nombre']}", venta_id,
                )
            cur.execute(
                """UPDATE reservas SET estado = 'atendida', descuento = ?, total = ?,
                       metodo_pago = ?, numero_boleta = ?, venta_id = ?, adelanto_aplicado = ?,
                       pagado_en = datetime('now', 'localtime')
                   WHERE id = ?""",
                (descuento, total, metodo_nombre, numero, venta_id, adelantos, reserva_id),
            )
        return self.obtener(reserva_id)

    def _linea_servicio(self, cur, venta_id: int, producto_id: int, importe: float) -> None:
        importe = round(float(importe), 2)
        self.venta_repo.crear_linea_detalle(
            cur, venta_id, producto_id, 1, importe, 0.0, importe,
            presentacion_nombre="Servicio", cantidad_presentacion=1, factor_unidades=1)

    def _linea_producto(self, cur, venta_id: int, item: dict, usuario_id: int) -> None:
        """Línea de un producto real: congela su costo, descuenta stock y deja el movimiento."""
        cur.execute("SELECT stock_actual, costo_promedio_actual FROM productos WHERE id = ?",
                    (item["referencia_id"],))
        fila = cur.fetchone()
        if fila["stock_actual"] < item["cantidad"]:
            raise ReservaError(f"Stock insuficiente de «{item['nombre']}».")
        self.venta_repo.crear_linea_detalle(
            cur, venta_id, item["referencia_id"], item["cantidad"], item["precio_unitario"],
            fila["costo_promedio_actual"], item["subtotal"])
        cur.execute("UPDATE productos SET stock_actual = ? WHERE id = ?",
                    (fila["stock_actual"] - item["cantidad"], item["referencia_id"]))
        self.inventario_repo.registrar_movimiento(
            cur, item["referencia_id"], "salida", item["cantidad"], "venta", venta_id, usuario_id)

    def _producto_del_servicio(self, cur, reserva: dict) -> int:
        """Producto oculto que representa el servicio de la reserva. Si el servicio ya no
        existe en el catálogo, se crea uno inactivo con el nombre que quedó en la reserva."""
        servicio_id = reserva.get("servicio_id")
        cur.execute("SELECT id FROM servicios WHERE id = ?", (servicio_id,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO servicios (nombre, precio, duracion_min, activo) VALUES (?, ?, 30, 0)",
                (reserva["servicio_nombre"], reserva["precio"]),
            )
            servicio_id = cur.lastrowid
        return self.servicio_service.asegurar_producto(cur, servicio_id)

    def _producto_del_subservicio(self, cur, item: dict) -> int:
        cur.execute("SELECT id FROM subservicios WHERE id = ?", (item["referencia_id"],))
        if cur.fetchone():
            return self.servicio_service.asegurar_producto_subservicio(cur, item["referencia_id"])
        cur.execute(
            """INSERT INTO productos (nombre, unidad_medida, precio_venta_actual, costo_promedio_actual,
                                      stock_actual, stock_minimo, activo)
               VALUES (?, 'servicio', ?, 0, 0, 0, 0)""", (item["nombre"], item["precio_unitario"]))
        return cur.lastrowid

    def resumen_pendientes(self) -> dict:
        """Reservas todavía por atender (estado 'reservada') y el dinero de adelantos que
        el negocio tiene recibido por ellas. Se usa para avisar antes de cambiar de modelo."""
        fila = self.db.get_connection().execute(
            """SELECT COUNT(*) AS cantidad,
                      COALESCE((SELECT SUM(p.monto) FROM reserva_pagos p
                                JOIN reservas r2 ON r2.id = p.reserva_id
                                WHERE r2.estado = ? AND p.estado = 'vigente'), 0) AS adelantos
               FROM reservas WHERE estado = ?""", (ESTADO_RESERVADA, ESTADO_RESERVADA)).fetchone()
        return {"cantidad": int(fila["cantidad"]), "adelantos": round(float(fila["adelantos"]), 2)}

    # ------------------------------------------------------ Boleta ----
    def registrar_envio(self, reserva_id: int, correo: str) -> None:
        with self.db.transaction() as cur:
            cur.execute("UPDATE reservas SET boleta_enviada_a = ? WHERE id = ?", (correo, reserva_id))

    @staticmethod
    def lineas_boleta(reserva: dict) -> list[dict]:
        """Líneas que se muestran en la boleta: el servicio base, cada sub-servicio y cada
        producto que se cobró aparte. Los productos incluidos en el precio no se listan."""
        lineas = [{"nombre": reserva["servicio_nombre"], "cantidad": 1,
                   "precio_unitario": float(reserva["precio"]), "subtotal": float(reserva["precio"])}]
        for item in reserva.get("items", []):
            if float(item["subtotal"]) > 0:
                lineas.append({"nombre": item["nombre"], "cantidad": item["cantidad"],
                               "precio_unitario": float(item["precio_unitario"]),
                               "subtotal": float(item["subtotal"])})
        return lineas

    @staticmethod
    def venta_para_ticket(reserva: dict, moneda: str = "S/") -> dict:
        """Arma el diccionario que entiende printing/ticket_template.py (el mismo de
        las ventas) a partir de una reserva cobrada."""
        lineas = ReservaService.lineas_boleta(reserva)
        subtotal = round(sum(l["subtotal"] for l in lineas), 2)
        total = float(reserva["total"] if reserva.get("total") is not None else subtotal)
        adelantos = float(reserva.get("adelanto_aplicado") or 0)
        lineas_pago = []
        if adelantos > 0:
            lineas_pago = [f"Adelantos: -{moneda} {adelantos:,.2f}",
                           f"Saldo pagado: {moneda} {total - adelantos:,.2f}"]
        return {
            "id": reserva["id"],
            "titulo_documento": "Boleta",
            "numero_documento": reserva["boleta_texto"],
            "fecha": (reserva.get("pagado_en") or "")[:16],
            "cliente_nombre": reserva["cliente_nombre"],
            "lineas_extra": [
                f"Cita: {fecha_dmy(parsear_fecha(reserva['fecha']))} "
                f"{reserva['hora_inicio']}-{reserva['hora_fin']}",
            ],
            "lineas": [{
                "producto_nombre": l["nombre"],
                "cantidad": l["cantidad"],
                "precio_venta_unitario": l["precio_unitario"],
                "subtotal": l["subtotal"],
                "factor_unidades": 1,
            } for l in lineas],
            "subtotal": subtotal,
            "descuento": float(reserva.get("descuento") or 0),
            "total": total,
            "lineas_pago": lineas_pago,
            "metodo_pago_nombre": reserva.get("metodo_pago"),
        }
