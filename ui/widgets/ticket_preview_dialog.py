"""
Diálogo de vista previa e impresión de ticket.

Muestra el ticket en una fuente monoespaciada con un ancho fijo que simula
el rollo de papel térmico, y permite imprimirlo (o reimprimirlo) con un
botón explícito en lugar de imprimir en silencio.

La vista previa muestra una sola copia (sin etiqueta) para no confundir al
usuario, pero al presionar "Imprimir" se generan y envían las copias reales
configuradas (cliente + control interno, o solo una, según configuración).
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QMessageBox
from PySide6.QtGui import QFont

from printing.ticket_printer import imprimir_ticket_venta, TicketPrinterError
from printing.ticket_template import generar_texto_ticket


class TicketPreviewDialog(QDialog):

    def __init__(self, venta: dict, config_negocio: dict, nombre_impresora: str | None,
                 ancho_caracteres: int = 32, imprimir_dos_copias: bool = True, parent=None):
        super().__init__(parent)
        self.venta = venta
        self.config_negocio = config_negocio
        self.nombre_impresora = nombre_impresora
        self.ancho_caracteres = ancho_caracteres
        self.imprimir_dos_copias = imprimir_dos_copias

        # La vista previa siempre muestra una sola copia limpia, sin la
        # marca de "COPIA CLIENTE"/"CONTROL INTERNO", para no confundir.
        self.texto_vista_previa = generar_texto_ticket(venta, config_negocio, ancho_caracteres)

        self._construir_ui(ancho_caracteres)

    def _construir_ui(self, ancho_caracteres: int) -> None:
        self.setWindowTitle("Vista previa del ticket")

        layout = QVBoxLayout(self)

        self.texto = QTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setPlainText(self.texto_vista_previa)
        fuente = QFont("Courier New")
        fuente.setStyleHint(QFont.Monospace)
        fuente.setPointSize(11)
        self.texto.setFont(fuente)
        self.texto.setLineWrapMode(QTextEdit.NoWrap)

        # Ancho aproximado de "rollo": columnas de texto * ancho de carácter monoespaciado.
        ancho_px = max(260, int(ancho_caracteres * 8.2) + 40)
        self.texto.setMinimumWidth(ancho_px)
        self.setMinimumHeight(420)
        self.texto.setStyleSheet("background: white; color: #111827; border: 1px solid #d1d5db;")
        layout.addWidget(self.texto)

        botones = QHBoxLayout()
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setProperty("class", "secondary")
        btn_cerrar.clicked.connect(self.accept)
        botones.addWidget(btn_cerrar)

        texto_boton = "Imprimir (2 copias)" if self.imprimir_dos_copias else "Imprimir"
        btn_imprimir = QPushButton(texto_boton)
        btn_imprimir.setProperty("class", "success")
        btn_imprimir.clicked.connect(self._imprimir)
        botones.addWidget(btn_imprimir)

        layout.addLayout(botones)

    def _imprimir(self) -> None:
        try:
            imprimir_ticket_venta(
                self.venta,
                self.config_negocio,
                self.ancho_caracteres,
                self.nombre_impresora,
                self.imprimir_dos_copias,
            )
        except TicketPrinterError as e:
            QMessageBox.warning(self, "Error al imprimir", str(e))
            return

        if not self.nombre_impresora:
            QMessageBox.information(
                self, "Sin impresora configurada",
                "No hay una impresora térmica activa en Configuración → Impresión.\n"
                "El ticket se guardó como archivo de texto en su lugar."
            )
        elif self.imprimir_dos_copias:
            QMessageBox.information(
                self, "Ticket enviado",
                "Se enviaron 2 copias a la impresora: una para el cliente y "
                "otra para tu control interno."
            )
        else:
            QMessageBox.information(self, "Ticket enviado", "El ticket se envió a la impresora.")