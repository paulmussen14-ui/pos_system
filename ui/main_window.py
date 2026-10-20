"""Ventana principal de la aplicación: sidebar + área de contenido (QStackedWidget)."""

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QStackedWidget, QButtonGroup, QFrame
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap

from ui.dashboard.dashboard_page import DashboardPage
from ui.ventas.ventas_page import VentasPage
from ui.productos.productos_page import ProductosPage
from ui.compras.compras_page import ComprasPage
from ui.inventario.inventario_page import InventarioPage
from ui.clientes.clientes_page import ClientesPage
from ui.caja.caja_page import CajaPage
from ui.reportes.reportes_page import ReportesPage
from ui.rrhh.rrhh_page import RrhhPage
from ui.proformas.proformas_page import ProformasPage
from ui.cupones.cupones_page import CuponesPage
from ui.configuracion.configuracion_page import ConfiguracionPage
from ui.reservas.agenda_page import AgendaPage
from ui.servicios.servicios_page import ServiciosPage
from services.configuracion_service import ConfiguracionService, MODELO_SERVICIOS, MODELO_VENTAS
from ui.tema_iconos import componer_tema
from ui.iconos import icono_menu, icono
from ui.tokens import paleta, establecer_color_marca, ANCHO_SIDEBAR, ESPACIO_SM, ESPACIO_MD, ESPACIO_LG
from config import STYLES_DIR, APP_ICON_PATH, APP_VERSION

# Logo del negocio (el que el cliente sube en Configuración): ocupa todo el ancho
# del menú arriba (sirve para logos anchos tipo banner y para logos cuadrados),
# con un margen interno para que no toque el borde de la tarjeta blanca.
ANCHO_LOGO = ANCHO_SIDEBAR - 2 * ESPACIO_MD
ALTO_LOGO = 104
MARGEN_LOGO = 8
# Si el negocio no tiene logo: cuadro con la inicial del nombre.
TAMANO_INICIAL = 48
ICONO_MENU = 20

# Texto que se muestra en el sidebar si el negocio aún no tiene nombre.
NOMBRE_NEGOCIO_POR_DEFECTO = "Mi Negocio"

ALTO_BARRA_SUPERIOR = 80
# Por debajo de esta altura de ventana se oculta la tarjeta "Nueva venta" del menú
# para que todos los botones sigan cabiendo sin desplazarse.
ALTO_MINIMO_TARJETA_MENU = 780

DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

# Texto pequeño al pie del menú ("" para ocultarlo).
PIE_SIDEBAR = f"POS Local · v{APP_VERSION}"

# Menú lateral: (nombre de la página, ícono). Los grupos con título agrupan por módulo.
# "Inicio" va arriba, sin grupo. El orden de aquí es también el orden del QStackedWidget.
MENU_INICIO = ("Inicio", "inicio")
MENU_AGENDA = ("Agenda", "calendario")   # solo en el modelo de servicios con reserva
MENU_GRUPOS = [
    ("OPERACIÓN", [("Ventas", "carrito"), ("Proformas", "ticket"), ("Caja", "caja_registradora"),
                  ("Clientes", "clientes")]),
    ("SERVICIOS", [("Servicios", "servicio")]),
    ("INVENTARIO", [("Productos", "producto"), ("Compras", "compras"), ("Inventario", "inventario")]),
    ("ADMINISTRACIÓN", [("RRHH", "usuario"), ("Cupones", "etiqueta"), ("Reportes", "reportes"),
                        ("Configuración", "configuracion")]),
]

# Qué se ve en el menú según el modelo de negocio (Configuración → Modelo de negocio).
# Lo que no está en ninguna lista se ve siempre (Inicio, Caja, Clientes, RRHH, Cupones, Reportes, Configuración).
# Productos, Compras e Inventario se quedan: los servicios pueden usar productos (descuentan stock).
PAGINAS_SOLO_VENTAS = {"Ventas", "Proformas"}
PAGINAS_SOLO_SERVICIOS = {"Servicios", "Agenda"}


class MainWindow(QMainWindow):

    def __init__(self, usuario, cerrar_sesion_callback):
        super().__init__()
        self.usuario = usuario
        self.cerrar_sesion_callback = cerrar_sesion_callback
        self.config_service = ConfiguracionService()
        self._tema_actual = "claro"
        self._iconos_menu = {}      # nombre de página -> (botón, nombre del ícono)
        self._logo_cargado = None   # (ruta, fecha de modificación) del logo mostrado
        self._modelo = self.config_service.obtener_modelo_negocio()
        self._titulos_grupo = {}    # título del grupo -> (etiqueta, nombres de sus páginas)

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
            "RRHH": lambda: RrhhPage(self.usuario),
            "Proformas": lambda: ProformasPage(self.usuario),
            "Cupones": lambda: CuponesPage(self.usuario),
            "Configuración": lambda: ConfiguracionPage(self.usuario),
            "Servicios": lambda: ServiciosPage(self.usuario),
            "Agenda": lambda: AgendaPage(self.usuario),
        }

        layout_sidebar.addSpacing(ESPACIO_SM)
        self._agregar_item_menu(layout_sidebar, MENU_INICIO, paginas_por_nombre)
        self._agregar_item_menu(layout_sidebar, MENU_AGENDA, paginas_por_nombre)
        for titulo_grupo, items in MENU_GRUPOS:
            etiqueta = QLabel(titulo_grupo)
            etiqueta.setObjectName("sidebarSection")
            layout_sidebar.addWidget(etiqueta)
            self._titulos_grupo[titulo_grupo] = (etiqueta, [nombre for nombre, _ in items])
            for item in items:
                self._agregar_item_menu(layout_sidebar, item, paginas_por_nombre)

        # En el modelo de servicios, la Agenda es una pantalla propia (botón debajo de Inicio);
        # el Inicio siempre muestra el dashboard.
        self.paginas["Agenda"].navegar = self.ir_a

        self.paginas["Configuración"].tema_cambiado = self._aplicar_tema
        self.paginas["Configuración"].modelo_cambiado = self._aplicar_modelo_negocio
        # Los accesos rápidos y enlaces "ver más" del Inicio abren otras pantallas.
        self.paginas["Inicio"].navegar = self.ir_a
        # Proformas ↔ Ventas: convertir carga la proforma en el carrito de Ventas.
        self.paginas["Proformas"].convertir = self._convertir_proforma
        self.paginas["Ventas"].proforma_guardada = lambda _id: self.paginas["Proformas"].actualizar()

        layout_sidebar.addStretch()
        self.tarjeta_venta = self._crear_tarjeta_nueva_venta()
        layout_sidebar.addWidget(self.tarjeta_venta)
        layout_sidebar.addSpacing(ESPACIO_SM)

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

        self.sidebar = sidebar
        columna_derecha = QWidget()
        layout_derecha = QVBoxLayout(columna_derecha)
        layout_derecha.setContentsMargins(0, 0, 0, 0)
        layout_derecha.setSpacing(0)
        layout_derecha.addWidget(self._crear_barra_superior())
        layout_derecha.addWidget(self.stack, stretch=1)

        layout_principal.addWidget(sidebar)
        layout_principal.addWidget(columna_derecha, stretch=1)

        # Seleccionar "Inicio" por defecto
        primer_boton = self.grupo_botones.buttons()[0]
        primer_boton.setChecked(True)
        self._aplicar_modelo_negocio(self._modelo, inicial=True)

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
        self.label_negocio.setAlignment(Qt.AlignCenter)
        bloque_texto.addWidget(self.label_negocio)

        fila_identidad.addLayout(bloque_texto, stretch=1)
        layout.addLayout(fila_identidad)
        self._actualizar_encabezado()
        return contenedor

    def _crear_tarjeta_nueva_venta(self) -> QFrame:
        """Tarjeta al pie del menú con el botón de la acción más usada: vender."""
        tarjeta = QFrame()
        tarjeta.setObjectName("sidebarCard")
        layout = QVBoxLayout(tarjeta)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.tarjeta_titulo = QLabel("¿Listo para vender?")
        self.tarjeta_titulo.setObjectName("sidebarCardTitulo")
        layout.addWidget(self.tarjeta_titulo)
        self.tarjeta_texto = QLabel("Registra una venta en segundos.")
        self.tarjeta_texto.setObjectName("sidebarCardTexto")
        self.tarjeta_texto.setWordWrap(True)
        layout.addWidget(self.tarjeta_texto)
        layout.addSpacing(6)

        boton = QPushButton("  Nueva venta")
        self.tarjeta_boton = boton
        boton.setObjectName("btnNuevaVenta")
        boton.setCursor(Qt.PointingHandCursor)
        boton.setIconSize(QSize(18, 18))
        boton.setIcon(icono("mas", "#ffffff", 18))
        boton.clicked.connect(self._accion_tarjeta)
        layout.addWidget(boton)

        contenedor = QWidget()
        envoltura = QVBoxLayout(contenedor)
        envoltura.setContentsMargins(ESPACIO_MD - 4, 0, ESPACIO_MD - 4, 0)
        envoltura.addWidget(tarjeta)
        return contenedor

    def _crear_barra_superior(self) -> QWidget:
        """Barra verde sobre el contenido: botón de menú, bienvenida, fecha y hora, y usuario."""
        barra = QWidget()
        barra.setObjectName("topBar")
        barra.setFixedHeight(ALTO_BARRA_SUPERIOR)
        layout = QHBoxLayout(barra)
        layout.setContentsMargins(ESPACIO_MD + 4, 0, ESPACIO_LG, 0)
        layout.setSpacing(ESPACIO_MD)

        self.boton_menu = QPushButton()
        self.boton_menu.setObjectName("btnMenu")
        self.boton_menu.setCursor(Qt.PointingHandCursor)
        self.boton_menu.setIconSize(QSize(22, 22))
        self.boton_menu.setIcon(icono("menu", "#ffffff", 22))
        self.boton_menu.setToolTip("Mostrar u ocultar el menú")
        self.boton_menu.clicked.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        layout.addWidget(self.boton_menu)

        bienvenida = QLabel("Bienvenido")
        bienvenida.setObjectName("topBarBienvenida")
        layout.addWidget(bienvenida)

        layout.addStretch()
        self.label_fecha_hora = QLabel()
        self.label_fecha_hora.setObjectName("topBarFecha")
        layout.addWidget(self.label_fecha_hora)
        layout.addStretch()

        self.label_avatar = QLabel("?")
        self.label_avatar.setObjectName("topBarAvatar")
        self.label_avatar.setFixedSize(36, 36)
        self.label_avatar.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label_avatar)

        datos = QVBoxLayout()
        datos.setSpacing(0)
        self.label_usuario_barra = QLabel()
        self.label_usuario_barra.setObjectName("topBarUsuario")
        rol = QLabel("Administrador")
        rol.setObjectName("topBarRol")
        datos.addWidget(self.label_usuario_barra)
        datos.addWidget(rol)
        layout.addLayout(datos)

        self._actualizar_usuario_barra()
        self._actualizar_reloj()
        self._timer_reloj = QTimer(self)
        self._timer_reloj.setInterval(1000)
        self._timer_reloj.timeout.connect(self._actualizar_reloj)
        self._timer_reloj.start()
        return barra

    def _actualizar_reloj(self) -> None:
        ahora = datetime.now()
        dia = DIAS_SEMANA[ahora.weekday()].capitalize()
        self.label_fecha_hora.setText(
            f"{dia}, {ahora.day} de {MESES[ahora.month - 1]} de {ahora.year}  ·  {ahora:%H:%M:%S}"
        )

    def _actualizar_usuario_barra(self) -> None:
        nombre = self._valor_usuario("nombre") or self._valor_usuario("usuario") or ""
        self.label_usuario_barra.setText(nombre)
        self.label_avatar.setText(nombre[:1].upper() or "?")

    def ir_a(self, nombre_pagina: str) -> None:
        """Abre una pantalla y marca su botón en el menú (lo usan el Inicio y la tarjeta Nueva venta)."""
        boton, _ = self._iconos_menu[nombre_pagina]
        boton.setChecked(True)
        self._navegar(nombre_pagina)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "tarjeta_venta"):
            self.tarjeta_venta.setVisible(self.height() >= ALTO_MINIMO_TARJETA_MENU)

    def _accion_tarjeta(self) -> None:
        """Botón de la tarjeta del menú: nueva venta, o nueva reserva si el negocio da servicios."""
        if self._modelo == MODELO_SERVICIOS:
            self.ir_a("Agenda")
            self.paginas["Agenda"].nueva_reserva()
        else:
            self.ir_a("Ventas")

    def _aplicar_modelo_negocio(self, modelo: str, inicial: bool = False) -> None:
        """Adapta el menú y el Inicio al modelo de negocio: ventas (productos) o
        servicios (reservas). No borra datos; solo muestra u oculta pantallas."""
        self._modelo = modelo if modelo in (MODELO_VENTAS, MODELO_SERVICIOS) else MODELO_VENTAS
        servicios = self._modelo == MODELO_SERVICIOS

        ocultas = PAGINAS_SOLO_VENTAS if servicios else PAGINAS_SOLO_SERVICIOS
        for nombre in PAGINAS_SOLO_VENTAS | PAGINAS_SOLO_SERVICIOS:
            boton, _ = self._iconos_menu[nombre]
            boton.setVisible(nombre not in ocultas)
        for etiqueta, nombres in self._titulos_grupo.values():
            etiqueta.setVisible(any(n not in ocultas for n in nombres))

        # El dashboard adapta sus accesos rápidos al modelo (Nueva reserva en vez de Nueva venta).
        self.paginas["Inicio"].aplicar_modelo(self._modelo)

        if servicios:
            self.tarjeta_titulo.setText("¿Nueva cita?")
            self.tarjeta_texto.setText("Reserva una hora en segundos.")
            self.tarjeta_boton.setText("  Nueva reserva")
        else:
            self.tarjeta_titulo.setText("¿Listo para vender?")
            self.tarjeta_texto.setText("Registra una venta en segundos.")
            self.tarjeta_boton.setText("  Nueva venta")

        self._actualizar_iconos_menu(self._tema_actual)
        if inicial:
            self.stack.setCurrentIndex(list(self.paginas.keys()).index("Inicio"))
        else:
            # Si la pantalla abierta ya no existe en este modelo, ir al Inicio;
            # si no, quedarse donde estaba.
            actual = list(self.paginas.keys())[self.stack.currentIndex()]
            if actual in ocultas:
                self.ir_a("Inicio")

    def _convertir_proforma(self, proforma: dict) -> None:
        self.paginas["Ventas"].cargar_proforma(proforma)
        self.ir_a("Ventas")

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

        if hasattr(self, "label_usuario_barra"):
            self._actualizar_usuario_barra()

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
        # El color de marca (Configuración → Apariencia) se lee aquí para que valga también al abrir.
        establecer_color_marca(self.config_service.obtener().get("color_marca"))
        nombre_archivo = "dark.qss" if tema == "oscuro" else "light.qss"
        ruta = STYLES_DIR / nombre_archivo
        if ruta.exists():
            # Tema base + capa de mejoras (ver ui/tema_iconos.py).
            self.setStyleSheet(componer_tema(ruta.read_text(encoding="utf-8"), tema))
        self._tema_actual = "oscuro" if tema == "oscuro" else "claro"
        self._actualizar_iconos_menu(self._tema_actual)
        # Si ya hay una pantalla abierta, se repinta para que tome los colores nuevos.
        if getattr(self, "_estilos_aplicados", False):
            pagina = list(self.paginas.values())[self.stack.currentIndex()]
            if hasattr(pagina, "actualizar") and pagina is not self.paginas["Configuración"]:
                pagina.actualizar()
        self._estilos_aplicados = True

    def _cerrar_sesion(self) -> None:
        self.close()
        self.cerrar_sesion_callback()