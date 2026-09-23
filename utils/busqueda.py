"""Ayudas para armar búsquedas seguras en SQLite (FTS5 y LIKE).

Guardar como utils/busqueda.py.

Problemas que resuelve:
1. Con FTS5, un texto como  Coca-Cola  o  Leche "Gloria"  dentro de MATCH
   provoca un error de sintaxis; la consulta falla y la lista queda vacía.
2. FTS5 solo encuentra desde el INICIO de una palabra: "ola" no encuentra
   "Coca Cola". Con LIKE '%ola%' sí.
3. En LIKE, los símbolos % y _ escritos por el usuario se comportan como
   comodines si no se escapan.
"""

import re


def palabras_de(texto: str) -> list:
    """Separa el texto en palabras (letras y números, con acentos y ñ)."""
    if not texto:
        return []
    return re.findall(r"\w+", texto)


def consulta_fts_prefijo(texto: str):
    """Arma una consulta MATCH segura: cada palabra entre comillas y con *
    para encontrar por prefijo. Devuelve None si no hay palabras.

    'coca col'  ->  "coca"* "col"*
    'Coca-Cola' ->  "Coca"* "Cola"*
    """
    palabras = palabras_de(texto)
    if not palabras:
        return None

    partes = []
    for palabra in palabras:
        partes.append('"' + palabra + '"*')
    return " ".join(partes)


def patron_like(texto: str) -> str:
    """Patrón LIKE '%texto%' con % y _ escapados. Usar con ESCAPE '\\'."""
    limpio = (texto or "").strip()
    limpio = limpio.replace("\\", "\\\\")
    limpio = limpio.replace("%", "\\%")
    limpio = limpio.replace("_", "\\_")
    return "%" + limpio + "%"


def filtro_por_palabras(columnas: list, texto: str):
    """Arma el filtro SQL de una búsqueda por LIKE, sin FTS.

    Cada palabra escrita debe aparecer en ALGUNA de las columnas indicadas,
    en cualquier orden y en cualquier parte del texto. Devuelve (sql, params);
    si no hay palabras devuelve ("", []) y no hay que filtrar nada.

    Ejemplo: filtro_por_palabras(["p.nombre"], "coca 1.5")
      -> ("(p.nombre LIKE ? ESCAPE '\\') AND (p.nombre LIKE ? ESCAPE '\\')",
          ["%coca%", "%1.5%"])
    """
    condiciones = []
    params = []

    for palabra in (texto or "").split():
        patron = patron_like(palabra)
        partes = []
        for columna in columnas:
            partes.append(columna + " LIKE ? ESCAPE '\\'")
            params.append(patron)
        condiciones.append("(" + " OR ".join(partes) + ")")

    return " AND ".join(condiciones), params