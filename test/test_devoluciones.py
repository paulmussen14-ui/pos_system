"""Prueba de devoluciones/anulaciones. USA UNA BASE DE DATOS TEMPORAL:
nunca toca la base real de la app (se detiene si no puede garantizarlo).

Uso (desde la carpeta pos_system):   python test_devoluciones.py
"""
import os
import sys
import tempfile

# --- ANTES de importar nada de la app: apuntar los datos a una carpeta temporal ---
_TMP = tempfile.mkdtemp(prefix="pos_test_")
os.environ["APPDATA"] = _TMP          # Windows
os.environ["HOME"] = _TMP             # Linux / Mac
os.environ["USERPROFILE"] = _TMP
sys.path.insert(0, os.getcwd())

from config import DATABASE_PATH      # noqa: E402
if not str(DATABASE_PATH).startswith(_TMP):
    print("ALTO: no pude aislar la base de datos de prueba. No se ejecuto nada.")
    sys.exit(1)
print(f"Usando base temporal (no la real): {DATABASE_PATH}\n")

from database.connection import get_db
from services.configuracion_service import ConfiguracionService
from services.producto_service import ProductoService
from services.venta_service import VentaService, VentaError
from models.venta import VentaDetalleItem

c = get_db().get_connection(); ConfiguracionService()
c.execute("insert into usuarios (nombre,usuario,password_hash,recovery_code_hash) values ('A','a','x','x')"); c.commit()
ps = ProductoService(); vs = VentaService()
efectivo = [m for m in vs.metodos_pago() if m["nombre"] == "Yape/Plin"][0]["id"]
stock = lambda pid: c.execute("select stock_actual from productos where id=?", (pid,)).fetchone()[0]
def nueva_venta(cant):
    pid = ps.crear_producto(f"P{cant}-{nueva_venta.n}", None, "", "unidad", 2, 100, 0, None, 1)
    nueva_venta.n += 1
    v = vs.registrar_venta([VentaDetalleItem(pid, "x", cant, 2.0, 1.0)], 1, None, efectivo)
    return pid, v
nueva_venta.n = 0
def falla(f, *a):
    try: f(*a); return None
    except VentaError as e: return str(e)

ok = True
def check(nombre, cond):
    global ok; ok &= bool(cond); print(("OK   " if cond else "FALLA"), nombre)

# 1) devolver de más en una sola vez
pid, v = nueva_venta(24)
check("devolver 30 de 24 -> rechazado", falla(vs.registrar_devolucion, v, pid, 30, "m", 1))
check("stock intacto tras rechazo (76)", stock(pid) == 76)

# 2) devoluciones parciales acumuladas
vs.registrar_devolucion(v, pid, 10, "m", 1)
check("devolución parcial 10 -> stock 86", stock(pid) == 86)
msg = falla(vs.registrar_devolucion, v, pid, 15, "m", 1)
check("15 más (solo quedan 14) -> rechazado", msg and "14" in msg)
vs.registrar_devolucion(v, pid, 14, "m", 1)
check("devolver los 14 restantes -> stock 100", stock(pid) == 100)
check("ya devuelto por completo -> rechazado", falla(vs.registrar_devolucion, v, pid, 1, "m", 1))

# 3) el caso del bug original: anular y luego devolver
pid2, v2 = nueva_venta(24)
vs.anular_venta(v2, 1)
check("anular -> stock 100", stock(pid2) == 100)
check("devolver en venta anulada -> rechazado", falla(vs.registrar_devolucion, v2, pid2, 24, "m", 1))
check("stock sigue en 100", stock(pid2) == 100)

# 4) devolver parte y luego anular: no debe reponer dos veces
pid3, v3 = nueva_venta(24)
vs.registrar_devolucion(v3, pid3, 10, "m", 1)
vs.anular_venta(v3, 1)
check("devolver 10 + anular -> stock 100 (no 110)", stock(pid3) == 100)

# 5) devolver todo y luego anular
pid4, v4 = nueva_venta(24)
vs.registrar_devolucion(v4, pid4, 24, "m", 1)
vs.anular_venta(v4, 1)
check("devolver todo + anular -> stock 100", stock(pid4) == 100)

# 6) validaciones básicas
check("cantidad 0 -> rechazado", falla(vs.registrar_devolucion, v, pid, 0, "m", 1))
check("producto ajeno a la venta -> rechazado", falla(vs.registrar_devolucion, v, pid2, 1, "m", 1))
check("venta inexistente -> rechazado", falla(vs.registrar_devolucion, 999, pid, 1, "m", 1))

# 7) movimientos de inventario cuadran con el stock
for p in (pid, pid2, pid3, pid4):
    neto = c.execute("""select coalesce(sum(case when tipo='salida' then -cantidad else cantidad end),0)
                        from inventario_movimientos where producto_id=?""", (p,)).fetchone()[0]
    check(f"producto {p}: movimientos netos == stock-100 ({neto:g})", abs(neto - (stock(p) - 100)) < 1e-9)
print("\nRESULTADO:", "TODO OK" if ok else "HAY FALLAS")