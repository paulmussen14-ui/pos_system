# Sistema POS Local

Sistema de Punto de Venta 100% local para Windows, construido con Python +
PySide6 + SQLite. No depende de Internet. Cada instalación tiene su propia
base de datos independiente.

## Requisitos

- Python 3.11 o superior
- Windows 10/11 (para impresión térmica y el .exe final; el código también
  corre en Linux/Mac en modo desarrollo, sin impresión real)

## Instalación (modo desarrollo)

```bash
cd pos_system
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

La primera vez que se ejecuta, la app te pedirá crear la cuenta de
administrador y te mostrará un **código de recuperación** — guárdalo, se
muestra una sola vez y es la única forma de recuperar la cuenta si olvidas
la contraseña.

## Dónde se guardan los datos

La base de datos, los backups y los logs se guardan en la carpeta de datos
del usuario de Windows, **no** junto al ejecutable:

```
%APPDATA%\POSLocal\
├── pos_local.db
├── backups\
└── logs\
```

Esto asegura que cada instalación tenga su propia base de datos
independiente, y que funcione aunque el .exe esté en una carpeta de solo
lectura como "Archivos de programa".

## Estructura del proyecto

```
pos_system/
├── main.py                 # Punto de entrada
├── config.py                # Rutas y constantes
├── database/                 # Esquema SQL y conexión SQLite
├── models/                   # Entidades (dataclasses)
├── repositories/             # Acceso a datos (SQL puro)
├── services/                 # Lógica de negocio
├── security/                 # Hash de contraseñas y código de recuperación
├── printing/                  # Generación e impresión de tickets
├── utils/                     # Validadores, logger, backups
├── ui/                        # Interfaz PySide6 (una carpeta por módulo)
└── resources/styles/          # Temas QSS (claro/oscuro)
```

Ver `arquitectura_pos_pyside6.md` para el detalle completo de arquitectura,
modelo de datos y flujos de negocio.

## Modelos de negocio: ventas o servicios con reservas

En **Configuración → Modelo de negocio** se elige cómo trabaja el negocio:

- **Ventas de productos**: el sistema de siempre (Inicio con resumen, Ventas, Productos, Compras, Inventario...).
- **Servicios con reserva** (consultorios, salones, talleres, clases...): el **Inicio pasa a ser una
  agenda semanal por horas**. Se ocultan Ventas, Proformas y Cupones, y
  aparece **Servicios**. Productos, Compras e Inventario se mantienen porque los servicios pueden usar productos.

Cambiar de modelo no borra nada; solo cambia el menú y el Inicio. El horario de atención (apertura,
cierre, bloques de 15-60 min y días) se define en la misma pestaña.

Flujo de una reserva: clic en una hora libre → elegir servicio y cliente → la reserva queda en la
agenda → al atender, **Cobrar y generar boleta** (método de pago, descuento opcional) → la boleta se
puede **ver/imprimir como ticket, guardar en PDF o enviar por correo**. El cobro queda registrado en
Caja (si es efectivo) y en Reportes como cualquier venta.

**Correo**: Configuración → Correo (servidor SMTP; Gmail/Outlook/Yahoo vienen precargados y requieren
una «contraseña de aplicación»). Es lo único que usa Internet, y solo al enviar. Los PDF se guardan
también en `%APPDATA%\POSLocal\boletas\`.

**Sub-servicios y productos** (Servicios → editar): cada servicio tiene un *precio base* y puede tener
*sub-servicios* (cada uno con su costo adicional, que se suma al base) y *productos* que se usan al
atender. Al cobrar, los productos descuentan stock; cada uno se marca como «Cobrar aparte» (suma su
precio de venta) o va incluido en el precio del servicio.

**Adelantos**: al reservar (o después, con «Recibir adelanto») se escribe el monto que deja el cliente
y con qué pagó. Si es en efectivo entra a la caja abierta. Al cobrar solo se paga el **saldo**
(total − adelantos) y la boleta muestra los adelantos. Si la reserva se cancela, se decide si el
adelanto se **devuelve** (sale de la caja si fue en efectivo) o se **retiene**.

> La boleta es un **comprobante interno de atención**, no un comprobante electrónico de SUNAT.

## Generar el ejecutable (.exe)

```bash
pip install pyinstaller
pyinstaller pos_local.spec
```

El ejecutable queda en `dist/POSLocal/POSLocal.exe` (o `dist/POSLocal.exe`
según la configuración). Cópialo junto con la carpeta que genera PyInstaller
a la máquina del cliente — no necesita Python instalado.

## Notas importantes

- **Costo interno nunca visible**: el costo del producto nunca se muestra en
  la pantalla de ventas ni en el ticket impreso, solo se usa internamente
  para calcular la utilidad.
- **Costeo**: se usa costo promedio ponderado (CPP). El costo de cada venta
  se "congela" en el momento de la venta (`costo_unitario_snapshot`), así que
  la utilidad histórica nunca cambia si el costo del producto cambia después.
- **Una sola cuenta**: el sistema está diseñado para un solo usuario
  administrador/propietario, sin registro ni autenticación online.
- **Impresión térmica**: usa el spooler de Windows (`pywin32`) en modo RAW.
  Si no hay impresora configurada o `pywin32` no está instalado, el ticket
  se guarda como `.txt` en la carpeta de datos en lugar de fallar.
- **Backups**: se pueden crear manualmente desde Configuración → Copias de
  seguridad. Usan la API nativa de respaldo de SQLite (segura incluso con la
  base de datos en uso).
