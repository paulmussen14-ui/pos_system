"""Etiqueta pequeña con color según estado (ok, advertencia, peligro)."""

from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):

    ESTILOS = {
        "ok": "badgeOk",
        "warning": "badgeWarning",
        "danger": "badgeDanger",
    }

    def __init__(self, texto: str, tipo: str = "ok", parent=None):
        super().__init__(texto, parent)
        self.setProperty("class", self.ESTILOS.get(tipo, "badgeOk"))
