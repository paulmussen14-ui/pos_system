"""Proformas: cotizaciones guardadas desde Ventas. No afectan stock ni caja."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument, QPageSize, QPageLayout
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QTextBrowser, QMessageBox, QFileDialog,
)
from html import escape
from datetime import datetime, timedelta

from services.proforma_service import ProformaService
from services.configuracion_service import ConfiguracionService
from ui.tokens import MARGEN_PAGINA, ESPACIO_MD
from ui.widgets.card import Card
from ui.widgets.page_header import PageHeader
from ui.widgets.status_badge import StatusBadge
from ui.widgets.tabla_erp import configurar_tabla_erp, item_derecha, item_centro, compactar_boton
from utils.validators import formatear_moneda


def html_proforma(p: dict, negocio: dict) -> str:
    moneda = negocio.get("moneda", "S/")
    filas = "".join(
        f"<tr><td>{escape(l['nombre_producto'])}</td>"
        f"<td align='center'>{(l.get('cantidad_presentacion') or l['cantidad']):g} {escape(l.get('presentacion_nombre') or 'Unidad')}</td>"
        f"<td align='right'>{formatear_moneda(l['precio_unitario'], moneda)}</td>"
        f"<td align='right'>{formatear_moneda(l['subtotal'], moneda)}</td></tr>"
        for l in p["lineas"])
    try:
        vence = (datetime.strptime(p["fecha"][:10], "%Y-%m-%d") + timedelta(days=p["validez_dias"])).strftime("%Y-%m-%d")
    except ValueError:
        vence = "—"
    cliente = escape(p.get("cliente") or "—")
    if p.get("cliente_tipo"):
        cliente += f" ({escape(p['cliente_tipo'])})"
    return f"""
    <h2 style='margin-bottom:0'>{escape(negocio.get('nombre_negocio') or 'Mi Negocio')}</h2>
    <p style='margin-top:2px;color:#555'>{escape(negocio.get('direccion') or '')}</p>
    <h3>PROFORMA N° {p['id']:05d}</h3>
    <p>Fecha: {p['fecha'][:16]} &nbsp;|&nbsp; Válida hasta: {vence}<br>Cliente: {cliente}</p>
    <table width='100%' cellspacing='0' cellpadding='5' border='1' style='border-color:#bbb'>
    <tr style='background:#eee'><th align='left'>Producto</th><th>Cantidad</th><th align='right'>P. unit.</th><th align='right'>Subtotal</th></tr>
    {filas}</table>
    <p align='right'>Subtotal: {formatear_moneda(p['subtotal'], moneda)}<br>
    Descuento: - {formatear_moneda(p['descuento'], moneda)}<br>
    <b style='font-size:15px'>TOTAL: {formatear_moneda(p['total'], moneda)}</b></p>
    <p style='color:#666;font-size:11px'>Esta proforma es una cotización informativa; no constituye comprobante de pago.
    Los precios y el stock pueden variar. {escape(p.get('notas') or '')}</p>"""


class ProformaDetalleDialog(QDialog):

    def __init__(self, proforma: dict, negocio: dict, parent=None):
        super().__init__(parent)
        self.proforma = proforma
        self.negocio = negocio
        self.setWindowTitle(f"Proforma #{proforma['id']}")
        self.resize(640, 640)
        v = QVBoxLayout(self)
        self.vista = QTextBrowser()
        self.vista.setHtml(html_proforma(proforma, negocio))
        v.addWidget(self.vista, 1)
        fila = QHBoxLayout()
        fila.addStretch()
        b_pdf = QPushButton("Guardar PDF")
        b_pdf.setProperty("class", "secondary")
        b_pdf.clicked.connect(self._pdf)
        b_imp = QPushButton("Imprimir")
        b_imp.setProperty("class", "secondary")
        b_imp.clicked.connect(self._imprimir)
        b_cerrar = QPushButton("Cerrar")
        b_cerrar.clicked.connect(self.accept)
        for b in (b_pdf, b_imp, b_cerrar):
            fila.addWidget(b)
        v.addLayout(fila)

    def _doc(self) -> QTextDocument:
        d = QTextDocument()
        d.setHtml(html_proforma(self.proforma, self.negocio))
        return d

    def _pdf(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar proforma", f"proforma_{self.proforma['id']:05d}.pdf",
                                              "PDF (*.pdf)")
        if not ruta:
            return
        imp = QPrinter(QPrinter.HighResolution)
        imp.setOutputFormat(QPrinter.PdfFormat)
        imp.setOutputFileName(ruta)
        imp.setPageSize(QPageSize(QPageSize.A4))
        self._doc().print_(imp)
        QMessageBox.information(self, "PDF guardado", ruta)

    def _imprimir(self) -> None:
        imp = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(imp, self)
        if dlg.exec() == QDialog.Accepted:
            self._doc().print_(imp)


class ProformasPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.service = ProformaService()
        self.config_service = ConfiguracionService()
        self.convertir = None  # callback(proforma_dict) → lo conecta la ventana principal
        self._filas: list[dict] = []
        self._construir_ui()
        self.actualizar()

    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA, MARGEN_PAGINA)
        raiz.setSpacing(ESPACIO_MD)
        raiz.addWidget(PageHeader("Proformas", "Cotizaciones: no descuentan stock ni mueven la caja"))
        tarjeta = Card("Proformas guardadas")
        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText("Buscar por cliente o N°...")
        self.input_buscar.setClearButtonEnabled(True)
        self.input_buscar.textChanged.connect(lambda: self.actualizar())
        tarjeta.cuerpo.addWidget(self.input_buscar)
        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels(["N°", "Fecha", "Cliente", "Total", "Estado", ""])
        h = self.tabla.horizontalHeader()
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (0, 1, 3, 4, 5):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        configurar_tabla_erp(self.tabla, derecha=(3,), centro=(0, 4), altura_fila=48)
        self.tabla.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.tabla.setColumnWidth(4, 120)
        self.tabla.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.tabla.setColumnWidth(5, 370)
        tarjeta.cuerpo.addWidget(self.tabla, 1)
        self.label_vacio = QLabel("No hay proformas. Arma un carrito en Ventas y usa «Guardar como proforma».")
        self.label_vacio.setProperty("class", "ayuda")
        self.label_vacio.setAlignment(Qt.AlignCenter)
        tarjeta.cuerpo.addWidget(self.label_vacio)
        raiz.addWidget(tarjeta, 1)

    def actualizar(self, *_):
        moneda = self.config_service.obtener().get("moneda", "S/")
        self._filas = self.service.listar(self.input_buscar.text())
        self.label_vacio.setVisible(not self._filas)
        self.tabla.clearContents()
        self.tabla.setRowCount(len(self._filas))
        tonos = {"pendiente": "info", "convertida": "ok", "anulada": "neutral"}
        for i, p in enumerate(self._filas):
            self.tabla.setItem(i, 0, item_centro(f"{p['id']:05d}"))
            self.tabla.setItem(i, 1, QTableWidgetItem(p["fecha"][:16]))
            cli = p.get("cliente") or "—"
            if p.get("cliente_tipo"):
                cli += f"  ({p['cliente_tipo']})"
            self.tabla.setItem(i, 2, QTableWidgetItem(cli))
            self.tabla.setItem(i, 3, item_derecha(formatear_moneda(p["total"], moneda)))
            self.tabla.setCellWidget(i, 4, StatusBadge(p["estado"].capitalize(), tonos.get(p["estado"], "neutral")))
            acc = QWidget()
            f = QHBoxLayout(acc)
            f.setContentsMargins(4, 4, 4, 4)
            f.setSpacing(6)
            b_ver = QPushButton("Ver / imprimir")
            b_ver.setProperty("class", "secondary")
            compactar_boton(b_ver)
            b_ver.clicked.connect(lambda _, pid=p["id"]: self._ver(pid))
            f.addWidget(b_ver)
            if p["estado"] == "pendiente":
                b_conv = QPushButton("Convertir en venta")
                b_conv.setProperty("class", "success")
                compactar_boton(b_conv)
                b_conv.clicked.connect(lambda _, pid=p["id"]: self._convertir(pid))
                b_anu = QPushButton("Anular")
                b_anu.setProperty("class", "secondary")
                compactar_boton(b_anu)
                b_anu.clicked.connect(lambda _, pid=p["id"]: self._anular(pid))
                f.addWidget(b_conv)
                f.addWidget(b_anu)
            self.tabla.setCellWidget(i, 5, acc)

    def _ver(self, pid: int) -> None:
        p = self.service.obtener(pid)
        if p:
            ProformaDetalleDialog(p, self.config_service.obtener(), self).exec()

    def _convertir(self, pid: int) -> None:
        p = self.service.obtener(pid)
        if p and self.convertir:
            self.convertir(p)

    def _anular(self, pid: int) -> None:
        if QMessageBox.question(self, "Anular proforma", f"¿Anular la proforma #{pid}?") == QMessageBox.Yes:
            self.service.anular(pid)
            self.actualizar()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.actualizar()
