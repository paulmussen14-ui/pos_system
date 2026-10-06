"""Ayudas para llenar QTableWidget sin congelar la ventana.

Problema que resuelve
---------------------
Cuando una columna usa `QHeaderView.ResizeToContents`, Qt vuelve a medir TODAS
las filas de esa columna cada vez que se agrega una celda (`setItem`) o se
cambia una altura de fila. Llenar N filas cuesta entonces N x N medidas: con
500 productos la pantalla de Ventas quedaba ~13 segundos sin responder.

`carga_rapida` apaga ese re-medido mientras se llena la tabla y lo hace UNA
sola vez al terminar (costo N en vez de N x N). El resultado visual es el
mismo: las columnas siguen ajustándose a su contenido.

Uso:

    from utils.tablas import carga_rapida

    with carga_rapida(self.tabla):
        self.tabla.setRowCount(len(filas))
        for i, fila in enumerate(filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(fila.nombre))
"""

from contextlib import contextmanager

from PySide6.QtWidgets import QHeaderView, QTableWidget


@contextmanager
def carga_rapida(tabla: QTableWidget):
    """Context manager: apaga repintado y auto-ajuste de columnas mientras se
    llena `tabla`, y los restaura (midiendo una sola vez) al salir."""
    header = tabla.horizontalHeader()
    columnas_auto = [
        i for i in range(tabla.columnCount())
        if header.sectionResizeMode(i) == QHeaderView.ResizeToContents
    ]

    tabla.setUpdatesEnabled(False)
    for i in columnas_auto:
        header.setSectionResizeMode(i, QHeaderView.Fixed)
    try:
        yield
    finally:
        for i in columnas_auto:
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        tabla.setUpdatesEnabled(True)


def cerca_del_final(tabla: QTableWidget, filas_de_margen: int = 5) -> bool:
    """True si el scroll vertical de `tabla` está a pocas filas del final.
    Sirve para pedir la siguiente página de resultados (carga al hacer scroll)."""
    total = tabla.rowCount()
    if total == 0:
        return False
    # Se usa la última fila visible (y no el valor de la barra) porque la barra
    # cuenta filas o píxeles según la plataforma/estilo.
    ultima_visible = tabla.rowAt(tabla.viewport().height() - 1)
    if ultima_visible < 0:          # la tabla entra completa en el área visible
        ultima_visible = total - 1
    return ultima_visible >= total - filas_de_margen
