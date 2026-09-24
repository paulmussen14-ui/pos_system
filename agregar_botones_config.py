#!/usr/bin/env python3
"""Agrega a Configuración > "Copias de seguridad" los botones de:
  - Exportar / Importar productos
  - Restaurar desde otro archivo
y hace que "Restaurar copia seleccionada" use la restauración segura con
reinicio automático.

Uso (desde la raíz del proyecto, DESPUÉS de aplicar_chofer_y_backup.py):
    python agregar_botones_config.py
Guarda una copia  configuracion_page.py.bak_antes_botones ; si algo no
coincide avisa y no modifica nada.
"""
import re
import sys
from pathlib import Path

RAIZ = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
PAGINA = RAIZ / "ui" / "configuracion" / "configuracion_page.py"
ACCIONES = RAIZ / "ui" / "configuracion" / "respaldo_acciones.py"


class Fallo(Exception):
    pass


def insertar_despues(texto, ancla, lineas, desc):
    """Inserta `lineas` (con la sangría del ancla) tras la única línea cuyo
    contenido, sin espacios, es exactamente `ancla`."""
    partes = texto.splitlines(keepends=True)
    idx = [i for i, l in enumerate(partes) if l.strip() == ancla]
    if len(idx) != 1:
        raise Fallo(f"{desc}: se esperaba 1 coincidencia de «{ancla}» y hay {len(idx)}.")
    i = idx[0]
    l = partes[i]
    if not l.endswith("\n"):
        partes[i] = l + "\n"
    sangria = l[: len(l) - len(l.lstrip())]
    nuevas = [(sangria + x if x else "") + "\n" for x in lineas]
    partes[i + 1:i + 1] = nuevas
    return "".join(partes)


def reemplazar_una_vez(texto, viejo, nuevo, desc):
    if texto.count(viejo) != 1:
        raise Fallo(f"{desc}: se esperaba 1 coincidencia y hay {texto.count(viejo)}.")
    return texto.replace(viejo, nuevo, 1)


def main():
    if not PAGINA.exists():
        raise Fallo(f"No encuentro {PAGINA}. ¿Estás en la raíz del proyecto?")
    if not ACCIONES.exists():
        raise Fallo("Falta ui/configuracion/respaldo_acciones.py: ejecuta primero aplicar_chofer_y_backup.py.")

    t = PAGINA.read_text(encoding="utf-8")
    if "exportar_productos_ui" in t:
        print("Ya estaba aplicado. No se hizo nada.")
        return

    t = insertar_despues(
        t, "from ui.configuracion.ticket_extras_dialog import TicketExtrasDialog",
        ["from ui.configuracion.respaldo_acciones import (",
         "    exportar_productos_ui, importar_productos_ui, restaurar_backup_ui,",
         ")"],
        "import")

    t = insertar_despues(
        t, "layout.addWidget(btn_restaurar)",
        ["",
         "btn_restaurar_archivo = QPushButton(\"Restaurar desde otro archivo...\")",
         "btn_restaurar_archivo.setProperty(\"class\", \"danger\")",
         "btn_restaurar_archivo.setToolTip(\"Elige un archivo .db de otra carpeta o de otra PC.\")",
         "btn_restaurar_archivo.clicked.connect(lambda: restaurar_backup_ui(self))",
         "layout.addWidget(btn_restaurar_archivo)",
         "",
         "titulo_productos = QLabel(\"Catálogo de productos (para migrar a otra PC)\")",
         "titulo_productos.setStyleSheet(\"font-weight: 600; margin-top: 12px;\")",
         "layout.addWidget(titulo_productos)",
         "",
         "fila_productos = QHBoxLayout()",
         "btn_exportar_productos = QPushButton(\"Exportar productos...\")",
         "btn_exportar_productos.clicked.connect(lambda: exportar_productos_ui(self))",
         "fila_productos.addWidget(btn_exportar_productos)",
         "btn_importar_productos = QPushButton(\"Importar productos...\")",
         "btn_importar_productos.clicked.connect(",
         "    lambda: importar_productos_ui(self, self.usuario.id)",
         ")",
         "fila_productos.addWidget(btn_importar_productos)",
         "fila_productos.addStretch()",
         "layout.addLayout(fila_productos)"],
        "botones en la pestaña de copias")

    t = reemplazar_una_vez(t, "Reinicia la app después de restaurar.",
                           "La app se reinicia sola al terminar.", "texto de aviso")

    patron = (r'        respuesta = QMessageBox\.question\(\s*self, "Confirmar restauración",'
              r'.*?Copia restaurada\. Cierra y vuelve a abrir la aplicación\."\)')
    nuevo = ("        from config import BACKUPS_DIR\n"
             "        # La confirmación, la restauración y el reinicio de la app los\n"
             "        # maneja restaurar_backup_ui.\n"
             "        restaurar_backup_ui(self, BACKUPS_DIR / item.text())")
    t, n = re.subn(patron, lambda m: nuevo, t, flags=re.DOTALL)
    if n != 1:
        raise Fallo(f"_restaurar_backup: se esperaba 1 bloque y hay {n}.")

    copia = PAGINA.with_name(PAGINA.name + ".bak_antes_botones")
    if not copia.exists():
        copia.write_text(PAGINA.read_text(encoding="utf-8"), encoding="utf-8")
    PAGINA.write_text(t, encoding="utf-8")
    print("Listo: botones agregados en Configuración > Copias de seguridad.")


if __name__ == "__main__":
    try:
        main()
    except Fallo as e:
        print(f"NO SE MODIFICÓ NADA. Motivo: {e}")
        sys.exit(1)
