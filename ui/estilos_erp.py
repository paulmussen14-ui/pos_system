"""Capa de estilos "ERP": se aplica DESPUÉS del tema base y de la capa de mejoras
(ver ui/tema_iconos.py), así que lo que se repite aquí manda sobre los .qss.

Es una plantilla con marcadores {{nombre}} que se reemplazan por los valores de
ui/tokens.py según el tema. De esta forma el tema claro y el oscuro comparten
exactamente la misma estructura y solo cambian los colores.

Solo usa propiedades que Qt soporta (nada de box-shadow, flex, grid ni transitions).
"""

from ui.tokens import ESCALAS, paleta
from utils.logger import logger

_PLANTILLA = """
/* ===== Capa ERP: base ===== */
QMainWindow, QWidget#centralWidget {
    background-color: {{fondo}};
}

QDialog {
    background-color: {{superficie}};
}

QMessageBox {
    background-color: {{superficie}};
}

QMessageBox QLabel {
    color: {{texto}};
}

QToolTip {
    background-color: {{menu_fondo}};
    color: #f8fafc;
    border: 1px solid {{menu_borde}};
    padding: 4px 8px;
    border-radius: {{r_sm}}px;
}

/* ===== Tipografía ===== */
QLabel#pageTitle {
    font-size: {{t_titulo}}px;
    font-weight: 700;
    color: {{texto}};
}

QLabel#pageSubtitle {
    font-size: {{t_texto}}px;
    color: {{texto_suave}};
}

QLabel#cardHeading {
    font-size: {{t_subtitulo}}px;
    font-weight: 600;
    color: {{texto}};
}

QLabel.ayuda {
    font-size: {{t_ayuda}}px;
    color: {{texto_suave}};
}

QLabel.total {
    font-size: {{t_total}}px;
    font-weight: 700;
    color: {{primario}};
}

/* ===== Tarjetas ===== */
QFrame.card {
    background-color: {{superficie}};
    border: 1px solid {{borde}};
    border-radius: {{r_lg}}px;
    padding: {{e_md}}px;
}

QFrame#erpCard {
    background-color: {{superficie}};
    border: 1px solid {{borde}};
    border-radius: {{r_lg}}px;
}

QLabel.cardTitle {
    color: {{texto_suave}};
    font-size: {{t_ayuda}}px;
    font-weight: 600;
}

QLabel.cardValue {
    color: {{texto}};
    font-size: {{t_kpi}}px;
    font-weight: 700;
}

QFrame#separador {
    background-color: {{borde}};
    border: none;
    min-height: 1px;
    max-height: 1px;
}

/* ===== Botones: primario por defecto, el resto por clase ===== */
QPushButton {
    background-color: {{primario}};
    color: #ffffff;
    border: 1px solid transparent;
    border-radius: {{r_sm}}px;
    padding: 6px {{e_md}}px;
    min-height: 20px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: {{primario_hover}};
}

QPushButton:pressed {
    background-color: {{primario_presionado}};
}

QPushButton:disabled {
    background-color: {{deshab_fondo}};
    color: {{deshab_texto}};
    border: 1px solid transparent;
}

QPushButton.secondary {
    background-color: {{superficie}};
    color: {{texto}};
    border: 1px solid {{borde_fuerte}};
}

QPushButton.secondary:hover {
    background-color: {{hover}};
    border: 1px solid {{texto_tenue}};
}

QPushButton.secondary:pressed {
    background-color: {{borde}};
}

QPushButton.secondary:disabled {
    background-color: {{superficie_alt}};
    color: {{texto_tenue}};
    border: 1px solid {{borde}};
}

QPushButton.danger {
    background-color: {{peligro}};
    color: #ffffff;
}

QPushButton.danger:hover {
    background-color: {{peligro_hover}};
}

QPushButton.danger:disabled {
    background-color: {{deshab_fondo}};
    color: {{deshab_texto}};
}

QPushButton.success {
    background-color: {{acento}};
    color: #ffffff;
}

QPushButton.success:hover {
    background-color: {{acento_hover}};
}

QPushButton.success:disabled {
    background-color: {{deshab_fondo}};
    color: {{deshab_texto}};
}

QPushButton.ghost {
    background-color: transparent;
    color: {{primario}};
    border: 1px solid transparent;
}

QPushButton.ghost:hover {
    background-color: {{primario_suave}};
}

QPushButton.large {
    padding: 12px {{e_lg}}px;
    font-size: {{t_subtitulo}}px;
    min-height: 24px;
    border-radius: {{r_md}}px;
}

QPushButton.large:disabled {
    background-color: {{deshab_fondo}};
    color: {{deshab_texto}};
}

QMessageBox QPushButton, QDialog QDialogButtonBox QPushButton {
    min-width: 84px;
}

/* ===== Campos ===== */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit {
    background-color: {{input_fondo}};
    color: {{texto}};
    border: 1px solid {{borde_fuerte}};
    border-radius: {{r_sm}}px;
    padding: 6px 10px;
    min-height: 20px;
    selection-background-color: {{primario}};
    selection-color: #ffffff;
    placeholder-text-color: {{texto_tenue}};
}

QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QTextEdit:hover {
    border: 1px solid {{texto_tenue}};
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTextEdit:focus {
    border: 1px solid {{primario}};
}

QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled, QTextEdit:disabled {
    background-color: {{superficie_alt}};
    color: {{texto_tenue}};
    border: 1px solid {{borde}};
}

/* El campo interno de los numéricos/fechas/listas editables no dibuja borde propio */
QSpinBox QLineEdit, QDoubleSpinBox QLineEdit, QDateEdit QLineEdit, QComboBox QLineEdit,
QSpinBox QLineEdit:hover, QDoubleSpinBox QLineEdit:hover, QDateEdit QLineEdit:hover, QComboBox QLineEdit:hover,
QSpinBox QLineEdit:focus, QDoubleSpinBox QLineEdit:focus, QDateEdit QLineEdit:focus, QComboBox QLineEdit:focus {
    background-color: transparent;
    border: none;
    padding: 0px;
    min-height: 0px;
}

QComboBox QAbstractItemView {
    background-color: {{superficie}};
    color: {{texto}};
    border: 1px solid {{borde_fuerte}};
    border-radius: {{r_sm}}px;
    selection-background-color: {{primario_suave}};
    selection-color: {{texto}};
    outline: none;
}

/* ===== Listas ===== */
QListWidget {
    background-color: {{superficie}};
    color: {{texto}};
    border: 1px solid {{borde}};
    border-radius: {{r_md}}px;
    outline: none;
}

QListWidget::item {
    padding: 6px 8px;
    border-radius: {{r_sm}}px;
}

QListWidget::item:hover {
    background-color: {{hover}};
}

QListWidget::item:selected {
    background-color: {{primario_suave}};
    color: {{texto}};
}

/* ===== Tablas ===== */
QTableWidget, QTableView {
    background-color: {{superficie}};
    alternate-background-color: {{superficie_alt}};
    color: {{texto}};
    border: 1px solid {{borde}};
    border-radius: {{r_md}}px;
    gridline-color: {{borde}};
    selection-background-color: {{primario_suave}};
    selection-color: {{texto}};
    outline: 0;
}

QTableWidget::item, QTableView::item {
    padding: 6px 10px;
    border: none;
}

QTableWidget::item:hover, QTableView::item:hover {
    background-color: {{hover}};
}

QTableWidget::item:selected, QTableView::item:selected,
QTableWidget::item:selected:!active, QTableView::item:selected:!active {
    background-color: {{primario_suave}};
    color: {{texto}};
}

QHeaderView {
    background-color: {{superficie_alt}};
    border: none;
}

QHeaderView::section {
    background-color: {{superficie_alt}};
    color: {{texto_suave}};
    padding: 10px 10px;
    border: none;
    border-bottom: 1px solid {{borde_fuerte}};
    font-size: {{t_ayuda}}px;
    font-weight: 600;
}

QHeaderView::section:horizontal:first {
    border-top-left-radius: 7px;
}

QHeaderView::section:horizontal:last {
    border-top-right-radius: 7px;
}

QHeaderView::section:vertical {
    padding: 4px 8px;
    border: none;
    border-bottom: 1px solid {{borde}};
    border-right: 1px solid {{borde}};
}

QTableCornerButton::section {
    background-color: {{superficie_alt}};
    border: none;
    border-bottom: 1px solid {{borde_fuerte}};
}

/* ===== Badges de estado (píldoras) ===== */
QLabel.badgeOk, QLabel.badgeWarning, QLabel.badgeDanger, QLabel.badgeInfo, QLabel.badgeNeutral {
    border-radius: 9px;
    padding: 2px 10px;
    font-size: {{t_ayuda}}px;
    font-weight: 600;
}

QLabel.badgeOk {
    background-color: {{exito_suave}};
    color: {{exito_texto}};
}

QLabel.badgeWarning {
    background-color: {{aviso_suave}};
    color: {{aviso_texto}};
}

QLabel.badgeDanger {
    background-color: {{peligro_suave}};
    color: {{peligro_texto}};
}

QLabel.badgeInfo {
    background-color: {{info_suave}};
    color: {{info_texto}};
}

QLabel.badgeNeutral {
    background-color: {{neutro_suave}};
    color: {{neutro_texto}};
}

/* ===== Pestañas ===== */
QTabWidget::pane {
    border: 1px solid {{borde}};
    border-radius: {{r_md}}px;
    background-color: {{superficie}};
}

QTabBar::tab {
    background-color: transparent;
    color: {{texto_suave}};
    padding: 9px {{e_md}}px;
    margin-right: 2px;
    border-bottom: 2px solid transparent;
}

QTabBar::tab:hover:!selected {
    background-color: {{hover}};
    color: {{texto}};
}

QTabBar::tab:selected {
    background-color: {{superficie}};
    color: {{primario}};
    font-weight: 600;
    border-bottom: 2px solid {{primario}};
}

/* ===== Separadores y barras de desplazamiento ===== */
QSplitter::handle {
    background-color: {{borde}};
}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: {{borde_fuerte}};
}

QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: {{texto_tenue}};
}

QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {
    background: {{texto_suave}};
}

/* ===== Chip (dato seleccionado, ej. cliente de la venta) y bloque de total ===== */
QLabel.chip {
    background-color: {{primario_suave}};
    color: {{primario_texto}};
    border-radius: {{r_md}}px;
    padding: 6px 10px;
    font-weight: 600;
}

QFrame#totalBox {
    background-color: {{superficie_alt}};
    border: 1px solid {{borde}};
    border-radius: {{r_md}}px;
}

QFrame#totalBox QLabel {
    background-color: transparent;
}

/* ===== Menú lateral ===== */
QWidget#sidebar {
    background-color: {{menu_fondo}};
    min-width: {{ancho_sidebar}}px;
    max-width: {{ancho_sidebar}}px;
}

QWidget#sidebarHeader {
    background-color: transparent;
    border-bottom: 1px solid {{menu_borde}};
}

QFrame#logoCard {
    background-color: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: {{r_md}}px;
}

QLabel#logoInicial {
    background-color: {{menu_activo}};
    color: #ffffff;
    border-radius: {{r_md}}px;
    font-size: 22px;
    font-weight: 700;
}

QLabel#sidebarTitle {
    color: #ffffff;
    font-size: {{t_subtitulo}}px;
    font-weight: 700;
    padding: 0px;
    qproperty-alignment: AlignCenter;
}

QLabel#sidebarUser {
    color: {{menu_texto}};
    font-size: {{t_texto}}px;
}

QLabel#sidebarSection {
    color: {{menu_texto_tenue}};
    font-size: 11px;
    font-weight: 700;
    padding: {{e_md}}px {{e_lg}}px 4px {{e_lg}}px;
}

QLabel#sidebarPie {
    color: {{menu_texto_tenue}};
    font-size: 11px;
    padding: 4px {{e_lg}}px;
}

QWidget#sidebar QPushButton#navItem {
    background-color: transparent;
    color: {{menu_texto}};
    text-align: left;
    padding: 10px 14px;
    margin: 1px 12px;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
}

QWidget#sidebar QPushButton#navItem:hover {
    background-color: {{menu_hover}};
    color: #ffffff;
}

QWidget#sidebar QPushButton#navItem:checked {
    background-color: {{menu_activo}};
    color: #ffffff;
    font-weight: 600;
}

QWidget#sidebar QPushButton#navLogout {
    background-color: transparent;
    color: {{menu_texto}};
    text-align: left;
    padding: 10px 14px;
    margin: 1px 12px;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
}

QWidget#sidebar QPushButton#navLogout:hover {
    background-color: {{peligro_suave}};
    color: {{peligro_texto}};
}

/* Tarjeta de acción rápida al pie del menú */
QFrame#sidebarCard {
    background-color: {{menu_hover}};
    border: 1px solid {{menu_borde}};
    border-radius: 12px;
}

QLabel#sidebarCardTitulo {
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
}

QLabel#sidebarCardTexto {
    color: {{menu_texto}};
    font-size: 12px;
}

QWidget#sidebar QPushButton#btnNuevaVenta {
    background-color: {{menu_activo}};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 700;
}

QWidget#sidebar QPushButton#btnNuevaVenta:hover {
    background-color: #0ea371;
}

/* ===== Barra superior ===== */
QWidget#topBar {
    background-color: {{menu_fondo}};
    border-bottom: 1px solid {{menu_borde}};
}

QLabel#topBarBienvenida {
    color: #ffffff;
    font-size: 17px;
    font-weight: 600;
}

QLabel#topBarFecha {
    color: {{menu_texto}};
    font-size: 13px;
    font-weight: 600;
}

QLabel#topBarUsuario {
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
}

QLabel#topBarRol {
    color: {{menu_texto_tenue}};
    font-size: 12px;
}

QLabel#topBarAvatar {
    background-color: {{menu_activo}};
    color: #ffffff;
    border-radius: 18px;
    font-size: 15px;
    font-weight: 700;
}

QWidget#topBar QPushButton#btnMenu {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 6px;
    min-height: 0px;
}

QWidget#topBar QPushButton#btnMenu:hover {
    background-color: {{menu_hover}};
}

/* ===== Inicio (dashboard) ===== */
QLabel#homeTitulo {
    color: {{texto}};
    font-size: 24px;
    font-weight: 700;
}

QLabel#homeSubtitulo {
    color: {{texto_suave}};
    font-size: 14px;
}

QFrame#kpiCard, QFrame#homeCard, QFrame#panelCaja {
    background-color: {{superficie}};
    border: 1px solid {{borde}};
    border-radius: 14px;
}

QLabel#kpiTitulo {
    color: {{texto_suave}};
    font-size: 13px;
}

QLabel#kpiValor {
    color: {{texto}};
    font-size: 22px;
    font-weight: 700;
}

QLabel#kpiValor[largo="medio"] { font-size: 19px; }
QLabel#kpiValor[largo="largo"] { font-size: 16px; }

QLabel#kpiDelta {
    font-size: 12px;
    font-weight: 600;
    color: {{texto_tenue}};
}

QLabel#kpiDelta[tendencia="sube"] {
    color: {{exito}};
}

QLabel#kpiDelta[tendencia="baja"] {
    color: {{peligro}};
}

QLabel#kpiIcono {
    border-radius: 20px;
    background-color: {{neutro_suave}};
}

QLabel#kpiIcono[tono="exito"] { background-color: {{exito_suave}}; }
QLabel#kpiIcono[tono="info"] { background-color: {{info_suave}}; }
QLabel#kpiIcono[tono="aviso"] { background-color: {{aviso_suave}}; }
QLabel#kpiIcono[tono="primario"] { background-color: {{primario_suave}}; }

QLabel#homeCardTitulo {
    color: {{texto}};
    font-size: 16px;
    font-weight: 700;
}

QPushButton#homeCardVerMas {
    background-color: transparent;
    color: {{acento}};
    border: none;
    padding: 0px;
    min-height: 0px;
    font-size: 13px;
    font-weight: 600;
}

QPushButton#homeCardVerMas:hover {
    background-color: transparent;
    color: {{acento_hover}};
}

QScrollArea#homeScroll, QWidget#homeContenido {
    background-color: {{fondo}};
    border: none;
}

QFrame#filaLista {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {{borde}};
}

QFrame#filaLista[ultima="true"] {
    border-bottom: none;
}

QLabel#filaTitulo {
    color: {{texto}};
    font-size: 14px;
    font-weight: 600;
}

QLabel#filaSub {
    color: {{texto_suave}};
    font-size: 12px;
}

QLabel#filaMonto {
    color: {{texto}};
    font-size: 14px;
    font-weight: 700;
}

QLabel#filaBurbuja {
    border-radius: 18px;
    background-color: {{neutro_suave}};
    color: {{texto}};
    font-size: 14px;
    font-weight: 700;
}

QLabel#filaBurbuja[tono="exito"] { background-color: {{exito_suave}}; }
QLabel#filaBurbuja[tono="info"] { background-color: {{info_suave}}; }
QLabel#filaBurbuja[tono="aviso"] { background-color: {{aviso_suave}}; }
QLabel#filaBurbuja[tono="peligro"] { background-color: {{peligro_suave}}; }
QLabel#filaBurbuja[tono="primario"] { background-color: {{primario_suave}}; }

QFrame#alertaStock {
    border-radius: 10px;
    border: 1px solid {{borde}};
}

QFrame#alertaStock[nivel="critico"] {
    background-color: {{peligro_suave}};
    border: 1px solid {{peligro}};
}

QFrame#alertaStock[nivel="bajo"] {
    background-color: {{aviso_suave}};
    border: 1px solid {{aviso}};
}

QFrame#alertaStock QLabel {
    background-color: transparent;
    border: none;
}

QFrame#alertaStock[nivel="critico"] QLabel#alertaDetalle {
    color: {{peligro_texto}};
}

QFrame#alertaStock[nivel="bajo"] QLabel#alertaDetalle {
    color: {{aviso_texto}};
}

QLabel#alertaDetalle {
    font-size: 12px;
    font-weight: 600;
}

QPushButton#btnAlerta {
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 5px 12px;
    min-height: 0px;
    font-size: 12px;
    font-weight: 700;
}

QPushButton#btnAlerta[nivel="critico"] { background-color: {{peligro}}; }
QPushButton#btnAlerta[nivel="critico"]:hover { background-color: {{peligro_hover}}; }
QPushButton#btnAlerta[nivel="bajo"] { background-color: {{aviso}}; }
QPushButton#btnAlerta[nivel="bajo"]:hover { background-color: {{aviso_texto}}; }

/* ===== Ventas: botones de categoría ===== */
QScrollArea#chipsScroll, QScrollArea#chipsScroll > QWidget > QWidget#chipsContenido {
    background-color: transparent;
    border: none;
}

QPushButton#chipCategoria {
    background-color: {{superficie_alt}};
    color: {{texto_suave}};
    border: 1px solid {{borde}};
    border-radius: 15px;
    padding: 5px 14px;
    min-height: 0px;
    font-size: 12px;
    font-weight: 600;
}

QPushButton#chipCategoria:hover {
    background-color: {{acento_suave}};
    border: 1px solid {{acento}};
    color: {{acento_texto}};
}

QPushButton#chipCategoria:checked {
    background-color: {{primario}};
    border: 1px solid {{primario}};
    color: #ffffff;
}

/* Panel derecho del inicio (caja + accesos rápidos) */
QFrame#panelDerecho {
    background-color: {{superficie}};
    border: none;
    border-left: 1px solid {{borde}};
}

QLabel#panelTitulo {
    color: {{texto}};
    font-size: 17px;
    font-weight: 700;
}

QLabel#panelSeccion {
    color: {{texto_suave}};
    font-size: 13px;
    font-weight: 600;
}

QFrame#panelCaja {
    background-color: {{superficie_alt}};
}

QLabel#cajaMonto {
    color: {{texto}};
    font-size: 26px;
    font-weight: 700;
}

QLabel#cajaDetalle {
    color: {{texto_suave}};
    font-size: 12px;
}

QPushButton#btnAcceso {
    background-color: {{superficie}};
    color: {{texto}};
    border: 1px solid {{borde_fuerte}};
    border-radius: 10px;
    padding: 10px 8px;
    font-size: 13px;
    font-weight: 600;
    min-height: 0px;
}

QPushButton#btnAcceso:hover {
    background-color: {{acento_suave}};
    border: 1px solid {{acento}};
    color: {{acento_texto}};
}

QPushButton#btnCaja {
    background-color: {{acento}};
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 14px;
    font-weight: 700;
}

QPushButton#btnCaja:hover {
    background-color: {{acento_hover}};
}

QProgressBar#barraPago {
    background-color: {{neutro_suave}};
    border: none;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
}

QProgressBar#barraPago::chunk {
    background-color: {{acento}};
    border-radius: 3px;
}
"""


def generar_capa_erp(tema: str) -> str:
    """Devuelve la capa de estilos ERP con los valores del tema ya puestos."""
    valores = {**paleta(tema), **{k: str(v) for k, v in ESCALAS.items()}}
    qss = _PLANTILLA
    for nombre, valor in valores.items():
        qss = qss.replace("{{" + nombre + "}}", valor)
    if "{{" in qss:
        logger.warning("La capa ERP tiene marcadores sin reemplazar: revisa ui/tokens.py")
    return qss
