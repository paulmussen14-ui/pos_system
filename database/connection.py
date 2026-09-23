"""
Conexión centralizada a la base de datos SQLite.

Provee una única conexión (patrón singleton) para toda la aplicación,
configura los PRAGMA necesarios y expone un context manager para
transacciones seguras (BEGIN / COMMIT / ROLLBACK).
"""

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config import DATABASE_PATH, SCHEMA_PATH


class DatabaseConnection:
    """Maneja una única conexión SQLite compartida por toda la app."""

    _instance: "DatabaseConnection | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_connection()
        return cls._instance

    def _init_connection(self) -> None:
        Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(
            str(DATABASE_PATH),
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row

        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")

        self._aplicar_esquema()

    def _aplicar_esquema(self) -> None:
        """Ejecuta schema.sql (crea tablas nuevas) y luego migra columnas
        nuevas hacia tablas que ya existían en instalaciones anteriores."""
        schema_sql = Path(SCHEMA_PATH).read_text(encoding="utf-8")
        self.conn.executescript(schema_sql)
        self.conn.commit()
        self._migrar_columnas_faltantes(schema_sql)
        self._poblar_fts_si_vacio("clientes_fts", "clientes")
        self._poblar_fts_si_vacio("productos_fts", "productos")

    def _poblar_fts_si_vacio(self, tabla_fts: str, tabla_origen: str) -> None:
        """Puebla la tabla FTS solo la primera vez (cuando está vacía).

        El CREATE VIRTUAL TABLE en schema.sql se repite en cada arranque
        (es IF NOT EXISTS), pero el poblado de datos no puede ir ahí:
        como schema.sql se ejecuta siempre, un INSERT masivo ahí
        duplicaría todas las filas en cada arranque. Aquí se hace una
        sola vez -- en arranques posteriores los triggers AFTER
        INSERT/UPDATE/DELETE ya mantienen la tabla FTS sincronizada,
        así que si ya tiene datos no se vuelve a insertar nada.

        Esto también resuelve la migración de instalaciones existentes:
        la primera vez que abren la nueva versión, la tabla FTS existe
        pero está vacía, así que se puebla sola desde la tabla original.
        """
        cur = self.conn.execute(f"SELECT COUNT(*) AS total FROM {tabla_fts}")
        if cur.fetchone()["total"] == 0:
            self.conn.execute(
                f"INSERT INTO {tabla_fts}(rowid, nombre) SELECT id, nombre FROM {tabla_origen}"
            )
            self.conn.commit()

    def _migrar_columnas_faltantes(self, schema_sql: str) -> None:
        """
        CREATE TABLE IF NOT EXISTS no agrega columnas nuevas a tablas que ya
        existían en instalaciones previas (SQLite no migra automáticamente).

        Esta función lee schema.sql, extrae todas las columnas que CADA
        tabla DEBERÍA tener, las compara contra las columnas que la tabla
        REALMENTE tiene en este archivo .db, y agrega con ALTER TABLE las
        que falten. Así, cualquier columna nueva que se agregue a
        schema.sql en el futuro se aplica sola en bases de datos antiguas,
        sin necesidad de scripts de migración manuales.
        """
        patron_tabla = re.compile(
            r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\)\s*;",
            re.IGNORECASE | re.DOTALL,
        )

        for match in patron_tabla.finditer(schema_sql):
            tabla = match.group(1)
            cuerpo = match.group(2)

            cur = self.conn.execute(f"PRAGMA table_info({tabla})")
            columnas_existentes = {fila[1] for fila in cur.fetchall()}

            for nombre_columna, definicion in self._parsear_columnas(cuerpo):
                if nombre_columna in columnas_existentes:
                    continue
                try:
                    self.conn.execute(
                        f"ALTER TABLE {tabla} ADD COLUMN {nombre_columna} {definicion}"
                    )
                except sqlite3.OperationalError:
                    # Restricciones que ALTER TABLE no soporta agregar después
                    # (ej. PRIMARY KEY): se ignora, porque esa columna ya
                    # debía existir desde la creación original de la tabla.
                    pass

        self.conn.commit()

    @staticmethod
    def _parsear_columnas(cuerpo_tabla: str) -> list[tuple[str, str]]:
        """Divide el cuerpo de un CREATE TABLE en columnas individuales,
        respetando comas dentro de paréntesis (ej. DEFAULT (datetime(...)))."""
        segmentos = []
        actual = []
        profundidad = 0
        for char in cuerpo_tabla:
            if char == "(":
                profundidad += 1
                actual.append(char)
            elif char == ")":
                profundidad -= 1
                actual.append(char)
            elif char == "," and profundidad == 0:
                segmentos.append("".join(actual))
                actual = []
            else:
                actual.append(char)
        if actual:
            segmentos.append("".join(actual))

        palabras_reservadas = ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE(", "CHECK(")
        columnas = []
        for segmento in segmentos:
            linea = " ".join(segmento.split())  # normaliza espacios/saltos de línea
            if not linea or linea.upper().startswith(palabras_reservadas):
                continue
            partes = linea.split(" ", 1)
            if len(partes) == 2:
                nombre, definicion = partes
                columnas.append((nombre, definicion))
        return columnas

    def get_connection(self) -> sqlite3.Connection:
        return self.conn

    @contextmanager
    def transaction(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("BEGIN")
            yield cursor
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cursor.close()

    def close(self) -> None:
        if self.conn:
            self.conn.close()


def get_db() -> DatabaseConnection:
    """Punto de acceso único a la base de datos en toda la app."""
    return DatabaseConnection()