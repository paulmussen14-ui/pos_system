"""Sistema de diseño: valores únicos de color, espaciado, radios y tipografía.

Todo el aspecto de la app sale de aquí. La plantilla de estilos
(ui/estilos_erp.py) usa estos valores con marcadores {{nombre}}, y el código
de las pantallas puede importar las constantes de espaciado para que los
layouts coincidan con los estilos.

Escala de espaciado: 8 / 16 / 24 (con 4 y 32 para casos puntuales).
Radios: 6 (campos, botones), 8 (tablas, listas), 12 (tarjetas, diálogos).
Tipografía: título 22, subtítulo 15, texto 13, ayuda 12.
"""

from ui import color_marca as _color_marca

# --- Espaciado (px) ---
ESPACIO_XS = 4
ESPACIO_SM = 8
ESPACIO_MD = 16
ESPACIO_LG = 24
ESPACIO_XL = 32

# --- Radios (px) ---
RADIO_SM = 6
RADIO_MD = 8
RADIO_LG = 12

# --- Tipografía (px) ---
TIPO_TITULO = 22
TIPO_SUBTITULO = 15
TIPO_TEXTO = 13
TIPO_AYUDA = 12
TIPO_KPI = 26
TIPO_TOTAL = 28

# --- Medidas fijas de la estructura ---
ANCHO_SIDEBAR = 240
MARGEN_PAGINA = ESPACIO_LG  # margen exterior de cada pantalla

ESCALAS = {
    "e_xs": ESPACIO_XS, "e_sm": ESPACIO_SM, "e_md": ESPACIO_MD,
    "e_lg": ESPACIO_LG, "e_xl": ESPACIO_XL,
    "r_sm": RADIO_SM, "r_md": RADIO_MD, "r_lg": RADIO_LG,
    "t_titulo": TIPO_TITULO, "t_subtitulo": TIPO_SUBTITULO,
    "t_texto": TIPO_TEXTO, "t_ayuda": TIPO_AYUDA,
    "t_kpi": TIPO_KPI, "t_total": TIPO_TOTAL,
    "ancho_sidebar": ANCHO_SIDEBAR,
}

# --- Paletas ---
# Familias semánticas: primario, exito, peligro, aviso, info.
# Cada una tiene el color fuerte, uno suave (fondo de badges y avisos) y uno
# de texto legible sobre ese fondo suave.
PALETAS = {
    "claro": {
        # Neutros
        "fondo": "#f3f5f9",
        "superficie": "#ffffff",
        "superficie_alt": "#f8fafc",
        "input_fondo": "#ffffff",
        "borde": "#e2e8f0",
        "borde_fuerte": "#cbd5e1",
        "texto": "#0f172a",
        "texto_suave": "#475569",
        "texto_tenue": "#94a3b8",
        "hover": "#f1f5f9",
        # Primario
        "primario": "#059669",
        "primario_hover": "#047857",
        "primario_presionado": "#065f46",
        "primario_suave": "#d1fae5",
        "primario_texto": "#065f46",
        # Éxito
        "exito": "#16a34a",
        "exito_hover": "#15803d",
        "exito_suave": "#dcfce7",
        "exito_texto": "#166534",
        # Acento: botones de acción principal ("success"), enlaces y resaltados. De fábrica es
        # el verde de éxito; con un color de marca pasa a ser el color de marca.
        "acento": "#16a34a",
        "acento_hover": "#15803d",
        "acento_suave": "#dcfce7",
        "acento_texto": "#166534",
        # Peligro
        "peligro": "#dc2626",
        "peligro_hover": "#b91c1c",
        "peligro_suave": "#fee2e2",
        "peligro_texto": "#991b1b",
        # Aviso
        "aviso": "#d97706",
        "aviso_suave": "#fef3c7",
        "aviso_texto": "#92400e",
        # Info
        "info": "#0284c7",
        "info_suave": "#e0f2fe",
        "info_texto": "#075985",
        # Neutro para badges
        "neutro_suave": "#e2e8f0",
        "neutro_texto": "#334155",
        # Menú lateral
        "menu_fondo": "#063f3a",
        "menu_borde": "#0d5750",
        "menu_texto": "#d3ebe6",
        "menu_texto_tenue": "#7fb8ad",
        "menu_hover": "#0b4f48",
        "menu_activo": "#10b981",
        "menu_icono": "#8fcabe",
        "menu_icono_activo": "#ffffff",
        # Deshabilitado
        "deshab_fondo": "#cbd5e1",
        "deshab_texto": "#f8fafc",
    },
    "oscuro": {
        "fondo": "#0f141c",
        "superficie": "#18202c",
        "superficie_alt": "#1d2634",
        "input_fondo": "#111823",
        "borde": "#2a3444",
        "borde_fuerte": "#3b475a",
        "texto": "#e6eaf0",
        "texto_suave": "#a3aebf",
        "texto_tenue": "#6b778a",
        "hover": "#212c3c",
        "primario": "#10b981",
        "primario_hover": "#059669",
        "primario_presionado": "#047857",
        "primario_suave": "#0b3a2e",
        "primario_texto": "#6ee7b7",
        "exito": "#22c55e",
        "exito_hover": "#16a34a",
        "exito_suave": "#12301f",
        "exito_texto": "#86efac",
        "acento": "#22c55e",
        "acento_hover": "#16a34a",
        "acento_suave": "#12301f",
        "acento_texto": "#86efac",
        "peligro": "#ef4444",
        "peligro_hover": "#dc2626",
        "peligro_suave": "#3d1a1d",
        "peligro_texto": "#fca5a5",
        "aviso": "#f59e0b",
        "aviso_suave": "#3a2b0e",
        "aviso_texto": "#fcd34d",
        "info": "#38bdf8",
        "info_suave": "#10304a",
        "info_texto": "#7dd3fc",
        "neutro_suave": "#2a3444",
        "neutro_texto": "#cbd5e1",
        "menu_fondo": "#04302c",
        "menu_borde": "#0a423c",
        "menu_texto": "#cfe5e0",
        "menu_texto_tenue": "#6fa89d",
        "menu_hover": "#0a423c",
        "menu_activo": "#10b981",
        "menu_icono": "#85bfb3",
        "menu_icono_activo": "#ffffff",
        "deshab_fondo": "#2a3444",
        "deshab_texto": "#6b778a",
    },
}


# Color de marca elegido por el cliente (Configuración → Apariencia). None = verde original.
_marca: dict | None = None


def establecer_color_marca(color: str | None) -> None:
    """Fija el color de marca: recalcula los tonos del primario y del menú lateral.
    None, vacío, inválido o el verde original dejan la paleta tal cual viene de fábrica."""
    global _marca
    color = _color_marca.normalizar(color)
    _marca = None if color in (None, _color_marca.COLOR_DEFECTO) else _color_marca.generar(color)


def paleta(tema: str) -> dict[str, str]:
    """Devuelve la paleta del tema ('claro' u 'oscuro'; cualquier otro valor = claro),
    con los tonos del color de marca si el cliente eligió uno."""
    clave = "oscuro" if tema == "oscuro" else "claro"
    base = PALETAS[clave]
    return {**base, **_marca[clave]} if _marca else base


def recolorear_qss(qss: str, tema: str) -> str:
    """Aplica el color de marca a los colores escritos a mano en los QSS base."""
    if not _marca:
        return qss
    return _color_marca.recolorear_qss(qss, _marca["qss_oscuro" if tema == "oscuro" else "qss_claro"])
