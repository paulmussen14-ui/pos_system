-- ============================================================
-- Esquema de base de datos - Sistema POS Local
-- SQLite - Normalizado
--
-- Las tablas están ordenadas según sus dependencias de FOREIGN KEY
-- (una tabla nunca referencia a otra que se cree después de ella).
-- ============================================================
PRAGMA foreign_keys = ON;
-- ------------------------------------------------------------
-- USUARIOS (solo debe existir 1: el administrador/propietario)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    usuario TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    recovery_code_hash TEXT NOT NULL,
    recovery_code_usado INTEGER NOT NULL DEFAULT 0,
    -- 0 = no usado, 1 = usado
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
-- ------------------------------------------------------------
-- CONFIGURACION (fila única del negocio)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS configuracion (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    nombre_negocio TEXT NOT NULL DEFAULT 'Mi Negocio',
    logo_path TEXT,
    direccion TEXT,
    moneda TEXT NOT NULL DEFAULT 'S/',
    igv_porcentaje REAL NOT NULL DEFAULT 0,
    ticket_encabezado TEXT,
    ticket_pie TEXT DEFAULT 'Gracias por su compra',
    tema TEXT NOT NULL DEFAULT 'claro',
    -- claro | oscuro
    -- Color de marca elegido por el cliente (hex, ej. #2563eb). Vacío = verde original
    color_marca TEXT NOT NULL DEFAULT '',
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    -- Modelo de negocio: 'ventas' (productos) o 'servicios' (reservas por hora)
    modelo_negocio TEXT NOT NULL DEFAULT 'ventas',
    -- Agenda de reservas (solo se usa en el modelo 'servicios'). agenda_dias: dígitos de los
    -- días de atención, 0 = lunes ... 6 = domingo (sin comas: el migrador de columnas separa por comas)
    agenda_hora_inicio TEXT NOT NULL DEFAULT '08:00',
    agenda_hora_fin TEXT NOT NULL DEFAULT '20:00',
    agenda_intervalo_min INTEGER NOT NULL DEFAULT 30,
    agenda_dias TEXT NOT NULL DEFAULT '012345',
    -- Envío de boletas por correo (SMTP)
    smtp_host TEXT NOT NULL DEFAULT '',
    smtp_puerto INTEGER NOT NULL DEFAULT 587,
    smtp_seguridad TEXT NOT NULL DEFAULT 'starttls',
    smtp_usuario TEXT NOT NULL DEFAULT '',
    smtp_password TEXT NOT NULL DEFAULT '',
    smtp_remitente_nombre TEXT NOT NULL DEFAULT '',
    smtp_remitente_email TEXT NOT NULL DEFAULT ''
);
-- ------------------------------------------------------------
-- CATEGORIAS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    activo INTEGER NOT NULL DEFAULT 1
);
-- ------------------------------------------------------------
-- PROVEEDORES
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    documento TEXT,
    telefono TEXT,
    direccion TEXT,
    activo INTEGER NOT NULL DEFAULT 1
);
-- ------------------------------------------------------------
-- PRODUCTOS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    categoria_id INTEGER REFERENCES categorias(id),
    marca TEXT,
    unidad_medida TEXT NOT NULL DEFAULT 'unidad',
    precio_venta_actual REAL NOT NULL DEFAULT 0,
    costo_promedio_actual REAL NOT NULL DEFAULT 0,
    stock_actual REAL NOT NULL DEFAULT 0,
    stock_minimo REAL NOT NULL DEFAULT 0,
    proveedor_id INTEGER REFERENCES proveedores(id),
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_productos_nombre ON productos(nombre);
CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos(categoria_id);
-- ------------------------------------------------------------
-- PRODUCTO_PRESENTACIONES
-- Formas adicionales de vender/comprar un mismo producto (caja,
-- docena, paquete de 6, etc.) sin duplicar el producto. La unidad
-- base sigue siendo productos.unidad_medida con su precio_venta_actual;
-- cada fila de aquí es una presentación EXTRA con su propio precio y
-- su equivalencia en unidades base (ej. "Caja" = 24 unidades, S/ 80).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS producto_presentaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    -- "Caja", "Docena", "6 unidades", etc.
    cantidad_unidades REAL NOT NULL DEFAULT 1,
    -- a cuántas unidades base equivale
    precio REAL NOT NULL DEFAULT 0,
    -- precio de venta de la presentación completa
    orden INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_presentaciones_producto ON producto_presentaciones(producto_id);
-- ------------------------------------------------------------
-- CLIENTES
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    documento TEXT,
    telefono TEXT,
    direccion TEXT,
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    email TEXT
);
CREATE INDEX IF NOT EXISTS idx_clientes_nombre ON clientes(nombre);
-- ------------------------------------------------------------
-- METODOS DE PAGO
-- es_efectivo indica si este método mueve dinero físico de la caja.
-- Se usa para decidir si una venta/compra genera un movimiento de caja
-- y si al anular una venta corresponde revertir ese movimiento.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS metodos_pago (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    es_efectivo INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1
);
-- ------------------------------------------------------------
-- CAJA - SESIONES
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS caja_sesiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    fecha_apertura TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    monto_apertura REAL NOT NULL DEFAULT 0,
    fecha_cierre TEXT,
    monto_esperado REAL,
    monto_contado REAL,
    diferencia REAL,
    estado TEXT NOT NULL DEFAULT 'abierta' -- abierta | cerrada
);
-- ------------------------------------------------------------
-- COMPRAS (cabecera)
-- pago_es_efectivo + caja_sesion_id: si la compra se pagó al contado,
-- se registra como egreso en la sesión de caja indicada.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id INTEGER REFERENCES proveedores(id),
    numero_documento TEXT,
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    subtotal REAL NOT NULL DEFAULT 0,
    impuesto REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    pago_es_efectivo INTEGER NOT NULL DEFAULT 0,
    caja_sesion_id INTEGER REFERENCES caja_sesiones(id),
    usuario_id INTEGER REFERENCES usuarios(id)
);
-- ------------------------------------------------------------
-- COMPRA_DETALLE (líneas)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS compra_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id INTEGER NOT NULL REFERENCES compras(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad REAL NOT NULL,
    costo_unitario REAL NOT NULL,
    subtotal REAL NOT NULL,
    presentacion_nombre TEXT NOT NULL DEFAULT 'Unidad',
    cantidad_presentacion REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_compras_fecha ON compras(fecha);
CREATE INDEX IF NOT EXISTS idx_compra_detalle_compra ON compra_detalle(compra_id);
CREATE INDEX IF NOT EXISTS idx_compra_detalle_producto ON compra_detalle(producto_id);
-- ------------------------------------------------------------
-- HISTORIAL DE COSTOS (nunca se sobrescribe, solo se agrega)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historial_costos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    costo_unitario REAL NOT NULL,
    costo_promedio_resultante REAL NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    compra_detalle_id INTEGER REFERENCES compra_detalle(id),
    motivo TEXT NOT NULL DEFAULT 'compra'
);
-- ------------------------------------------------------------
-- HISTORIAL DE PRECIOS DE VENTA
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historial_precios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    precio_venta REAL NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
-- ------------------------------------------------------------
-- VENTAS (cabecera)
-- pago_es_efectivo: snapshot de si el método de pago usado afecta caja.
-- Se congela en el momento de la venta (igual que el costo) para que,
-- si luego se activa/desactiva el flag es_efectivo del método de pago,
-- la anulación de ventas antiguas siga revirtiendo lo que corresponde.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER REFERENCES clientes(id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    subtotal REAL NOT NULL DEFAULT 0,
    descuento REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    metodo_pago_id INTEGER REFERENCES metodos_pago(id),
    pago_es_efectivo INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'completada',
    -- completada | anulada
    caja_sesion_id INTEGER REFERENCES caja_sesiones(id),
    chofer TEXT,
    -- Cliente libre: nombre/tipo escritos a mano, NO se guardan en clientes
    cliente_libre_nombre TEXT,
    cliente_libre_tipo TEXT,
    cupon_codigo TEXT
);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente_id);
-- Para los reportes por cliente dentro de la ventana de 15 días, aunque el historial sea enorme
CREATE INDEX IF NOT EXISTS idx_ventas_cliente_fecha ON ventas(cliente_id, fecha);
-- ------------------------------------------------------------
-- VENTA_DETALLE (líneas) -- costo_unitario_snapshot es CLAVE:
-- congela el costo al momento de la venta para que la utilidad
-- histórica nunca cambie aunque el costo del producto cambie después.
-- ------------------------------------------------------------
-- presentacion_nombre / cantidad_presentacion / factor_unidades: en qué
-- medida se vendió (ej. "Caja" x12 = factor 12), igual que ya se guarda en
-- compra_detalle. Van sin NOT NULL a propósito: en tickets ya emitidos antes
-- de este cambio quedan en NULL, y toda la app los trata como "Unidad"
-- (factor 1) cuando vienen vacíos, así que esos tickets viejos se siguen
-- mostrando en unidad base, sin romper nada.
CREATE TABLE IF NOT EXISTS venta_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL REFERENCES ventas(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad REAL NOT NULL,
    precio_venta_unitario REAL NOT NULL,
    costo_unitario_snapshot REAL NOT NULL,
    subtotal REAL NOT NULL,
    presentacion_nombre TEXT,
    cantidad_presentacion REAL,
    factor_unidades REAL
);
CREATE INDEX IF NOT EXISTS idx_venta_detalle_venta ON venta_detalle(venta_id);
CREATE INDEX IF NOT EXISTS idx_venta_detalle_producto ON venta_detalle(producto_id);
-- ------------------------------------------------------------
-- DEVOLUCIONES
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devoluciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL REFERENCES ventas(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad REAL NOT NULL,
    motivo TEXT,
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    usuario_id INTEGER REFERENCES usuarios(id)
);
-- ------------------------------------------------------------
-- INVENTARIO_MOVIMIENTOS (fuente única de verdad de los cambios de stock)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inventario_movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    tipo TEXT NOT NULL,
    -- entrada | salida | ajuste
    cantidad REAL NOT NULL,
    referencia_tipo TEXT,
    -- venta | compra | ajuste | anulacion | devolucion
    referencia_id INTEGER,
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    usuario_id INTEGER REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS idx_inv_mov_producto ON inventario_movimientos(producto_id);
CREATE INDEX IF NOT EXISTS idx_inv_mov_referencia ON inventario_movimientos(referencia_tipo, referencia_id);
-- Las pantallas de inventario solo piden los últimos días: sin este índice recorrían toda la tabla
CREATE INDEX IF NOT EXISTS idx_inv_mov_fecha ON inventario_movimientos(fecha);
-- ------------------------------------------------------------
-- CAJA_MOVIMIENTOS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS caja_movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caja_sesion_id INTEGER NOT NULL REFERENCES caja_sesiones(id),
    tipo TEXT NOT NULL,
    -- venta | ingreso_manual | egreso | retiro | compra
    monto REAL NOT NULL,
    descripcion TEXT,
    referencia_id INTEGER,
    -- ej. venta_id o compra_id
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
-- ------------------------------------------------------------
-- CONFIGURACION DE IMPRESION
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS configuracion_impresion (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    tipo_impresora TEXT DEFAULT 'termica_58mm',
    -- termica_58mm | termica_80mm | ninguna
    ancho_papel_mm INTEGER DEFAULT 58,
    nombre_impresora TEXT,
    activo INTEGER NOT NULL DEFAULT 0
);
-- ============================================================
-- BÚSQUEDA DE TEXTO COMPLETO (FTS5)
-- ============================================================
-- ------------------------------------------------------------
-- CLIENTES FTS
-- ------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS clientes_fts USING fts5(
    nombre,
    content = 'clientes',
    content_rowid = 'id'
);
-- Mantener clientes_fts sincronizada al insertar
CREATE TRIGGER IF NOT EXISTS clientes_ai
AFTER
INSERT ON clientes BEGIN
INSERT INTO clientes_fts(rowid, nombre)
VALUES (new.id, new.nombre);
END;
-- Mantener clientes_fts sincronizada al eliminar
CREATE TRIGGER IF NOT EXISTS clientes_ad
AFTER DELETE ON clientes BEGIN
INSERT INTO clientes_fts(clientes_fts, rowid, nombre)
VALUES ('delete', old.id, old.nombre);
END;
-- Mantener clientes_fts sincronizada al actualizar
CREATE TRIGGER IF NOT EXISTS clientes_au
AFTER
UPDATE OF nombre ON clientes BEGIN
INSERT INTO clientes_fts(clientes_fts, rowid, nombre)
VALUES ('delete', old.id, old.nombre);
INSERT INTO clientes_fts(rowid, nombre)
VALUES (new.id, new.nombre);
END;
-- ------------------------------------------------------------
-- PRODUCTOS FTS
-- ------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS productos_fts USING fts5(
    nombre,
    content = 'productos',
    content_rowid = 'id'
);
-- Mantener productos_fts sincronizada al insertar
CREATE TRIGGER IF NOT EXISTS productos_ai
AFTER
INSERT ON productos BEGIN
INSERT INTO productos_fts(rowid, nombre)
VALUES (new.id, new.nombre);
END;
-- Mantener productos_fts sincronizada al eliminar
CREATE TRIGGER IF NOT EXISTS productos_ad
AFTER DELETE ON productos BEGIN
INSERT INTO productos_fts(productos_fts, rowid, nombre)
VALUES ('delete', old.id, old.nombre);
END;
-- Mantener productos_fts sincronizada al actualizar
CREATE TRIGGER IF NOT EXISTS productos_au
AFTER
UPDATE OF nombre ON productos BEGIN
INSERT INTO productos_fts(productos_fts, rowid, nombre)
VALUES ('delete', old.id, old.nombre);
INSERT INTO productos_fts(rowid, nombre)
VALUES (new.id, new.nombre);
END;
CREATE INDEX IF NOT EXISTS idx_historial_costos_producto ON historial_costos(producto_id);
CREATE INDEX IF NOT EXISTS idx_historial_precios_producto ON historial_precios(producto_id);
CREATE INDEX IF NOT EXISTS idx_caja_mov_sesion ON caja_movimientos(caja_sesion_id);
CREATE INDEX IF NOT EXISTS idx_devoluciones_venta ON devoluciones(venta_id, producto_id);

-- ------------------------------------------------------------
-- CUPONES (códigos generados por el sistema)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cupones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    descripcion TEXT,
    tipo TEXT NOT NULL DEFAULT 'porcentaje',   -- porcentaje | monto
    valor REAL NOT NULL DEFAULT 0,
    compra_minima REAL NOT NULL DEFAULT 0,
    fecha_inicio TEXT,
    fecha_fin TEXT,
    usos_maximos INTEGER NOT NULL DEFAULT 0,   -- 0 = ilimitado
    usos INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ------------------------------------------------------------
-- PROFORMAS (cotizaciones: no mueven stock ni caja)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proformas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    cliente_id INTEGER REFERENCES clientes(id),
    cliente_nombre TEXT,
    cliente_tipo TEXT,
    subtotal REAL NOT NULL DEFAULT 0,
    descuento REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    validez_dias INTEGER NOT NULL DEFAULT 7,
    notas TEXT,
    estado TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente | convertida | anulada
    venta_id INTEGER REFERENCES ventas(id)
);
CREATE TABLE IF NOT EXISTS proforma_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proforma_id INTEGER NOT NULL REFERENCES proformas(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    nombre_producto TEXT NOT NULL,
    cantidad REAL NOT NULL,
    precio_unitario REAL NOT NULL,
    subtotal REAL NOT NULL,
    presentacion_nombre TEXT,
    cantidad_presentacion REAL,
    factor_unidades REAL
);
CREATE INDEX IF NOT EXISTS idx_proforma_detalle ON proforma_detalle(proforma_id);

-- ------------------------------------------------------------
-- RRHH
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trabajadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    documento TEXT,
    telefono TEXT,
    funcion TEXT,
    tipo_pago TEXT NOT NULL DEFAULT 'mensual', -- mensual | quincenal | semanal
    monto_base REAL NOT NULL DEFAULT 0,        -- sueldo por periodo
    fecha_ingreso TEXT,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    hora_entrada TEXT,                         -- horario: 'HH:MM'
    hora_salida TEXT,
    dias_laborales TEXT                        -- '0,1,2,3,4,5' (0 = lunes)
);
CREATE TABLE IF NOT EXISTS trabajador_asistencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id),
    fecha TEXT NOT NULL,                       -- 'YYYY-MM-DD'
    entrada TEXT,                              -- 'HH:MM'
    salida TEXT,
    minutos_tarde INTEGER NOT NULL DEFAULT 0,
    observacion TEXT,
    UNIQUE (trabajador_id, fecha)
);
CREATE TABLE IF NOT EXISTS trabajador_pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id),
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    periodo_desde TEXT,
    periodo_hasta TEXT,
    base REAL NOT NULL DEFAULT 0,
    bonificaciones REAL NOT NULL DEFAULT 0,
    descuentos REAL NOT NULL DEFAULT 0,
    adelantos REAL NOT NULL DEFAULT 0,
    neto REAL NOT NULL DEFAULT 0,
    usuario_id INTEGER REFERENCES usuarios(id),
    caja_sesion_id INTEGER REFERENCES caja_sesiones(id),
    notas TEXT
);
CREATE TABLE IF NOT EXISTS trabajador_movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id),
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    tipo TEXT NOT NULL,                        -- adelanto | descuento | bonificacion
    monto REAL NOT NULL,
    motivo TEXT,
    pago_id INTEGER REFERENCES trabajador_pagos(id),  -- NULL = pendiente
    anulado INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_trab_mov ON trabajador_movimientos(trabajador_id, pago_id);
CREATE INDEX IF NOT EXISTS idx_trab_pagos ON trabajador_pagos(trabajador_id);

-- ------------------------------------------------------------
-- SERVICIOS (catálogo del modelo 'servicios')
-- producto_id apunta a un producto OCULTO (activo = 0, sin stock) que
-- representa al servicio dentro de ventas/caja/reportes. No tiene FOREIGN KEY
-- a propósito para no estorbar la limpieza de registros antiguos.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS servicios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    precio REAL NOT NULL DEFAULT 0,
    duracion_min INTEGER NOT NULL DEFAULT 30,
    producto_id INTEGER,
    activo INTEGER NOT NULL DEFAULT 1,
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ------------------------------------------------------------
-- RESERVAS (agenda por hora)
-- Guarda su propia copia de los datos de la boleta (número, total, método de
-- pago), así la boleta se puede volver a generar y reenviar aunque la venta
-- asociada ya haya sido eliminada por la limpieza de registros antiguos.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reservas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    hora_inicio TEXT NOT NULL,
    hora_fin TEXT NOT NULL,
    servicio_id INTEGER,
    servicio_nombre TEXT NOT NULL,
    precio REAL NOT NULL DEFAULT 0,
    cliente_id INTEGER,
    cliente_nombre TEXT NOT NULL,
    cliente_telefono TEXT,
    cliente_email TEXT,
    notas TEXT,
    estado TEXT NOT NULL DEFAULT 'reservada',
    descuento REAL NOT NULL DEFAULT 0,
    total REAL,
    metodo_pago TEXT,
    numero_boleta INTEGER,
    venta_id INTEGER,
    pagado_en TEXT,
    boleta_enviada_a TEXT,
    comprobante_enviado_a TEXT,
    adelanto_aplicado REAL NOT NULL DEFAULT 0,
    pago_recibido REAL,
    pago_cambio REAL,
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_reservas_fecha ON reservas(fecha, hora_inicio);

-- ------------------------------------------------------------
-- OPCIONES (tabla subservicios): CATÁLOGO GLOBAL de adicionales, definidos una sola vez
-- y compartidos por todos los servicios (ver servicio_subservicios). Tienen un costo extra
-- que se suma al precio base (NUNCA vienen incluidos en el precio del servicio) y dos clases:
--   'efecto' = se cobra aparte y se pueden elegir varios a la vez (ej. "Ojo de gato").
--   'tipo'   = otra modalidad del servicio, sin ser un efecto; se elige uno solo (ej. "Esculpidas").
-- servicio_id: columna LEGADA (antes cada opción pertenecía a un servicio). Hoy siempre es 0;
--   qué servicios usan la opción lo dice servicio_subservicios.
-- producto_id: producto oculto que la representa en ventas (ver SERVICIOS).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subservicios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    servicio_id INTEGER NOT NULL DEFAULT 0,
    nombre TEXT NOT NULL,
    precio REAL NOT NULL DEFAULT 0,
    producto_id INTEGER,
    activo INTEGER NOT NULL DEFAULT 1,
    clase TEXT NOT NULL DEFAULT 'efecto'
);
CREATE INDEX IF NOT EXISTS idx_subservicios_servicio ON subservicios(servicio_id);

-- Qué opciones del catálogo aplican a cada servicio (cada servicio solo marca cuáles).
CREATE TABLE IF NOT EXISTS servicio_subservicios (
    servicio_id INTEGER NOT NULL,
    subservicio_id INTEGER NOT NULL,
    PRIMARY KEY (servicio_id, subservicio_id)
);
CREATE INDEX IF NOT EXISTS idx_serv_sub_opcion ON servicio_subservicios(subservicio_id);

-- ------------------------------------------------------------
-- PRODUCTOS DE UN SERVICIO: lo que se usa/entrega al atender. Al cobrar descuentan
-- stock. cobrar = 1 suma su precio de venta al total; cobrar = 0 significa que va
-- incluido en el precio del servicio (solo descuenta stock).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS servicio_productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    servicio_id INTEGER NOT NULL,
    producto_id INTEGER NOT NULL,
    cantidad REAL NOT NULL DEFAULT 1,
    cobrar INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_servicio_productos_servicio ON servicio_productos(servicio_id);

-- ------------------------------------------------------------
-- RESERVA_ITEMS: sub-servicios y productos elegidos en una reserva (copia de nombre y
-- precio del momento). tipo: subservicio | producto. El servicio base va en reservas.precio.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reserva_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reserva_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    referencia_id INTEGER,
    nombre TEXT NOT NULL,
    cantidad REAL NOT NULL DEFAULT 1,
    precio_unitario REAL NOT NULL DEFAULT 0,
    subtotal REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reserva_items_reserva ON reserva_items(reserva_id);

-- ------------------------------------------------------------
-- RESERVA_PAGOS: adelantos recibidos al reservar (o después). estado:
-- vigente (cuenta para el saldo) | devuelto (se devolvió al cancelar) | retenido (se quedó el negocio).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reserva_pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reserva_id INTEGER NOT NULL,
    monto REAL NOT NULL,
    metodo_pago_id INTEGER,
    metodo_nombre TEXT,
    es_efectivo INTEGER NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'vigente',
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_reserva_pagos_reserva ON reserva_pagos(reserva_id);
