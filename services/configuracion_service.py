"""Lógica de negocio de configuración general del sistema."""

import shutil
from pathlib import Path

from PIL import Image

from config import APP_DATA_DIR
from database.connection import get_db
from utils.logger import logger

# Extensiones que acepta "Cambiar logo..." / "Cambiar QR de Yape...".
EXTENSIONES_IMAGEN = (".png", ".jpg", ".jpeg")


class ConfiguracionService:

    def __init__(self):
        self.db = get_db()
        self._migrar_columnas_faltantes()
        self._asegurar_fila_configuracion()

    def _migrar_columnas_faltantes(self) -> None:
        """
        Agrega columnas nuevas a tablas existentes sin perder datos.
        Necesario porque los usuarios que ya instalaron la app tienen la
        tabla configuracion_impresion sin la columna imprimir_dos_copias,
        y la tabla configuracion sin la columna qr_yape_path.
        """
        with self.db.transaction() as cur:
            cur.execute("PRAGMA table_info(configuracion_impresion)")
            columnas = {fila["name"] for fila in cur.fetchall()}
            if "imprimir_dos_copias" not in columnas:
                cur.execute(
                    "ALTER TABLE configuracion_impresion "
                    "ADD COLUMN imprimir_dos_copias INTEGER NOT NULL DEFAULT 1"
                )

            cur.execute("PRAGMA table_info(configuracion)")
            columnas_config = {fila["name"] for fila in cur.fetchall()}
            if "qr_yape_path" not in columnas_config:
                cur.execute("ALTER TABLE configuracion ADD COLUMN qr_yape_path TEXT")

    def _asegurar_fila_configuracion(self) -> None:
        with self.db.transaction() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM configuracion")
            if cur.fetchone()["total"] == 0:
                cur.execute("INSERT INTO configuracion (id, nombre_negocio) VALUES (1, 'Mi Negocio')")
            cur.execute("SELECT COUNT(*) AS total FROM configuracion_impresion")
            if cur.fetchone()["total"] == 0:
                cur.execute("INSERT INTO configuracion_impresion (id) VALUES (1)")
            cur.execute("SELECT COUNT(*) AS total FROM metodos_pago")
            if cur.fetchone()["total"] == 0:
                metodos_default = (
                    ("Efectivo", 1),
                    ("Tarjeta", 0),
                    ("Yape/Plin", 0),
                    ("Transferencia", 0),
                )
                for nombre, es_efectivo in metodos_default:
                    cur.execute(
                        "INSERT INTO metodos_pago (nombre, es_efectivo) VALUES (?, ?)",
                        (nombre, es_efectivo),
                    )

    def obtener(self) -> dict:
        cur = self.db.get_connection().execute("SELECT * FROM configuracion WHERE id = 1")
        return dict(cur.fetchone())

    def actualizar(self, nombre_negocio: str, direccion: str, moneda: str,
                    igv_porcentaje: float, ticket_pie: str, tema: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                """UPDATE configuracion SET
                       nombre_negocio = ?, direccion = ?, moneda = ?,
                       igv_porcentaje = ?, ticket_pie = ?, tema = ?,
                       actualizado_en = datetime('now', 'localtime')
                   WHERE id = 1""",
                (nombre_negocio, direccion, moneda, igv_porcentaje, ticket_pie, tema),
            )

    # ------------------------------------------------------ Imágenes ----
    def _guardar_imagen(self, ruta_origen: str, nombre_archivo: str) -> str:
        """
        Valida que ruta_origen sea una imagen legible y la copia a
        APP_DATA_DIR con un nombre fijo (ej. "logo.png", "qr_yape.jpg"), en
        vez de guardar solo la ruta que eligió el usuario. Así, si el
        usuario mueve, renombra o borra el archivo original después, el
        logo/QR guardado en la app no se rompe.

        Lanza ValueError (con un mensaje apto para mostrar al usuario) si
        el archivo no existe o no es una imagen válida.
        """
        origen = Path(ruta_origen)
        if not origen.exists():
            raise ValueError("El archivo seleccionado no existe.")

        try:
            with Image.open(origen) as img:
                img.verify()
        except Exception as exc:
            raise ValueError("El archivo seleccionado no es una imagen válida.") from exc

        extension = origen.suffix.lower() or ".png"
        destino = APP_DATA_DIR / f"{nombre_archivo}{extension}"

        # Si antes había una versión con otra extensión (ej. tenía logo.jpg
        # y ahora sube logo.png), borramos la vieja para no dejar archivos
        # huérfanos ocupando espacio.
        for existente in APP_DATA_DIR.glob(f"{nombre_archivo}.*"):
            if existente != destino:
                existente.unlink(missing_ok=True)

        # Si el usuario elige justo el archivo que la app ya tiene guardado,
        # no hay nada que copiar (copyfile fallaría con SameFileError).
        if origen.resolve() != destino.resolve():
            shutil.copyfile(origen, destino)
        return str(destino)

    def _quitar_imagen(self, columna: str) -> None:
        """
        Deja la columna (logo_path o qr_yape_path) en NULL y borra el archivo
        guardado en APP_DATA_DIR. Solo se borra el archivo si está dentro de
        APP_DATA_DIR (el que copió la app), nunca uno que esté en otra carpeta.
        Si el archivo ya no existe o no se puede borrar, igual se quita la
        imagen de la configuración y el error queda en el log.
        """
        if columna not in ("logo_path", "qr_yape_path"):
            raise ValueError(f"Columna de imagen no válida: {columna}")

        fila = self.db.get_connection().execute(
            f"SELECT {columna} AS ruta FROM configuracion WHERE id = 1"
        ).fetchone()
        ruta = fila["ruta"] if fila else None

        with self.db.transaction() as cur:
            cur.execute(f"UPDATE configuracion SET {columna} = NULL WHERE id = 1")

        if not ruta:
            return
        archivo = Path(ruta)
        try:
            if archivo.parent.resolve() == APP_DATA_DIR.resolve():
                archivo.unlink(missing_ok=True)
        except OSError:
            logger.exception(f"No se pudo borrar el archivo de imagen: {ruta}")

    def actualizar_logo(self, ruta_logo: str) -> None:
        ruta_guardada = self._guardar_imagen(ruta_logo, "logo")
        with self.db.transaction() as cur:
            cur.execute("UPDATE configuracion SET logo_path = ? WHERE id = 1", (ruta_guardada,))

    def quitar_logo(self) -> None:
        """Quita el logo: deja de imprimirse en el ticket y se borra su archivo."""
        self._quitar_imagen("logo_path")

    def actualizar_qr_yape(self, ruta_qr: str | None) -> None:
        ruta_guardada = self._guardar_imagen(ruta_qr, "qr_yape") if ruta_qr else None
        with self.db.transaction() as cur:
            cur.execute("UPDATE configuracion SET qr_yape_path = ? WHERE id = 1", (ruta_guardada,))

    def quitar_qr_yape(self) -> None:
        """Quita el QR de Yape: deja de imprimirse en el ticket y se borra su archivo."""
        self._quitar_imagen("qr_yape_path")

    def reparar_rutas_imagenes(self) -> list[str]:
        """
        Reconecta el logo y el QR de Yape con su archivo cuando la base de
        datos perdió la referencia. Pasa, por ejemplo, si se abrió otra base
        (o se restauró un backup) mientras las imágenes seguían guardadas en
        la carpeta de datos: la imagen está, pero qr_yape_path quedó vacío o
        apunta a una carpeta que ya no existe.

        Para cada imagen cuyo archivo no se encuentra en la ruta guardada
        (o que no tiene ruta), busca logo.* / qr_yape.* dentro de
        APP_DATA_DIR y, si lo encuentra, guarda esa ruta. Si la ruta guardada
        sigue siendo válida no toca nada. Devuelve una descripción de lo que
        reparó (lista vacía si no hizo falta nada).
        """
        reparadas = []
        config = self.obtener()
        for columna, base, descripcion in (
            ("logo_path", "logo", "el logo"),
            ("qr_yape_path", "qr_yape", "el QR de Yape"),
        ):
            ruta = config.get(columna)
            if ruta and Path(ruta).is_file():
                continue

            candidatos = sorted(
                p for p in APP_DATA_DIR.glob(f"{base}.*")
                if p.is_file() and p.suffix.lower() in EXTENSIONES_IMAGEN
            )
            if not candidatos:
                continue

            with self.db.transaction() as cur:
                cur.execute(f"UPDATE configuracion SET {columna} = ? WHERE id = 1", (str(candidatos[0]),))
            mensaje = f"Se reconectó {descripcion} con el archivo {candidatos[0].name}"
            logger.warning(f"{mensaje} (ruta guardada antes: {ruta!r})")
            reparadas.append(mensaje)
        return reparadas

    def obtener_config_impresion(self) -> dict:
        cur = self.db.get_connection().execute("SELECT * FROM configuracion_impresion WHERE id = 1")
        return dict(cur.fetchone())

    def actualizar_config_impresion(self, tipo_impresora: str, ancho_papel_mm: int,
                                     nombre_impresora: str, activo: bool,
                                     imprimir_dos_copias: bool = True) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                """UPDATE configuracion_impresion SET
                       tipo_impresora = ?, ancho_papel_mm = ?, nombre_impresora = ?,
                       activo = ?, imprimir_dos_copias = ?
                   WHERE id = 1""",
                (tipo_impresora, ancho_papel_mm, nombre_impresora, int(activo), int(imprimir_dos_copias)),
            )

    def listar_metodos_pago(self) -> list[dict]:
        cur = self.db.get_connection().execute("SELECT * FROM metodos_pago ORDER BY nombre")
        return [dict(r) for r in cur.fetchall()]

    def crear_metodo_pago(self, nombre: str, es_efectivo: bool = False) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO metodos_pago (nombre, es_efectivo) VALUES (?, ?)",
                (nombre.strip(), int(es_efectivo)),
            )

    def alternar_metodo_pago(self, metodo_id: int, activo: bool) -> None:
        with self.db.transaction() as cur:
            cur.execute("UPDATE metodos_pago SET activo = ? WHERE id = ?", (int(activo), metodo_id))