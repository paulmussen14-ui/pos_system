"""Funciones de validación reutilizables para formularios de la UI."""


def es_numero_positivo(texto: str) -> bool:
    try:
        return float(texto.replace(",", ".")) >= 0
    except (ValueError, AttributeError):
        return False


def es_numero_mayor_a_cero(texto: str) -> bool:
    try:
        return float(texto.replace(",", ".")) > 0
    except (ValueError, AttributeError):
        return False


def a_float_seguro(texto: str, valor_default: float = 0.0) -> float:
    try:
        return float(str(texto).replace(",", "."))
    except (ValueError, AttributeError):
        return valor_default


def texto_no_vacio(texto: str) -> bool:
    return bool(texto and texto.strip())


def formatear_moneda(monto: float, simbolo: str = "S/") -> str:
    return f"{simbolo} {monto:,.2f}"
