"""Agenda semanal: pantalla propia (menú «Agenda») de los negocios que trabajan con reservas.

Columnas = días de la semana, filas = horas. Un clic en una hora libre abre «Nueva
reserva»; un clic en una reserva abre su detalle (cobrar, boleta, editar, cancelar).
Los colores salen de la paleta del tema, igual que el resto de la app.
"""

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QRect, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QStyledItemDelegate, QStyle, QMessageBox, QDialog,
)

from services.configuracion_service import ConfiguracionService
from services.reserva_service import (
    ReservaService, ESTADO_RESERVADA, ESTADO_ATENDIDA, ESTADO_NO_ASISTIO,
)
from services.servicio_service import ServicioService
from ui.reservas.reserva_dialogs import ReservaDialog, DetalleReservaDialog
from ui.tokens import MARGEN_PAGINA, ESPACIO_MD, ESPACIO_SM, paleta
from ui.widgets.card import Card
from ui.widgets.page_header import PageHeader
from ui.widgets.status_badge import StatusBadge
from utils.fechas import (
    DIAS_CORTOS, a_hhmm, a_minutos, lunes_de, parsear_fecha, rango_semana,
)
from utils.validators import formatear_moneda

_INTERVALO_REFRESCO_MS = 60_000
_ALTO_FILA = {15: 30, 20: 34, 30: 44, 45: 56, 60: 60}

_ROL_DATOS = Qt.UserRole          # ("libre", "YYYY-MM-DD", "HH:MM") | ("reserva", id)
_ROL_ESTILO = Qt.UserRole + 1     # dict con colores y textos de la tarjeta de reserva


def _mezclar(a: str, b: str, peso_b: float) -> QColor:
    """Mezcla dos colores hex: peso_b = 0 devuelve `a`, 1 devuelve `b`."""
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * peso_b),
        round(ca.green() + (cb.green() - ca.green()) * peso_b),
        round(ca.blue() + (cb.blue() - ca.blue()) * peso_b),
    )


class _TarjetaReservaDelegate(QStyledItemDelegate):
    """Dibuja cada reserva como una tarjeta con barra de color a la izquierda, ocupando
    todas las filas que dura. Las celdas libres se pintan con el estilo normal."""

    def paint(self, pintor: QPainter, opcion, indice) -> None:
        estilo = indice.data(_ROL_ESTILO)
        if not estilo:
            super().paint(pintor, opcion, indice)
            return

        pintor.save()
        pintor.setRenderHint(QPainter.Antialiasing, True)
        pintor.fillRect(opcion.rect, QColor(estilo["fondo_celda"]))

        caja = QRectF(opcion.rect).adjusted(3, 3, -3, -3)
        ruta = QPainterPath()
        ruta.addRoundedRect(caja, 6, 6)
        pintor.fillPath(ruta, QColor(estilo["fondo"]))
        pintor.setClipPath(ruta)
        pintor.fillRect(QRectF(caja.left(), caja.top(), 4, caja.height()), QColor(estilo["acento"]))
        if opcion.state & QStyle.State_MouseOver:
            pintor.fillPath(ruta, QColor(255, 255, 255, 40))

        area = QRect(int(caja.left()) + 12, int(caja.top()) + 4,
                     int(caja.width()) - 18, int(caja.height()) - 8)
        fuente = QFont(opcion.font)
        fuente.setPixelSize(12)
        negrita = QFont(fuente)
        negrita.setBold(True)

        y = area.top()
        for texto, tipografia, color in (
            (estilo["titulo"], negrita, estilo["texto"]),
            (estilo["subtitulo"], fuente, estilo["texto_suave"]),
            (estilo["detalle"], fuente, estilo["texto_suave"]),
        ):
            if not texto:
                continue
            metricas = QFontMetrics(tipografia)
            if y + metricas.height() > area.bottom() + 2:
                break  # no caben más líneas en esta tarjeta
            pintor.setFont(tipografia)
            pintor.setPen(QColor(color))
            pintor.drawText(QRect(area.left(), y, area.width(), metricas.height()),
                            Qt.AlignLeft | Qt.AlignVCenter,
                            metricas.elidedText(texto, Qt.ElideRight, area.width()))
            y += metricas.height() + 1
        pintor.restore()


class AgendaPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.reserva_service = ReservaService()
        self.servicio_service = ServicioService()
        self.config_service = ConfiguracionService()
        self.navegar = None  # la ventana principal asigna navegar(nombre_pagina)
        self._lunes = lunes_de(date.today())
        self._ya_desplazado = False
        self._construir_ui()
        self.actualizar()

        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVALO_REFRESCO_MS)
        self._timer.timeout.connect(lambda: self.isVisible() and self.actualizar())
        self._timer.start()

    # ------------------------------------------------------ Interfaz ----
    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA)
        raiz.setSpacing(ESPACIO_MD)

        self.cabecera = PageHeader("Agenda de reservas", "")
        self.btn_anterior = QPushButton("‹  Anterior")
        self.btn_hoy = QPushButton("Hoy")
        self.btn_siguiente = QPushButton("Siguiente  ›")
        for boton, funcion in ((self.btn_anterior, lambda: self._mover_semana(-1)),
                               (self.btn_hoy, self._ir_a_hoy),
                               (self.btn_siguiente, lambda: self._mover_semana(1))):
            boton.setProperty("class", "secondary")
            boton.clicked.connect(funcion)
            self.cabecera.agregar_accion(boton)
        self.btn_nueva = QPushButton("+  Nueva reserva")
        self.btn_nueva.setProperty("class", "success")
        self.btn_nueva.clicked.connect(lambda: self.nueva_reserva())
        self.cabecera.agregar_accion(self.btn_nueva)
        raiz.addWidget(self.cabecera)

        # Resumen del día + leyenda de colores
        fila_resumen = QHBoxLayout()
        fila_resumen.setSpacing(ESPACIO_SM)
        self.badge_reservas = StatusBadge("", "info")
        self.badge_pendientes = StatusBadge("", "warning")
        self.badge_cobrado = StatusBadge("", "ok")
        for badge in (self.badge_reservas, self.badge_pendientes, self.badge_cobrado):
            fila_resumen.addWidget(badge)
        fila_resumen.addStretch()
        leyenda = QLabel("Clic en una hora libre para reservar · clic en una reserva para cobrar o ver su boleta")
        leyenda.setProperty("class", "ayuda")
        fila_resumen.addWidget(leyenda)
        raiz.addLayout(fila_resumen)

        tarjeta = Card("", margen=ESPACIO_SM)
        self.tabla = QTableWidget(0, 0)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabla.setFocusPolicy(Qt.NoFocus)
        self.tabla.setShowGrid(True)
        self.tabla.setAlternatingRowColors(False)
        self.tabla.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tabla.setMouseTracking(True)
        self.tabla.viewport().setCursor(Qt.PointingHandCursor)
        self.tabla.verticalHeader().setFixedWidth(64)
        self.tabla.verticalHeader().setDefaultAlignment(Qt.AlignRight | Qt.AlignTop)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabla.horizontalHeader().setHighlightSections(False)
        self.tabla.verticalHeader().setHighlightSections(False)
        self.tabla.setItemDelegate(_TarjetaReservaDelegate(self.tabla))
        self.tabla.cellClicked.connect(self._on_celda)
        tarjeta.cuerpo.addWidget(self.tabla, 1)
        raiz.addWidget(tarjeta, 1)

    # ---------------------------------------------------- Navegación ----
    def _mover_semana(self, delta: int) -> None:
        self._lunes += timedelta(days=7 * delta)
        self._ya_desplazado = False
        self.actualizar()

    def _ir_a_hoy(self) -> None:
        self._lunes = lunes_de(date.today())
        self._ya_desplazado = False
        self.actualizar()

    # ------------------------------------------------------- Pintado ----
    def actualizar(self) -> None:
        config = self.config_service.obtener()
        moneda = config.get("moneda", "S/")
        colores = paleta("oscuro" if config.get("tema") == "oscuro" else "claro")
        agenda = self.config_service.obtener_agenda()
        paso = agenda["intervalo_min"]
        apertura, cierre = a_minutos(agenda["hora_inicio"]), a_minutos(agenda["hora_fin"])

        reservas = self.reserva_service.listar_semana(self._lunes)

        # Días visibles: los de atención + cualquier día que ya tenga reservas.
        con_reservas = {parsear_fecha(r["fecha"]).weekday() for r in reservas}
        dias = [d for d in range(7) if d in agenda["dias"] or d in con_reservas]
        if not dias:
            dias = list(range(7))

        # Filas: el horario de atención, ampliado si hay reservas fuera de él.
        inicio_grid, fin_grid = apertura, cierre
        for r in reservas:
            inicio_grid = min(inicio_grid, (a_minutos(r["hora_inicio"]) // paso) * paso)
            fin_grid = max(fin_grid, -(-a_minutos(r["hora_fin"]) // paso) * paso)
        n_filas = max(1, (fin_grid - inicio_grid) // paso)

        hoy = date.today()
        ahora_min = datetime.now().hour * 60 + datetime.now().minute
        fechas = {d: self._lunes + timedelta(days=d) for d in dias}

        self.cabecera.set_subtitulo(f"Semana del {rango_semana(self._lunes)}")
        self.btn_hoy.setEnabled(self._lunes != lunes_de(hoy))

        tabla = self.tabla
        tabla.setUpdatesEnabled(False)
        tabla.clearSpans()
        tabla.clear()
        tabla.setRowCount(n_filas)
        tabla.setColumnCount(len(dias))
        tabla.setStyleSheet(
            f"QTableWidget {{ gridline-color: {colores['borde']}; background: {colores['superficie']}; }}")
        tabla.verticalHeader().setDefaultSectionSize(_ALTO_FILA.get(paso, 44))

        tabla.setHorizontalHeaderLabels([
            (f"Hoy · {DIAS_CORTOS[d]} {fechas[d].day}" if fechas[d] == hoy
             else f"{DIAS_CORTOS[d]} {fechas[d].day}") for d in dias
        ])
        tabla.setVerticalHeaderLabels([a_hhmm(inicio_grid + i * paso) for i in range(n_filas)])

        # Celdas libres (con tinte para hoy y apagadas si ya pasaron).
        for fila in range(n_filas):
            minutos = inicio_grid + fila * paso
            for col, d in enumerate(dias):
                fecha = fechas[d]
                pasado = fecha < hoy or (fecha == hoy and minutos + paso <= ahora_min)
                fuera = not (apertura <= minutos < cierre) or d not in agenda["dias"]
                if fuera:
                    fondo = colores["superficie_alt"]
                elif pasado:
                    fondo = colores["fondo"]
                elif fecha == hoy:
                    fondo = _mezclar(colores["superficie"], colores["primario_suave"], 0.35).name()
                else:
                    fondo = colores["superficie"]
                item = QTableWidgetItem("")
                item.setBackground(QBrush(QColor(fondo)))
                item.setData(_ROL_DATOS, ("libre", fecha.isoformat(), a_hhmm(minutos)))
                item.setToolTip(f"Reservar {DIAS_CORTOS[d]} {fecha.day} a las {a_hhmm(minutos)}")
                tabla.setItem(fila, col, item)

        # Tarjetas de reserva (cada una ocupa las filas que dura).
        ocupadas: set[tuple[int, int]] = set()
        for r in reservas:
            d = parsear_fecha(r["fecha"]).weekday()
            if d not in fechas:
                continue
            col = dias.index(d)
            fila_ini = (a_minutos(r["hora_inicio"]) - inicio_grid) // paso
            fila_fin = -(-(a_minutos(r["hora_fin"]) - inicio_grid) // paso)
            filas = range(max(0, fila_ini), min(n_filas, max(fila_fin, fila_ini + 1)))
            if not filas or any((f, col) in ocupadas for f in filas):
                continue  # reservas montadas por un cambio de intervalo: se ignora la segunda
            ocupadas.update((f, col) for f in filas)

            fila = filas[0]
            item = tabla.item(fila, col)
            fondo_celda = item.background().color().name()
            item.setData(_ROL_DATOS, ("reserva", r["id"]))
            item.setData(_ROL_ESTILO, self._estilo_reserva(r, colores, moneda, fondo_celda, len(filas)))
            item.setToolTip(self._tooltip_reserva(r, moneda))
            if len(filas) > 1:
                tabla.setSpan(fila, col, len(filas), 1)

        tabla.setUpdatesEnabled(True)
        self._pintar_resumen(moneda)
        if not self._ya_desplazado:
            self._ya_desplazado = True
            self._desplazar_a_hora_actual(inicio_grid, paso, n_filas)

    @staticmethod
    def _estilo_reserva(r: dict, colores: dict, moneda: str, fondo_celda: str, filas: int) -> dict:
        familia = {
            ESTADO_RESERVADA: "info",
            ESTADO_ATENDIDA: "exito",
            ESTADO_NO_ASISTIO: "aviso",
        }.get(r["estado"], "info")
        if r["estado"] == ESTADO_ATENDIDA:
            detalle = f"✓ {r['boleta_texto']} · {formatear_moneda(r['total'], moneda)}"
        elif r["estado"] == ESTADO_NO_ASISTIO:
            detalle = "No asistió"
        else:
            detalle = f"{r['hora_inicio']} – {r['hora_fin']}"
            if r.get("adelanto_total"):
                detalle += f" · Adelanto {formatear_moneda(r['adelanto_total'], moneda)}"
        return {
            "fondo_celda": fondo_celda,
            "fondo": colores[f"{familia}_suave"],
            "acento": colores[familia],
            "texto": colores[f"{familia}_texto"],
            "texto_suave": colores[f"{familia}_texto"],
            "titulo": r["cliente_nombre"],
            "subtitulo": r["servicio_nombre"],
            "detalle": detalle,
        }

    @staticmethod
    def _tooltip_reserva(r: dict, moneda: str) -> str:
        lineas = [f"{r['cliente_nombre']} — {r['servicio_nombre']}",
                  f"{r['hora_inicio']} a {r['hora_fin']} · {formatear_moneda(r['total_estimado'], moneda)}"]
        if r.get("notas"):
            lineas.append(f"Notas: {r['notas']}")
        if r.get("adelanto_total"):
            lineas.append(f"Adelanto recibido: {formatear_moneda(r['adelanto_total'], moneda)}")
        if r["estado"] == ESTADO_ATENDIDA:
            lineas.append(f"Boleta {r['boleta_texto']}")
        return "\n".join(lineas)

    def _pintar_resumen(self, moneda: str) -> None:
        resumen = self.reserva_service.resumen_del_dia(date.today())
        self.badge_reservas.setText(f"Hoy: {resumen['total']} reserva(s)")
        self.badge_pendientes.setText(f"{resumen['pendientes']} por cobrar")
        self.badge_cobrado.setText(f"Cobrado hoy: {formatear_moneda(resumen['cobrado'], moneda)}")
        for badge in (self.badge_reservas, self.badge_pendientes, self.badge_cobrado):
            badge.style().unpolish(badge)
            badge.style().polish(badge)

    def _desplazar_a_hora_actual(self, inicio_grid: int, paso: int, n_filas: int) -> None:
        """Al abrir la semana de hoy, deja visible la hora actual (una fila de margen)."""
        if self._lunes != lunes_de(date.today()):
            self.tabla.scrollToTop()
            return
        ahora = datetime.now().hour * 60 + datetime.now().minute
        fila = min(max((ahora - inicio_grid) // paso - 1, 0), n_filas - 1)
        # Se busca la celda al momento de desplazar: la tabla pudo repintarse en el medio.
        def desplazar() -> None:
            item = self.tabla.item(fila, 0)
            if item is not None:
                self.tabla.scrollToItem(item, QAbstractItemView.PositionAtTop)
        QTimer.singleShot(0, desplazar)

    # ---------------------------------------------------- Interacción ----
    def _on_celda(self, fila: int, col: int) -> None:
        item = self.tabla.item(fila, col)
        datos = item.data(_ROL_DATOS) if item else None
        if not datos:
            return
        if datos[0] == "reserva":
            dialogo = DetalleReservaDialog(datos[1], self.usuario, self)
            dialogo.exec()
            if dialogo.cambio:
                self.actualizar()
        else:
            self.nueva_reserva(parsear_fecha(datos[1]), datos[2])

    def nueva_reserva(self, fecha: date | None = None, hora: str | None = None) -> None:
        """Abre el formulario de reserva. Sin parámetros propone hoy y la próxima hora libre."""
        if not self.servicio_service.listar(solo_activos=True):
            respuesta = QMessageBox.question(
                self, "Primero crea un servicio",
                "Para reservar una hora necesitas al menos un servicio (con su precio y duración).\n\n"
                "¿Quieres ir a «Servicios» ahora?")
            if respuesta == QMessageBox.Yes and callable(self.navegar):
                self.navegar("Servicios")
            return

        agenda = self.config_service.obtener_agenda()
        if fecha is None:
            fecha = date.today()
        if hora is None:
            paso = agenda["intervalo_min"]
            apertura = a_minutos(agenda["hora_inicio"])
            ahora = datetime.now().hour * 60 + datetime.now().minute
            if fecha == date.today() and ahora > apertura:
                apertura = -(-ahora // paso) * paso
            hora = a_hhmm(min(apertura, a_minutos(agenda["hora_fin"]) - paso))

        dialogo = ReservaDialog(fecha, hora, usuario=self.usuario, parent=self)
        if dialogo.exec() == QDialog.Accepted:
            # Muestra la semana de la reserva recién creada.
            nueva = self.reserva_service.obtener(dialogo.reserva_id)
            if nueva:
                self._lunes = lunes_de(parsear_fecha(nueva["fecha"]))
            self.actualizar()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self.actualizar()
