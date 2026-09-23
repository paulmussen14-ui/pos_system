# Arquitectura del Sistema POS Local — PySide6 + SQLite

## 1. Arquitectura general

Aplicación de escritorio, monolítica, sin servidor, con arquitectura en capas (estilo *layered / clean-ish*, adaptado a un proyecto de escritorio de tamaño mediano — no es necesario over-engineering con DDD puro):

```
┌─────────────────────────────────────────┐
│              UI (PySide6)                │  Ventanas, widgets, QSS
├─────────────────────────────────────────┤
│         Controladores / Presenters       │  Conectan UI ↔ Servicios
├─────────────────────────────────────────┤
│         Servicios (lógica de negocio)    │  Reglas: ventas, caja, costos
├─────────────────────────────────────────┤
│         Repositorios (acceso a datos)    │  Consultas SQL, transacciones
├─────────────────────────────────────────┤
│         Base de datos (SQLite)           │  Persistencia local
└─────────────────────────────────────────┘
```

Principios:
- **UI no habla directo con SQLite.** Siempre pasa por Servicios → Repositorios.
- **Servicios contienen las reglas de negocio** (ej. "no permitir venta sin stock", "calcular utilidad con costo histórico").
- **Repositorios solo hacen CRUD y consultas**, sin lógica de negocio.
- Cada módulo (ventas, productos, compras, etc.) tiene su propio repositorio y servicio.
- Uso de **transacciones SQLite explícitas** en cualquier operación que toque más de una tabla (ej. registrar venta = cabecera + detalle + movimiento de inventario + movimiento de caja).

## 2. Estructura de carpetas

```
pos_system/
├── main.py                        # Punto de entrada
├── config.py                      # Rutas, constantes globales
│
├── database/
│   ├── connection.py               # Conexión SQLite, PRAGMA, singleton
│   ├── schema.sql                  # DDL completo
│   ├── migrations/                 # Scripts de migración versionados
│   └── seed.py                     # Datos iniciales (métodos de pago, etc.)
│
├── models/                         # Dataclasses / entidades (sin lógica)
│   ├── producto.py
│   ├── venta.py
│   ├── compra.py
│   ├── cliente.py
│   ├── caja.py
│   └── usuario.py
│
├── repositories/                   # Acceso a datos (SQL puro)
│   ├── producto_repository.py
│   ├── venta_repository.py
│   ├── compra_repository.py
│   ├── inventario_repository.py
│   ├── caja_repository.py
│   ├── cliente_repository.py
│   └── usuario_repository.py
│
├── services/                       # Lógica de negocio
│   ├── auth_service.py             # Login, hash, recuperación
│   ├── venta_service.py            # Cálculo totales, descuentos, anulación
│   ├── compra_service.py           # Registro compra + historial de costos
│   ├── inventario_service.py       # Stock, movimientos, alertas
│   ├── caja_service.py             # Apertura/cierre, diferencia
│   ├── costo_service.py            # Costo promedio ponderado / FIFO
│   └── reporte_service.py          # Agregaciones para reportes
│
├── ui/
│   ├── main_window.py              # QMainWindow, sidebar, QStackedWidget
│   ├── login/
│   │   ├── login_window.py
│   │   ├── setup_admin_window.py   # Primera instalación
│   │   └── recovery_window.py
│   ├── dashboard/
│   │   └── dashboard_page.py
│   ├── ventas/
│   │   ├── ventas_page.py
│   │   └── venta_dialog_devolucion.py
│   ├── productos/
│   │   ├── productos_page.py
│   │   └── producto_form_dialog.py
│   ├── compras/
│   │   ├── compras_page.py
│   │   └── compra_form_dialog.py
│   ├── inventario/
│   │   └── inventario_page.py
│   ├── clientes/
│   │   └── clientes_page.py
│   ├── caja/
│   │   └── caja_page.py
│   ├── reportes/
│   │   └── reportes_page.py
│   ├── configuracion/
│   │   └── configuracion_page.py
│   └── widgets/                    # Componentes reutilizables (cards, tablas)
│
├── printing/
│   ├── ticket_printer.py           # Impresión térmica (ESC/POS)
│   └── ticket_template.py
│
├── security/
│   ├── password_hasher.py          # Argon2id/bcrypt
│   └── recovery_code.py            # Generación/validación código
│
├── utils/
│   ├── validators.py
│   ├── logger.py
│   └── backup_manager.py
│
├── resources/
│   ├── styles/                     # Archivos .qss (claro/oscuro)
│   ├── icons/
│   └── logo/
│
└── logs/                            # Logs de errores en runtime
```

Regla de dependencia: `ui` → `services` → `repositories` → `database`. Nunca al revés, y `ui` nunca importa `repositories` directamente.

## 3. Modelo de base de datos (tablas principales)

**usuarios**
`id, nombre, usuario, password_hash, recovery_code_hash, recovery_code_usado, creado_en`

**configuracion**
`id, nombre_negocio, logo_path, direccion, moneda, igv_porcentaje, ticket_pie, creado_en`

**categorias**
`id, nombre, activo`

**proveedores**
`id, nombre, documento, telefono, direccion, activo`

**productos**
`id, nombre, categoria_id (FK), marca, unidad_medida, precio_venta_actual, stock_actual, stock_minimo, proveedor_id (FK), activo, creado_en`

**historial_costos**
`id, producto_id (FK), costo_unitario, fecha, compra_detalle_id (FK, nullable), motivo`

**historial_precios** *(opcional pero recomendado, igual razonamiento que costos)*
`id, producto_id (FK), precio_venta, fecha`

**clientes**
`id, nombre, documento, telefono, direccion, creado_en`

**compras**
`id, proveedor_id (FK), numero_documento, fecha, subtotal, impuesto, total, usuario_id (FK)`

**compra_detalle**
`id, compra_id (FK), producto_id (FK), cantidad, costo_unitario, subtotal`

**ventas**
`id, cliente_id (FK, nullable), usuario_id (FK), fecha, subtotal, descuento, total, metodo_pago_id (FK), estado (completada/anulada), caja_sesion_id (FK)`

**venta_detalle**
`id, venta_id (FK), producto_id (FK), cantidad, precio_venta_unitario, costo_unitario_snapshot, subtotal`

> 🔑 Clave del diseño de costos: `costo_unitario_snapshot` se copia al momento de la venta desde el costo vigente (según FIFO o promedio ponderado). Así, aunque `historial_costos` cambie después, la venta ya registrada conserva su costo real de ese momento — la utilidad histórica nunca se recalcula sola.

**devoluciones**
`id, venta_id (FK), producto_id (FK), cantidad, motivo, fecha, usuario_id (FK)`

**inventario_movimientos**
`id, producto_id (FK), tipo (entrada/salida/ajuste), cantidad, referencia_tipo (venta/compra/ajuste), referencia_id, fecha, usuario_id (FK)`

**caja_sesiones**
`id, usuario_id (FK), fecha_apertura, monto_apertura, fecha_cierre (nullable), monto_esperado, monto_contado, diferencia, estado (abierta/cerrada)`

**caja_movimientos**
`id, caja_sesion_id (FK), tipo (venta/ingreso_manual/egreso/retiro), monto, descripcion, fecha`

**metodos_pago**
`id, nombre, activo`

**configuracion_impresion**
`id, tipo_impresora, ancho_papel, nombre_impresora, activo`

## 4. Relaciones clave

- `productos (1) → (N) historial_costos` — nunca se borra, solo se agrega.
- `ventas (1) → (N) venta_detalle` — cabecera/detalle clásico.
- `compras (1) → (N) compra_detalle` — cada línea genera una entrada en `historial_costos` e `inventario_movimientos`.
- `caja_sesiones (1) → (N) caja_movimientos` — toda venta con pago en efectivo genera un movimiento tipo "venta".
- `clientes (1) → (N) ventas` — historial de compras por cliente vía join.
- `venta_detalle.costo_unitario_snapshot` es la pieza que hace posible que **la utilidad histórica sea inmutable**.

## 5. Estrategia de costeo (promedio ponderado recomendado)

Recomiendo **costo promedio ponderado (CPP)** sobre FIFO puro, porque:
- Es mucho más simple de implementar y auditar en SQLite.
- Con productos de mermería/negocio pequeño, no suele ser crítico distinguir lotes exactos.
- Se recalcula con una fórmula directa en cada compra:

```
nuevo_costo_promedio = (stock_actual × costo_promedio_actual + cantidad_comprada × costo_compra)
                        / (stock_actual + cantidad_comprada)
```

Ejemplo del enunciado:
```
Compra 1: 10 × S/7  → stock=10, costo_prom=7.00
Compra 2: 20 × S/8  → nuevo_costo = (10×7 + 20×8) / 30 = 7.67
```
Este `costo_promedio` es el que se guarda en `productos.costo_promedio_actual` (campo adicional que añadiría a la tabla) y se copia a `venta_detalle.costo_unitario_snapshot` en cada venta.

Si más adelante quieres trazabilidad por lote exacto, se puede migrar a FIFO real usando `historial_costos` como cola — pero para v1 recomiendo CPP.

## 6. Flujo de autenticación

```
Primera ejecución (no hay usuarios en BD)
  → Pantalla "Crear cuenta de administrador"
  → Ingresa nombre, usuario, contraseña, confirmar
  → Se genera código de recuperación (ej. 16 caracteres, mostrado UNA vez)
  → Se hashea password (Argon2id) y el código de recuperación (hash aparte)
  → Se guarda en tabla usuarios
  → Redirige a login

Login normal
  → Usuario ingresa usuario + password
  → Se verifica hash con Argon2id.verify()
  → Si correcto → abre MainWindow
  → Si incorrecto → mensaje de error (sin distinguir "usuario no existe" vs "clave incorrecta")

Recuperación de contraseña
  → Usuario hace clic en "Olvidé mi contraseña"
  → Ingresa código de recuperación
  → Se verifica contra recovery_code_hash Y que recovery_code_usado = False
  → Si válido → permite ingresar nueva contraseña
  → Se actualiza password_hash, se marca recovery_code_usado = True
  → (Opcional) se genera un nuevo código de recuperación al final
```

## 7. Flujo de ventas

```
1. Usuario abre "Ventas" (requiere caja abierta)
2. Busca producto por nombre → selecciona
3. Ingresa cantidad → sistema valida stock disponible
4. Se agrega línea: producto, cantidad, precio_venta_actual, subtotal (auto-calculado)
5. Puede repetir para más productos, modificar cantidades o eliminar líneas
6. Sistema recalcula total en tiempo real (suma subtotales - descuento)
7. Selecciona cliente (opcional) y método de pago
8. Clic en "Registrar venta":
   - BEGIN TRANSACTION
   - Inserta cabecera en ventas
   - Inserta líneas en venta_detalle (con costo_unitario_snapshot = costo_promedio_actual del producto en ese momento)
   - Descuenta stock en productos + inserta en inventario_movimientos (tipo salida)
   - Si pago es efectivo → inserta en caja_movimientos (tipo venta)
   - COMMIT
9. Genera e imprime ticket (sin mostrar costo interno)

Anulación de venta:
   - Cambia estado a "anulada"
   - Revierte stock (inventario_movimientos tipo entrada, referencia "anulación")
   - Revierte movimiento de caja si aplica
   - No borra el registro (trazabilidad)

Devolución:
   - Registra en devoluciones
   - Ajusta stock (entrada)
   - No modifica la venta original, es un registro adicional vinculado
```

## 8. Flujo de compras

```
1. Usuario abre "Compras" → "Nueva compra"
2. Selecciona proveedor, ingresa número de documento y fecha
3. Agrega productos con cantidad y costo unitario (uno o varios)
4. Sistema calcula subtotal, impuesto (si aplica), total
5. Al guardar:
   - BEGIN TRANSACTION
   - Inserta cabecera en compras
   - Inserta líneas en compra_detalle
   - Por cada línea:
       - Inserta en historial_costos (costo_unitario, fecha, referencia a la compra)
       - Recalcula costo_promedio_actual del producto (fórmula CPP)
       - Aumenta stock_actual del producto
       - Inserta en inventario_movimientos (tipo entrada, referencia compra)
   - COMMIT
```

## 9. Flujo de inventario

```
- Todo cambio de stock pasa SIEMPRE por inventario_movimientos (nunca se actualiza
  productos.stock_actual "a mano" sin dejar rastro).
- inventario_service expone:
    - registrar_entrada(producto_id, cantidad, referencia)
    - registrar_salida(producto_id, cantidad, referencia)
    - ajustar_stock(producto_id, cantidad_nueva, motivo)  # para conteos físicos
- La página de Inventario es principalmente de LECTURA + ajustes manuales;
  entradas/salidas normales vienen de compras/ventas automáticamente.
- Alertas de "stock bajo" y "agotado" se calculan comparando stock_actual vs stock_minimo,
  no se guardan como estado fijo (se recalculan al vuelo).
```

## 10. Flujo de caja

```
Apertura:
  - Requiere que no haya sesión "abierta" para el usuario actual
  - Ingresa monto_apertura → inserta caja_sesiones (estado=abierta)

Durante el día:
  - Cada venta en efectivo → caja_movimientos (tipo=venta, +monto)
  - Ingresos manuales → caja_movimientos (tipo=ingreso_manual, +monto)
  - Egresos/retiros → caja_movimientos (tipo=egreso o retiro, -monto)

Cierre:
  - monto_esperado = monto_apertura + SUM(movimientos)
  - Usuario ingresa monto_contado (conteo físico)
  - diferencia = monto_contado - monto_esperado
  - Actualiza caja_sesiones: fecha_cierre, monto_esperado, monto_contado, diferencia, estado=cerrada
  - No se puede vender sin una sesión de caja abierta
```

## 11. Sistema de recuperación de contraseña (detalle de seguridad)

- El código de recuperación se genera con `secrets.token_hex()` o similar (criptográficamente seguro), formateado en grupos legibles (ej. `XXXX-XXXX-XXXX-XXXX`).
- Se muestra **una sola vez** en pantalla al crear la cuenta, con advertencia clara de que debe guardarlo.
- En BD solo se guarda su **hash** (mismo esquema que la contraseña), nunca en texto plano.
- Un solo uso: campo `recovery_code_usado` se marca `True` tras el primer uso exitoso.
- No hay preguntas de seguridad (nombre de mascota, etc.) — descartado por ser débil, tal como pediste.

---

## Próximos pasos

Con esto definida la arquitectura, base de datos, flujos y estructura de carpetas, quedo a la espera de tu aprobación (o ajustes) antes de empezar a generar el código paso a paso. Cuando confirmes, sugiero este orden de construcción:

1. `database/schema.sql` + `connection.py` (base de datos primero)
2. `security/` + `services/auth_service.py` + pantallas de login/setup
3. `main_window.py` + sidebar + navegación básica
4. Módulo Productos (CRUD simple, es la base de todo lo demás)
5. Módulo Ventas (el más complejo)
6. Compras → Inventario → Caja → Clientes
7. Reportes → Configuración → Impresión de tickets
8. Empaquetado con PyInstaller

¿Quieres que ajuste algo de este diseño antes de empezar, o avanzamos con este orden?
