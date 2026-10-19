"""Nombres de días y meses en español y formatos de fecha/hora para la agenda y las boletas."""

from datetime import date, datetime, timedelta

DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def lunes_de(dia: date) -> date:
    """Lunes de la semana que contiene `dia`."""
    return dia - timedelta(days=dia.weekday())


def parsear_fecha(texto: str) -> date:
    """'YYYY-MM-DD' -> date."""
    return datetime.strptime(texto[:10], "%Y-%m-%d").date()


def fecha_larga(dia: date) -> str:
    """'martes 20 de octubre de 2026'."""
    return f"{DIAS_SEMANA[dia.weekday()]} {dia.day} de {MESES[dia.month - 1]} de {dia.year}"


def fecha_dmy(dia: date) -> str:
    """'20/10/2026'."""
    return f"{dia.day:02d}/{dia.month:02d}/{dia.year}"


def rango_semana(lunes: date) -> str:
    """'19 – 25 de octubre de 2026' (o con dos meses/años si la semana cruza el cambio)."""
    domingo = lunes + timedelta(days=6)
    if lunes.year != domingo.year:
        return (f"{lunes.day} de {MESES[lunes.month - 1]} de {lunes.year} – "
                f"{domingo.day} de {MESES[domingo.month - 1]} de {domingo.year}")
    if lunes.month != domingo.month:
        return (f"{lunes.day} de {MESES[lunes.month - 1]} – "
                f"{domingo.day} de {MESES[domingo.month - 1]} de {domingo.year}")
    return f"{lunes.day} – {domingo.day} de {MESES[domingo.month - 1]} de {domingo.year}"


def a_minutos(hhmm: str) -> int:
    """'08:30' -> 510."""
    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)


def a_hhmm(minutos: int) -> str:
    """510 -> '08:30'."""
    return f"{minutos // 60:02d}:{minutos % 60:02d}"
