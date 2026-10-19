"""Página de Inicio / Dashboard: resumen del día.

Diseño tipo "SupaPOS": tarjetas de resumen con variación contra ayer, gráfico de
ventas, productos más vendidos, últimas ventas, alertas de inventario y, a la
derecha, un panel con el estado de la caja y accesos rápidos.

Se refresca sola cada 60 s (si la pantalla está visible) y al cambiar
de fecha, para que nunca muestre datos de ayer. La carga corre en un hilo
aparte (Worker) para no congelar la ventana.
"""

from datetime import date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QScrollArea,
    QFrame, QPushButton, QProgressBar, QSizePolicy,
)
from PySide6.QtCore import Qt, QThreadPool, QTimer, QSize

from config import DIAS_RETENCION
from services.reporte_service import ReporteService
from services.configuracion_service import ConfiguracionService
from ui.iconos import pixmap_icono, icono
from ui.tokens import paleta
from ui.widgets.line_chart import _AreaCanvas
from utils.validators import formatear_moneda
from utils.worker import Worker

_INTERVALO_REFRESCO_MS = 60_000  # 1 minuto
_ANCHO_PANEL = 290
_ANCHO_MINIMO_PARA_PANEL = 1080  # por debajo de este ancho de página se oculta el panel derecho
_TONOS_RANKING = ["exito", "info", "aviso", "primario", "exito"]
_MAX_ALERTAS = 4


def _repulir(widget: QWidget) -> None:
    """Hace que Qt vuelva a leer el QSS después de cambiar una propiedad dinámica."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _vaciar(layout) -> None:
    """Quita y destruye todo lo que hay dentro de un layout."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            _vaciar(item.layout())
            item.layout().deleteLater()


def _variacion(hoy: float, ayer: float) -> tuple[str, str]:
    """Texto y tendencia ('sube' | 'baja' | 'igual') de la variación contra ayer."""
    if not ayer:
        return ("Sin datos de ayer", "igual") if not hoy else ("Sin ventas ayer", "igual")
    pct = (hoy - ayer) / ayer * 100
    if pct > 0.05:
        return f"↑ {pct:.1f}% vs ayer", "sube"
    if pct < -0.05:
        return f"↓ {abs(pct):.1f}% vs ayer", "baja"
    return "= igual que ayer", "igual"


class _Elidida(QLabel):
    """Etiqueta de una línea que, si el texto no cabe, lo corta con "…" en vez de
    ensanchar la tarjeta. El texto completo queda en el tooltip."""

    def __init__(self, texto: str = "", parent=None):
        super().__init__(parent)
        self._completo = texto
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self._aplicar()

    def setText(self, texto: str) -> None:  # noqa: N802 (nombre de Qt)
        self._completo = texto
        self._aplicar()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._aplicar()

    def _aplicar(self) -> None:
        ancho = max(self.width(), 20)
        super().setText(self.fontMetrics().elidedText(self._completo, Qt.ElideRight, ancho))
        self.setToolTip(self._completo if self.text() != self._completo else "")


class _TarjetaKpi(QFrame):
    """Tarjeta de resumen: título, valor grande, variación y un ícono en círculo."""

    def __init__(self, titulo: str, nombre_icono: str, tono: str, parent=None):
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self._nombre_icono = nombre_icono
        self._tono = tono

        grilla = QGridLayout(self)
        grilla.setContentsMargins(18, 16, 18, 16)
        grilla.setHorizontalSpacing(8)
        grilla.setVerticalSpacing(4)

        self.label_titulo = _Elidida(titulo)
        self.label_titulo.setObjectName("kpiTitulo")
        self.label_valor = QLabel("—")
        self.label_valor.setObjectName("kpiValor")
        self.label_delta = _Elidida("")
        self.label_delta.setObjectName("kpiDelta")

        self.burbuja = QLabel()
        self.burbuja.setObjectName("kpiIcono")
        self.burbuja.setProperty("tono", tono)
        self.burbuja.setFixedSize(40, 40)
        self.burbuja.setAlignment(Qt.AlignCenter)

        grilla.addWidget(self.label_titulo, 0, 0)
        grilla.addWidget(self.burbuja, 0, 1, Qt.AlignTop | Qt.AlignRight)
        grilla.addWidget(self.label_valor, 1, 0, 1, 2)
        grilla.addWidget(self.label_delta, 2, 0, 1, 2)
        grilla.setColumnStretch(0, 1)
        # El valor grande nunca ensancha la tarjeta: si es muy largo, baja de tamaño (ver set_valor).
        self.label_valor.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.label_valor.setMinimumWidth(0)

    def pintar_icono(self, colores: dict) -> None:
        self.burbuja.setPixmap(pixmap_icono(self._nombre_icono, colores[self._tono], 20))

    def set_valor(self, texto: str) -> None:
        self.label_valor.setText(texto)
        largo = "normal" if len(texto) <= 12 else "medio" if len(texto) <= 14 else "largo"
        self.label_valor.setProperty("largo", largo)
        _repulir(self.label_valor)

    def set_variacion(self, texto: str, tendencia: str) -> None:
        self.label_delta.setText(texto)
        self.label_delta.setProperty("tendencia", tendencia)
        _repulir(self.label_delta)


class _TarjetaLista(QFrame):
    """Tarjeta blanca con título, enlace "ver más" opcional y un cuerpo vertical."""

    def __init__(self, titulo: str, texto_enlace: str = "", al_pulsar_enlace=None, parent=None):
        super().__init__(parent)
        self.setObjectName("homeCard")

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(20, 18, 20, 14)
        raiz.setSpacing(6)

        cabecera = QHBoxLayout()
        etiqueta = QLabel(titulo)
        etiqueta.setObjectName("homeCardTitulo")
        cabecera.addWidget(etiqueta)
        cabecera.addStretch()
        if texto_enlace:
            enlace = QPushButton(texto_enlace)
            enlace.setObjectName("homeCardVerMas")
            enlace.setCursor(Qt.PointingHandCursor)
            enlace.setFlat(True)
            if al_pulsar_enlace:
                enlace.clicked.connect(al_pulsar_enlace)
            cabecera.addWidget(enlace)
        raiz.addLayout(cabecera)

        self.cuerpo = QVBoxLayout()
        self.cuerpo.setSpacing(0)
        raiz.addLayout(self.cuerpo, 1)


def _crear_fila(titulo: str, subtitulo: str, monto: str, sub_monto: str = "",
                pixmap=None, texto_burbuja: str = "", tono: str = "exito",
                ultima: bool = False) -> QFrame:
    """Fila de lista: burbuja (ícono o número) + dos líneas de texto + monto a la derecha."""
    fila = QFrame()
    fila.setObjectName("filaLista")
    fila.setProperty("ultima", "true" if ultima else "false")
    disposicion = QHBoxLayout(fila)
    disposicion.setContentsMargins(0, 10, 0, 10)
    disposicion.setSpacing(12)

    burbuja = QLabel()
    burbuja.setObjectName("filaBurbuja")
    burbuja.setProperty("tono", tono)
    burbuja.setFixedSize(36, 36)
    burbuja.setAlignment(Qt.AlignCenter)
    if pixmap is not None:
        burbuja.setPixmap(pixmap)
    else:
        burbuja.setText(texto_burbuja)
    disposicion.addWidget(burbuja)

    textos = QVBoxLayout()
    textos.setSpacing(1)
    l_titulo = _Elidida(titulo)
    l_titulo.setObjectName("filaTitulo")
    l_sub = _Elidida(subtitulo)
    l_sub.setObjectName("filaSub")
    textos.addWidget(l_titulo)
    textos.addWidget(l_sub)
    disposicion.addLayout(textos, 1)

    derecha = QVBoxLayout()
    derecha.setSpacing(1)
    l_monto = QLabel(monto)
    l_monto.setObjectName("filaMonto")
    l_monto.setAlignment(Qt.AlignRight)
    derecha.addWidget(l_monto)
    if sub_monto:
        l_sub_monto = QLabel(sub_monto)
        l_sub_monto.setObjectName("filaSub")
        l_sub_monto.setAlignment(Qt.AlignRight)
        derecha.addWidget(l_sub_monto)
    disposicion.addLayout(derecha)
    return fila


def _mensaje_vacio(texto: str, clase: str = "badgeNeutral") -> QWidget:
    contenedor = QWidget()
    disposicion = QHBoxLayout(contenedor)
    disposicion.setContentsMargins(0, 14, 0, 14)
    etiqueta = QLabel(texto)
    etiqueta.setProperty("class", clase)
    disposicion.addWidget(etiqueta)
    disposicion.addStretch()
    return contenedor


class DashboardPage(QWidget):

    def __init__(self, usuario, parent=None):
        super().__init__(parent)
        self.usuario = usuario
        self.reporte_service = ReporteService()
        self.config_service = ConfiguracionService()
        # La ventana principal asigna aquí una función navegar(nombre_pagina) para que
        # los accesos rápidos y los enlaces "ver más" abran la pantalla correspondiente.
        self.navegar = None
        self._req_id = 0  # descarta resultados de una carga anterior si se refresca de nuevo antes de que termine
        self._fecha_actual = date.today()
        self._botones_acceso: list[tuple[QPushButton, str]] = []
        self._construir_ui()
        self.actualizar()

        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVALO_REFRESCO_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------------
    # Construcción de la pantalla
    # ------------------------------------------------------------------
    def _ir(self, destino: str) -> None:
        if self.navegar:
            self.navegar(destino)

    def _nombre_usuario(self) -> str:
        for campo in ("nombre", "usuario"):
            valor = self.usuario.get(campo) if isinstance(self.usuario, dict) else getattr(self.usuario, campo, None)
            if valor:
                return str(valor)
        return ""

    def _construir_ui(self) -> None:
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        contenido = QWidget()
        contenido.setObjectName("homeContenido")
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(24, 24, 24, 24)
        columna.setSpacing(20)

        # --- Encabezado ---
        titulo = QLabel("Resumen de hoy")
        titulo.setObjectName("homeTitulo")
        columna.addWidget(titulo)

        nombre = self._nombre_usuario()
        saludo = f"Hola, {nombre}. " if nombre else ""
        subtitulo = QLabel(f"{saludo}Esto es lo que está pasando hoy en tu negocio.")
        subtitulo.setObjectName("homeSubtitulo")
        columna.addWidget(subtitulo)

        self.label_error = QLabel("")
        self.label_error.setProperty("class", "badgeDanger")
        self.label_error.setVisible(False)
        columna.addWidget(self.label_error, 0, Qt.AlignLeft)

        # --- Tarjetas de resumen ---
        fila_kpi = QHBoxLayout()
        fila_kpi.setSpacing(12)
        self.kpi_ventas = _TarjetaKpi("Ventas del día", "moneda", "exito")
        self.kpi_caja = _TarjetaKpi("Dinero en caja", "caja_registradora", "info")
        self.kpi_utilidad = _TarjetaKpi("Utilidad bruta", "tendencia", "aviso")
        self.kpi_ticket = _TarjetaKpi("Ticket medio", "tarjeta", "primario")
        self._kpis = (self.kpi_ventas, self.kpi_caja, self.kpi_utilidad, self.kpi_ticket)
        for tarjeta in self._kpis:
            fila_kpi.addWidget(tarjeta, 1)
        columna.addLayout(fila_kpi)

        # --- Fila 1: gráfico de ventas + productos más vendidos ---
        fila_1 = QHBoxLayout()
        fila_1.setSpacing(16)

        tarjeta_grafico = _TarjetaLista(f"Ventas por día (últimos {DIAS_RETENCION} días)")
        self.canvas_ventas = _AreaCanvas()
        self.canvas_ventas.setMinimumHeight(230)
        self.canvas_ventas.setMinimumWidth(0)
        tarjeta_grafico.cuerpo.addWidget(self.canvas_ventas)
        fila_1.addWidget(tarjeta_grafico, 3)

        self.tarjeta_top = _TarjetaLista("Productos más vendidos", "Ver productos", lambda: self._ir("Productos"))
        fila_1.addWidget(self.tarjeta_top, 2)
        columna.addLayout(fila_1)

        # --- Fila 2: últimas ventas + alertas de inventario ---
        fila_2 = QHBoxLayout()
        fila_2.setSpacing(16)
        self.tarjeta_ventas = _TarjetaLista("Últimas ventas", "Ver todas", lambda: self._ir("Ventas"))
        self.tarjeta_alertas = _TarjetaLista("Alertas de inventario", "Ver inventario", lambda: self._ir("Inventario"))
        fila_2.addWidget(self.tarjeta_ventas, 1)
        fila_2.addWidget(self.tarjeta_alertas, 1)
        columna.addLayout(fila_2)

        columna.addStretch()
        scroll.setWidget(contenido)
        raiz.addWidget(scroll, 1)

        # --- Panel derecho (en lugar del carrito) ---
        self.panel_derecho = self._construir_panel_derecho()
        raiz.addWidget(self.panel_derecho)

    def _construir_panel_derecho(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panelDerecho")
        panel.setFixedWidth(_ANCHO_PANEL)

        columna = QVBoxLayout(panel)
        columna.setContentsMargins(20, 24, 20, 20)
        columna.setSpacing(14)

        titulo = QLabel("Caja")
        titulo.setObjectName("panelTitulo")
        columna.addWidget(titulo)

        # Tarjeta de estado de caja
        self.tarjeta_caja = QFrame()
        self.tarjeta_caja.setObjectName("panelCaja")
        caja = QVBoxLayout(self.tarjeta_caja)
        caja.setContentsMargins(16, 14, 16, 14)
        caja.setSpacing(4)

        self.badge_caja = QLabel("Cerrada")
        self.badge_caja.setProperty("class", "badgeDanger")
        caja.addWidget(self.badge_caja, 0, Qt.AlignLeft)

        self.label_caja_monto = QLabel(formatear_moneda(0))
        self.label_caja_monto.setObjectName("cajaMonto")
        caja.addWidget(self.label_caja_monto)

        self.label_caja_detalle = QLabel("Abre la caja para empezar a vender.")
        self.label_caja_detalle.setObjectName("cajaDetalle")
        self.label_caja_detalle.setWordWrap(True)
        caja.addWidget(self.label_caja_detalle)

        self.label_clientes_hoy = QLabel("Clientes atendidos hoy: 0")
        self.label_clientes_hoy.setObjectName("cajaDetalle")
        caja.addWidget(self.label_clientes_hoy)

        self.boton_caja = QPushButton("Abrir caja")
        self.boton_caja.setObjectName("btnCaja")
        self.boton_caja.setCursor(Qt.PointingHandCursor)
        self.boton_caja.clicked.connect(lambda: self._ir("Caja"))
        caja.addSpacing(6)
        caja.addWidget(self.boton_caja)
        columna.addWidget(self.tarjeta_caja)

        # Accesos rápidos
        seccion = QLabel("Accesos rápidos")
        seccion.setObjectName("panelSeccion")
        columna.addWidget(seccion)

        grilla = QGridLayout()
        grilla.setHorizontalSpacing(10)
        grilla.setVerticalSpacing(10)
        accesos = [
            ("Venta", "carrito", "Ventas", "Nueva venta"),
            ("Compra", "compras", "Compras", "Nueva compra"),
            ("Cliente", "clientes", "Clientes", "Nuevo cliente"),
            ("Producto", "producto", "Productos", "Nuevo producto"),
        ]
        for i, (texto, nombre_icono, destino, ayuda) in enumerate(accesos):
            boton = QPushButton(" " + texto)
            boton.setToolTip(ayuda)
            boton.setObjectName("btnAcceso")
            boton.setCursor(Qt.PointingHandCursor)
            boton.setIconSize(QSize(18, 18))
            boton.clicked.connect(lambda _=False, d=destino: self._ir(d))
            self._botones_acceso.append((boton, nombre_icono))
            grilla.addWidget(boton, i // 2, i % 2)
        columna.addLayout(grilla)

        # Métodos de pago
        self.titulo_pagos = QLabel(f"Métodos de pago (últimos {DIAS_RETENCION} días)")
        self.titulo_pagos.setObjectName("panelSeccion")
        columna.addSpacing(4)
        columna.addWidget(self.titulo_pagos)

        self.lista_pagos = QVBoxLayout()
        self.lista_pagos.setSpacing(10)
        columna.addLayout(self.lista_pagos)

        columna.addStretch()
        return panel

    def resizeEvent(self, event) -> None:
        """En ventanas angostas se oculta el panel derecho para que el resto respire."""
        super().resizeEvent(event)
        self.panel_derecho.setVisible(self.width() >= _ANCHO_MINIMO_PARA_PANEL)

    # ------------------------------------------------------------------
    # Carga de datos
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        """Se ejecuta cada minuto: si cambió el día, recarga siempre; si no,
        refresca solo cuando la pantalla está visible."""
        hoy = date.today()
        if hoy != self._fecha_actual:
            self._fecha_actual = hoy
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
        self.label_error.setText("No se pudo cargar el resumen del negocio.")
        self.label_error.setVisible(True)
        _repulir(self.label_error)

    def _on_resumen_listo(self, req_id: int, resumen: dict) -> None:
        if req_id != self._req_id:
            return  # respuesta vieja, se descarta
        self.label_error.setVisible(False)

        config = self.config_service.obtener()
        moneda = config.get("moneda", "S/")
        tema = "oscuro" if config.get("tema") == "oscuro" else "claro"
        colores = paleta(tema)

        self._pintar_tarjetas(resumen, moneda, colores)
        self._pintar_grafico(resumen, colores)
        self._pintar_top_productos(resumen, moneda, colores)
        self._pintar_ultimas_ventas(resumen, moneda, colores)
        self._pintar_alertas(resumen, colores)
        self._pintar_panel(resumen, moneda, colores)

    # ------------------------------------------------------------------
    # Pintado de cada bloque
    # ------------------------------------------------------------------
    def _pintar_tarjetas(self, resumen: dict, moneda: str, colores: dict) -> None:
        comp = resumen["comparativo"]
        ventas_hoy = resumen["ventas_del_dia_total"]
        cantidad_hoy = resumen["ventas_del_dia_cantidad"]
        utilidad_hoy = resumen["utilidad_del_dia"]
        promedio_hoy = ventas_hoy / cantidad_hoy if cantidad_hoy else 0.0
        promedio_ayer = comp["total_ayer"] / comp["cantidad_ayer"] if comp["cantidad_ayer"] else 0.0

        self.kpi_ventas.set_valor(formatear_moneda(ventas_hoy, moneda))
        self.kpi_ventas.set_variacion(*_variacion(ventas_hoy, comp["total_ayer"]))

        # Dinero que hay en la caja ahora (efectivo esperado de la sesión abierta).
        caja = resumen["estado_caja"]
        if caja.get("abierta"):
            self.kpi_caja.set_valor(formatear_moneda(caja["monto_esperado"], moneda))
            self.kpi_caja.set_variacion(f"Apertura {formatear_moneda(caja['monto_apertura'], moneda)}", "igual")
        else:
            self.kpi_caja.set_valor(formatear_moneda(0, moneda))
            self.kpi_caja.set_variacion("Caja cerrada", "igual")

        self.kpi_utilidad.set_valor(formatear_moneda(utilidad_hoy, moneda))
        self.kpi_utilidad.set_variacion(*_variacion(utilidad_hoy, resumen["utilidad_ayer"]))

        self.kpi_ticket.set_valor(formatear_moneda(promedio_hoy, moneda))
        self.kpi_ticket.set_variacion(*_variacion(promedio_hoy, promedio_ayer))

        for tarjeta in self._kpis:
            tarjeta.pintar_icono(colores)

    def _pintar_grafico(self, resumen: dict, colores: dict) -> None:
        self.canvas_ventas.set_colores(colores["exito"], colores["texto_tenue"], colores["borde"])
        self.canvas_ventas.set_datos([(f["etiqueta"], f["total"]) for f in resumen["ventas_por_dia"]])

    def _pintar_top_productos(self, resumen: dict, moneda: str, colores: dict) -> None:
        _vaciar(self.tarjeta_top.cuerpo)
        productos = resumen["productos_mas_vendidos"][:5]
        if not productos:
            self.tarjeta_top.cuerpo.addWidget(_mensaje_vacio("Aún no hay ventas registradas."))
            return
        for i, fila in enumerate(productos):
            self.tarjeta_top.cuerpo.addWidget(_crear_fila(
                titulo=fila["nombre"],
                subtitulo=f"{fila['cantidad_total']:g} unidades",
                monto=formatear_moneda(fila["monto_total"], moneda),
                texto_burbuja=str(i + 1),
                tono=_TONOS_RANKING[i % len(_TONOS_RANKING)],
                ultima=(i == len(productos) - 1),
            ))

    def _pintar_ultimas_ventas(self, resumen: dict, moneda: str, colores: dict) -> None:
        _vaciar(self.tarjeta_ventas.cuerpo)
        ventas = resumen["ultimas_ventas"]
        if not ventas:
            self.tarjeta_ventas.cuerpo.addWidget(_mensaje_vacio("Todavía no hay ventas."))
            return
        pixmap = pixmap_icono("ticket", colores["exito"], 18)
        for i, venta in enumerate(ventas):
            fecha = venta["fecha"] or ""
            hora = fecha[11:16]
            cuando = hora if venta["es_hoy"] else f"{fecha[8:10]}/{fecha[5:7]} {hora}"
            cliente = venta["cliente_nombre"] or "Cliente general"
            self.tarjeta_ventas.cuerpo.addWidget(_crear_fila(
                titulo=venta["metodo_pago_nombre"] or "Sin método de pago",
                subtitulo=f"{cliente} · {cuando}",
                monto=formatear_moneda(venta["total"], moneda),
                pixmap=pixmap,
                tono="exito",
                ultima=(i == len(ventas) - 1),
            ))

    def _pintar_alertas(self, resumen: dict, colores: dict) -> None:
        cuerpo = self.tarjeta_alertas.cuerpo
        _vaciar(cuerpo)
        agotados = resumen["agotados"]
        bajos = resumen["stock_bajo"]
        pendientes = [("critico", p) for p in agotados] + [("bajo", p) for p in bajos]
        if not pendientes:
            cuerpo.addWidget(_mensaje_vacio("Todo el inventario está en orden.", "badgeOk"))
            return

        pixmap_critico = pixmap_icono("alerta", colores["peligro"], 18)
        pixmap_bajo = pixmap_icono("alerta", colores["aviso"], 18)
        cuerpo.addSpacing(6)
        for nivel, producto in pendientes[:_MAX_ALERTAS]:
            alerta = QFrame()
            alerta.setObjectName("alertaStock")
            alerta.setProperty("nivel", nivel)
            fila = QHBoxLayout(alerta)
            fila.setContentsMargins(12, 10, 12, 10)
            fila.setSpacing(10)

            icono_alerta = QLabel()
            icono_alerta.setPixmap(pixmap_critico if nivel == "critico" else pixmap_bajo)
            fila.addWidget(icono_alerta)

            textos = QVBoxLayout()
            textos.setSpacing(1)
            nombre = _Elidida(producto.nombre)
            nombre.setObjectName("filaTitulo")
            detalle = _Elidida(
                "Agotado" if nivel == "critico"
                else f"Bajo: quedan {producto.stock_actual:g} {producto.unidad_medida} (mín. {producto.stock_minimo:g})"
            )
            detalle.setObjectName("alertaDetalle")
            textos.addWidget(nombre)
            textos.addWidget(detalle)
            fila.addLayout(textos, 1)

            boton = QPushButton("Reponer")
            boton.setObjectName("btnAlerta")
            boton.setProperty("nivel", nivel)
            boton.setCursor(Qt.PointingHandCursor)
            boton.clicked.connect(lambda _=False: self._ir("Compras"))
            fila.addWidget(boton)

            cuerpo.addWidget(alerta)
            cuerpo.addSpacing(8)

        restantes = len(pendientes) - _MAX_ALERTAS
        if restantes > 0:
            mas = QLabel(f"+ {restantes} producto(s) más con alerta")
            mas.setObjectName("filaSub")
            cuerpo.addWidget(mas)

    def _pintar_panel(self, resumen: dict, moneda: str, colores: dict) -> None:
        caja = resumen["estado_caja"]
        if caja.get("abierta"):
            self.badge_caja.setText("Abierta")
            self.badge_caja.setProperty("class", "badgeOk")
            self.label_caja_monto.setText(formatear_moneda(caja["monto_esperado"], moneda))
            self.label_caja_detalle.setText(
                f"Efectivo esperado en caja · apertura {formatear_moneda(caja['monto_apertura'], moneda)}"
            )
            self.boton_caja.setText("Ir a Caja")
        else:
            self.badge_caja.setText("Cerrada")
            self.badge_caja.setProperty("class", "badgeDanger")
            self.label_caja_monto.setText(formatear_moneda(0, moneda))
            self.label_caja_detalle.setText("Abre la caja para empezar a vender.")
            self.boton_caja.setText("Abrir caja")
        _repulir(self.badge_caja)

        self.label_clientes_hoy.setText(f"Clientes atendidos hoy: {int(resumen['comparativo']['clientes_hoy'])}")

        for boton, nombre_icono in self._botones_acceso:
            boton.setIcon(icono(nombre_icono, colores["texto_suave"], 18))

        # Métodos de pago: nombre + monto + barra con su porcentaje del total
        _vaciar(self.lista_pagos)
        metodos = resumen["ventas_metodo_pago"][:4]
        total = sum(m["total"] for m in metodos) or 0.0
        if not metodos or not total:
            self.lista_pagos.addWidget(_mensaje_vacio("Sin ventas todavía."))
            return
        for metodo in metodos:
            porcentaje = metodo["total"] / total * 100
            bloque = QVBoxLayout()
            bloque.setSpacing(4)
            fila = QHBoxLayout()
            nombre = _Elidida(f"{metodo['metodo']} · {porcentaje:.0f}%")
            nombre.setObjectName("filaTitulo")
            monto = QLabel(formatear_moneda(metodo["total"], moneda))
            monto.setObjectName("filaMonto")
            monto.setAlignment(Qt.AlignRight)
            fila.addWidget(nombre, 1)
            fila.addWidget(monto)
            bloque.addLayout(fila)
            barra = QProgressBar()
            barra.setObjectName("barraPago")
            barra.setRange(0, 1000)
            barra.setValue(int(porcentaje * 10))
            barra.setTextVisible(False)
            bloque.addWidget(barra)
            self.lista_pagos.addLayout(bloque)
