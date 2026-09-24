#!/usr/bin/env python3
"""Aplica en pos_system:
  1) Chofer por venta (columna ventas.chofer, campo en Ventas con el chofer
     predeterminado de Configuración, y guardado en cada venta).
  2) Backup/restauración de productos (services/backup_productos_service.py).
  3) Restauración de backup más segura + reinicio controlado
     (ui/configuracion/respaldo_acciones.py).

Uso (desde la carpeta del proyecto):   python aplicar_chofer_y_backup.py
Antes de modificar un archivo guarda una copia  <archivo>.bak_antes_cambios
Si algo no coincide, avisa y NO modifica nada.
"""
import os
import re
import sys
from pathlib import Path

RAIZ = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
EXCLUIR = {".venv", "venv", ".git", "build", "dist", "__pycache__", "node_modules", ".idea"}

MODULO_SERVICIO = '"""Exportar e importar el catálogo de productos (para migrar a otra PC).\n\nFormato: un archivo JSON con categorías, proveedores y productos (con sus\npresentaciones, stock y costo). Al importar NUNCA se pisan productos que ya\nexisten (se comparan por nombre, sin distinguir mayúsculas ni tildes de\nmayúscula/minúscula): se omiten y se informan. El import completo es UNA sola\ntransacción (todo o nada) y solo empieza si TODO el archivo es válido.\n"""\n\nimport json\nfrom datetime import datetime\nfrom pathlib import Path\n\nFORMATO = "pos_productos"\nVERSION = 1\n\n\nclass ProductoBackupError(Exception):\n    """Error de negocio al exportar/importar (mensaje apto para el usuario)."""\n\n\ndef _clave(texto) -> str:\n    return " ".join(str(texto or "").split()).casefold()\n\n\ndef _texto(valor) -> str | None:\n    limpio = " ".join(str(valor or "").split())\n    return limpio or None\n\n\ndef _numero(valor, campo: str, exclusivo: bool = False) -> float:\n    if valor is None or valor == "":\n        valor = 0\n    try:\n        n = float(valor)\n    except (TypeError, ValueError):\n        raise ValueError(f"{campo} no es un número válido")\n    if n < 0 or (exclusivo and n == 0):\n        raise ValueError(f"{campo} debe ser {\'mayor a\' if exclusivo else \'mayor o igual a\'} 0")\n    return n\n\n\nclass BackupProductosService:\n\n    def __init__(self, db=None):\n        if db is None:\n            from database.connection import get_db\n            db = get_db()\n        self.db = db\n\n    # ------------------------------------------------------------ Exportar\n    def exportar(self, ruta) -> int:\n        """Guarda los productos ACTIVOS en un archivo JSON. Devuelve cuántos."""\n        conn = self.db.get_connection()\n\n        presentaciones: dict[int, list] = {}\n        for r in conn.execute(\n            "SELECT producto_id, nombre, cantidad_unidades, precio FROM producto_presentaciones "\n            "WHERE activo = 1 ORDER BY orden, id"\n        ):\n            presentaciones.setdefault(r["producto_id"], []).append({\n                "nombre": r["nombre"],\n                "cantidad_unidades": r["cantidad_unidades"],\n                "precio": r["precio"],\n            })\n\n        productos = []\n        for r in conn.execute(\n            """SELECT p.*, c.nombre AS categoria, pr.nombre AS proveedor\n               FROM productos p\n               LEFT JOIN categorias c ON c.id = p.categoria_id\n               LEFT JOIN proveedores pr ON pr.id = p.proveedor_id\n               WHERE p.activo = 1 ORDER BY p.nombre"""\n        ):\n            productos.append({\n                "nombre": r["nombre"],\n                "categoria": r["categoria"],\n                "marca": r["marca"],\n                "unidad_medida": r["unidad_medida"],\n                "precio_venta_actual": r["precio_venta_actual"],\n                "costo_promedio_actual": r["costo_promedio_actual"],\n                "stock_actual": r["stock_actual"],\n                "stock_minimo": r["stock_minimo"],\n                "proveedor": r["proveedor"],\n                "presentaciones": presentaciones.get(r["id"], []),\n            })\n\n        datos = {\n            "formato": FORMATO,\n            "version": VERSION,\n            "exportado_en": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),\n            "categorias": [r["nombre"] for r in conn.execute(\n                "SELECT nombre FROM categorias WHERE activo = 1 ORDER BY nombre")],\n            "proveedores": [dict(r) for r in conn.execute(\n                "SELECT nombre, documento, telefono, direccion FROM proveedores "\n                "WHERE activo = 1 ORDER BY nombre")],\n            "productos": productos,\n        }\n        Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")\n        return len(productos)\n\n    # ------------------------------------------------------------ Importar\n    def _leer_y_validar(self, ruta) -> dict:\n        try:\n            datos = json.loads(Path(ruta).read_text(encoding="utf-8"))\n        except (OSError, ValueError) as e:\n            raise ProductoBackupError(f"No se pudo leer el archivo: {e}")\n\n        if not isinstance(datos, dict) or datos.get("formato") != FORMATO:\n            raise ProductoBackupError("El archivo no es una exportación de productos de este sistema.")\n        if datos.get("version") != VERSION:\n            raise ProductoBackupError(\n                f"Versión de archivo no compatible ({datos.get(\'version\')}). Se esperaba la {VERSION}."\n            )\n        if not isinstance(datos.get("productos"), list):\n            raise ProductoBackupError("El archivo no tiene la lista de productos.")\n\n        errores: list[str] = []\n        productos = []\n        for i, bruto in enumerate(datos["productos"], start=1):\n            try:\n                productos.append(self._normalizar(bruto))\n            except ValueError as e:\n                errores.append(f"Producto #{i}: {e}")\n        if errores:\n            resto = f" (y {len(errores) - 5} errores más)" if len(errores) > 5 else ""\n            raise ProductoBackupError(\n                "El archivo tiene datos inválidos, no se importó nada:\\n- "\n                + "\\n- ".join(errores[:5]) + resto\n            )\n\n        proveedores = []\n        for bruto in datos.get("proveedores") or []:\n            if isinstance(bruto, dict) and _texto(bruto.get("nombre")):\n                proveedores.append({k: _texto(bruto.get(k)) for k in ("nombre", "documento", "telefono", "direccion")})\n\n        return {\n            "productos": productos,\n            "categorias": [c for c in (_texto(x) for x in datos.get("categorias") or []) if c],\n            "proveedores": proveedores,\n        }\n\n    @staticmethod\n    def _normalizar(bruto) -> dict:\n        if not isinstance(bruto, dict):\n            raise ValueError("formato incorrecto")\n        nombre = _texto(bruto.get("nombre"))\n        if not nombre:\n            raise ValueError("falta el nombre")\n\n        pres = []\n        vistos = set()\n        for p in bruto.get("presentaciones") or []:\n            if not isinstance(p, dict):\n                raise ValueError(f\'"{nombre}": presentación con formato incorrecto\')\n            pn = _texto(p.get("nombre"))\n            if not pn:\n                raise ValueError(f\'"{nombre}": una presentación no tiene nombre\')\n            if _clave(pn) in vistos:\n                raise ValueError(f\'"{nombre}": presentación repetida "{pn}"\')\n            vistos.add(_clave(pn))\n            try:\n                pres.append({\n                    "nombre": pn,\n                    "cantidad_unidades": _numero(p.get("cantidad_unidades"), "cantidad de la presentación", True),\n                    "precio": _numero(p.get("precio"), "precio de la presentación"),\n                })\n            except ValueError as e:\n                raise ValueError(f\'"{nombre}" ({pn}): {e}\')\n\n        try:\n            return {\n                "nombre": nombre,\n                "categoria": _texto(bruto.get("categoria")),\n                "marca": _texto(bruto.get("marca")),\n                "unidad_medida": _texto(bruto.get("unidad_medida")) or "unidad",\n                "precio_venta_actual": _numero(bruto.get("precio_venta_actual"), "precio de venta"),\n                "costo_promedio_actual": _numero(bruto.get("costo_promedio_actual"), "costo"),\n                "stock_actual": _numero(bruto.get("stock_actual"), "stock"),\n                "stock_minimo": _numero(bruto.get("stock_minimo"), "stock mínimo"),\n                "proveedor": _texto(bruto.get("proveedor")),\n                "presentaciones": pres,\n            }\n        except ValueError as e:\n            raise ValueError(f\'"{nombre}": {e}\')\n\n    def importar(self, ruta, usuario_id: int | None = None) -> dict:\n        """Crea los productos que no existan. Devuelve\n        {"creados": n, "omitidos": [nombres ya existentes o repetidos]}."""\n        datos = self._leer_y_validar(ruta)\n        conn = self.db.get_connection()\n\n        existentes = {_clave(r["nombre"]) for r in conn.execute("SELECT nombre FROM productos")}\n        categorias = {_clave(r["nombre"]): r["id"] for r in conn.execute("SELECT id, nombre FROM categorias")}\n        proveedores = {_clave(r["nombre"]): r["id"] for r in conn.execute("SELECT id, nombre FROM proveedores")}\n        datos_prov = {_clave(p["nombre"]): p for p in datos["proveedores"]}\n\n        creados = 0\n        omitidos: list[str] = []\n\n        with self.db.transaction() as cur:\n            def id_categoria(nombre):\n                if not nombre:\n                    return None\n                clave = _clave(nombre)\n                if clave not in categorias:\n                    cur.execute("INSERT INTO categorias (nombre) VALUES (?)", (nombre,))\n                    categorias[clave] = cur.lastrowid\n                return categorias[clave]\n\n            def id_proveedor(nombre):\n                if not nombre:\n                    return None\n                clave = _clave(nombre)\n                if clave not in proveedores:\n                    extra = datos_prov.get(clave, {})\n                    cur.execute(\n                        "INSERT INTO proveedores (nombre, documento, telefono, direccion) VALUES (?, ?, ?, ?)",\n                        (nombre, extra.get("documento"), extra.get("telefono"), extra.get("direccion")),\n                    )\n                    proveedores[clave] = cur.lastrowid\n                return proveedores[clave]\n\n            for nombre in datos["categorias"]:\n                id_categoria(nombre)\n\n            for p in datos["productos"]:\n                clave = _clave(p["nombre"])\n                if clave in existentes:\n                    omitidos.append(p["nombre"])\n                    continue\n                existentes.add(clave)\n\n                cur.execute(\n                    """INSERT INTO productos\n                       (nombre, categoria_id, marca, unidad_medida, precio_venta_actual,\n                        costo_promedio_actual, stock_actual, stock_minimo, proveedor_id, activo)\n                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",\n                    (p["nombre"], id_categoria(p["categoria"]), p["marca"], p["unidad_medida"],\n                     p["precio_venta_actual"], p["costo_promedio_actual"], p["stock_actual"],\n                     p["stock_minimo"], id_proveedor(p["proveedor"])),\n                )\n                producto_id = cur.lastrowid\n\n                cur.execute("INSERT INTO historial_precios (producto_id, precio_venta) VALUES (?, ?)",\n                            (producto_id, p["precio_venta_actual"]))\n                if p["costo_promedio_actual"] > 0:\n                    cur.execute(\n                        """INSERT INTO historial_costos\n                           (producto_id, costo_unitario, costo_promedio_resultante, motivo)\n                           VALUES (?, ?, ?, \'importacion\')""",\n                        (producto_id, p["costo_promedio_actual"], p["costo_promedio_actual"]),\n                    )\n                if p["stock_actual"] > 0:\n                    # El stock inicial queda registrado en el kardex como ajuste.\n                    cur.execute(\n                        """INSERT INTO inventario_movimientos\n                           (producto_id, tipo, cantidad, referencia_tipo, referencia_id, usuario_id)\n                           VALUES (?, \'ajuste\', ?, \'ajuste\', NULL, ?)""",\n                        (producto_id, p["stock_actual"], usuario_id),\n                    )\n                for orden, pr in enumerate(p["presentaciones"]):\n                    cur.execute(\n                        """INSERT INTO producto_presentaciones\n                           (producto_id, nombre, cantidad_unidades, precio, orden, activo)\n                           VALUES (?, ?, ?, ?, ?, 1)""",\n                        (producto_id, pr["nombre"], pr["cantidad_unidades"], pr["precio"], orden),\n                    )\n                creados += 1\n\n        return {"creados": creados, "omitidos": omitidos}\n'
MODULO_ACCIONES = '"""Acciones de respaldo para la pantalla de Configuración.\n\n- exportar_productos_ui / importar_productos_ui: migrar el catálogo a otra PC.\n- restaurar_backup_ui: restaura un backup completo de la base y REINICIA la\n  aplicación de forma controlada (la conexión queda cerrada tras restaurar).\n"""\n\nimport os\nimport subprocess\nimport sys\nfrom datetime import datetime\n\nfrom PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox\n\nfrom config import BACKUPS_DIR\nfrom __MODULO_BACKUP__ import BaseCerradaError, restaurar_backup\nfrom services.backup_productos_service import BackupProductosService, ProductoBackupError\nfrom utils.logger import logger\n\n\ndef reiniciar_aplicacion() -> None:\n    """Abre una instancia nueva del programa y cierra la actual."""\n    if getattr(sys, "frozen", False):          # .exe empaquetado\n        comando = [sys.executable, *sys.argv[1:]]\n    else:                                       # python main.py\n        comando = [sys.executable, *sys.argv]\n\n    opciones = {}\n    if os.name == "nt":\n        opciones["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP\n    try:\n        subprocess.Popen(comando, cwd=os.getcwd(), close_fds=True, **opciones)\n    except Exception:\n        logger.exception("No se pudo reiniciar la aplicación automáticamente")\n        QMessageBox.warning(None, "Reinicio", "Cierra el programa y ábrelo de nuevo para continuar.")\n    QApplication.quit()\n\n\ndef exportar_productos_ui(parent) -> None:\n    nombre = f"productos_{datetime.now():%Y%m%d}.json"\n    ruta, _ = QFileDialog.getSaveFileName(parent, "Exportar productos", nombre, "Productos (*.json)")\n    if not ruta:\n        return\n    try:\n        cantidad = BackupProductosService().exportar(ruta)\n    except Exception as e:\n        logger.exception("Error al exportar productos")\n        QMessageBox.critical(parent, "Exportar productos", f"No se pudo exportar:\\n{e}")\n        return\n    QMessageBox.information(parent, "Exportar productos", f"Se exportaron {cantidad} productos a:\\n{ruta}")\n\n\ndef importar_productos_ui(parent, usuario_id: int | None = None) -> dict | None:\n    """Devuelve el resumen si se importó algo, para que la pantalla se refresque."""\n    ruta, _ = QFileDialog.getOpenFileName(parent, "Importar productos", "", "Productos (*.json)")\n    if not ruta:\n        return None\n    try:\n        resumen = BackupProductosService().importar(ruta, usuario_id)\n    except ProductoBackupError as e:\n        QMessageBox.warning(parent, "Importar productos", str(e))\n        return None\n    except Exception as e:\n        logger.exception("Error al importar productos")\n        QMessageBox.critical(parent, "Importar productos", f"No se pudo importar:\\n{e}")\n        return None\n\n    mensaje = f"Productos creados: {resumen[\'creados\']}"\n    omitidos = resumen["omitidos"]\n    if omitidos:\n        mensaje += (f"\\nOmitidos por ya existir o estar repetidos: {len(omitidos)}\\n"\n                    + ", ".join(omitidos[:10]) + ("…" if len(omitidos) > 10 else ""))\n    QMessageBox.information(parent, "Importar productos", mensaje)\n    return resumen\n\n\ndef restaurar_backup_ui(parent, ruta=None) -> None:\n    if ruta is None:\n        ruta, _ = QFileDialog.getOpenFileName(\n            parent, "Elegir backup a restaurar", str(BACKUPS_DIR), "Base de datos (*.db)"\n        )\n    if not ruta:\n        return\n\n    respuesta = QMessageBox.warning(\n        parent, "Restaurar backup",\n        "Se reemplazará TODA la información actual (ventas, productos, clientes, "\n        "usuarios y configuración) por la del backup elegido.\\n\\n"\n        "Antes se guardará una copia de seguridad de lo actual, y la aplicación se "\n        "reiniciará al terminar.\\n\\n¿Continuar?",\n        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,\n    )\n    if respuesta != QMessageBox.Yes:\n        return\n\n    try:\n        restaurar_backup(ruta)\n    except BaseCerradaError as e:\n        # La conexión ya se cerró: hay que reiniciar sí o sí.\n        QMessageBox.critical(parent, "Restaurar backup", str(e))\n        reiniciar_aplicacion()\n        return\n    except Exception as e:\n        # Falló antes de tocar la base actual: se puede seguir trabajando.\n        logger.exception("Error al restaurar backup")\n        QMessageBox.critical(parent, "Restaurar backup", f"No se pudo restaurar:\\n{e}")\n        return\n\n    QMessageBox.information(parent, "Restaurar backup",\n                            "Backup restaurado. La aplicación se reiniciará ahora.")\n    reiniciar_aplicacion()\n'


class Fallo(Exception):
    pass


def buscar(nombre=None, contiene=None):
    res = []
    for carpeta, dirs, archivos in os.walk(RAIZ):
        dirs[:] = [d for d in dirs if d not in EXCLUIR]
        for a in archivos:
            if nombre is not None and a != nombre:
                continue
            if nombre is None and not a.endswith(".py"):
                continue
            p = Path(carpeta) / a
            if p.resolve() == Path(__file__).resolve():
                continue   # este mismo script no cuenta
            if contiene:
                try:
                    if contiene not in p.read_text(encoding="utf-8"):
                        continue
                except Exception:
                    continue
            res.append(p)
    return res


def unico(desc, nombre=None, contiene=None):
    res = buscar(nombre, contiene)
    if len(res) != 1:
        raise Fallo(f"No pude identificar {desc} (encontrados: {[str(r) for r in res] or 'ninguno'}).")
    return res[0]


def reemplazar_una_vez(texto, viejo, nuevo, desc):
    if texto.count(viejo) != 1:
        raise Fallo(f"{desc}: se esperaba 1 coincidencia y hay {texto.count(viejo)}.")
    return texto.replace(viejo, nuevo, 1)


def regex_una_vez(texto, patron, reemplazo, desc):
    nuevo, n = re.subn(patron, reemplazo, texto, flags=re.DOTALL)
    if n != 1:
        raise Fallo(f"{desc}: se esperaba 1 coincidencia y hay {n}.")
    return nuevo


def insertar_despues(texto, ancla, por_ocurrencia, desc):
    """Inserta líneas (con la misma sangría del ancla) tras cada línea cuyo
    contenido, sin espacios, sea exactamente `ancla`."""
    lineas = texto.splitlines(keepends=True)
    salida, n = [], 0
    for l in lineas:
        salida.append(l)
        if l.strip() == ancla:
            if n >= len(por_ocurrencia):
                n += 1
                continue
            if not l.endswith("\n"):
                salida[-1] = l + "\n"
            sangria = l[: len(l) - len(l.lstrip())]
            for nueva in por_ocurrencia[n]:
                salida.append((sangria + nueva if nueva else "") + "\n")
            n += 1
    if n != len(por_ocurrencia):
        raise Fallo(f"{desc}: se esperaban {len(por_ocurrencia)} coincidencias de «{ancla}» y hay {n}.")
    return "".join(salida)


def insertar_antes(texto, ancla, bloque, desc):
    lineas = texto.splitlines(keepends=True)
    idx = [i for i, l in enumerate(lineas) if l.strip() == ancla]
    if len(idx) != 1:
        raise Fallo(f"{desc}: se esperaba 1 coincidencia de «{ancla}» y hay {len(idx)}.")
    lineas[idx[0]:idx[0]] = [b + "\n" for b in bloque.split("\n")] + ["\n"]
    return "".join(lineas)


# ------------------------------------------------------------------ edits
def editar_schema(t):
    if "chofer TEXT" in t:
        return t
    return regex_una_vez(
        t,
        r"(caja_sesion_id INTEGER REFERENCES caja_sesiones\(id\))(\s*\);\s*CREATE INDEX IF NOT EXISTS idx_ventas_fecha)",
        r"\1,\n    chofer TEXT\2",
        "schema.sql (tabla ventas)",
    )


def editar_repo(t):
    if "chofer" in t:
        return t
    t = reemplazar_una_vez(t, "metodo_pago_id, pago_es_efectivo, caja_sesion_id) -> int:",
                           "metodo_pago_id, pago_es_efectivo, caja_sesion_id, chofer=None) -> int:", "crear_venta (firma)")
    t = reemplazar_una_vez(t, "pago_es_efectivo, estado, caja_sesion_id)",
                           "pago_es_efectivo, estado, caja_sesion_id, chofer)", "crear_venta (columnas)")
    t = reemplazar_una_vez(t, "'completada', ?)", "'completada', ?, ?)", "crear_venta (valores)")
    t = reemplazar_una_vez(t, "metodo_pago_id, int(pago_es_efectivo), caja_sesion_id),",
                           "metodo_pago_id, int(pago_es_efectivo), caja_sesion_id, chofer),", "crear_venta (parámetros)")
    return t


def editar_servicio(t):
    if "chofer" in t:
        return t
    t = regex_una_vez(t, r"(descuento: float = 0\.0,)(\s*\)\s*->\s*int:)",
                      r"\1\n        chofer: str | None = None,\2", "registrar_venta (firma)")
    t = reemplazar_una_vez(
        t, "metodo_pago_id, pago_es_efectivo, caja_sesion_id,",
        "metodo_pago_id, pago_es_efectivo, caja_sesion_id,\n"
        "                chofer=(chofer or \"\").strip() or None,",
        "registrar_venta (llamada al repositorio)")
    return t


METODOS_CHOFER = '''    def _chofer_predeterminado(self) -> str:
        """Chofer guardado en Configuración > Datos del ticket."""
        try:
            return (TicketExtrasService().para_ticket().get("chofer") or "").strip()
        except Exception:
            logger.exception("No se pudo leer el chofer predeterminado")
            return ""

    def _cargar_chofer_por_defecto(self, forzar: bool = False) -> None:
        """Pone el chofer predeterminado en el campo. No pisa lo que el usuario
        escribió a mano, salvo que se pida (forzar) o siga siendo el anterior
        predeterminado."""
        nuevo = self._chofer_predeterminado()
        actual = self.input_chofer.text().strip()
        anterior = getattr(self, "_chofer_default_anterior", "")
        if forzar or not actual or actual == anterior:
            self.input_chofer.setText(nuevo)
        self._chofer_default_anterior = nuevo'''


def editar_ventas_page(t):
    if "input_chofer" in t:
        return t
    t = insertar_despues(t, "from services.caja_service import CajaService",
                         [["from services.ticket_extras_service import TicketExtrasService"]], "import")
    t = insertar_antes(t, "def _cargar_metodos_pago(self) -> None:", METODOS_CHOFER, "métodos de chofer")
    t = insertar_despues(t, "fila_venta.addWidget(self.combo_metodo_pago)", [[
        "fila_venta.addSpacing(16)",
        "fila_venta.addWidget(QLabel(\"Chofer:\"))",
        "self.input_chofer = QLineEdit()",
        "self.input_chofer.setPlaceholderText(\"Chofer de esta venta\")",
        "self.input_chofer.setMinimumWidth(180)",
        "fila_venta.addWidget(self.input_chofer)",
    ]], "campo chofer en la UI")
    # 1ª aparición: en actualizar(); 2ª: al limpiar el formulario tras registrar.
    t = insertar_despues(t, "self._cargar_metodos_pago()", [
        ["self._cargar_chofer_por_defecto()"],
        ["self._cargar_chofer_por_defecto(forzar=True)"],
    ], "carga del chofer predeterminado")
    t = insertar_despues(t, "descuento=self.input_descuento.value(),",
                         [["chofer=self.input_chofer.text(),"]], "registrar_venta con chofer")
    return t


CLASE_BASE_CERRADA = [
    "",
    "",
    "class BaseCerradaError(Exception):",
    '    """La conexión ya se cerró y no se pudo reemplazar la base: hay que reiniciar la app."""',
]


def editar_backup(t):
    if "BaseCerradaError" in t:
        return t
    t = insertar_despues(t, "from utils.logger import logger", [CLASE_BASE_CERRADA], "clase BaseCerradaError")
    patron = (r"    get_db\(\)\.close\(\)\s*\n"
              r"    for sufijo in \(\"-wal\", \"-shm\"\):\s*\n"
              r"        Path\(str\(DATABASE_PATH\) \+ sufijo\)\.unlink\(missing_ok=True\)\s*\n"
              r"    os\.replace\(str\(temporal\), str\(DATABASE_PATH\)\)")
    nuevo = (
        "    get_db().close()\n"
        "    try:\n"
        "        for sufijo in (\"-wal\", \"-shm\"):\n"
        "            Path(str(DATABASE_PATH) + sufijo).unlink(missing_ok=True)\n"
        "        os.replace(str(temporal), str(DATABASE_PATH))\n"
        "    except OSError as e:\n"
        "        logger.exception(\"No se pudo reemplazar la base de datos al restaurar\")\n"
        "        _borrar_con_auxiliares(temporal)\n"
        "        raise BaseCerradaError(\n"
        "            \"No se pudo reemplazar la base de datos (puede estar abierta por otro programa \"\n"
        "            \"o bloqueada por OneDrive). La base actual no se modificó, pero la aplicación \"\n"
        "            \"debe reiniciarse.\"\n"
        "        ) from e"
    )
    return regex_una_vez(t, patron, nuevo.replace("\\", "\\\\"), "restaurar_backup (reemplazo de la base)")


def main():
    cambios = {}   # ruta -> texto nuevo

    def preparar(ruta, funcion):
        original = ruta.read_text(encoding="utf-8")
        nuevo = funcion(original)
        if nuevo != original:
            cambios[ruta] = nuevo
            print(f"  · modificará {ruta.relative_to(RAIZ)}")
        else:
            print(f"  · ya estaba aplicado: {ruta.relative_to(RAIZ)}")

    print("Buscando archivos…")
    schema = unico("schema.sql", nombre="schema.sql")
    repo = unico("venta_repository.py", nombre="venta_repository.py")
    servicio = unico("venta_service.py", nombre="venta_service.py")
    pagina = unico("ventas_page.py", nombre="ventas_page.py")
    backup = unico("el servicio de backup (def restaurar_backup)", contiene="def restaurar_backup(")

    preparar(schema, editar_schema)
    preparar(repo, editar_repo)
    preparar(servicio, editar_servicio)
    preparar(pagina, editar_ventas_page)
    preparar(backup, editar_backup)

    mod_backup = ".".join(backup.relative_to(RAIZ).with_suffix("").parts)
    acciones = MODULO_ACCIONES.replace("__MODULO_BACKUP__", mod_backup)

    carpeta_servicios = RAIZ / "services"
    carpeta_ui = RAIZ / "ui" / "configuracion"
    for c in (carpeta_servicios, carpeta_ui):
        if not c.is_dir():
            raise Fallo(f"No existe la carpeta {c.relative_to(RAIZ)}. ¿Estás en la raíz del proyecto?")

    nuevos = {
        carpeta_servicios / "backup_productos_service.py": MODULO_SERVICIO,
        carpeta_ui / "respaldo_acciones.py": acciones,
    }

    for ruta, texto in cambios.items():
        copia = ruta.with_name(ruta.name + ".bak_antes_cambios")
        if not copia.exists():
            copia.write_text(ruta.read_text(encoding="utf-8"), encoding="utf-8")
        ruta.write_text(texto, encoding="utf-8")
    for ruta, texto in nuevos.items():
        if ruta.exists():
            copia = ruta.with_name(ruta.name + ".bak_antes_cambios")
            if not copia.exists():
                copia.write_text(ruta.read_text(encoding="utf-8"), encoding="utf-8")
        ruta.write_text(texto, encoding="utf-8")
        print(f"  · escribió {ruta.relative_to(RAIZ)}")

    print("\nListo. Falta agregar 3 botones en ui/configuracion/configuracion_page.py "
          "(ver instrucciones) y reiniciar la app para que la base agregue la columna 'chofer'.")


if __name__ == "__main__":
    try:
        main()
    except Fallo as e:
        print(f"\nNO SE MODIFICÓ NADA. Motivo: {e}")
        sys.exit(1)