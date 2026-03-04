import sqlite3
import io
import base64
import matplotlib.pyplot as plt

def get_db_connection():
    conn = sqlite3.connect('logistica.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    # Tabla camiones
    conn.execute('''
        CREATE TABLE IF NOT EXISTS camiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placa TEXT UNIQUE NOT NULL,
            modelo TEXT NOT NULL,
            anio INTEGER,
            capacidad REAL,
            estado TEXT DEFAULT 'Operativo',
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla conductores
    conn.execute('''
        CREATE TABLE IF NOT EXISTS conductores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            dni TEXT UNIQUE,
            licencia TEXT,
            categoria TEXT,
            telefono TEXT,
            vencimiento DATE,
            direccion TEXT,
            estado TEXT DEFAULT 'Activo',
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla cambios de aceite
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cambios_aceite (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camion_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            kilometraje INTEGER NOT NULL,
            proximo_cambio INTEGER NOT NULL,
            observaciones TEXT,
            FOREIGN KEY (camion_id) REFERENCES camiones (id) ON DELETE CASCADE
        )
    ''')
    
    # Tabla historial de mantenimiento
    conn.execute('''
        CREATE TABLE IF NOT EXISTS historial_mantenimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camion_id INTEGER NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            kilometraje REAL,
            combustible REAL,
            averias REAL,
            carga REAL,
            rutas REAL,
            resultado TEXT,
            FOREIGN KEY (camion_id) REFERENCES camiones (id) ON DELETE CASCADE
        )
    ''')
    
    # Tabla viajes (NUEVA)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS viajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camion_id INTEGER NOT NULL,
            conductor_id INTEGER,
            origen TEXT NOT NULL,
            destino TEXT NOT NULL,
            fecha_salida DATE NOT NULL,
            fecha_llegada DATE,
            carga TEXT NOT NULL,
            estado TEXT DEFAULT 'Programado',
            observaciones TEXT,
            kilometraje REAL DEFAULT 0,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (camion_id) REFERENCES camiones (id),
            FOREIGN KEY (conductor_id) REFERENCES conductores (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def obtener_estadisticas():
    conn = get_db_connection()
    
    try:
        total_camiones = conn.execute('SELECT COUNT(*) FROM camiones').fetchone()[0]
        total_conductores = conn.execute('SELECT COUNT(*) FROM conductores').fetchone()[0]
        camiones_operativos = conn.execute("SELECT COUNT(*) FROM camiones WHERE estado = 'Operativo'").fetchone()[0]
        total_viajes = conn.execute('SELECT COUNT(*) FROM viajes').fetchone()[0]
        
        # Viajes del mes actual
        viajes_mes = conn.execute('''
            SELECT COUNT(*) FROM viajes 
            WHERE strftime('%Y-%m', fecha_salida) = strftime('%Y-%m', 'now')
        ''').fetchone()[0]
        
        # Alertas de mantenimiento
        alertas = conn.execute('''
            SELECT c.placa, ca.kilometraje, ca.proximo_cambio,
                   ROUND((ca.kilometraje * 100.0 / ca.proximo_cambio), 2) as porcentaje
            FROM cambios_aceite ca
            JOIN camiones c ON ca.camion_id = c.id
            WHERE ca.kilometraje >= ca.proximo_cambio * 0.8
            ORDER BY porcentaje DESC
        ''').fetchall()
        
    except Exception as e:
        print(f"Error obteniendo estadísticas: {e}")
        total_camiones = 0
        total_conductores = 0
        camiones_operativos = 0
        total_viajes = 0
        viajes_mes = 0
        alertas = []
    
    finally:
        conn.close()
    
    return {
        'total_camiones': total_camiones,
        'total_conductores': total_conductores,
        'camiones_operativos': camiones_operativos,
        'total_viajes': total_viajes,
        'viajes_mes': viajes_mes,
        'alertas': alertas
    }

def generar_grafica_mantenimiento(datos):
    """Genera gráfica de mantenimiento y retorna en base64"""
    try:
        plt.figure(figsize=(8, 5))
        categorias = ['Kilometraje', 'Combustible', 'Averías', 'Carga', 'Rutas']
        valores = list(datos.values())
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57']
        bars = plt.bar(categorias, valores, color=colors, alpha=0.8)
        
        # Añadir valores en las barras
        for bar, valor in zip(bars, valores):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f'{valor}%', ha='center', va='bottom', fontweight='bold')
        
        plt.ylim(0, 110)
        plt.title('Análisis de Mantenimiento Predictivo', fontweight='bold', pad=20)
        plt.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        
        # Convertir a base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        return f"data:image/png;base64,{image_base64}"
    except Exception as e:
        print(f"Error generando gráfica: {e}")
        return None

def predecir_mantenimiento(km, comb, aver, carg, rut):
    """Lógica de predicción de mantenimiento"""
    puntaje = (km * 0.3 + comb * 0.2 + aver * 0.25 + carg * 0.15 + rut * 0.1)
    
    if puntaje >= 80:
        return "Mantenimiento Urgente Requerido", "danger"
    elif puntaje >= 60:
        return "Mantenimiento Recomendado", "warning"
    elif puntaje >= 40:
        return "Monitoreo Continuo", "info"
    else:
        return "Estado Óptimo", "success"