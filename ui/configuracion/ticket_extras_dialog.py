"""Pantalla "Datos del ticket": número para reclamos, términos de devolución,
Yape, chofer y número del negocio, con vista previa del ticket en vivo."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QMessageBox
)
from PySide6.QtGui import QFont, QFontMetrics

from services.ticket_extras_service import TicketExtrasService
from printing.ticket_template import generar_texto_ticket
from utils.logger import logger

ANCHO_PREVIEW_CARACTERES = 32  # papel de 58 mm

# Venta de ejemplo solo para la vista previa (no se guarda en ningún lado).
_VENTA_EJEMPLO = {
    "id": 123,
    "fecha": "2026-09-23 14:50:24",
    "cliente_nombre": "Cliente de ejemplo",
    "cliente_direccion": "Av. Ejemplo 123, Lima",
    "subtotal": 3.66,
    "descuento": 0,
    "total": 3.66,
    "metodo_pago_nombre": "Efectivo",
    "lineas": [
        {
            "producto_nombre": "Producto de ejemplo",
            "cantidad": 2,
            "precio_venta_unitario": 1.83,
            "subtotal": 3.66,
        }
    ],
}


class TicketExtrasDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = TicketExtrasService()
        self.setWindowTitle("Datos del ticket")
        self.resize(820, 600)

        layout_principal = QHBoxLayout(self)

        # ---- Izquierda: formulario ----
        columna_form = QVBoxLayout()
        form = QFormLayout()

        self.input_telefono_negocio = QLineEdit()
        self.input_telefono_negocio.setPlaceholderText("Ej. 987 654 321")
        self.input_telefono_reclamos = QLineEdit()
        self.input_telefono_reclamos.setPlaceholderText("Número para reclamos")
        self.input_yape_numero = QLineEdit()
        self.input_yape_numero.setPlaceholderText("Número de Yape")
        self.input_yape_titular = QLineEdit()
        self.input_yape_titular.setPlaceholderText("Nombre del titular (opcional)")
        self.input_chofer = QLineEdit()
        self.input_chofer.setPlaceholderText("Chofer por defecto (opcional)")

        self.input_politica = QPlainTextEdit()
        self.input_politica.setPlaceholderText(
            "Ej. Devoluciones dentro de 7 días con este ticket.\n"
            "No se aceptan cambios de productos abiertos."
        )
        self.input_politica.setFixedHeight(130)

        form.addRow("Número del negocio:", self.input_telefono_negocio)
        form.addRow("Número para reclamos:", self.input_telefono_reclamos)
        form.addRow("Yape (número):", self.input_yape_numero)
        form.addRow("Yape (titular):", self.input_yape_titular)
        form.addRow("Chofer:", self.input_chofer)
        columna_form.addLayout(form)

        columna_form.addWidget(QLabel("Términos de devolución:"))
        columna_form.addWidget(self.input_politica)

        ayuda = QLabel(
            "Solo se imprime lo que llenes. Evita tildes si tu impresora "
            "térmica muestra mal los acentos."
        )
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color: #6b7280; font-size: 11px;")
        columna_form.addWidget(ayuda)
        columna_form.addStretch()

        botones = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setProperty("class", "secondary")
        btn_cancelar.clicked.connect(self.reject)
        btn_guardar = QPushButton("Guardar")
        btn_guardar.clicked.connect(self._guardar)
        botones.addWidget(btn_cancelar)
        botones.addWidget(btn_guardar)
        columna_form.addLayout(botones)

        layout_principal.addLayout(columna_form, 3)

        # ---- Derecha: vista previa ----
        columna_preview = QVBoxLayout()
        columna_preview.addWidget(QLabel("Vista previa (papel de 58 mm):"))

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        fuente = QFont("Courier New", 9)
        fuente.setStyleHint(QFont.Monospace)
        self.preview.setFont(fuente)
        metricas = QFontMetrics(fuente)
        ancho_texto = metricas.horizontalAdvance("0") * (ANCHO_PREVIEW_CARACTERES + 3)
        self.preview.setMinimumWidth(ancho_texto)
        self.preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        columna_preview.addWidget(self.preview)

        layout_principal.addLayout(columna_preview, 2)

        self._cargar_valores()

        # Se conectan DESPUÉS de cargar, para no regenerar la vista previa
        # una vez por cada campo mientras se llena el formulario.
        for campo in (
            self.input_telefono_negocio, self.input_telefono_reclamos,
            self.input_yape_numero, self.input_yape_titular, self.input_chofer,
        ):
            campo.textChanged.connect(self._actualizar_preview)
        self.input_politica.textChanged.connect(self._actualizar_preview)

        self._actualizar_preview()

    def _cargar_valores(self) -> None:
        datos = self.service.obtener()
        self.input_telefono_negocio.setText(datos["telefono_negocio"])
        self.input_telefono_reclamos.setText(datos["telefono_reclamos"])
        self.input_yape_numero.setText(datos["yape_numero"])
        self.input_yape_titular.setText(datos["yape_titular"])
        self.input_chofer.setText(datos["chofer"])
        self.input_politica.setPlainText(datos["politica_devolucion"])

    def _leer_formulario(self) -> dict:
        return {
            "telefono_negocio": self.input_telefono_negocio.text().strip(),
            "telefono_reclamos": self.input_telefono_reclamos.text().strip(),
            "yape_numero": self.input_yape_numero.text().strip(),
            "yape_titular": self.input_yape_titular.text().strip(),
            "chofer": self.input_chofer.text().strip(),
            "politica_devolucion": self.input_politica.toPlainText().strip(),
        }

    def _actualizar_preview(self) -> None:
        datos = self._leer_formulario()
        config = {
            "nombre_negocio": "Mi Negocio",
            "moneda": "S/",
            "ticket_pie": "Gracias por su compra",
            "telefono": datos["telefono_negocio"],
            "telefono_reclamos": datos["telefono_reclamos"],
            "yape_numero": datos["yape_numero"],
            "yape_titular": datos["yape_titular"],
            "chofer": datos["chofer"],
            "politica_devolucion": datos["politica_devolucion"],
            # La vista previa usa lo que está escrito ahora, no lo guardado.
            "_sin_datos_extra": True,
        }
        try:
            texto = generar_texto_ticket(_VENTA_EJEMPLO, config, ANCHO_PREVIEW_CARACTERES)
        except Exception:
            logger.exception("No se pudo generar la vista previa del ticket")
            texto = "No se pudo generar la vista previa."
        self.preview.setPlainText(texto)

    def _guardar(self) -> None:
        try:
            self.service.guardar(self._leer_formulario())
        except Exception:
            logger.exception("No se pudieron guardar los datos del ticket")
            QMessageBox.warning(self, "Error", "No se pudieron guardar los datos del ticket.")
            return
        self.accept()