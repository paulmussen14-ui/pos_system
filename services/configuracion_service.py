"""Lógica de negocio de configuración general del sistema."""

from database.connection import get_db


class ConfiguracionService:

    def __init__(self):
        self.db = get_db()
        self._migrar_columnas_faltantes()
        self._asegurar_fila_configuracion()

    def _migrar_columnas_faltantes(self) -> None:
        """
        Agrega columnas nuevas a tablas existentes sin perder datos.
        Necesario porque los usuarios que ya instalaron la app tienen la
        tabla configuracion_impresion sin la columna imprimir_dos_copias.
        """
        with self.db.transaction() as cur:
            cur.execute("PRAGMA table_info(configuracion_impresion)")
            columnas = {fila["name"] for fila in cur.fetchall()}
            if "imprimir_dos_copias" not in columnas:
                cur.execute(
                    "ALTER TABLE configuracion_impresion "
                    "ADD COLUMN imprimir_dos_copias INTEGER NOT NULL DEFAULT 1"
                )

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

    def actualizar_logo(self, ruta_logo: str) -> None:
        with self.db.transaction() as cur:
            cur.execute("UPDATE configuracion SET logo_path = ? WHERE id = 1", (ruta_logo,))

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