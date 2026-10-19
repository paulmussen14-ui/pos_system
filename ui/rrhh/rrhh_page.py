"""RRHH: trabajadores, adelantos/descuentos/bonificaciones y pagos de sueldo."""

from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout, QComboBox, QDoubleSpinBox,
    QCheckBox, QDateEdit, QMessageBox, QTabWidget, QMenu, QTimeEdit,
)

from services.rrhh_service import RrhhService, RrhhError
from services.caja_service import CajaService
from services.configuracion_service import ConfiguracionService
from ui.tokens import MARGEN_PAGINA, ESPACIO_MD
from ui.widgets.card import Card
from ui.widgets.page_header import PageHeader
from ui.widgets.status_badge import StatusBadge
from ui.widgets.tabla_erp import configurar_tabla_erp, item_derecha, item_centro, compactar_boton
from utils.validators import formatear_moneda

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
ETIQUETA_MOV = {"adelanto": "Adelanto", "descuento": "Descuento", "bonificacion": "Bonificación"}


def _tabla(columnas, stretch, derecha=(), centro=()) -> QTableWidget:
    t = QTableWidget(0, len(columnas))
    t.setHorizontalHeaderLabels(columnas)
    h = t.horizontalHeader()
    for c in range(len(columnas)):
        h.setSectionResizeMode(c, QHeaderView.Stretch if c == stretch else QHeaderView.ResizeToContents)
    configurar_tabla_erp(t, derecha=derecha, centro=centro, altura_fila=48)
    return t


class TrabajadorDialog(QDialog):

    def __init__(self, service: RrhhService, trabajador: dict | None = None, parent=None):
        super().__init__(parent)
        self.service = service
        self.trabajador = trabajador
        self.setWindowTitle("Editar trabajador" if trabajador else "Nuevo trabajador")
        self.resize(460, 480)
        v = QVBoxLayout(self)
        f = QFormLayout()
        t = trabajador or {}
        self.nombre = QLineEdit(t.get("nombre", ""))
        self.documento = QLineEdit(t.get("documento") or "")
        self.telefono = QLineEdit(t.get("telefono") or "")
        self.funcion = QLineEdit(t.get("funcion") or "")
        self.funcion.setPlaceholderText("Ej. Cajero, Repartidor, Almacenero")
        self.tipo = QComboBox()
        for clave, texto in (("mensual", "Mensual"), ("quincenal", "Quincenal"), ("semanal", "Semanal")):
            self.tipo.addItem(texto, clave)
        self.tipo.setCurrentIndex(max(self.tipo.findData(t.get("tipo_pago", "mensual")), 0))
        self.monto = QDoubleSpinBox()
        self.monto.setMaximum(9999999)
        self.monto.setPrefix("S/ ")
        self.monto.setValue(t.get("monto_base", 0) or 0)
        self.ingreso = QDateEdit(QDate.fromString(t["fecha_ingreso"][:10], "yyyy-MM-dd")
                                 if t.get("fecha_ingreso") else QDate.currentDate())
        self.ingreso.setCalendarPopup(True)
        self.ingreso.setDisplayFormat("yyyy-MM-dd")
        self.hora_entrada = QTimeEdit(QTime.fromString(t.get("hora_entrada") or "08:00", "HH:mm"))
        self.hora_salida = QTimeEdit(QTime.fromString(t.get("hora_salida") or "17:00", "HH:mm"))
        for h in (self.hora_entrada, self.hora_salida):
            h.setDisplayFormat("HH:mm")
        dias_marcados = set((t.get("dias_laborales") or "0,1,2,3,4,5").split(","))
        fila_dias = QHBoxLayout()
        self.chk_dias = []
        for n, nombre in enumerate(DIAS):
            c = QCheckBox(nombre)
            c.setChecked(str(n) in dias_marcados)
            self.chk_dias.append(c)
            fila_dias.addWidget(c)
        self.activo = QCheckBox("Trabajador activo")
        self.activo.setChecked(bool(t.get("activo", 1)))
        for etiqueta, w in (("Nombre", self.nombre), ("Documento", self.documento), ("Teléfono", self.telefono),
                            ("Función", self.funcion), ("Tipo de pago", self.tipo),
                            ("Sueldo por periodo", self.monto), ("Fecha de ingreso", self.ingreso),
                            ("Hora de entrada", self.hora_entrada), ("Hora de salida", self.hora_salida)):
            f.addRow(etiqueta, w)
        f.addRow("Días de trabajo", fila_dias)
        f.addRow("", self.activo)
        v.addLayout(f)
        fila = QHBoxLayout()
        fila.addStretch()
        c = QPushButton("Cancelar")
        c.setProperty("class", "secondary")
        c.clicked.connect(self.reject)
        g = QPushButton("Guardar")
        g.setProperty("class", "success")
        g.clicked.connect(self._guardar)
        fila.addWidget(c)
        fila.addWidget(g)
        v.addLayout(fila)

    def _guardar(self) -> None:
        try:
            self.service.guardar_trabajador({
                "nombre": self.nombre.text(), "documento": self.documento.text(),
                "telefono": self.telefono.text(), "funcion": self.funcion.text(),
                "tipo_pago": self.tipo.currentData(), "monto_base": self.monto.value(),
                "fecha_ingreso": self.ingreso.date().toString("yyyy-MM-dd"),
                "activo": self.activo.isChecked(),
                "hora_entrada": self.hora_entrada.time().toString("HH:mm"),
                "hora_salida": self.hora_salida.time().toString("HH:mm"),
                "dias_laborales": ",".join(str(n) for n, c in enumerate(self.chk_dias) if c.isChecked()),
            }, self.trabajador["id"] if self.trabajador else None)
        except RrhhError as e:
            QMessageBox.warning(self, "No se pudo guardar", str(e))
            return
        self.accept()


class MovimientoDialog(QDialog):

    def __init__(self, service: RrhhService, trabajador: dict, tipo: str, parent=None):
        super().__init__(parent)
        self.service, self.trabajador, self.tipo = service, trabajador, tipo
        self.setWindowTitle(f"{ETIQUETA_MOV[tipo]} — {trabajador['nombre']}")
        self.resize(360, 200)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.monto = QDoubleSpinBox()
        self.monto.setMaximum(9999999)
        self.monto.setPrefix("S/ ")
        self.motivo = QLineEdit()
        self.motivo.setPlaceholderText("Motivo (opcional)")
        f.addRow("Monto", self.monto)
        f.addRow("Motivo", self.motivo)
        v.addLayout(f)
        ayuda = QLabel({"adelanto": "Se restará del próximo pago.",
                        "descuento": "Se restará del próximo pago (faltas, tardanzas, etc.).",
                        "bonificacion": "Se sumará al próximo pago."}[tipo])
        ayuda.setProperty("class", "ayuda")
        v.addWidget(ayuda)
        fila = QHBoxLayout()
        fila.addStretch()
        c = QPushButton("Cancelar")
        c.setProperty("class", "secondary")
        c.clicked.connect(self.reject)
        g = QPushButton("Registrar")
        g.setProperty("class", "success")
        g.clicked.connect(self._guardar)
        fila.addWidget(c)
        fila.addWidget(g)
        v.addLayout(fila)

    def _guardar(self) -> None:
        try:
            self.service.registrar_movimiento(self.trabajador["id"], self.tipo, self.monto.value(),
                                              self.motivo.text())
        except RrhhError as e:
            QMessageBox.warning(self, "No se pudo registrar", str(e))
            return
        self.accept()


class RrhhPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.service = RrhhService()
        self.caja_service = CajaService()
        self.config_service = ConfiguracionService()
        self._trabajadores: list[dict] = []
        self._movs: list[dict] = []
        self._construir_ui()
        self.actualizar()

    # ------------------------------------------------------------ UI ----
    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA)
        raiz.setSpacing(ESPACIO_MD)
        cab = PageHeader("RRHH", "Trabajadores, adelantos, descuentos, bonificaciones y pagos")
        btn_nuevo = QPushButton("+  Agregar trabajador")
        btn_nuevo.setProperty("class", "success")
        btn_nuevo.clicked.connect(self._nuevo_trabajador)
        cab.agregar_accion(btn_nuevo)
        raiz.addWidget(cab)

        self.pestanas = QTabWidget()
        raiz.addWidget(self.pestanas, 1)

        # Trabajadores
        t1 = Card()
        self.tabla_trab = _tabla(["Nombre", "Función", "Pago", "Sueldo", "Bonif.", "Desc.", "Adelantos",
                                  "A pagar", "Estado", ""], 0, derecha=(3, 4, 5, 6, 7), centro=(2, 8))
        self.tabla_trab.horizontalHeader().setSectionResizeMode(8, QHeaderView.Fixed)
        self.tabla_trab.setColumnWidth(8, 100)
        self.tabla_trab.horizontalHeader().setSectionResizeMode(9, QHeaderView.Fixed)
        self.tabla_trab.setColumnWidth(9, 190)
        t1.cuerpo.addWidget(self.tabla_trab, 1)
        self.label_vacio = QLabel("Aún no hay trabajadores. Agrega el primero con «Agregar trabajador».")
        self.label_vacio.setProperty("class", "ayuda")
        self.label_vacio.setAlignment(Qt.AlignCenter)
        t1.cuerpo.addWidget(self.label_vacio)
        self.pestanas.addTab(t1, "Trabajadores")

        # Movimientos
        t2 = Card()
        self.tabla_mov = _tabla(["Fecha", "Trabajador", "Tipo", "Monto", "Motivo", "Estado", ""], 4,
                                derecha=(3,), centro=(2, 5))
        self.tabla_mov.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.tabla_mov.setColumnWidth(2, 120)
        self.tabla_mov.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.tabla_mov.setColumnWidth(5, 110)
        self.tabla_mov.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.tabla_mov.setColumnWidth(6, 90)
        t2.cuerpo.addWidget(self.tabla_mov, 1)
        self.pestanas.addTab(t2, "Adelantos y descuentos")

        # Asistencia
        t4 = Card()
        t4.set_titulo("Hoy")
        self.tabla_hoy = _tabla(["Trabajador", "Horario", "Entrada", "Salida", "Tardanza", ""], 0, centro=(1, 2, 3, 4))
        for c, w in ((1, 130), (2, 90), (3, 90), (4, 110), (5, 270)):
            self.tabla_hoy.horizontalHeader().setSectionResizeMode(c, QHeaderView.Fixed)
            self.tabla_hoy.setColumnWidth(c, w)
        self.tabla_hoy.setMaximumHeight(260)
        t4.cuerpo.addWidget(self.tabla_hoy)
        titulo_hist = QLabel("Historial")
        titulo_hist.setObjectName("cardHeading")
        t4.cuerpo.addWidget(titulo_hist)
        self.tabla_asist = _tabla(["Fecha", "Trabajador", "Entrada", "Salida", "Horas", "Tardanza"], 1,
                                  centro=(2, 3, 4, 5))
        t4.cuerpo.addWidget(self.tabla_asist, 1)
        self.pestanas.addTab(t4, "Asistencia")

        # Pagos
        t3 = Card()
        self.tabla_pagos = _tabla(["Fecha", "Trabajador", "Base", "Bonif.", "Desc.", "Adelantos", "Neto pagado",
                                   "Caja"], 1, derecha=(2, 3, 4, 5, 6), centro=(7,))
        t3.cuerpo.addWidget(self.tabla_pagos, 1)
        self.pestanas.addTab(t3, "Pagos realizados")

    def _moneda(self) -> str:
        return self.config_service.obtener().get("moneda", "S/")

    def _boton(self, texto, fn, clase="secondary") -> QPushButton:
        b = QPushButton(texto)
        b.setProperty("class", clase)
        compactar_boton(b)
        b.clicked.connect(fn)
        return b

    # -------------------------------------------------------- Datos ----
    def actualizar(self) -> None:
        m = self._moneda()
        self._trabajadores = self.service.listar_trabajadores()
        for tabla in (self.tabla_trab, self.tabla_mov, self.tabla_pagos, self.tabla_hoy, self.tabla_asist):
            tabla.clearContents()
        self.label_vacio.setVisible(not self._trabajadores)
        self.tabla_trab.setRowCount(len(self._trabajadores))
        for i, t in enumerate(self._trabajadores):
            neto = t["monto_base"] + t["bonos_pend"] - t["descuentos_pend"] - t["adelantos_pend"]
            vals = [t["nombre"], t["funcion"] or "—"]
            self.tabla_trab.setItem(i, 0, QTableWidgetItem(vals[0]))
            self.tabla_trab.setItem(i, 1, QTableWidgetItem(vals[1]))
            self.tabla_trab.setItem(i, 2, item_centro(t["tipo_pago"].capitalize()))
            for col, v in ((3, t["monto_base"]), (4, t["bonos_pend"]), (5, t["descuentos_pend"]),
                           (6, t["adelantos_pend"]), (7, neto)):
                self.tabla_trab.setItem(i, col, item_derecha(formatear_moneda(v, m)))
            self.tabla_trab.setCellWidget(i, 8, StatusBadge("Activo" if t["activo"] else "Inactivo",
                                                            "ok" if t["activo"] else "neutral"))
            acc = QWidget()
            f = QHBoxLayout(acc)
            f.setContentsMargins(4, 4, 4, 4)
            f.setSpacing(6)
            if t["activo"]:
                f.addWidget(self._boton("Pagar", lambda _, tt=t: self._pagar(tt), "success"))
            mas = QPushButton("Más")
            mas.setProperty("class", "secondary")
            compactar_boton(mas, 80)
            menu = QMenu(mas)
            if t["activo"]:
                menu.addAction("Registrar adelanto", lambda tt=t: self._mov(tt, "adelanto"))
                menu.addAction("Registrar descuento", lambda tt=t: self._mov(tt, "descuento"))
                menu.addAction("Registrar bonificación", lambda tt=t: self._mov(tt, "bonificacion"))
                menu.addSeparator()
            menu.addAction("Editar trabajador", lambda tt=t: self._editar(tt))
            mas.setMenu(menu)
            f.addWidget(mas)
            self.tabla_trab.setCellWidget(i, 9, acc)

        self._movs = self.service.listar_movimientos()
        self.tabla_mov.setRowCount(len(self._movs))
        tonos = {"adelanto": "warning", "descuento": "danger", "bonificacion": "ok"}
        for i, mv in enumerate(self._movs):
            self.tabla_mov.setItem(i, 0, QTableWidgetItem(mv["fecha"][:16]))
            self.tabla_mov.setItem(i, 1, QTableWidgetItem(mv["trabajador"]))
            self.tabla_mov.setCellWidget(i, 2, StatusBadge(ETIQUETA_MOV[mv["tipo"]], tonos[mv["tipo"]]))
            self.tabla_mov.setItem(i, 3, item_derecha(formatear_moneda(mv["monto"], m)))
            self.tabla_mov.setItem(i, 4, QTableWidgetItem(mv["motivo"] or ""))
            self.tabla_mov.setCellWidget(i, 5, StatusBadge("Pendiente" if not mv["pago_id"] else "Liquidado",
                                                           "info" if not mv["pago_id"] else "neutral"))
            if not mv["pago_id"]:
                self.tabla_mov.setCellWidget(i, 6, self._boton("Anular", lambda _, x=mv: self._anular_mov(x)))
            else:
                self.tabla_mov.removeCellWidget(i, 6)

        self._pintar_asistencia()

        pagos = self.service.listar_pagos()
        self.tabla_pagos.setRowCount(len(pagos))
        for i, p in enumerate(pagos):
            self.tabla_pagos.setItem(i, 0, QTableWidgetItem(p["fecha"][:16]))
            self.tabla_pagos.setItem(i, 1, QTableWidgetItem(p["trabajador"]))
            for col, k in ((2, "base"), (3, "bonificaciones"), (4, "descuentos"), (5, "adelantos"), (6, "neto")):
                self.tabla_pagos.setItem(i, col, item_derecha(formatear_moneda(p[k], m)))
            self.tabla_pagos.setItem(i, 7, item_centro("Egreso" if p["caja_sesion_id"] and p["neto"] > 0 else "—"))

    def _pintar_asistencia(self) -> None:
        hoy = self.service.asistencia_hoy()
        activos = [t for t in self._trabajadores if t["activo"]]
        self.tabla_hoy.setRowCount(len(activos))
        for i, t in enumerate(activos):
            a = hoy.get(t["id"])
            horario = (f"{t['hora_entrada']} – {t['hora_salida']}" if t.get("hora_entrada") else "—")
            self.tabla_hoy.setItem(i, 0, QTableWidgetItem(t["nombre"]))
            self.tabla_hoy.setItem(i, 1, item_centro(horario))
            self.tabla_hoy.setItem(i, 2, item_centro(a["entrada"] if a and a["entrada"] else "—"))
            self.tabla_hoy.setItem(i, 3, item_centro(a["salida"] if a and a["salida"] else "—"))
            if a and a["minutos_tarde"]:
                self.tabla_hoy.setCellWidget(i, 4, StatusBadge(f"{a['minutos_tarde']} min", "warning"))
            elif a:
                self.tabla_hoy.setCellWidget(i, 4, StatusBadge("Puntual", "ok"))
            acc = QWidget()
            f = QHBoxLayout(acc)
            f.setContentsMargins(4, 4, 4, 4)
            f.setSpacing(6)
            if not a:
                f.addWidget(self._boton("Marcar entrada", lambda _, tt=t: self._marcar(tt, True), "success"))
            elif not a["salida"]:
                f.addWidget(self._boton("Marcar salida", lambda _, tt=t: self._marcar(tt, False), "success"))
            else:
                f.addWidget(QLabel("Jornada completa"))
            self.tabla_hoy.setCellWidget(i, 5, acc)

        filas = self.service.listar_asistencia()
        self.tabla_asist.setRowCount(len(filas))
        for i, r in enumerate(filas):
            self.tabla_asist.setItem(i, 0, QTableWidgetItem(r["fecha"]))
            self.tabla_asist.setItem(i, 1, QTableWidgetItem(r["trabajador"]))
            self.tabla_asist.setItem(i, 2, item_centro(r["entrada"] or "—"))
            self.tabla_asist.setItem(i, 3, item_centro(r["salida"] or "—"))
            self.tabla_asist.setItem(i, 4, item_centro(r["horas"] or "—"))
            self.tabla_asist.setItem(i, 5, item_centro(f"{r['minutos_tarde']} min" if r["minutos_tarde"] else "—"))

    def _marcar(self, t: dict, entrada: bool) -> None:
        try:
            if entrada:
                self.service.marcar_entrada(t["id"])
            else:
                self.service.marcar_salida(t["id"])
        except RrhhError as e:
            QMessageBox.warning(self, "Asistencia", str(e))
        self.actualizar()

    # ------------------------------------------------------ Acciones ----
    def _nuevo_trabajador(self) -> None:
        if TrabajadorDialog(self.service, None, self).exec() == QDialog.Accepted:
            self.actualizar()

    def _editar(self, t: dict) -> None:
        if TrabajadorDialog(self.service, t, self).exec() == QDialog.Accepted:
            self.actualizar()

    def _mov(self, t: dict, tipo: str) -> None:
        if MovimientoDialog(self.service, t, tipo, self).exec() == QDialog.Accepted:
            self.actualizar()

    def _anular_mov(self, mv: dict) -> None:
        if QMessageBox.question(self, "Anular movimiento", "¿Anular este movimiento?") != QMessageBox.Yes:
            return
        try:
            self.service.anular_movimiento(mv["id"])
        except RrhhError as e:
            QMessageBox.warning(self, "No se pudo anular", str(e))
        self.actualizar()

    def _pagar(self, t: dict) -> None:
        m = self._moneda()
        try:
            c = self.service.calcular_pago(t["id"])
        except RrhhError as e:
            QMessageBox.warning(self, "Pago", str(e))
            return
        caja_abierta = bool(self.caja_service.estado_actual(self.usuario.id).get("abierta"))
        aviso = ("El pago saldrá de la caja abierta como egreso." if caja_abierta
                 else "La caja está cerrada: el pago quedará registrado pero NO saldrá de la caja.")
        if QMessageBox.question(
            self, f"Pagar a {t['nombre']}",
            f"Pago {c['tipo_pago']}\n\n"
            f"Sueldo base:      {formatear_moneda(c['base'], m)}\n"
            f"+ Bonificaciones: {formatear_moneda(c['bonificaciones'], m)}\n"
            f"− Descuentos:     {formatear_moneda(c['descuentos'], m)}\n"
            f"− Adelantos:      {formatear_moneda(c['adelantos'], m)}\n"
            f"────────────────────\n"
            f"NETO A PAGAR:     {formatear_moneda(c['neto'], m)}\n\n{aviso}\n\n¿Registrar el pago?"
        ) != QMessageBox.Yes:
            return
        try:
            self.service.registrar_pago(t["id"], self.usuario.id)
        except RrhhError as e:
            QMessageBox.warning(self, "No se pudo registrar el pago", str(e))
            return
        self.actualizar()
        self.pestanas.setCurrentIndex(2)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.actualizar()
