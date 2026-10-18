"""Ayudas para que todas las tablas se vean y se alineen igual.

Reglas del sistema de diseño: texto a la izquierda, números y montos a la
derecha, sin cuadrícula vertical, filas altas y legibles, encabezado fijo
(el encabezado de un QTableWidget no se desplaza con las filas).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QAbstractItemView

from ui.tokens import paleta

ALINEAR_DERECHA = Qt.AlignRight | Qt.AlignVCenter
ALINEAR_IZQUIERDA = Qt.AlignLeft | Qt.AlignVCenter
ALINEAR_CENTRO = Qt.AlignCenter


def configurar_tabla_erp(tabla: QTableWidget, derecha=(), centro=(), altura_fila: int = 36) -> None:
    """Aplica el aspecto estándar a `tabla`. Llamar DESPUÉS de poner los
    encabezados (setHorizontalHeaderLabels).

    derecha / centro: índices de columnas cuyo encabezado se alinea a la
    derecha (montos, cantidades) o al centro (#, acciones).
    """
    tabla.verticalHeader().setVisible(False)
    tabla.verticalHeader().setDefaultSectionSize(altura_fila)
    tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
    tabla.setSelectionMode(QAbstractItemView.SingleSelection)
    tabla.setAlternatingRowColors(True)
    tabla.setShowGrid(False)
    tabla.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    encabezado = tabla.horizontalHeader()
    encabezado.setDefaultAlignment(ALINEAR_IZQUIERDA)
    encabezado.setHighlightSections(False)
    for columna in range(tabla.columnCount()):
        if columna in derecha:
            alineacion = ALINEAR_DERECHA
        elif columna in centro:
            alineacion = ALINEAR_CENTRO
        else:
            alineacion = ALINEAR_IZQUIERDA
        tabla.model().setHeaderData(columna, Qt.Horizontal, int(alineacion), Qt.TextAlignmentRole)


def item_derecha(texto: str) -> QTableWidgetItem:
    """Celda de solo lectura con el texto alineado a la derecha (montos, cantidades)."""
    item = QTableWidgetItem(texto)
    item.setTextAlignment(ALINEAR_DERECHA)
    return item


def item_centro(texto: str) -> QTableWidgetItem:
    item = QTableWidgetItem(texto)
    item.setTextAlignment(ALINEAR_CENTRO)
    return item


def colorear_stock(item: QTableWidgetItem, agotado: bool, bajo: bool, tema: str) -> None:
    """Pinta el stock en rojo (agotado) o ámbar (bajo) con los colores del tema."""
    if not (agotado or bajo):
        return
    colores = paleta(tema)
    clave = "peligro" if agotado else "aviso"
    item.setForeground(QBrush(QColor(colores[clave])))
    fuente = QFont(item.font())
    fuente.setBold(True)
    item.setFont(fuente)
