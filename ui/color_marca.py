"""Color de marca: el cliente elige UN color y el sistema calcula el resto.

A partir del color elegido se generan, para el tema claro y el oscuro, todos los tonos
que usa la app: botón principal, hover y presionado, fondos suaves de badges y
resaltados, texto sobre fondo suave y los colores del menú lateral.

"Inteligente" quiere decir que el sistema cuida la legibilidad por el cliente:
  - el botón principal se oscurece solo si el texto blanco no se leería (contraste >= 3.5,
    el mínimo para texto en negrita de botones);
  - el texto sobre los fondos suaves se ajusta hasta tener contraste >= 7;
  - el menú lateral siempre sale oscuro, con textos claros que se leen bien.

Este módulo no depende de Qt ni de otros módulos de la app (solo matemática de colores).
"""

import colorsys
import re

COLOR_DEFECTO = "#059669"   # el verde original del sistema
CONTRASTE_BOTON = 3.5       # contraste mínimo del texto blanco sobre el botón principal

# Colores listos para elegir (nombre, color base). Son puntos de partida: el sistema los
# ajusta si hace falta para que se lean bien.
PRESETS = [
    ("Esmeralda", "#059669"),
    ("Turquesa", "#0d9488"),
    ("Azul", "#2563eb"),
    ("Índigo", "#4f46e5"),
    ("Violeta", "#7c3aed"),
    ("Rosa", "#db2777"),
    ("Rojo", "#dc2626"),
    ("Naranja", "#c2410c"),
    ("Ámbar", "#b45309"),
    ("Grafito", "#475569"),
]

# Verdes del sistema original que están escritos a mano en los QSS base (resources/styles).
# Cada uno se reemplaza por el tono equivalente del color elegido. Los verdes de "éxito"
# (ventas cobradas, badges OK) NO están aquí: siguen verdes siempre.
_VERDES_CLARO = {"#059669": "base", "#047857": "hover", "#065f46": "presionado", "#d1fae5": "suave"}
_VERDES_OSCURO = {"#059669": "base", "#10b981": "brillante", "#047857": "hover",
                  "#0b3a2e": "suave", "#34d399": "texto"}

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def normalizar(color) -> str | None:
    """'#2563EB' / '2563eb' -> '#2563eb'. None si no es un color válido de 6 dígitos."""
    if not isinstance(color, str):
        return None
    m = _HEX.match(color.strip())
    return "#" + m.group(1).lower() if m else None


def _a_rgb(color: str) -> tuple[float, float, float]:
    return tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _a_hex(h: float, l: float, s: float) -> str:
    l = min(max(l, 0.0), 1.0)
    r, g, b = colorsys.hls_to_rgb(h % 1.0, l, min(max(s, 0.0), 1.0))
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def _luminancia(color: str) -> float:
    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in _a_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(color_a: str, color_b: str) -> float:
    """Relación de contraste WCAG entre dos colores (1 = igual, 21 = blanco sobre negro)."""
    la, lb = sorted((_luminancia(color_a), _luminancia(color_b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def generar(color: str) -> dict:
    """Calcula todos los tonos a partir del color elegido.

    Devuelve {"base": color final del botón (ya ajustado), "ajustado": bool,
              "claro": {...}, "oscuro": {...}} donde "claro" y "oscuro" tienen las claves
    de la paleta (primario, primario_hover, ..., menu_fondo, ...) y "qss_*" los reemplazos
    para los colores escritos a mano en los QSS base.
    """
    elegido = normalizar(color) or COLOR_DEFECTO
    h, l0, s = colorsys.rgb_to_hls(*_a_rgb(elegido))
    s = min(s, 0.95)

    # Color del botón principal: el elegido, oscurecido lo justo para que el texto blanco se lea.
    l = min(max(l0, 0.14), 0.60)
    while contraste(_a_hex(h, l, s), "#ffffff") < CONTRASTE_BOTON and l > 0.12:
        l -= 0.01
    base = _a_hex(h, l, s)

    # Hover / presionado: más oscuros; si el color ya es casi negro, más claros.
    if l >= 0.24:
        hover, presionado = _a_hex(h, l - 0.06, s), _a_hex(h, l - 0.12, s)
    else:
        hover, presionado = _a_hex(h, l + 0.07, s), _a_hex(h, l + 0.14, s)

    # Tema claro: fondo suave y texto legible encima.
    suave = _a_hex(h, 0.92, min(s, 0.85))
    lt = 0.22
    while contraste(_a_hex(h, lt, s), suave) < 7 and lt > 0.08:
        lt -= 0.01
    texto = _a_hex(h, lt, s)

    # Tema oscuro: tono más brillante para fondos oscuros.
    brillante = _a_hex(h, min(max(l + 0.08, 0.40), 0.56), s)
    lb = min(max(l + 0.08, 0.40), 0.56)
    brillante_hover = _a_hex(h, lb - 0.08, s)
    brillante_pres = _a_hex(h, max(lb - 0.15, 0.10), s)
    suave_osc = _a_hex(h, 0.13, s * 0.7)
    texto_osc = _a_hex(h, 0.72, min(s, 0.8))

    def menu(l_fondo: float, l_borde: float, l_hover: float, activo: str) -> dict:
        sm = min(s, 0.75)
        return {
            "menu_fondo": _a_hex(h, l_fondo, sm),
            "menu_borde": _a_hex(h, l_borde, sm),
            "menu_hover": _a_hex(h, l_hover, sm),
            "menu_texto": _a_hex(h, 0.88, min(s, 0.40)),
            "menu_texto_tenue": _a_hex(h, 0.62, min(s, 0.35)),
            "menu_activo": activo,
            "menu_icono": _a_hex(h, 0.66, min(s, 0.40)),
            "menu_icono_activo": "#ffffff",
        }

    claro = {
        "primario": base, "primario_hover": hover, "primario_presionado": presionado,
        "primario_suave": suave, "primario_texto": texto,
        "acento": base, "acento_hover": hover, "acento_suave": suave, "acento_texto": texto,
        **menu(0.14, 0.19, 0.17, brillante),
    }
    oscuro = {
        "primario": brillante, "primario_hover": brillante_hover,
        "primario_presionado": brillante_pres,
        "primario_suave": suave_osc, "primario_texto": texto_osc,
        "acento": brillante, "acento_hover": brillante_hover,
        "acento_suave": suave_osc, "acento_texto": texto_osc,
        **menu(0.10, 0.15, 0.15, brillante),
    }

    valores_claro = {"base": base, "hover": hover, "presionado": presionado, "suave": suave}
    valores_oscuro = {"base": base, "brillante": brillante, "hover": hover,
                      "suave": suave_osc, "texto": _a_hex(h, 0.52, s * 0.7)}
    return {
        "elegido": elegido,
        "base": base,
        "ajustado": base != elegido and abs(l - l0) > 0.005,
        "claro": claro,
        "oscuro": oscuro,
        "qss_claro": {v: valores_claro[r] for v, r in _VERDES_CLARO.items()},
        "qss_oscuro": {v: valores_oscuro[r] for v, r in _VERDES_OSCURO.items()},
    }


def recolorear_qss(qss: str, reemplazos: dict[str, str]) -> str:
    """Cambia los colores escritos a mano en un QSS (un solo paso, sin encadenar cambios)."""
    if not reemplazos:
        return qss
    patron = re.compile("(" + "|".join(re.escape(c) for c in reemplazos) + r")(?![0-9a-fA-F])",
                        re.IGNORECASE)
    return patron.sub(lambda m: reemplazos[m.group(1).lower()], qss)
