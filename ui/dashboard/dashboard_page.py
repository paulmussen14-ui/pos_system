"""Página de Inicio / Dashboard: resumen del negocio.

El resumen (`ReporteService.resumen_dashboard`) hace varias consultas SQL;
para que abrir o refrescar esta pantalla nunca bloquee la interfaz (aunque
el negocio ya tenga miles de ventas registradas), la carga corre en un
`Worker` en segundo plano, igual que en Ventas/Productos/Clientes/Inventario.
"""

from datetime import date

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Qt, QThreadPool

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


class DashboardPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.reporte_service = ReporteService()
        self.config_service = ConfiguracionService()
        self._req_id = 0  # descarta resultados de una carga anterior si se refresca de nuevo antes de que termine
        self._construir_ui()
        self.actualizar()

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

        # Fila de métricas principales (diarias — se reinician solas cada día,
        # sin depender del cierre de caja)
        fila_metricas = QHBoxLayout()
        fila_metricas.setSpacing(16)
        self.card_ventas = MetricCard("Ventas del día", formatear_moneda(0))
        self.card_utilidad = MetricCard("Utilidad bruta del día", formatear_moneda(0))
        self.card_compras = MetricCard("Compras del día", formatear_moneda(0))
        self.card_caja = MetricCard("Estado de caja", "Cerrada")
        for card in (self.card_ventas, self.card_utilidad, self.card_compras, self.card_caja):
            fila_metricas.addWidget(card)
        layout.addLayout(fila_metricas)

        # Fila de métricas mensuales (mes calendario en curso)
        subtitulo_mes = QLabel("Este mes")
        subtitulo_mes.setStyleSheet("font-size: 14px; font-weight: 600; color: #6b7280; margin-top: 4px;")
        layout.addWidget(subtitulo_mes)

        fila_metricas_mes = QHBoxLayout()
        fila_metricas_mes.setSpacing(16)
        self.card_ventas_mes = MetricCard("Ventas del mes", formatear_moneda(0))
        self.card_utilidad_mes = MetricCard("Utilidad bruta del mes", formatear_moneda(0))
        self.card_compras_mes = MetricCard("Compras del mes", formatear_moneda(0))
        self.card_ticket_promedio_mes = MetricCard("Ticket promedio del mes", formatear_moneda(0))
        for card in (self.card_ventas_mes, self.card_utilidad_mes,
                     self.card_compras_mes, self.card_ticket_promedio_mes):
            fila_metricas_mes.addWidget(card)
        layout.addLayout(fila_metricas_mes)

        # Fila de alertas de stock
        fila_alertas = QHBoxLayout()
        fila_alertas.setSpacing(16)
        self.label_stock_bajo = QLabel()
        self.label_agotados = QLabel()
        fila_alertas.addWidget(self.label_stock_bajo)
        fila_alertas.addWidget(self.label_agotados)
        fila_alertas.addStretch()
        layout.addLayout(fila_alertas)

        # Gráficos: tendencia de ventas (línea) + desglose por método de
        # pago (circular), en vez de la tabla de últimas ventas.
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

    def actualizar(self) -> None:
        """Dispara la carga del resumen en un hilo aparte para que abrir o
        refrescar el dashboard nunca congele la ventana, sin importar cuántas
        ventas tenga acumuladas el negocio."""
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
            return  # el usuario ya salió y volvió a entrar; se descarta esta respuesta vieja

        config = self.config_service.obtener()
        moneda = config.get("moneda", "S/")
        oscuro = config.get("tema") == "oscuro"

        self.card_ventas.actualizar_valor(formatear_moneda(resumen["ventas_del_dia_total"], moneda))
        self.card_utilidad.actualizar_valor(formatear_moneda(resumen["utilidad_del_dia"], moneda))
        self.card_compras.actualizar_valor(formatear_moneda(resumen["compras_del_dia_total"], moneda))

        self.card_ventas_mes.actualizar_valor(formatear_moneda(resumen["ventas_del_mes_total"], moneda))
        self.card_utilidad_mes.actualizar_valor(formatear_moneda(resumen["utilidad_del_mes"], moneda))
        self.card_compras_mes.actualizar_valor(formatear_moneda(resumen["compras_del_mes_total"], moneda))
        self.card_ticket_promedio_mes.actualizar_valor(formatear_moneda(resumen["ticket_promedio_mes"], moneda))

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