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
    subtotal REAL NOT NULL,
    presentacion_nombre TEXT NOT NULL DEFAULT 'Unidad',
    cantidad_presentacion REAL NOT NULL DEFAULT 0
);
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
    chofer TEXT
);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente_id);
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