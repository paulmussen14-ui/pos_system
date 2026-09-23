"""Prueba del documento de clientes (servicio + formulario).
USA UNA CARPETA TEMPORAL: no toca tu base de datos real y no abre ventanas.

Uso (desde la carpeta pos_system):   python test_documento_clientes.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="pos_test_")
os.environ["APPDATA"] = _TMP
os.environ["HOME"] = _TMP
os.environ["USERPROFILE"] = _TMP
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.getcwd())

from config import DATABASE_PATH  # noqa: E402
if not str(DATABASE_PATH).startswith(_TMP):
    print("ALTO: no pude aislar la base de datos de prueba. No se ejecuto nada.")
    sys.exit(1)
print(f"Usando base temporal (no la real): {DATABASE_PATH}\n")

from PySide6.QtWidgets import QApplication  # noqa: E402
from database.connection import get_db  # noqa: E402
from services.cliente_service import ClienteService  # noqa: E402

app = QApplication.instance() or QApplication([])
get_db()
cs = ClienteService()
ok = True


def check(nombre, cond):
    global ok
    ok &= bool(cond)
    print(("OK   " if cond else "FALLA"), nombre)


def doc(cid):
    return cs.obtener_por_id(cid).documento


# ---- Servicio ----
cid = cs.crear("Juan Perez", "987", "Av. Lima 1", "12345678")
check("crear con documento lo guarda", doc(cid) == "12345678")
check("buscar por documento encuentra al cliente", [c.nombre for c in cs.listar("1234")] == ["Juan Perez"])

cs.actualizar(cid, "Juan P. Perez", "999", "Av. Lima 2")
check("actualizar SIN documento lo conserva (el bug original)", doc(cid) == "12345678")
check("...y sí cambia los demás datos", cs.obtener_por_id(cid).nombre == "Juan P. Perez")

cs.actualizar(cid, "Juan P. Perez", "999", "Av. Lima 2", "87654321")
check("actualizar con documento nuevo lo cambia", doc(cid) == "87654321")

cs.actualizar(cid, "Juan P. Perez", "999", "Av. Lima 2", "  ")
check("actualizar con documento vacío lo borra a propósito", doc(cid) == "")

cid2 = cs.crear("Ana Ruiz", "", "")
check("crear sin documento sigue funcionando (compatibilidad)", doc(cid2) == "")

# ---- Formulario ----
from ui.clientes.clientes_page import ClienteFormDialog  # noqa: E402

cs.actualizar(cid, "Juan P. Perez", "999", "Av. Lima 2", "11112222")
d = ClienteFormDialog(cliente=cs.obtener_por_id(cid))
check("el formulario muestra el documento del cliente", d.input_documento.text() == "11112222")
d.input_nombre.setText("Juan Perez Gomez")
d._guardar()
check("editar solo el nombre en el formulario conserva el documento", doc(cid) == "11112222")

d = ClienteFormDialog(cliente=cs.obtener_por_id(cid))
d.input_documento.setText("20123456789")
d._guardar()
check("cambiar el documento en el formulario lo guarda", doc(cid) == "20123456789")

d = ClienteFormDialog()
d.input_nombre.setText("Empresa SAC")
d.input_documento.setText("20555666777")
d._guardar()
nuevo = [c for c in cs.listar("Empresa")][0]
check("cliente nuevo desde el formulario guarda su documento", nuevo.documento == "20555666777")

print("\nRESULTADO:", "TODO OK" if ok else "HAY FALLAS")
sys.exit(0 if ok else 1)