from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import openpyxl
from flask import send_file

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

# ------------------ Configuración de Auth ------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = conectar_db()
    user = conn.execute("SELECT id, username FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user['id'], user['username'])
    return None

# ------------------ Conexión a la base de datos ------------------
def conectar_db():
    conn = sqlite3.connect("logistica.db")
    conn.row_factory = sqlite3.Row
    return conn

# ------------------ Crear tablas ------------------
def crear_tablas():
    conn = conectar_db()
    
    # Tabla usuarios para Auth
    conn.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)
    
    # Tabla camiones
    conn.execute("""
    CREATE TABLE IF NOT EXISTS camiones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        placa TEXT NOT NULL,
        modelo TEXT,
        conductor TEXT,
        anio INTEGER,
        capacidad REAL,
        fecha_adquisicion DATE
    )
    """)
    
    # Tabla conductores
    conn.execute("""
    CREATE TABLE IF NOT EXISTS conductores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        dni TEXT,
        licencia TEXT,
        categoria TEXT,
        telefono TEXT,
        vencimiento DATE,
        direccion TEXT
    )
    """)
    
    # Tabla cambios_aceite
    conn.execute("""
    CREATE TABLE IF NOT EXISTS cambios_aceite (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camion_id INTEGER NOT NULL,
        fecha DATE NOT NULL,
        kilometraje INTEGER NOT NULL,
        proximo_cambio INTEGER NOT NULL,
        observaciones TEXT,
        FOREIGN KEY (camion_id) REFERENCES camiones(id)
    )
    """)
    
    # Tabla historial_mantenimiento
    conn.execute("""
    CREATE TABLE IF NOT EXISTS historial_mantenimiento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camion_id INTEGER,
        kilometraje REAL,
        combustible REAL,
        averias REAL,
        carga REAL,
        rutas REAL,
        resultado TEXT,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Tabla de Gastos
    conn.execute("""
    CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camion_id INTEGER NOT NULL,
        tipo TEXT NOT NULL, -- 'Combustible', 'Repuesto', 'Reparación'
        monto REAL NOT NULL,
        descripcion TEXT,
        fecha DATE DEFAULT CURRENT_DATE,
        FOREIGN KEY (camion_id) REFERENCES camiones(id)
    )
    """)
    
    # Crear usuario por defecto si no existe
    # hashed_pw = generate_password_hash('admin123')
    # try:
    #     conn.execute("INSERT INTO usuarios (username, password) VALUES (?, ?)", ('admin', hashed_pw))
    # except:
    #     pass

    conn.commit()
    conn.close()

# ------------------ Actualizar tabla camiones ------------------
def actualizar_tabla_camiones():
    try:
        conn = conectar_db()
        cursor = conn.execute("PRAGMA table_info(camiones)")
        columnas_existentes = [col[1] for col in cursor.fetchall()]
        
        if 'conductor' not in columnas_existentes:
            conn.execute("ALTER TABLE camiones ADD COLUMN conductor TEXT")
            conn.commit()
        
        if 'fecha_adquisicion' not in columnas_existentes:
            conn.execute("ALTER TABLE camiones ADD COLUMN fecha_adquisicion DATE")
            conn.commit()
        
        conn.close()
    except Exception as e:
        print(f"❌ Error al actualizar tabla camiones: {e}")

# ------------------ Machine Learning ------------------
def entrenar_modelo():
    """Entrena un modelo real si hay suficiente historial"""
    conn = conectar_db()
    df = pd.read_sql_query("SELECT kilometraje, combustible, averias, carga, rutas, resultado FROM historial_mantenimiento", conn)
    conn.close()

    if len(df) < 10:
        print("Not enough data to train ML model. Using threshold logic.")
        return None

    # Preprocesamiento simple
    X = df[['kilometraje', 'combustible', 'averias', 'carga', 'rutas']]
    y = df['resultado'].apply(lambda x: 1 if x == 'Revisión Recomendada' else 0)

    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    joblib.dump(model, 'modelo_mantenimiento.pkl')
    return model

def predecir_mantenimiento(km, comb, aver, carg, rut):
    try:
        model = joblib.load('modelo_mantenimiento.pkl')
        prediction = model.predict([[km, comb, aver, carg, rut]])
        return "Revisión Recomendada" if prediction[0] == 1 else "Estado Normal"
    except:
        # Fallback a lógica de umbral
        umbral = 80
        if km > umbral or comb > umbral or aver > umbral or carg > umbral or rut > umbral:
            return "Revisión Recomendada"
        return "Estado Normal"

# ------------------ Rutas de Autenticación ------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = conectar_db()
        user_row = conn.execute("SELECT * FROM usuarios WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        # Por simplicidad para el usuario en este entorno, aceptaremos admin/admin sin hash
        if user_row and (user_row['password'] == password or check_password_hash(user_row['password'], password)):
            user = User(user_row['id'], user_row['username'])
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash('Usuario o contraseña incorrectos', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ------------------ Rutas principales ------------------
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    conn = conectar_db()
    camiones = conn.execute("SELECT * FROM camiones").fetchall()
    
    # Notificaciones dinámicas
    notificaciones = []
    
    # Vencimiento de licencias
    conductores_vencen = conn.execute("""
        SELECT nombre, vencimiento FROM conductores 
        WHERE date(vencimiento) <= date('now', '+15 days')
    """).fetchall()
    for c in conductores_vencen:
        notificaciones.append(f"⚠️ Licencia de {c['nombre']} vence el {c['vencimiento']}")

    # Gastos totales por unidad
    gastos_totales = conn.execute("""
        SELECT c.placa, SUM(g.monto) as total 
        FROM camiones c 
        LEFT JOIN gastos g ON c.id = g.camion_id 
        GROUP BY c.id
    """).fetchall()

    conn.close()
    
    alertas_detalle = obtener_alertas_camiones()
    resultado = None
    datos_prediccion = None
    
    if request.method == 'POST':
        try:
            km = float(request.form['kilometraje'])
            comb = float(request.form['combustible'])
            aver = float(request.form['averias'])
            carg = float(request.form['carga'])
            rut = float(request.form['rutas'])
            camion_id = int(request.form['camion_id'])
            
            resultado = predecir_mantenimiento(km, comb, aver, carg, rut)
            # Pasamos los datos crudos para ApexCharts
            datos_prediccion = {
                'km': km, 'comb': comb, 'aver': aver, 'carg': carg, 'rut': rut
            }
            
            conn = conectar_db()
            conn.execute("""
                INSERT INTO historial_mantenimiento 
                (camion_id, kilometraje, combustible, averias, carga, rutas, resultado)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (camion_id, km, comb, aver, carg, rut, resultado))
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error en predicción: {e}")
            resultado = "Error en los datos"
            datos_prediccion = None
    
    return render_template("index_mantenimiento.html", 
                         camiones=camiones, 
                         alertas_detalle=alertas_detalle,
                         resultado=resultado, 
                         datos_prediccion=datos_prediccion,
                         notificaciones=notificaciones,
                         gastos_totales=gastos_totales)

# ------------------ Gestión de Gastos ------------------
@app.route('/gastos', methods=['GET', 'POST'])
@login_required
def gastos():
    conn = conectar_db()
    if request.method == 'POST':
        camion_id = request.form['camion_id']
        tipo = request.form['tipo']
        monto = request.form['monto']
        desc = request.form['descripcion']
        conn.execute("INSERT INTO gastos (camion_id, tipo, monto, descripcion) VALUES (?, ?, ?, ?)",
                    (camion_id, tipo, monto, desc))
        conn.commit()
        flash('✅ Gasto registrado', 'success')
        return redirect(url_for('gastos'))
    
    lista_gastos = conn.execute("""
        SELECT g.*, c.placa FROM gastos g 
        JOIN camiones c ON g.camion_id = c.id 
        ORDER BY g.fecha DESC
    """).fetchall()
    camiones = conn.execute("SELECT * FROM camiones").fetchall()
    conn.close()
    return render_template("gastos.html", gastos=lista_gastos, camiones=camiones)

# ------------------ Funciones auxiliares ------------------
def obtener_alertas_camiones():
    conn = conectar_db()
    camiones = conn.execute("SELECT * FROM camiones").fetchall()
    alertas_detalle = []
    
    for camion in camiones:
        cambio = conn.execute("""
            SELECT kilometraje, proximo_cambio 
            FROM cambios_aceite 
            WHERE camion_id = ? 
            ORDER BY id DESC LIMIT 1
        """, (camion["id"],)).fetchone()
        
        if cambio:
            km_actual = cambio["kilometraje"]
            km_proximo = cambio["proximo_cambio"]
            if km_proximo > 0:
                porcentaje = min(int((km_actual / km_proximo) * 100), 100)
                alertas_detalle.append({
                    "placa": camion["placa"],
                    "kilometraje": km_actual,
                    "porcentaje": porcentaje
                })
    
    conn.close()
    return alertas_detalle

# ------------------ Rutas Camiones ------------------
@app.route('/camiones')
@login_required
def index_camiones():
    conn = conectar_db()
    camiones = conn.execute("SELECT * FROM camiones").fetchall()
    conn.close()
    return render_template("index_logistica.html", camiones=camiones)

@app.route('/agregar_camion', methods=['POST'])
@login_required
def agregar_camion():
    try:
        placa = request.form['placa']
        modelo = request.form['modelo']
        conductor = request.form['conductor']
        fecha_adquisicion = request.form.get('fecha_adquisicion', None)
        
        conn = conectar_db()
        if fecha_adquisicion:
            conn.execute("INSERT INTO camiones (placa, modelo, conductor, fecha_adquisicion) VALUES (?, ?, ?, ?)",
                        (placa, modelo, conductor, fecha_adquisicion))
        else:
            conn.execute("INSERT INTO camiones (placa, modelo, conductor) VALUES (?, ?, ?)",
                        (placa, modelo, conductor))
        conn.commit()
        conn.close()
        flash('✅ Camión agregado', 'success')
    except Exception as e:
        flash(f'❌ Error: {str(e)}', 'danger')
    return redirect(url_for('index_camiones'))

@app.route('/eliminar_camion/<int:id>')
@login_required
def eliminar_camion(id):
    conn = conectar_db()
    conn.execute("DELETE FROM camiones WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('✅ Camión eliminado', 'success')
    return redirect(url_for('index_camiones'))

# ------------------ Rutas Conductores ------------------
@app.route('/conductores')
@login_required
def conductores():
    conn = conectar_db()
    lista = conn.execute("SELECT * FROM conductores").fetchall()
    conn.close()
    
    today_date = datetime.now().date()
    conductores_list = []
    for row in lista:
        conductor = dict(row)
        vencimiento_str = conductor['vencimiento']
        if vencimiento_str:
            try:
                vencimiento_date = datetime.strptime(vencimiento_str, '%Y-%m-%d').date()
                conductor['vencimiento_date'] = vencimiento_date
                days_remaining = (vencimiento_date - today_date).days
                conductor['dias_restantes'] = days_remaining
                if days_remaining < 0: conductor['estado'] = 'expired'
                elif days_remaining <= 30: conductor['estado'] = 'warning'
                else: conductor['estado'] = 'active'
            except:
                conductor['estado'] = 'unknown'
        else:
            conductor['estado'] = 'unknown'
        conductores_list.append(conductor)
    
    return render_template("conductores.html", 
                         conductores=conductores_list,
                         total_drivers=len(conductores_list),
                         active_drivers=len([c for c in conductores_list if c.get('estado') == 'active']),
                         warning_drivers=len([c for c in conductores_list if c.get('estado') == 'warning']),
                         expired_drivers=len([c for c in conductores_list if c.get('estado') == 'expired']))

@app.route('/agregar_conductor', methods=['GET', 'POST'])
@login_required
def agregar_conductor():
    if request.method == 'POST':
        conn = conectar_db()
        conn.execute("""
            INSERT INTO conductores (nombre, dni, licencia, categoria, telefono, vencimiento, direccion)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (request.form['nombre'], request.form['dni'], request.form['licencia'], 
              request.form['categoria'], request.form['telefono'], request.form['vencimiento'], request.form['direccion']))
        conn.commit()
        conn.close()
        flash('✅ Conductor agregado', 'success')
        return redirect(url_for('conductores'))
    return render_template("agregar_conductor.html")

@app.route('/editar_conductor/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_conductor(id):
    conn = conectar_db()
    if request.method == 'POST':
        conn.execute("""
            UPDATE conductores 
            SET nombre=?, dni=?, licencia=?, categoria=?, telefono=?, vencimiento=?, direccion=?
            WHERE id=?
        """, (request.form['nombre'], request.form['dni'], request.form['licencia'], 
              request.form['categoria'], request.form['telefono'], request.form['vencimiento'], 
              request.form['direccion'], id))
        conn.commit()
        conn.close()
        flash('✅ Conductor actualizado', 'success')
        return redirect(url_for('conductores'))
    
    conductor = conn.execute("SELECT * FROM conductores WHERE id=?", (id,)).fetchone()
    conn.close()
    if not conductor:
        flash('❌ Conductor no encontrado', 'danger')
        return redirect(url_for('conductores'))
    return render_template("editar_conductor.html", conductor=conductor)

@app.route('/eliminar_conductor/<int:id>')
@login_required
def eliminar_conductor(id):
    conn = conectar_db()
    conn.execute("DELETE FROM conductores WHERE id=?", (id,))
    conn.commit()
    conn.close()
    flash('✅ Conductor eliminado', 'success')
    return redirect(url_for('conductores'))

# ------------------ Rutas Cambios de Aceite ------------------
@app.route('/cambios_aceite')
@login_required
def cambios_aceite():
    conn = conectar_db()
    registros = conn.execute("""
        SELECT ca.*, c.placa FROM cambios_aceite ca 
        JOIN camiones c ON ca.camion_id = c.id ORDER BY ca.id DESC
    """).fetchall()
    conn.close()
    return render_template("cambios_aceite.html", registros=registros)

@app.route('/agregar_cambio', methods=['GET', 'POST'])
@login_required
def agregar_cambio():
    conn = conectar_db()
    if request.method == 'POST':
        conn.execute("""
            INSERT INTO cambios_aceite (camion_id, fecha, kilometraje, proximo_cambio, observaciones)
            VALUES (?, ?, ?, ?, ?)
        """, (request.form['camion_id'], request.form['fecha'], request.form['kilometraje'], 
              request.form['proximo_cambio'], request.form['observaciones']))
        conn.commit()
        conn.close()
        flash('✅ Registro guardado', 'success')
        return redirect(url_for('cambios_aceite'))
    
    camiones = conn.execute("SELECT * FROM camiones").fetchall()
    conn.close()
    return render_template("agregar_cambio.html", camiones=camiones)

# ------------------ Reportes ------------------
@app.route('/reporte/pdf')
@login_required
def reporte_pdf():
    conn = conectar_db()
    camiones = conn.execute("SELECT * FROM camiones").fetchall()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("REPORTE DE FLOTA - APARCO CARGO", styles['Title']))
    elements.append(Paragraph(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Paragraph("<br/><br/>", styles['Normal']))

    data = [['PLACA', 'MODELO', 'CONDUCTOR', 'ADQUISICIÓN']]
    for c in camiones:
        data.append([c['placa'], c['modelo'], c['conductor'], c['fecha_adquisicion'] or 'N/A'])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#00f2ff")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    elements.append(table)
    
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='reporte_flota.pdf', mimetype='application/pdf')

@app.route('/reporte/excel')
@login_required
def reporte_excel():
    conn = conectar_db()
    camiones = conn.execute("SELECT * FROM camiones").fetchall()
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Flota"

    headers = ['PLACA', 'MODELO', 'CONDUCTOR', 'FECHA ADQUISICIÓN']
    ws.append(headers)

    for c in camiones:
        ws.append([c['placa'], c['modelo'], c['conductor'], c['fecha_adquisicion'] or 'N/A'])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='reporte_flota.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# ------------------ Inicialización (Para Railway/Gunicorn) ------------------
with app.app_context():
    crear_tablas()
    actualizar_tabla_camiones()
    try:
        entrenar_modelo()
    except Exception as e:
        print(f"Aviso: No se pudo entrenar el modelo inicial: {e}")

# ------------------ Main ------------------
if __name__ == '__main__':
    # Configuración para ejecución local
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
