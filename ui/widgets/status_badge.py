"""Etiqueta pequeña (píldora) con color según estado.

Tipos: ok (verde), warning (ámbar), danger (rojo), info (celeste), neutral (gris).
Los colores salen del sistema de diseño (ui/tokens.py) y cambian con el tema.
"""

from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):

    ESTILOS = {
        "ok": "badgeOk",
        "warning": "badgeWarning",
        "danger": "badgeDanger",
        "info": "badgeInfo",
        "neutral": "badgeNeutral",
    }

    def __init__(self, texto: str, tipo: str = "ok", parent=None):
        super().__init__(texto, parent)
        self.setProperty("class", self.ESTILOS.get(tipo, "badgeOk"))
