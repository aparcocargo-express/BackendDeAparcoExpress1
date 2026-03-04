import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS camiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placa TEXT NOT NULL,
    modelo TEXT NOT NULL,
    año INTEGER NOT NULL,
    capacidad INTEGER NOT NULL
)
""")

conn.commit()
conn.close()
print("✅ Tabla 'camiones' creada correctamente (si no existía).")
crear_tabla_historial()
