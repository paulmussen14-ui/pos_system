"""Pestaña "Correo" de Configuración: datos del servidor para enviar boletas por email.

El programa sigue siendo local; Internet solo se usa en el momento de enviar un correo.
"""

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QSpinBox, QMessageBox, QInputDialog,
)

from services import correo_service
from services.configuracion_service import ConfiguracionService, ConfiguracionError
from ui.tokens import ESPACIO_SM, ESPACIO_MD
from ui.widgets.card import Card
from utils.validators import es_email_valido
from utils.worker import Worker

# Valores habituales de los proveedores más usados: (nombre, servidor, puerto, seguridad, ayuda).
PROVEEDORES = [
    ("Otro (escribir a mano)", "", 587, "starttls", ""),
    ("Gmail", "smtp.gmail.com", 587, "starttls",
     "Gmail no acepta tu contraseña normal. Activa la verificación en 2 pasos en tu cuenta de "
     "Google y crea una «contraseña de aplicación»; esa es la que va en «Contraseña»."),
    ("Outlook / Hotmail", "smtp-mail.outlook.com", 587, "starttls",
     "Si tu cuenta tiene verificación en 2 pasos, usa una «contraseña de aplicación»."),
    ("Yahoo", "smtp.mail.yahoo.com", 465, "ssl",
     "Yahoo exige una «contraseña de aplicación» generada desde la seguridad de tu cuenta."),
]

SEGURIDADES = [
    ("STARTTLS (puerto 587, el más común)", "starttls"),
    ("SSL/TLS (puerto 465)", "ssl"),
    ("Sin cifrado (no recomendado)", "ninguna"),
]


class CorreoTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_service = ConfiguracionService()
        self._construir_ui()
        self.cargar()

    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, ESPACIO_MD, 0, 0)
        raiz.setSpacing(ESPACIO_MD)

        tarjeta = Card("Correo para enviar boletas")
        formulario = QFormLayout()
        formulario.setHorizontalSpacing(ESPACIO_MD)

        self.combo_proveedor = QComboBox()
        for nombre, *_ in PROVEEDORES:
            self.combo_proveedor.addItem(nombre)
        self.combo_proveedor.currentIndexChanged.connect(self._aplicar_proveedor)

        self.input_host = QLineEdit()
        self.input_host.setPlaceholderText("ej. smtp.gmail.com")
        self.input_puerto = QSpinBox()
        self.input_puerto.setRange(1, 65535)
        self.input_puerto.setValue(587)
        self.combo_seguridad = QComboBox()
        for texto, valor in SEGURIDADES:
            self.combo_seguridad.addItem(texto, valor)
        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("tucorreo@gmail.com")
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_remitente_nombre = QLineEdit()
        self.input_remitente_nombre.setPlaceholderText("Si lo dejas vacío se usa el nombre del negocio")
        self.input_remitente_email = QLineEdit()
        self.input_remitente_email.setPlaceholderText("Si lo dejas vacío se usa el usuario")

        formulario.addRow("Proveedor:", self.combo_proveedor)
        formulario.addRow("Servidor SMTP:", self.input_host)
        formulario.addRow("Puerto:", self.input_puerto)
        formulario.addRow("Seguridad:", self.combo_seguridad)
        formulario.addRow("Usuario:", self.input_usuario)
        formulario.addRow("Contraseña:", self.input_password)
        formulario.addRow("Nombre que verá el cliente:", self.input_remitente_nombre)
        formulario.addRow("Correo remitente:", self.input_remitente_email)
        tarjeta.cuerpo.addLayout(formulario)

        self.label_ayuda_proveedor = QLabel("")
        self.label_ayuda_proveedor.setProperty("class", "ayuda")
        self.label_ayuda_proveedor.setWordWrap(True)
        self.label_ayuda_proveedor.setVisible(False)
        tarjeta.cuerpo.addWidget(self.label_ayuda_proveedor)

        privacidad = QLabel(
            "La contraseña se guarda en la base de datos de este equipo (no se envía a ningún "
            "lado salvo al servidor de correo). Usa una contraseña de aplicación y no la "
            "principal de tu cuenta."
        )
        privacidad.setProperty("class", "ayuda")
        privacidad.setWordWrap(True)
        tarjeta.cuerpo.addWidget(privacidad)
        raiz.addWidget(tarjeta)

        botones = QHBoxLayout()
        botones.setSpacing(ESPACIO_SM)
        self.btn_guardar = QPushButton("Guardar cambios")
        self.btn_guardar.setProperty("class", "success")
        self.btn_guardar.clicked.connect(self._guardar)
        self.btn_probar = QPushButton("Enviar correo de prueba")
        self.btn_probar.setProperty("class", "secondary")
        self.btn_probar.clicked.connect(self._probar)
        botones.addWidget(self.btn_guardar)
        botones.addWidget(self.btn_probar)
        botones.addStretch()
        raiz.addLayout(botones)
        raiz.addStretch()

    # ------------------------------------------------------- Datos ----
    def cargar(self) -> None:
        datos = self.config_service.obtener_correo()
        self.input_host.setText(datos["host"])
        self.input_puerto.setValue(datos["puerto"])
        indice = self.combo_seguridad.findData(datos["seguridad"])
        self.combo_seguridad.setCurrentIndex(indice if indice >= 0 else 0)
        self.input_usuario.setText(datos["usuario"])
        self.input_password.setText(datos["password"])
        self.input_remitente_nombre.setText(datos["remitente_nombre"])
        self.input_remitente_email.setText(datos["remitente_email"])

    def _aplicar_proveedor(self, indice: int) -> None:
        _, host, puerto, seguridad, ayuda = PROVEEDORES[indice]
        if host:  # "Otro" no pisa lo que el usuario ya escribió
            self.input_host.setText(host)
            self.input_puerto.setValue(puerto)
            self.combo_seguridad.setCurrentIndex(self.combo_seguridad.findData(seguridad))
        self.label_ayuda_proveedor.setText(ayuda)
        self.label_ayuda_proveedor.setVisible(bool(ayuda))

    # ----------------------------------------------------- Acciones ----
    def _guardar(self) -> bool:
        remitente = self.input_remitente_email.text().strip()
        if remitente and not es_email_valido(remitente):
            QMessageBox.warning(self, "Correo remitente", "El correo remitente no parece válido.")
            return False
        try:
            self.config_service.actualizar_correo(
                self.input_host.text(), self.input_puerto.value(),
                self.combo_seguridad.currentData(), self.input_usuario.text(),
                self.input_password.text(), self.input_remitente_nombre.text(), remitente,
            )
        except ConfiguracionError as e:
            QMessageBox.warning(self, "No se pudo guardar", str(e))
            return False
        QMessageBox.information(self, "Guardado", "La configuración del correo se guardó.")
        return True

    def _probar(self) -> None:
        # Se prueba con lo que está escrito ahora, guardándolo antes para que
        # las boletas usen exactamente esos datos.
        if not self._guardar():
            return
        datos, nombre_negocio = correo_service.cargar_datos_correo()
        if not (datos["host"] and datos["usuario"] and datos["password"]):
            QMessageBox.warning(self, "Faltan datos", "Completa el servidor, el usuario y la contraseña.")
            return

        sugerido = datos["remitente_email"] or datos["usuario"]
        destino, aceptado = QInputDialog.getText(
            self, "Correo de prueba", "¿A qué correo enviamos la prueba?", text=sugerido)
        if not aceptado:
            return
        destino = destino.strip()
        if not es_email_valido(destino):
            QMessageBox.warning(self, "Correo no válido", "Escribe un correo válido para la prueba.")
            return

        self.btn_probar.setEnabled(False)
        self.btn_probar.setText("Enviando...")
        worker = Worker(correo_service.enviar_correo_seguro, destino,
                        f"Prueba de correo - {nombre_negocio or 'POS Local'}",
                        "Este es un correo de prueba. Si lo estás leyendo, el envío de "
                        "boletas por correo ya funciona.\n",
                        None, datos, nombre_negocio)
        worker.signals.finished.connect(lambda error, d=destino: self._prueba_terminada(error, d))
        worker.signals.error.connect(lambda _: self._prueba_terminada("Ocurrió un error inesperado.", destino))
        QThreadPool.globalInstance().start(worker)

    def _prueba_terminada(self, error: str | None, destino: str) -> None:
        self.btn_probar.setEnabled(True)
        self.btn_probar.setText("Enviar correo de prueba")
        if error:
            QMessageBox.warning(self, "No se pudo enviar", error)
        else:
            QMessageBox.information(
                self, "Correo enviado",
                f"Se envió un correo de prueba a {destino}.\nRevisa también la carpeta de spam.")
