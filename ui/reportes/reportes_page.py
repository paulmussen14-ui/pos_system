"""Página de Reportes: ventas, utilidad, compras, inventario, más vendidos, ventas por cliente."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QDateEdit
)
from PySide6.QtCore import QDate, QThreadPool

from services.reporte_service import ReporteService
from services.configuracion_service import ConfiguracionService
from utils.validators import formatear_moneda
from utils.worker import Worker
from utils.logger import logger


class ReportesPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.reporte_service = ReporteService()
        self.config_service = ConfiguracionService()
        self._datos_actuales: dict = {}
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        titulo = QLabel("Reportes")
        titulo.setStyleSheet("font-size: 24px; font-weight: 700;")
        layout.addWidget(titulo)

        # Filtro de fechas (aplica al tab de ventas y utilidad)
        fila_filtro = QHBoxLayout()
        fila_filtro.addWidget(QLabel("Desde:"))
        self.fecha_desde = QDateEdit(calendarPopup=True)
        self.fecha_desde.setDate(QDate.currentDate().addMonths(-1))
        fila_filtro.addWidget(self.fecha_desde)

        fila_filtro.addWidget(QLabel("Hasta:"))
        self.fecha_hasta = QDateEdit(calendarPopup=True)
        self.fecha_hasta.setDate(QDate.currentDate())
        fila_filtro.addWidget(self.fecha_hasta)

        btn_filtrar = QPushButton("Filtrar")
        btn_filtrar.clicked.connect(self.actualizar)
        fila_filtro.addWidget(btn_filtrar)
        fila_filtro.addStretch()
        layout.addLayout(fila_filtro)

        self.tabs = QTabWidget()

        self.tabla_ventas = self._crear_tabla(["#", "Fecha", "Cliente", "Total", "Estado"])
        self.tabs.addTab(self._envolver_con_export(self.tabla_ventas, "ventas"), "Ventas")

        self.tabla_utilidad = self._crear_tabla(["Venta", "Fecha", "Producto", "Cantidad", "Utilidad"])
        self.tabs.addTab(self._envolver_con_export(self.tabla_utilidad, "utilidad"), "Utilidad bruta")

        self.tabla_compras = self._crear_tabla(["#", "Fecha", "Proveedor", "Total"])
        self.tabs.addTab(self._envolver_con_export(self.tabla_compras, "compras"), "Compras")

        self.tabla_inventario = self._crear_tabla(["Producto", "Stock", "Mínimo", "Costo prom.", "Valor inventario"])
        self.tabs.addTab(self._envolver_con_export(self.tabla_inventario, "inventario"), "Inventario")

        self.tabla_mas_vendidos = self._crear_tabla(["Producto", "Cantidad vendida", "Monto total"])
        self.tabs.addTab(self._envolver_con_export(self.tabla_mas_vendidos, "mas_vendidos"), "Más vendidos")

        self.tabla_por_cliente = self._crear_tabla(["Cliente", "N° ventas", "Total comprado"])
        self.tabs.addTab(self._envolver_con_export(self.tabla_por_cliente, "ventas_por_cliente"), "Ventas por cliente")

        layout.addWidget(self.tabs)

    def _crear_tabla(self, columnas: list[str]) -> QTableWidget:
        tabla = QTableWidget(0, len(columnas))
        tabla.setHorizontalHeaderLabels(columnas)
        tabla.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tabla.verticalHeader().setVisible(False)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        return tabla

    def _envolver_con_export(self, tabla: QTableWidget, nombre_reporte: str) -> QWidget:
        contenedor = QWidget()
        layout = QVBoxLayout(contenedor)
        layout.setContentsMargins(0, 8, 0, 0)

        btn_exportar = QPushButton("Exportar a Excel")
        btn_exportar.setProperty("class", "secondary")
        btn_exportar.clicked.connect(lambda: self._exportar(nombre_reporte))
        layout.addWidget(btn_exportar)
        layout.addWidget(tabla)
        return contenedor

    def actualizar(self) -> None:
        """Dispara las seis consultas de reportes en un solo hilo en segundo
        plano (todas juntas, para no abrir varios hilos a la vez contra la
        misma conexión SQLite) y solo actualiza las tablas cuando terminan.
        Antes esto corría en el hilo de la UI y con suficiente historial de
        ventas/compras podía "congelar" la pantalla igual que pasaba en
        Ventas."""
        moneda = self.config_service.obtener().get("moneda", "S/")
        desde = self.fecha_desde.date().toString("yyyy-MM-dd")
        hasta = self.fecha_hasta.date().toString("yyyy-MM-dd")

        worker = Worker(self._cargar_todos_los_reportes, desde, hasta)
        worker.signals.finished.connect(
            lambda datos, moneda=moneda: self._on_reportes_listos(datos, moneda)
        )
        worker.signals.error.connect(self._on_error_carga)
        QThreadPool.globalInstance().start(worker)

    def _cargar_todos_los_reportes(self, desde: str, hasta: str) -> dict:
        """Corre en el hilo en segundo plano: solo consultas, nada de widgets."""
        return {
            "ventas": self.reporte_service.reporte_ventas(desde, hasta),
            "utilidad": self.reporte_service.reporte_utilidad(desde, hasta),
            "compras": self.reporte_service.reporte_compras(),
            "inventario": self.reporte_service.reporte_inventario(),
            "mas_vendidos": self.reporte_service.reporte_productos_mas_vendidos(),
            "ventas_por_cliente": self.reporte_service.reporte_ventas_por_cliente(),
        }

    def _on_error_carga(self, error_texto: str) -> None:
        logger.error("Error al cargar reportes: %s", error_texto)
        QMessageBox.warning(
            self, "Error al cargar reportes",
            "No se pudieron cargar los reportes. Intenta de nuevo.",
        )

    def _on_reportes_listos(self, datos: dict, moneda: str) -> None:
        ventas = datos["ventas"]
        self.tabla_ventas.setRowCount(len(ventas))
        for fila, v in enumerate(ventas):
            self.tabla_ventas.setItem(fila, 0, QTableWidgetItem(str(v["id"])))
            self.tabla_ventas.setItem(fila, 1, QTableWidgetItem(str(v["fecha"])))
            self.tabla_ventas.setItem(fila, 2, QTableWidgetItem(v.get("cliente_nombre") or "-"))
            self.tabla_ventas.setItem(fila, 3, QTableWidgetItem(formatear_moneda(v["total"], moneda)))
            self.tabla_ventas.setItem(fila, 4, QTableWidgetItem(v["estado"]))

        utilidad = datos["utilidad"]
        self.tabla_utilidad.setRowCount(len(utilidad))
        for fila, u in enumerate(utilidad):
            self.tabla_utilidad.setItem(fila, 0, QTableWidgetItem(str(u["venta_id"])))
            self.tabla_utilidad.setItem(fila, 1, QTableWidgetItem(str(u["fecha"])))
            self.tabla_utilidad.setItem(fila, 2, QTableWidgetItem(u["producto"]))
            self.tabla_utilidad.setItem(fila, 3, QTableWidgetItem(str(u["cantidad"])))
            self.tabla_utilidad.setItem(fila, 4, QTableWidgetItem(formatear_moneda(u["utilidad"], moneda)))

        compras = datos["compras"]
        self.tabla_compras.setRowCount(len(compras))
        for fila, c in enumerate(compras):
            self.tabla_compras.setItem(fila, 0, QTableWidgetItem(str(c["id"])))
            self.tabla_compras.setItem(fila, 1, QTableWidgetItem(str(c["fecha"])))
            self.tabla_compras.setItem(fila, 2, QTableWidgetItem(c.get("proveedor_nombre") or "-"))
            self.tabla_compras.setItem(fila, 3, QTableWidgetItem(formatear_moneda(c["total"], moneda)))

        inventario = datos["inventario"]
        self.tabla_inventario.setRowCount(len(inventario))
        for fila, i in enumerate(inventario):
            self.tabla_inventario.setItem(fila, 0, QTableWidgetItem(i["producto"]))
            self.tabla_inventario.setItem(fila, 1, QTableWidgetItem(str(i["stock_actual"])))
            self.tabla_inventario.setItem(fila, 2, QTableWidgetItem(str(i["stock_minimo"])))
            self.tabla_inventario.setItem(fila, 3, QTableWidgetItem(formatear_moneda(i["costo_promedio"], moneda)))
            self.tabla_inventario.setItem(fila, 4, QTableWidgetItem(formatear_moneda(i["valor_inventario"], moneda)))

        mas_vendidos = datos["mas_vendidos"]
        self.tabla_mas_vendidos.setRowCount(len(mas_vendidos))
        for fila, m in enumerate(mas_vendidos):
            self.tabla_mas_vendidos.setItem(fila, 0, QTableWidgetItem(m["nombre"]))
            self.tabla_mas_vendidos.setItem(fila, 1, QTableWidgetItem(str(m["cantidad_total"])))
            self.tabla_mas_vendidos.setItem(fila, 2, QTableWidgetItem(formatear_moneda(m["monto_total"], moneda)))

        por_cliente = datos["ventas_por_cliente"]
        self.tabla_por_cliente.setRowCount(len(por_cliente))
        for fila, c in enumerate(por_cliente):
            self.tabla_por_cliente.setItem(fila, 0, QTableWidgetItem(c["cliente"]))
            self.tabla_por_cliente.setItem(fila, 1, QTableWidgetItem(str(c["cantidad_ventas"])))
            self.tabla_por_cliente.setItem(fila, 2, QTableWidgetItem(formatear_moneda(c["total_comprado"], moneda)))

        self._datos_actuales = datos

    def _exportar(self, nombre_reporte: str) -> None:
        datos = self._datos_actuales.get(nombre_reporte, [])
        if not datos:
            QMessageBox.information(self, "Sin datos", "No hay datos para exportar en este reporte.")
            return

        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte", f"{nombre_reporte}.xlsx", "Excel (*.xlsx)"
        )
        if not ruta:
            return

        try:
            self.reporte_service.exportar_a_excel(datos, ruta)
        except Exception as e:
            QMessageBox.warning(self, "Error al exportar", str(e))
            return

        QMessageBox.information(self, "Exportado", f"Reporte guardado en:\n{ruta}")