"""Ventana principal de la aplicación: sidebar + área de contenido (QStackedWidget)."""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QStackedWidget, QButtonGroup, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

from ui.dashboard.dashboard_page import DashboardPage
from ui.ventas.ventas_page import VentasPage
from ui.productos.productos_page import ProductosPage
from ui.compras.compras_page import ComprasPage
from ui.inventario.inventario_page import InventarioPage
from ui.clientes.clientes_page import ClientesPage
from ui.caja.caja_page import CajaPage
from ui.reportes.reportes_page import ReportesPage
from ui.configuracion.configuracion_page import ConfiguracionPage
from services.configuracion_service import ConfiguracionService
from config import STYLES_DIR, APP_ICON_PATH, APP_LOGO_SIDEBAR_PATH

# Tamaño de la tarjeta que enmarca el logo y alto al que se escala la imagen
# dentro de ella (deja un margen parejo alrededor, en vez de pegarla al borde).
TAMANO_TARJETA_LOGO = 96
ALTO_LOGO_SIDEBAR = 64

# Texto que se muestra en el sidebar si el negocio aún no tiene nombre.
NOMBRE_NEGOCIO_POR_DEFECTO = "POS-Ventas"


class MainWindow(QMainWindow):

    def __init__(self, usuario, cerrar_sesion_callback):
        super().__init__()
        self.usuario = usuario
        self.cerrar_sesion_callback = cerrar_sesion_callback
        self.config_service = ConfiguracionService()

        self.setWindowTitle("Sistema POS Local - FayzerDEV")
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1200, 720)

        self._construir_ui()
        self._aplicar_tema(self.config_service.obtener().get("tema", "claro"))

    def _construir_ui(self) -> None:
        widget_central = QWidget()
        widget_central.setObjectName("centralWidget")
        self.setCentralWidget(widget_central)

        layout_principal = QHBoxLayout(widget_central)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # ---- Sidebar ----
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        layout_sidebar = QVBoxLayout(sidebar)
        layout_sidebar.setContentsMargins(0, 0, 0, 0)
        layout_sidebar.setSpacing(0)

        # ---- Encabezado del sidebar: logo grande arriba, negocio y usuario debajo ----
        contenedor_titulo = QWidget()
        contenedor_titulo.setObjectName("sidebarHeader")
        layout_titulo = QVBoxLayout(contenedor_titulo)
        layout_titulo.setContentsMargins(18, 28, 18, 22)
        layout_titulo.setSpacing(14)
        layout_titulo.setAlignment(Qt.AlignHCenter)

        if APP_LOGO_SIDEBAR_PATH.exists():
            tarjeta_logo = QFrame()
            tarjeta_logo.setObjectName("logoCard")
            tarjeta_logo.setFixedSize(TAMANO_TARJETA_LOGO, TAMANO_TARJETA_LOGO)
            layout_tarjeta = QVBoxLayout(tarjeta_logo)
            layout_tarjeta.setContentsMargins(0, 0, 0, 0)
            layout_tarjeta.setAlignment(Qt.AlignCenter)

            label_logo = QLabel()
            pixmap = QPixmap(str(APP_LOGO_SIDEBAR_PATH))
            pixmap = pixmap.scaledToHeight(ALTO_LOGO_SIDEBAR, Qt.SmoothTransformation)
            label_logo.setPixmap(pixmap)
            label_logo.setAlignment(Qt.AlignCenter)
            layout_tarjeta.addWidget(label_logo)

            layout_titulo.addWidget(tarjeta_logo, alignment=Qt.AlignHCenter)

        # Nombre del negocio (antes era el texto fijo "POS-Ventas") y, debajo,
        # el nombre del usuario que inició sesión.
        bloque_texto = QVBoxLayout()
        bloque_texto.setSpacing(4)

        self.label_negocio = QLabel(NOMBRE_NEGOCIO_POR_DEFECTO)
        self.label_negocio.setObjectName("sidebarTitle")
        self.label_negocio.setAlignment(Qt.AlignHCenter)
        self.label_negocio.setWordWrap(True)
        bloque_texto.addWidget(self.label_negocio)

        self.label_usuario = QLabel()
        self.label_usuario.setObjectName("sidebarUser")
        self.label_usuario.setAlignment(Qt.AlignHCenter)
        self.label_usuario.setWordWrap(True)
        bloque_texto.addWidget(self.label_usuario)

        layout_titulo.addLayout(bloque_texto)
        layout_sidebar.addWidget(contenedor_titulo)
        self._actualizar_encabezado()

        self.stack = QStackedWidget()

        self.paginas = {
            "🏠 Inicio": DashboardPage(self.usuario),
            "🛒 Ventas": VentasPage(self.usuario),
            "📦 Productos": ProductosPage(self.usuario),
            "🚚 Compras": ComprasPage(self.usuario),
            "📊 Inventario": InventarioPage(self.usuario),
            "👥 Clientes": ClientesPage(self.usuario),
            "💵 Caja": CajaPage(self.usuario),
            "📈 Reportes": ReportesPage(self.usuario),
            "⚙️ Configuración": ConfiguracionPage(self.usuario),
        }
        self.paginas["⚙️ Configuración"].tema_cambiado = self._aplicar_tema

        self.grupo_botones = QButtonGroup(self)
        self.grupo_botones.setExclusive(True)

        for nombre, pagina in self.paginas.items():
            boton = QPushButton(nombre)
            boton.setCheckable(True)
            boton.clicked.connect(lambda _, n=nombre: self._navegar(n))
            layout_sidebar.addWidget(boton)
            self.grupo_botones.addButton(boton)
            self.stack.addWidget(pagina)

        layout_sidebar.addStretch()

        btn_cerrar_sesion = QPushButton("🚪 Cerrar sesión")
        btn_cerrar_sesion.setProperty("class", "secondary")
        btn_cerrar_sesion.clicked.connect(self._cerrar_sesion)
        layout_sidebar.addWidget(btn_cerrar_sesion)
        layout_sidebar.setContentsMargins(0, 0, 0, 12)

        layout_principal.addWidget(sidebar)
        layout_principal.addWidget(self.stack, stretch=1)

        # Seleccionar "Inicio" por defecto
        primer_boton = self.grupo_botones.buttons()[0]
        primer_boton.setChecked(True)
        self.stack.setCurrentIndex(0)

    def _valor_usuario(self, campo: str):
        """Lee un campo del usuario aunque venga como objeto o como diccionario."""
        if isinstance(self.usuario, dict):
            return self.usuario.get(campo)
        return getattr(self.usuario, campo, None)

    def _actualizar_encabezado(self) -> None:
        """Muestra en el sidebar el nombre del negocio y del usuario. Se vuelve
        a llamar al navegar, así un cambio hecho en Configuración se refleja
        sin reiniciar."""
        config = self.config_service.obtener()
        negocio = (config.get("nombre_negocio") or "").strip() or NOMBRE_NEGOCIO_POR_DEFECTO
        self.label_negocio.setText(negocio)

        nombre_usuario = (
            self._valor_usuario("nombre") or self._valor_usuario("usuario") or ""
        )
        self.label_usuario.setText(f"👤 {nombre_usuario}" if nombre_usuario else "")
        self.label_usuario.setVisible(bool(nombre_usuario))

    def _navegar(self, nombre_pagina: str) -> None:
        indice = list(self.paginas.keys()).index(nombre_pagina)
        self.stack.setCurrentIndex(indice)
        self._actualizar_encabezado()

        pagina = self.paginas[nombre_pagina]
        if hasattr(pagina, "actualizar"):
            pagina.actualizar()

    def _aplicar_tema(self, tema: str) -> None:
        nombre_archivo = "dark.qss" if tema == "oscuro" else "light.qss"
        ruta = STYLES_DIR / nombre_archivo
        if ruta.exists():
            self.setStyleSheet(ruta.read_text(encoding="utf-8"))

    def _cerrar_sesion(self) -> None:
        self.close()
        self.cerrar_sesion_callback()