"""Página de Inicio / Dashboard: resumen del día.

Muestra solo ventas del día, utilidad bruta del día y estado de caja.
Se refresca sola cada 60 s (si la pantalla está visible) y al cambiar
de fecha, para que nunca muestre datos de ayer.
"""

from datetime import date

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Qt, QThreadPool, QTimer

from services.reporte_service import ReporteService
from services.configuracion_service import ConfiguracionService
from ui.widgets.metric_card import MetricCard
from ui.widgets.line_chart import LineChartWidget
from ui.widgets.donut_chart import DonutChartWidget
from ui.widgets.bar_chart import BarChartWidget
from utils.validators import formatear_moneda
from utils.worker import Worker

_MESES_CORTO = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]

_INTERVALO_REFRESCO_MS = 60_000  # 1 minuto


class DashboardPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.reporte_service = ReporteService()
        self.config_service = ConfiguracionService()
        self._req_id = 0  # descarta resultados de una carga anterior si se refresca de nuevo antes de que termine
        self._fecha_actual = date.today()
        self._construir_ui()
        self.actualizar()

        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVALO_REFRESCO_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _construir_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")

        contenido = QWidget()
        layout = QVBoxLayout(contenido)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        titulo = QLabel("Inicio")
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        layout.addWidget(titulo)

        self.label_fecha = QLabel(f"Hoy: {self._fecha_actual.strftime('%d/%m/%Y')}")
        self.label_fecha.setStyleSheet("font-size: 14px; font-weight: 600; color: #6b7280;")
        layout.addWidget(self.label_fecha)

        # Métricas del día (se reinician solas cada día, sin depender del cierre de caja)
        fila_metricas = QHBoxLayout()
        fila_metricas.setSpacing(16)
        self.card_ventas = MetricCard("Ventas del día", formatear_moneda(0))
        self.card_utilidad = MetricCard("Utilidad bruta del día", formatear_moneda(0))
        self.card_caja = MetricCard("Estado de caja", "Cerrada")
        for card in (self.card_ventas, self.card_utilidad, self.card_caja):
            fila_metricas.addWidget(card)
        layout.addLayout(fila_metricas)

        # Fila de alertas de stock
        fila_alertas = QHBoxLayout()
        fila_alertas.setSpacing(16)
        self.label_stock_bajo = QLabel()
        self.label_agotados = QLabel()
        fila_alertas.addWidget(self.label_stock_bajo)
        fila_alertas.addWidget(self.label_agotados)
        fila_alertas.addStretch()
        layout.addLayout(fila_alertas)

        # Gráficos
        subtitulo_graficos = QLabel("Tendencia")
        subtitulo_graficos.setStyleSheet("font-size: 14px; font-weight: 600; color: #6b7280; margin-top: 4px;")
        layout.addWidget(subtitulo_graficos)

        fila_graficos = QHBoxLayout()
        fila_graficos.setSpacing(16)
        self.chart_ventas_anio = LineChartWidget(f"Ventas por mes ({date.today().year})")
        self.chart_metodo_pago = DonutChartWidget("Ventas por método de pago (este mes)")
        fila_graficos.addWidget(self.chart_ventas_anio, 2)
        fila_graficos.addWidget(self.chart_metodo_pago, 1)
        layout.addLayout(fila_graficos)

        self.chart_top_productos = BarChartWidget("Productos más vendidos (este mes)")
        layout.addWidget(self.chart_top_productos)

        layout.addStretch()
        scroll.setWidget(contenido)

        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.addWidget(scroll)

    def _tick(self) -> None:
        """Se ejecuta cada minuto: si cambió el día, recarga siempre; si no,
        refresca solo cuando la pantalla está visible."""
        hoy = date.today()
        if hoy != self._fecha_actual:
            self._fecha_actual = hoy
            self.label_fecha.setText(f"Hoy: {hoy.strftime('%d/%m/%Y')}")
            self.actualizar()
        elif self.isVisible():
            self.actualizar()

    def actualizar(self) -> None:
        """Dispara la carga del resumen en un hilo aparte para que abrir o
        refrescar el dashboard nunca congele la ventana."""
        self._req_id += 1
        req_id = self._req_id
        worker = Worker(self.reporte_service.resumen_dashboard, self.usuario.id)
        worker.signals.finished.connect(lambda resumen: self._on_resumen_listo(req_id, resumen))
        worker.signals.error.connect(lambda msg: self._on_error(req_id, msg))
        QThreadPool.globalInstance().start(worker)

    def _on_error(self, req_id: int, mensaje: str) -> None:
        if req_id != self._req_id:
            return  # llegó tarde, ya hay una carga más nueva en curso
        self.label_stock_bajo.setText("No se pudo cargar el resumen del negocio.")
        self.label_stock_bajo.setProperty("class", "badgeDanger")
        self.label_stock_bajo.style().unpolish(self.label_stock_bajo)
        self.label_stock_bajo.style().polish(self.label_stock_bajo)

    def _on_resumen_listo(self, req_id: int, resumen: dict) -> None:
        if req_id != self._req_id:
            return  # respuesta vieja, se descarta

        config = self.config_service.obtener()
        moneda = config.get("moneda", "S/")
        oscuro = config.get("tema") == "oscuro"

        self.card_ventas.actualizar_valor(formatear_moneda(resumen["ventas_del_dia_total"], moneda))
        self.card_utilidad.actualizar_valor(formatear_moneda(resumen["utilidad_del_dia"], moneda))

        estado_caja = resumen["estado_caja"]
        if estado_caja.get("abierta"):
            self.card_caja.actualizar_valor(f"Abierta ({formatear_moneda(estado_caja['monto_esperado'], moneda)})")
        else:
            self.card_caja.actualizar_valor("Cerrada")

        n_bajo = len(resumen["stock_bajo"])
        n_agotados = len(resumen["agotados"])
        self.label_stock_bajo.setText(f"⚠ {n_bajo} producto(s) con stock bajo")
        self.label_stock_bajo.setProperty("class", "badgeWarning" if n_bajo else "badgeOk")
        self.label_agotados.setText(f"✕ {n_agotados} producto(s) agotado(s)")
        self.label_agotados.setProperty("class", "badgeDanger" if n_agotados else "badgeOk")
        for lbl in (self.label_stock_bajo, self.label_agotados):
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

        self.chart_ventas_anio.set_modo_oscuro(oscuro)
        puntos = [
            (_MESES_CORTO[int(fila["mes"]) - 1], fila["total"])
            for fila in resumen["ventas_por_mes"]
        ]
        self.chart_ventas_anio.set_datos(puntos)

        self.chart_metodo_pago.set_modo_oscuro(oscuro)
        segmentos = [(fila["metodo"], fila["total"]) for fila in resumen["ventas_metodo_pago_mes"]]
        self.chart_metodo_pago.set_datos(segmentos, moneda)

        self.chart_top_productos.set_modo_oscuro(oscuro)
        ranking = [
            (fila["nombre"], fila["cantidad_total"])
            for fila in resumen["productos_mas_vendidos_mes"]
        ]
        self.chart_top_productos.set_datos(ranking, formateador=lambda v: f"{v:g} u.")