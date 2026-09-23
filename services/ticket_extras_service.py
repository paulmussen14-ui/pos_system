"""Datos extra del ticket: número para reclamos, términos de devolución, Yape,
chofer y número del negocio.

Se guardan en su propia tabla (configuracion_ticket, una sola fila) que se
crea sola la primera vez, así no hace falta tocar la base ni migrar nada.
"""

from database.connection import get_db

# Campos que se guardan (nombre de columna = nombre del campo).
CAMPOS = [
    "telefono_negocio",
    "telefono_reclamos",
    "yape_numero",
    "yape_titular",
    "chofer",
    "politica_devolucion",
]


class TicketExtrasService:

    _tabla_lista = False

    def __init__(self):
        self.db = get_db()
        self._crear_tabla_si_no_existe()

    def _crear_tabla_si_no_existe(self) -> None:
        if TicketExtrasService._tabla_lista:
            return
        with self.db.transaction() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS configuracion_ticket (
                       id INTEGER PRIMARY KEY CHECK (id = 1),
                       telefono_negocio TEXT NOT NULL DEFAULT '',
                       telefono_reclamos TEXT NOT NULL DEFAULT '',
                       yape_numero TEXT NOT NULL DEFAULT '',
                       yape_titular TEXT NOT NULL DEFAULT '',
                       chofer TEXT NOT NULL DEFAULT '',
                       politica_devolucion TEXT NOT NULL DEFAULT ''
                   )"""
            )
        TicketExtrasService._tabla_lista = True

    def obtener(self) -> dict:
        """Devuelve todos los campos (vacíos si todavía no se guardó nada)."""
        cur = self.db.get_connection().execute(
            "SELECT * FROM configuracion_ticket WHERE id = 1"
        )
        fila = cur.fetchone()
        datos = dict(fila) if fila else {}

        resultado = {}
        for campo in CAMPOS:
            resultado[campo] = datos.get(campo) or ""
        return resultado

    def guardar(self, datos: dict) -> None:
        valores = []
        for campo in CAMPOS:
            valores.append((datos.get(campo) or "").strip())

        columnas = ", ".join(CAMPOS)
        signos = ", ".join(["?"] * len(CAMPOS))
        asignaciones = ", ".join(f"{campo} = excluded.{campo}" for campo in CAMPOS)

        with self.db.transaction() as cur:
            cur.execute(
                f"""INSERT INTO configuracion_ticket (id, {columnas})
                    VALUES (1, {signos})
                    ON CONFLICT(id) DO UPDATE SET {asignaciones}""",
                valores,
            )

    def para_ticket(self) -> dict:
        """Solo los campos con valor, con los nombres que usa ticket_template."""
        datos = self.obtener()
        nombres_en_ticket = {
            "telefono_negocio": "telefono",
            "telefono_reclamos": "telefono_reclamos",
            "yape_numero": "yape_numero",
            "yape_titular": "yape_titular",
            "chofer": "chofer",
            "politica_devolucion": "politica_devolucion",
        }

        resultado = {}
        for campo, nombre_ticket in nombres_en_ticket.items():
            if datos[campo]:
                resultado[nombre_ticket] = datos[campo]
        return resultado