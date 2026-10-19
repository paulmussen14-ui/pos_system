"""Pestaña "Apariencia" de Configuración: el cliente elige el color de su sistema.

Elige un color de la lista (o uno propio) y el sistema calcula solo los tonos del botón
principal, los resaltados, los textos y el menú lateral, cuidando que todo se lea bien
(ver ui/color_marca.py). Una vista previa muestra cómo quedará antes de aplicarlo.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFrame,
    QColorDialog, QMessageBox,
)

from services.configuracion_service import ConfiguracionService, ConfiguracionError
from ui.color_marca import COLOR_DEFECTO, PRESETS, generar, normalizar
from ui.tokens import PALETAS, ESPACIO_SM, ESPACIO_MD
from ui.widgets.card import Card

TAM_MUESTRA = 36


class AparienciaTab(QWidget):

    # Se emite después de guardar el color: la ventana principal vuelve a pintar el sistema.
    color_aplicado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_service = ConfiguracionService()
        self._muestras: list[tuple[QPushButton, str]] = []
        self._color = COLOR_DEFECTO
        self._construir_ui()
        self.cargar()

    # ------------------------------------------------------ Interfaz ----
    def _construir_ui(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, ESPACIO_MD, 0, 0)
        raiz.setSpacing(ESPACIO_MD)

        tarjeta = Card("Color de tu sistema")
        ayuda = QLabel(
            "Elige el color que represente a tu negocio. El sistema calcula solo los tonos de "
            "los botones, los resaltados, los textos y el menú lateral, y ajusta lo necesario "
            "para que todo se lea bien.")
        ayuda.setProperty("class", "ayuda")
        ayuda.setWordWrap(True)
        tarjeta.cuerpo.addWidget(ayuda)

        grilla = QGridLayout()
        grilla.setHorizontalSpacing(ESPACIO_SM + 4)
        grilla.setVerticalSpacing(ESPACIO_SM)
        for i, (nombre, color) in enumerate(PRESETS):
            boton = QPushButton()
            boton.setCheckable(True)
            boton.setCursor(Qt.PointingHandCursor)
            boton.setFixedSize(TAM_MUESTRA, TAM_MUESTRA)
            boton.setToolTip(nombre)
            boton.clicked.connect(lambda _=False, c=color: self._elegir(c))
            self._muestras.append((boton, color))
            grilla.addWidget(boton, 0, i)
        grilla.setColumnStretch(len(PRESETS), 1)
        tarjeta.cuerpo.addLayout(grilla)

        fila = QHBoxLayout()
        self.boton_otro = QPushButton("Otro color...")
        self.boton_otro.setProperty("class", "secondary")
        self.boton_otro.setToolTip("Elige cualquier color; el sistema lo ajusta para que se lea bien.")
        self.boton_otro.clicked.connect(self._elegir_otro)
        fila.addWidget(self.boton_otro)
        self.label_color = QLabel("")
        fila.addWidget(self.label_color)
        fila.addStretch()
        tarjeta.cuerpo.addLayout(fila)

        self.label_aviso = QLabel("")
        self.label_aviso.setProperty("class", "ayuda")
        self.label_aviso.setWordWrap(True)
        tarjeta.cuerpo.addWidget(self.label_aviso)
        raiz.addWidget(tarjeta)

        tarjeta_prev = Card("Vista previa")
        self.preview = QFrame()
        self.preview.setObjectName("previewMarca")
        capa = QHBoxLayout(self.preview)
        capa.setContentsMargins(0, 0, 0, 0)
        capa.setSpacing(0)

        self.prev_menu = QFrame()
        self.prev_menu.setFixedWidth(150)
        capa_menu = QVBoxLayout(self.prev_menu)
        capa_menu.setContentsMargins(10, 12, 10, 12)
        capa_menu.setSpacing(6)
        self.prev_item_activo = QLabel("  Inicio")
        self.prev_item_2 = QLabel("  Reservas")
        self.prev_item_3 = QLabel("  Caja")
        for etiqueta in (self.prev_item_activo, self.prev_item_2, self.prev_item_3):
            capa_menu.addWidget(etiqueta)
        capa_menu.addStretch()
        capa.addWidget(self.prev_menu)

        self.prev_panel = QFrame()
        capa_panel = QVBoxLayout(self.prev_panel)
        capa_panel.setContentsMargins(16, 14, 16, 14)
        capa_panel.setSpacing(10)
        self.prev_titulo = QLabel("Resumen del día")
        self.prev_texto = QLabel("Así se verán tus botones, avisos y enlaces.")
        fila_botones = QHBoxLayout()
        self.prev_boton = QLabel("Guardar")
        self.prev_boton.setAlignment(Qt.AlignCenter)
        self.prev_badge = QLabel("Confirmada")
        self.prev_badge.setAlignment(Qt.AlignCenter)
        self.prev_enlace = QLabel("Ver todas")
        fila_botones.addWidget(self.prev_boton)
        fila_botones.addWidget(self.prev_badge)
        fila_botones.addWidget(self.prev_enlace)
        fila_botones.addStretch()
        capa_panel.addWidget(self.prev_titulo)
        capa_panel.addWidget(self.prev_texto)
        capa_panel.addLayout(fila_botones)
        capa_panel.addStretch()
        capa.addWidget(self.prev_panel, 1)
        self.preview.setMinimumHeight(150)
        tarjeta_prev.cuerpo.addWidget(self.preview)
        raiz.addWidget(tarjeta_prev)

        botones = QHBoxLayout()
        self.boton_aplicar = QPushButton("Aplicar color")
        self.boton_aplicar.setProperty("class", "success")
        self.boton_aplicar.clicked.connect(self._aplicar)
        self.boton_restablecer = QPushButton("Volver al verde original")
        self.boton_restablecer.setProperty("class", "secondary")
        self.boton_restablecer.clicked.connect(self._restablecer)
        botones.addWidget(self.boton_aplicar)
        botones.addWidget(self.boton_restablecer)
        botones.addStretch()
        raiz.addLayout(botones)
        raiz.addStretch()

    # ------------------------------------------------------- Lógica ----
    def cargar(self) -> None:
        self._elegir(self.config_service.obtener_color_marca() or COLOR_DEFECTO)

    def _tema(self) -> str:
        return "oscuro" if self.config_service.obtener().get("tema") == "oscuro" else "claro"

    def _elegir(self, color: str) -> None:
        color = normalizar(color) or COLOR_DEFECTO
        self._color = color
        for boton, color_muestra in self._muestras:
            boton.setChecked(color_muestra == color)
        self._pintar_muestras()
        self._actualizar_vista_previa()

    def _elegir_otro(self) -> None:
        inicial = QColor(self._color)
        elegido = QColorDialog.getColor(inicial, self, "Elige el color de tu sistema")
        if elegido.isValid():
            self._elegir(elegido.name())

    def _pintar_muestras(self) -> None:
        borde = PALETAS[self._tema()]["texto"]
        for boton, color in self._muestras:
            marcado = boton.isChecked()
            boton.setText("✓" if marcado else "")
            boton.setStyleSheet(
                f"QPushButton {{ background-color: {color}; color: #ffffff; font-weight: 700;"
                f" border: {3 if marcado else 1}px solid {borde if marcado else 'rgba(0,0,0,40)'};"
                f" border-radius: {TAM_MUESTRA // 2}px; padding: 0px; min-height: 0px; }}")

    def _actualizar_vista_previa(self) -> None:
        tema = self._tema()
        g = generar(self._color)
        c = {**PALETAS[tema], **g[tema]}
        self.label_color.setText(f"Tu color: {self._color.upper()}")
        self.label_aviso.setText(
            "Ajustamos un poco el tono para que el texto blanco de los botones se lea bien."
            if g["ajustado"] else "")
        self.label_aviso.setVisible(g["ajustado"])

        self.prev_menu.setStyleSheet(f"QFrame {{ background-color: {c['menu_fondo']}; "
                                     f"border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}")
        base_item = "padding: 6px; border-radius: 6px; font-weight: 600; "
        self.prev_item_activo.setStyleSheet(
            f"background-color: {c['menu_activo']}; color: {c['menu_icono_activo']}; {base_item}")
        for etiqueta in (self.prev_item_2, self.prev_item_3):
            etiqueta.setStyleSheet(f"background-color: transparent; color: {c['menu_texto']}; {base_item}")

        self.prev_panel.setStyleSheet(
            f"QFrame {{ background-color: {c['superficie']}; border: 1px solid {c['borde']}; "
            f"border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}")
        self.prev_titulo.setStyleSheet(
            f"background: transparent; border: none; color: {c['texto']}; font-size: 15px; font-weight: 700;")
        self.prev_texto.setStyleSheet(
            f"background: transparent; border: none; color: {c['texto_suave']};")
        self.prev_boton.setStyleSheet(
            f"background-color: {c['acento']}; color: #ffffff; border: none; border-radius: 6px; "
            f"padding: 7px 18px; font-weight: 600;")
        self.prev_badge.setStyleSheet(
            f"background-color: {c['primario_suave']}; color: {c['primario_texto']}; border: none; "
            f"border-radius: 10px; padding: 4px 12px; font-weight: 600;")
        self.prev_enlace.setStyleSheet(
            f"background: transparent; border: none; color: {c['acento']}; font-weight: 600;")

    def _aplicar(self) -> None:
        try:
            self.config_service.guardar_color_marca(self._color)
        except ConfiguracionError as e:
            QMessageBox.warning(self, "No se pudo guardar", str(e))
            return
        self.color_aplicado.emit()
        self._actualizar_vista_previa()

    def _restablecer(self) -> None:
        self._elegir(COLOR_DEFECTO)
        self._aplicar()
