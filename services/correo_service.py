"""Envío de correos (boletas en PDF) por SMTP.

Es lo único del sistema que necesita Internet, y solo cuando se pide enviar un
correo. Funciona con cualquier proveedor SMTP (Gmail, Outlook, el correo del
dominio del negocio...). Los datos de conexión se guardan en Configuración → Correo.

Esta función NO toca widgets de Qt, así que puede correr dentro de un Worker
(hilo aparte) sin congelar la ventana.
"""

import mimetypes
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from services.configuracion_service import ConfiguracionService
from utils.fechas import fecha_dmy, fecha_larga, parsear_fecha
from utils.logger import logger
from utils.validators import es_email_valido, formatear_moneda

TIEMPO_ESPERA_SEG = 20


class CorreoError(Exception):
    """Fallo al configurar o enviar un correo (mensaje apto para mostrar al usuario)."""


def correo_configurado() -> bool:
    """True si hay servidor, usuario y contraseña guardados."""
    datos = ConfiguracionService().obtener_correo()
    return bool(datos["host"] and datos["usuario"] and datos["password"])


def _direccion_remitente(datos: dict) -> str:
    direccion = datos["remitente_email"] or datos["usuario"]
    if not es_email_valido(direccion):
        raise CorreoError(
            "Falta el correo remitente. En Configuración → Correo escribe el correo "
            "desde el que se enviarán las boletas."
        )
    return direccion


def cargar_datos_correo() -> tuple[dict, str]:
    """Lee la configuración de correo y el nombre del negocio. Llamar desde el hilo
    principal y pasar el resultado a enviar_correo(), así el hilo de envío no toca
    la base de datos."""
    config = ConfiguracionService()
    return config.obtener_correo(), (config.obtener().get("nombre_negocio") or "").strip()


def enviar_correo(destinatario: str, asunto: str, cuerpo: str,
                  adjuntos: list[Path] | None = None,
                  datos: dict | None = None, nombre_negocio: str | None = None) -> None:
    """Envía un correo de texto con adjuntos opcionales. Lanza CorreoError con un
    mensaje claro si algo falla (configuración, red, usuario/contraseña...).

    datos / nombre_negocio: resultado de cargar_datos_correo(). Si no se pasan, se
    leen de la base de datos (solo hacerlo desde el hilo principal).
    """
    destinatario = (destinatario or "").strip()
    if not es_email_valido(destinatario):
        raise CorreoError("El correo del destinatario no es válido.")

    if datos is None:
        datos, nombre_negocio = cargar_datos_correo()
    if not (datos["host"] and datos["usuario"] and datos["password"]):
        raise CorreoError(
            "El correo todavía no está configurado. Complétalo en Configuración → Correo."
        )

    nombre_remitente = datos["remitente_nombre"] or (nombre_negocio or "")

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = formataddr((nombre_remitente, _direccion_remitente(datos)))
    mensaje["To"] = destinatario
    mensaje.set_content(cuerpo)

    for ruta in adjuntos or []:
        ruta = Path(ruta)
        if not ruta.is_file():
            raise CorreoError(f"No se encontró el archivo a adjuntar: {ruta.name}")
        tipo, _ = mimetypes.guess_type(ruta.name)
        principal, _, secundario = (tipo or "application/octet-stream").partition("/")
        mensaje.add_attachment(ruta.read_bytes(), maintype=principal,
                               subtype=secundario, filename=ruta.name)

    try:
        _enviar(datos, mensaje)
    except smtplib.SMTPAuthenticationError as exc:
        logger.warning("Correo: autenticación rechazada (%s)", exc.smtp_code)
        raise CorreoError(
            "El servidor rechazó el usuario o la contraseña. Si usas Gmail u Outlook "
            "necesitas una «contraseña de aplicación», no la contraseña normal."
        ) from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise CorreoError("El servidor no aceptó el correo del destinatario.") from exc
    except smtplib.SMTPException as exc:
        logger.warning("Correo: error SMTP: %s", exc)
        raise CorreoError(f"El servidor de correo respondió con un error: {exc}") from exc
    except socket.gaierror as exc:
        raise CorreoError(
            "No se encontró el servidor de correo. Revisa el nombre del servidor y tu conexión a Internet."
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise CorreoError("El servidor de correo tardó demasiado en responder.") from exc
    except ssl.SSLError as exc:
        raise CorreoError(
            "No se pudo establecer una conexión segura. Prueba cambiar el tipo de "
            "seguridad o el puerto (465 con SSL, 587 con STARTTLS)."
        ) from exc
    except OSError as exc:
        raise CorreoError(f"No se pudo conectar con el servidor de correo: {exc}") from exc


def _enviar(datos: dict, mensaje: EmailMessage) -> None:
    host, puerto, seguridad = datos["host"], datos["puerto"], datos["seguridad"]
    contexto = ssl.create_default_context()
    if seguridad == "ssl":
        servidor = smtplib.SMTP_SSL(host, puerto, timeout=TIEMPO_ESPERA_SEG, context=contexto)
    else:
        servidor = smtplib.SMTP(host, puerto, timeout=TIEMPO_ESPERA_SEG)
    with servidor:
        if seguridad == "starttls":
            servidor.starttls(context=contexto)
        servidor.login(datos["usuario"], datos["password"])
        servidor.send_message(mensaje)


def enviar_prueba(destinatario: str, datos: dict | None = None,
                  nombre_negocio: str | None = None) -> None:
    """Correo corto para comprobar que la configuración funciona."""
    if datos is None:
        datos, nombre_negocio = cargar_datos_correo()
    nombre = nombre_negocio or "tu negocio"
    enviar_correo(
        destinatario,
        f"Prueba de correo - {nombre}",
        f"Hola,\n\nEste es un correo de prueba enviado desde el sistema de {nombre}.\n"
        "Si lo estás leyendo, el envío de boletas por correo ya funciona.\n",
        datos=datos, nombre_negocio=nombre_negocio,
    )


def enviar_correo_seguro(*args, **kwargs) -> str | None:
    """Igual que enviar_correo pero devuelve el mensaje de error en vez de lanzarlo
    (None si todo salió bien). Pensada para correr dentro de un Worker."""
    try:
        enviar_correo(*args, **kwargs)
    except CorreoError as exc:
        return str(exc)
    except Exception:
        logger.exception("Correo: error inesperado al enviar")
        return "Ocurrió un error inesperado al enviar el correo. Revisa el registro (logs) del programa."
    return None


def armar_correo_adelanto(reserva: dict, config_negocio: dict, monto: float) -> tuple[str, str]:
    """(asunto, cuerpo) del aviso que recibe el cliente cuando paga un adelanto de su reserva."""
    negocio = (config_negocio.get("nombre_negocio") or "").strip() or "Nuestro negocio"
    moneda = config_negocio.get("moneda", "S/")
    dia = fecha_dmy(parsear_fecha(reserva["fecha"]))
    total = float(reserva.get("total_estimado") or 0)
    adelantos = float(reserva.get("adelanto_total") or 0)
    saldo = max(round(total - adelantos, 2), 0.0)
    asunto = f"Pago recibido - tu cita en {negocio}"
    lineas = [
        f"Hola {reserva['cliente_nombre']},",
        "",
        f"Recibimos tu pago de {formatear_moneda(monto, moneda)}. ¡Gracias! Tu reserva está confirmada.",
        "",
        f"Servicio: {reserva['servicio_nombre']}",
        f"Fecha: {dia}, de {reserva['hora_inicio']} a {reserva['hora_fin']}",
        f"Total del servicio: {formatear_moneda(total, moneda)}",
        f"Adelantos recibidos: {formatear_moneda(adelantos, moneda)}",
        (f"Saldo pendiente (se paga al terminar el servicio): {formatear_moneda(saldo, moneda)}"
         if saldo > 0 else "Tu servicio ya está pagado por completo."),
        "",
        "Cuando termine tu servicio te enviaremos tu boleta por este mismo medio.",
    ]
    telefono = (config_negocio.get("telefono") or "").strip()
    if telefono:
        lineas += ["", f"Si necesitas reprogramar o tienes alguna consulta, escríbenos al {telefono}."]
    lineas += ["", negocio]
    direccion = (config_negocio.get("direccion") or "").strip()
    if direccion:
        lineas.append(direccion)
    return asunto, "\n".join(lineas) + "\n"


def armar_correo_reserva(reserva: dict, config_negocio: dict) -> tuple[str, str]:
    """(asunto, cuerpo) del mensaje que recibe el cliente al reservar, junto con el
    comprobante de reserva en PDF: avisa que tiene una cita pendiente."""
    negocio = (config_negocio.get("nombre_negocio") or "").strip() or "Nuestro negocio"
    moneda = config_negocio.get("moneda", "S/")
    dia = fecha_larga(parsear_fecha(reserva["fecha"]))
    total = float(reserva.get("total_estimado") or 0)
    adelantos = float(reserva.get("adelanto_total") or 0)
    saldo = max(round(total - adelantos, 2), 0.0)
    asunto = f"Cita pendiente: {dia}, {reserva['hora_inicio']} - {negocio}"
    lineas = [
        f"Hola {reserva['cliente_nombre']},",
        "",
        f"Tienes una cita pendiente en {negocio}:",
        "",
        f"Fecha: {dia}",
        f"Hora: {reserva['hora_inicio']} a {reserva['hora_fin']}",
        f"Servicio: {reserva['servicio_nombre']}",
        f"Total del servicio: {formatear_moneda(total, moneda)}",
    ]
    if adelantos > 0:
        lineas.append(f"Adelanto recibido: {formatear_moneda(adelantos, moneda)}")
    lineas.append(f"Saldo por pagar al terminar el servicio: {formatear_moneda(saldo, moneda)}")
    lineas += ["", "Adjuntamos tu comprobante de reserva en PDF.",
               "Cuando termine tu servicio te enviaremos tu boleta final por este mismo medio."]
    telefono = (config_negocio.get("telefono") or "").strip()
    if telefono:
        lineas += ["", f"Si necesitas reprogramar o tienes alguna consulta, escríbenos al {telefono}."]
    lineas += ["", negocio]
    direccion = (config_negocio.get("direccion") or "").strip()
    if direccion:
        lineas.append(direccion)
    return asunto, "\n".join(lineas) + "\n"


def armar_correo_boleta(reserva: dict, config_negocio: dict) -> tuple[str, str]:
    """(asunto, cuerpo) del correo que acompaña a la boleta en PDF."""
    negocio = (config_negocio.get("nombre_negocio") or "").strip() or "Nuestro negocio"
    moneda = config_negocio.get("moneda", "S/")
    dia = fecha_dmy(parsear_fecha(reserva["fecha"]))
    asunto = f"Tu boleta {reserva['boleta_texto']} - {negocio}"
    lineas = [
        f"Hola {reserva['cliente_nombre']},",
        "",
        f"Gracias por tu visita a {negocio}. Adjuntamos tu boleta {reserva['boleta_texto']} en PDF.",
        "",
        f"Servicio: {reserva['servicio_nombre']}",
        f"Fecha: {dia}, de {reserva['hora_inicio']} a {reserva['hora_fin']}",
        f"Total pagado: {formatear_moneda(reserva.get('total') or 0, moneda)}",
    ]
    if reserva.get("metodo_pago"):
        lineas.append(f"Método de pago: {reserva['metodo_pago']}")
    pie = (config_negocio.get("ticket_pie") or "").strip()
    lineas += ["", pie or "¡Gracias por tu preferencia!", negocio]
    direccion = (config_negocio.get("direccion") or "").strip()
    if direccion:
        lineas.append(direccion)
    return asunto, "\n".join(lineas) + "\n"


def armar_correo_cupon(cupon: dict, config_negocio: dict, nombre_cliente: str = "") -> tuple[str, str]:
    """(asunto, cuerpo) del correo que acompaña al cupón de descuento en PDF."""
    from printing.cupon_pdf import texto_vigencia
    negocio = (config_negocio.get("nombre_negocio") or "").strip() or "Nuestro negocio"
    moneda = config_negocio.get("moneda", "S/")
    asunto = f"Tu cupón de descuento - {negocio}"
    valor = (f"{cupon['valor']:g}%" if cupon["tipo"] == "porcentaje"
             else formatear_moneda(cupon["valor"], moneda))
    saludo = f"Hola {nombre_cliente.strip()}," if nombre_cliente.strip() else "Hola,"
    lineas = [
        saludo,
        "",
        f"Te regalamos un cupón de {valor} de descuento en {negocio}.",
        "",
        f"Código: {cupon['codigo']}",
        texto_vigencia(cupon),
    ]
    if cupon.get("compra_minima"):
        lineas.append(f"Compra mínima: {formatear_moneda(cupon['compra_minima'], moneda)}")
    lineas += ["", "Adjuntamos el cupón en PDF. Preséntalo o indica el código al momento de pagar."]
    telefono = (config_negocio.get("telefono") or "").strip()
    if telefono:
        lineas += ["", f"Si tienes alguna consulta, escríbenos al {telefono}."]
    lineas += ["", negocio]
    direccion = (config_negocio.get("direccion") or "").strip()
    if direccion:
        lineas.append(direccion)
    return asunto, "\n".join(lineas) + "\n"
