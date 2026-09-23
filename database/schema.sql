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
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
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
    creado_en TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
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
    subtotal REAL NOT NULL
);
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
    caja_sesion_id INTEGER REFERENCES caja_sesiones(id)
);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente_id);
-- ------------------------------------------------------------
-- VENTA_DETALLE (líneas) -- costo_unitario_snapshot es CLAVE:
-- congela el costo al momento de la venta para que la utilidad
-- histórica nunca cambie aunque el costo del producto cambie después.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS venta_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL REFERENCES ventas(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad REAL NOT NULL,
    precio_venta_unitario REAL NOT NULL,
    costo_unitario_snapshot REAL NOT NULL,
    subtotal REAL NOT NULL
);
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