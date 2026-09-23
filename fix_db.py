import sqlite3
from config import DATABASE_PATH

print(f"Usando base de datos en: {DATABASE_PATH}")

conn = sqlite3.connect(str(DATABASE_PATH))

cur = conn.execute("PRAGMA table_info(metodos_pago)")
columnas = {fila[1] for fila in cur.fetchall()}

if "es_efectivo" not in columnas:
    conn.execute("ALTER TABLE metodos_pago ADD COLUMN es_efectivo INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE metodos_pago SET es_efectivo = 1 WHERE nombre = 'Efectivo'")
    conn.commit()
    print("✅ Columna 'es_efectivo' agregada y 'Efectivo' marcado correctamente.")
else:
    print("La columna ya existía, no se hizo nada.")

conn.close()