"""Ventana principal de la aplicación: sidebar + área de contenido (QStackedWidget)."""

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QStackedWidget, QButtonGroup, QFrame
)
from PySide6.QtCore import Qt, QSize
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
from ui.tema_iconos import componer_tema
from ui.iconos import icono_menu
from ui.tokens import paleta, ANCHO_SIDEBAR, ESPACIO_SM, ESPACIO_MD
from config import STYLES_DIR, APP_ICON_PATH, APP_VERSION

# Logo del negocio (el que el cliente sube en Configuración): ocupa todo el ancho
# del menú arriba (sirve para logos anchos tipo banner y para logos cuadrados),
# con un margen interno para que no toque el borde de la tarjeta blanca.
ANCHO_LOGO = ANCHO_SIDEBAR - 2 * ESPACIO_MD
ALTO_LOGO = 76
MARGEN_LOGO = 8
# Si el negocio no tiene logo: cuadro con la inicial del nombre.
TAMANO_INICIAL = 48
ICONO_MENU = 20

# Texto que se muestra en el sidebar si el negocio aún no tiene nombre.
NOMBRE_NEGOCIO_POR_DEFECTO = "Mi Negocio"

# Texto pequeño al pie del menú ("" para ocultarlo).
PIE_SIDEBAR = f"POS Local · v{APP_VERSION}"

# Menú lateral: (nombre de la página, ícono). Los grupos con título agrupan por módulo.
# "Inicio" va arriba, sin grupo. El orden de aquí es también el orden del QStackedWidget.
MENU_INICIO = ("Inicio", "inicio")
MENU_GRUPOS = [
    ("OPERACIÓN", [("Ventas", "carrito"), ("Caja", "caja_registradora"), ("Clientes", "clientes")]),
    ("INVENTARIO", [("Productos", "producto"), ("Compras", "compras"), ("Inventario", "inventario")]),
    ("ADMINISTRACIÓN", [("Reportes", "reportes"), ("Configuración", "configuracion")]),
]


class MainWindow(QMainWindow):

    def __init__(self, usuario, cerrar_sesion_callback):
        super().__init__()
        self.usuario = usuario
        self.cerrar_sesion_callback = cerrar_sesion_callback
        self.config_service = ConfiguracionService()
        self._tema_actual = "claro"
        self._iconos_menu = {}      # nombre de página -> (botón, nombre del ícono)
        self._logo_cargado = None   # (ruta, fecha de modificación) del logo mostrado

        self.setWindowTitle("Sistema POS Local - FayzerDEV")
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setMinimumSize(1100, 680)
        self.resize(1366, 768)

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
        layout_sidebar.setContentsMargins(0, 0, 0, ESPACIO_SM)
        layout_sidebar.setSpacing(0)

        layout_sidebar.addWidget(self._crear_encabezado_sidebar())

        self.stack = QStackedWidget()
        self.paginas = {}
        self.grupo_botones = QButtonGroup(self)
        self.grupo_botones.setExclusive(True)

        paginas_por_nombre = {
            "Inicio": lambda: DashboardPage(self.usuario),
            "Ventas": lambda: VentasPage(self.usuario),
            "Caja": lambda: CajaPage(self.usuario),
            "Clientes": lambda: ClientesPage(self.usuario),
            "Productos": lambda: ProductosPage(self.usuario),
            "Compras": lambda: ComprasPage(self.usuario),
            "Inventario": lambda: InventarioPage(self.usuario),
            "Reportes": lambda: ReportesPage(self.usuario),
            "Configuración": lambda: ConfiguracionPage(self.usuario),
        }

        layout_sidebar.addSpacing(ESPACIO_SM)
        self._agregar_item_menu(layout_sidebar, MENU_INICIO, paginas_por_nombre)
        for titulo_grupo, items in MENU_GRUPOS:
            etiqueta = QLabel(titulo_grupo)
            etiqueta.setObjectName("sidebarSection")
            layout_sidebar.addWidget(etiqueta)
            for item in items:
                self._agregar_item_menu(layout_sidebar, item, paginas_por_nombre)

        self.paginas["Configuración"].tema_cambiado = self._aplicar_tema

        layout_sidebar.addStretch()

        btn_cerrar_sesion = QPushButton("  Cerrar sesión")
        btn_cerrar_sesion.setObjectName("navLogout")
        btn_cerrar_sesion.setCursor(Qt.PointingHandCursor)
        btn_cerrar_sesion.setIconSize(QSize(ICONO_MENU, ICONO_MENU))
        btn_cerrar_sesion.clicked.connect(self._cerrar_sesion)
        self._iconos_menu["__salir__"] = (btn_cerrar_sesion, "salir")
        layout_sidebar.addWidget(btn_cerrar_sesion)

        if PIE_SIDEBAR:
            pie = QLabel(PIE_SIDEBAR)
            pie.setObjectName("sidebarPie")
            layout_sidebar.addWidget(pie)

        layout_principal.addWidget(sidebar)
        layout_principal.addWidget(self.stack, stretch=1)

        # Seleccionar "Inicio" por defecto
        primer_boton = self.grupo_botones.buttons()[0]
        primer_boton.setChecked(True)
        self.stack.setCurrentIndex(0)

    def _crear_encabezado_sidebar(self) -> QWidget:
        """Logo del negocio a todo el ancho arriba; debajo, nombre del negocio y usuario.
        Sin logo: la inicial del negocio a la izquierda y los textos a su lado."""
        contenedor = QWidget()
        contenedor.setObjectName("sidebarHeader")
        layout = QVBoxLayout(contenedor)
        layout.setContentsMargins(ESPACIO_MD, ESPACIO_MD, ESPACIO_MD, ESPACIO_MD)
        layout.setSpacing(12)

        # Tarjeta blanca con la imagen del logo (solo se ve si el negocio subió uno).
        self.tarjeta_logo = QFrame()
        self.tarjeta_logo.setObjectName("logoCard")
        self.tarjeta_logo.setFixedSize(ANCHO_LOGO, ALTO_LOGO)
        layout_logo = QVBoxLayout(self.tarjeta_logo)
        layout_logo.setContentsMargins(MARGEN_LOGO, MARGEN_LOGO, MARGEN_LOGO, MARGEN_LOGO)
        self.label_logo = QLabel()
        self.label_logo.setAlignment(Qt.AlignCenter)
        layout_logo.addWidget(self.label_logo)
        layout.addWidget(self.tarjeta_logo)

        fila_identidad = QHBoxLayout()
        fila_identidad.setSpacing(12)

        self.label_inicial = QLabel("M")
        self.label_inicial.setObjectName("logoInicial")
        self.label_inicial.setFixedSize(TAMANO_INICIAL, TAMANO_INICIAL)
        self.label_inicial.setAlignment(Qt.AlignCenter)
        fila_identidad.addWidget(self.label_inicial)

        bloque_texto = QVBoxLayout()
        bloque_texto.setSpacing(2)
        self.label_negocio = QLabel(NOMBRE_NEGOCIO_POR_DEFECTO)
        self.label_negocio.setObjectName("sidebarTitle")
        self.label_negocio.setWordWrap(True)
        bloque_texto.addWidget(self.label_negocio)

        self.label_usuario = QLabel()
        self.label_usuario.setObjectName("sidebarUser")
        self.label_usuario.setWordWrap(True)
        bloque_texto.addWidget(self.label_usuario)

        fila_identidad.addLayout(bloque_texto, stretch=1)
        layout.addLayout(fila_identidad)
        self._actualizar_encabezado()
        return contenedor

    def _agregar_item_menu(self, layout_sidebar, item, paginas_por_nombre) -> None:
        """Crea el botón del menú y construye su página dentro del QStackedWidget."""
        nombre, nombre_icono = item
        pagina = paginas_por_nombre[nombre]()
        self.paginas[nombre] = pagina
        self.stack.addWidget(pagina)

        boton = QPushButton("  " + nombre)
        boton.setObjectName("navItem")
        boton.setCheckable(True)
        boton.setCursor(Qt.PointingHandCursor)
        boton.setIconSize(QSize(ICONO_MENU, ICONO_MENU))
        boton.clicked.connect(lambda _, n=nombre: self._navegar(n))
        layout_sidebar.addWidget(boton)
        self.grupo_botones.addButton(boton)
        self._iconos_menu[nombre] = (boton, nombre_icono)

    def _actualizar_iconos_menu(self, tema: str) -> None:
        """Repinta los íconos del menú con los colores del tema."""
        colores = paleta(tema)
        for boton, nombre_icono in self._iconos_menu.values():
            boton.setIcon(icono_menu(
                nombre_icono, colores["menu_icono"], colores["menu_icono_activo"],
                colores["menu_icono_activo"], ICONO_MENU,
            ))

    def _valor_usuario(self, campo: str):
        """Lee un campo del usuario aunque venga como objeto o como diccionario."""
        if isinstance(self.usuario, dict):
            return self.usuario.get(campo)
        return getattr(self.usuario, campo, None)

    def _actualizar_encabezado(self) -> None:
        """Muestra en el sidebar el logo y el nombre del negocio y el usuario. Se vuelve
        a llamar al navegar, así un cambio hecho en Configuración se refleja
        sin reiniciar."""
        config = self.config_service.obtener()
        negocio = (config.get("nombre_negocio") or "").strip() or NOMBRE_NEGOCIO_POR_DEFECTO
        self.label_negocio.setText(negocio)
        self._actualizar_logo(config.get("logo_path"), negocio)

        nombre_usuario = (
            self._valor_usuario("nombre") or self._valor_usuario("usuario") or ""
        )
        self.label_usuario.setText(nombre_usuario)
        self.label_usuario.setVisible(bool(nombre_usuario))

    def _actualizar_logo(self, ruta_logo, negocio: str) -> None:
        """Muestra el logo del NEGOCIO (el de Configuración). Si no hay logo o el
        archivo no se puede leer, muestra la inicial del nombre del negocio."""
        pixmap = QPixmap()
        if ruta_logo and os.path.isfile(ruta_logo):
            marca = (ruta_logo, os.path.getmtime(ruta_logo))
            if marca == self._logo_cargado:
                return
            pixmap = QPixmap(ruta_logo)
            self._logo_cargado = marca if not pixmap.isNull() else None
        else:
            self._logo_cargado = None

        if not pixmap.isNull():
            # Se escala al tamaño real en pantalla (con su escala de pantalla) para que no se vea borroso.
            escala = self.devicePixelRatioF()
            ancho = int((ANCHO_LOGO - 2 * MARGEN_LOGO) * escala)
            alto = int((ALTO_LOGO - 2 * MARGEN_LOGO) * escala)
            ajustado = pixmap.scaled(ancho, alto, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            ajustado.setDevicePixelRatio(escala)
            self.label_logo.setPixmap(ajustado)
            self.tarjeta_logo.setVisible(True)
            self.label_inicial.setVisible(False)
        else:
            self.label_inicial.setText(negocio[:1].upper() or "?")
            self.tarjeta_logo.setVisible(False)
            self.label_inicial.setVisible(True)

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
            # Tema base + capa de mejoras (ver ui/tema_iconos.py).
            self.setStyleSheet(componer_tema(ruta.read_text(encoding="utf-8"), tema))
        self._tema_actual = "oscuro" if tema == "oscuro" else "claro"
        self._actualizar_iconos_menu(self._tema_actual)

    def _cerrar_sesion(self) -> None:
        self.close()
        self.cerrar_sesion_callback()