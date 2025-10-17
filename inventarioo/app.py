# app.py - Versión Mejorada (Solo Inventario)
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import altair as alt
import io
import base64

# Configuración de la página
st.set_page_config(
    page_title="Sistema de Inventario Cloud",
    layout="wide",
    page_icon="📦",
    initial_sidebar_state="expanded"
)

# Título principal
st.title("📦 Sistema de Inventario en la Nube")
st.markdown("---")

class DatabaseManager:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        """Inicializa la base de datos SQLite"""
        try:
            conn = sqlite3.connect('inventario.db', check_same_thread=False)
            cursor = conn.cursor()
            
            # Tabla de productos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS productos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    categoria TEXT,
                    stock INTEGER NOT NULL DEFAULT 0,
                    stock_minimo INTEGER NOT NULL DEFAULT 0,
                    precio_compra REAL DEFAULT 0,
                    precio_venta REAL DEFAULT 0,
                    tipo_medida TEXT DEFAULT 'UNIDAD',
                    ubicacion TEXT,
                    activo BOOLEAN DEFAULT 1,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla de movimientos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS movimientos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL CHECK(tipo IN ('ENTRADA', 'SALIDA')),
                    producto_id INTEGER NOT NULL,
                    cantidad INTEGER NOT NULL,
                    motivo TEXT,
                    usuario TEXT NOT NULL DEFAULT 'sistema',
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (producto_id) REFERENCES productos (id)
                )
            ''')
            
            # Tabla de usuarios
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    rol TEXT DEFAULT 'USUARIO',
                    activo BOOLEAN DEFAULT 1,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insertar usuario admin por defecto
            cursor.execute('''
                INSERT OR IGNORE INTO usuarios (usuario, password, nombre, rol) 
                VALUES ('admin', 'admin', 'Administrador', 'ADMIN')
            ''')
            
            # Verificar si hay productos de ejemplo
            cursor.execute("SELECT COUNT(*) FROM productos")
            count = cursor.fetchone()[0]
            
            if count == 0:
                # Insertar productos de ejemplo
                productos_ejemplo = [
                    ('Arroz Integral', 'Granos', 50, 10, 1500, 2000, 'KILO', 'Estante A-1'),
                    ('Leche Descremada', 'Lácteos', 25, 5, 800, 1200, 'LITRO', 'Refrigerador B-2'),
                    ('Aceite de Oliva', 'Aceites', 15, 3, 3000, 4500, 'LITRO', 'Estante C-3'),
                    ('Harina de Trigo', 'Harinas', 30, 8, 1200, 1800, 'KILO', 'Estante A-2'),
                    ('Atún en Lata', 'Enlatados', 40, 12, 1500, 2200, 'UNIDAD', 'Estante D-1'),
                    ('Azúcar Blanca', 'Endulzantes', 60, 15, 1200, 1800, 'KILO', 'Estante B-1'),
                    ('Café Molido', 'Bebidas', 20, 5, 4500, 6500, 'KILO', 'Estante C-2'),
                    ('Jabón Líquido', 'Limpieza', 35, 8, 2500, 3800, 'LITRO', 'Estante D-3'),
                    ('Papel Higiénico', 'Limpieza', 100, 20, 1800, 2800, 'UNIDAD', 'Estante E-1'),
                    ('Detergente', 'Limpieza', 18, 5, 3200, 4800, 'LITRO', 'Estante E-2')
                ]
                
                cursor.executemany('''
                    INSERT INTO productos 
                    (nombre, categoria, stock, stock_minimo, precio_compra, precio_venta, tipo_medida, ubicacion) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', productos_ejemplo)
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            st.error(f"❌ Error inicializando base de datos: {e}")
    
    def get_connection(self):
        return sqlite3.connect('inventario.db', check_same_thread=False)

class InventarioManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def ejecutar_consulta(self, query, params=None, commit=False):
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if query.strip().upper().startswith('SELECT'):
                columns = [description[0] for description in cursor.description]
                resultado = cursor.fetchall()
                resultado_dict = [dict(zip(columns, row)) for row in resultado]
                conn.close()
                return resultado_dict
            else:
                if commit:
                    conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            st.error(f"❌ Error en consulta: {e}")
            return None
    
    def obtener_productos(self, filtro_categoria=None, filtro_estado=None, busqueda=None):
        """Obtiene productos con filtros avanzados"""
        try:
            query = '''
                SELECT *, 
                       CASE 
                           WHEN stock = 0 THEN 'SIN_STOCK'
                           WHEN stock <= stock_minimo THEN 'STOCK_BAJO'
                           ELSE 'STOCK_OK'
                       END as estado_stock
                FROM productos 
                WHERE activo = 1
            '''
            
            params = []
            
            # Aplicar filtros
            if filtro_categoria and filtro_categoria != 'Todas':
                query += ' AND categoria = ?'
                params.append(filtro_categoria)
            
            if filtro_estado and filtro_estado != 'Todos':
                if filtro_estado == 'Sin Stock':
                    query += ' AND stock = 0'
                elif filtro_estado == 'Stock Bajo':
                    query += ' AND stock <= stock_minimo AND stock > 0'
                elif filtro_estado == 'Stock OK':
                    query += ' AND stock > stock_minimo'
            
            if busqueda:
                query += ' AND (nombre LIKE ? OR categoria LIKE ? OR ubicacion LIKE ?)'
                params.extend([f'%{busqueda}%', f'%{busqueda}%', f'%{busqueda}%'])
            
            query += ' ORDER BY nombre'
            
            productos = self.ejecutar_consulta(query, params)
            
            if productos:
                for producto in productos:
                    producto['medida_display'] = self._obtener_medida_display(producto['tipo_medida'])
                    producto['valor_total'] = producto['stock'] * producto.get('precio_compra', 0)
                    # Calcular días de stock basado en consumo promedio
                    producto['dias_stock'] = self.calcular_dias_stock(producto['id'])
            
            return productos or []
        except Exception as e:
            st.error(f"❌ Error obteniendo productos: {e}")
            return []
    
    def _obtener_medida_display(self, tipo_medida):
        medidas = {
            'UNIDAD': 'unid',
            'KILO': 'kg',
            'LITRO': 'lt',
            'METRO': 'm'
        }
        return medidas.get(tipo_medida, 'unid')
    
    def calcular_dias_stock(self, producto_id):
        """Calcula días aproximados de stock basado en historial"""
        try:
            # Obtener movimientos de los últimos 30 días
            movimientos = self.ejecutar_consulta('''
                SELECT tipo, cantidad, fecha 
                FROM movimientos 
                WHERE producto_id = ? AND fecha >= datetime('now', '-30 days')
                ORDER BY fecha DESC
            ''', (producto_id,))
            
            if not movimientos:
                return "Sin datos"
            
            # Calcular consumo promedio diario
            salidas = sum(m['cantidad'] for m in movimientos if m['tipo'] == 'SALIDA')
            consumo_diario = salidas / 30
            
            if consumo_diario == 0:
                return "∞"
            
            # Obtener stock actual
            producto = self.ejecutar_consulta("SELECT stock FROM productos WHERE id = ?", (producto_id,))
            if producto:
                stock_actual = producto[0]['stock']
                dias = stock_actual / consumo_diario
                return f"{dias:.1f}"
            
            return "N/A"
        except:
            return "N/A"
    
    def obtener_categorias(self):
        """Obtiene categorías únicas"""
        try:
            categorias = self.ejecutar_consulta('''
                SELECT DISTINCT categoria 
                FROM productos 
                WHERE categoria IS NOT NULL AND categoria != '' 
                ORDER BY categoria
            ''')
            return [cat['categoria'] for cat in categorias] if categorias else []
        except:
            return []
    
    def obtener_estadisticas(self, productos_filtrados=None):
        """Calcula estadísticas del inventario"""
        try:
            if productos_filtrados is None:
                productos = self.obtener_productos()
            else:
                productos = productos_filtrados
            
            if not productos:
                return {}
            
            total_productos = len(productos)
            productos_sin_stock = len([p for p in productos if p['estado_stock'] == 'SIN_STOCK'])
            productos_stock_bajo = len([p for p in productos if p['estado_stock'] == 'STOCK_BAJO'])
            valor_total = sum(p['stock'] * p.get('precio_compra', 0) for p in productos)
            stock_total = sum(p['stock'] for p in productos)
            
            # Productos por categoría
            categorias_count = {}
            for p in productos:
                cat = p.get('categoria', 'Sin categoría')
                categorias_count[cat] = categorias_count.get(cat, 0) + 1
            
            return {
                'total_productos': total_productos,
                'sin_stock': productos_sin_stock,
                'stock_bajo': productos_stock_bajo,
                'valor_total': valor_total,
                'stock_total': stock_total,
                'productos_ok': total_productos - productos_sin_stock - productos_stock_bajo,
                'categorias_count': categorias_count
            }
        except:
            return {}
    
    def agregar_producto(self, datos):
        """Agrega un nuevo producto"""
        try:
            query = """
                INSERT INTO productos (nombre, categoria, stock, stock_minimo, 
                                     precio_compra, precio_venta, tipo_medida, ubicacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            params = (
                datos['nombre'].strip(),
                datos.get('categoria', ''),
                datos.get('stock', 0),
                datos.get('stock_minimo', 0),
                datos.get('precio_compra', 0),
                datos.get('precio_venta', 0),
                datos.get('tipo_medida', 'UNIDAD'),
                datos.get('ubicacion', '')
            )
            
            resultado = self.ejecutar_consulta(query, params, commit=True)
            
            if resultado:
                # Registrar movimiento inicial
                producto_id = self.ejecutar_consulta("SELECT last_insert_rowid()")[0]['last_insert_rowid()']
                self.registrar_movimiento(producto_id, "ENTRADA", datos.get('stock', 0), "Creación de producto")
                return True, "✅ Producto agregado correctamente"
            return False, "❌ Error al agregar producto"
        except Exception as e:
            return False, f"❌ Error: {e}"
    
    def actualizar_producto(self, producto_id, datos):
        """Actualiza un producto existente"""
        try:
            query = """
                UPDATE productos 
                SET nombre = ?, categoria = ?, stock_minimo = ?,
                    precio_compra = ?, precio_venta = ?, tipo_medida = ?, ubicacion = ?
                WHERE id = ?
            """
            
            params = (
                datos['nombre'].strip(),
                datos.get('categoria', ''),
                datos.get('stock_minimo', 0),
                datos.get('precio_compra', 0),
                datos.get('precio_venta', 0),
                datos.get('tipo_medida', 'UNIDAD'),
                datos.get('ubicacion', ''),
                producto_id
            )
            
            resultado = self.ejecutar_consulta(query, params, commit=True)
            
            if resultado:
                return True, "✅ Producto actualizado correctamente"
            return False, "❌ Error al actualizar producto"
        except Exception as e:
            return False, f"❌ Error: {e}"
    
    def eliminar_producto(self, producto_id):
        """Elimina un producto (desactiva)"""
        try:
            resultado = self.ejecutar_consulta(
                "UPDATE productos SET activo = 0 WHERE id = ?", 
                (producto_id,), 
                commit=True
            )
            
            if resultado:
                return True, "✅ Producto eliminado correctamente"
            return False, "❌ Error al eliminar producto"
        except Exception as e:
            return False, f"❌ Error: {e}"
    
    def ajustar_stock(self, producto_id, cantidad, tipo, motivo="Ajuste manual"):
        """Ajusta el stock de un producto"""
        try:
            # Obtener stock actual
            producto = self.ejecutar_consulta("SELECT stock FROM productos WHERE id = ?", (producto_id,))
            if not producto:
                return False, "Producto no encontrado"
            
            stock_actual = producto[0]['stock']
            
            if tipo == "ENTRADA":
                nuevo_stock = stock_actual + cantidad
            else:  # SALIDA
                if stock_actual < cantidad:
                    return False, "❌ Stock insuficiente para esta salida"
                nuevo_stock = stock_actual - cantidad
            
            # Actualizar stock
            self.ejecutar_consulta("UPDATE productos SET stock = ? WHERE id = ?", 
                                  (nuevo_stock, producto_id), commit=True)
            
            # Registrar movimiento
            self.registrar_movimiento(producto_id, tipo, cantidad, motivo)
            return True, f"✅ Stock actualizado: {nuevo_stock}"
        except Exception as e:
            return False, f"❌ Error: {e}"
    
    def registrar_movimiento(self, producto_id, tipo, cantidad, motivo):
        """Registra un movimiento en el historial"""
        try:
            query = """
                INSERT INTO movimientos (tipo, producto_id, cantidad, motivo)
                VALUES (?, ?, ?, ?)
            """
            return self.ejecutar_consulta(query, (tipo, producto_id, cantidad, motivo), commit=True)
        except:
            return False

# FUNCIONES DE LA INTERFAZ - INVENTARIO MEJORADO
def mostrar_inventario(inventario):
    st.header("📋 Inventario Completo")
    
    # Filtros avanzados en expander
    with st.expander("🔍 Filtros Avanzados", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # Búsqueda por texto
            busqueda = st.text_input("🔎 Buscar", placeholder="Nombre, categoría, ubicación...")
        
        with col2:
            # Filtro por categoría
            categorias = ['Todas'] + inventario.obtener_categorias()
            filtro_categoria = st.selectbox("Categoría", categorias)
        
        with col3:
            # Filtro por estado de stock
            filtro_estado = st.selectbox("Estado", 
                                       ['Todos', 'Stock OK', 'Stock Bajo', 'Sin Stock'])
        
        with col4:
            # Ordenamiento
            ordenamiento = st.selectbox("Ordenar por", 
                                      ['Nombre A-Z', 'Nombre Z-A', 'Stock (Mayor)', 'Stock (Menor)', 'Valor (Mayor)'])
    
    # Aplicar filtros y obtener productos
    productos = inventario.obtener_productos(filtro_categoria, filtro_estado, busqueda)
    
    # Aplicar ordenamiento
    if productos:
        if ordenamiento == 'Nombre A-Z':
            productos.sort(key=lambda x: x['nombre'])
        elif ordenamiento == 'Nombre Z-A':
            productos.sort(key=lambda x: x['nombre'], reverse=True)
        elif ordenamiento == 'Stock (Mayor)':
            productos.sort(key=lambda x: x['stock'], reverse=True)
        elif ordenamiento == 'Stock (Menor)':
            productos.sort(key=lambda x: x['stock'])
        elif ordenamiento == 'Valor (Mayor)':
            productos.sort(key=lambda x: x['valor_total'], reverse=True)
    
    # Mostrar estadísticas de filtro
    stats_filtro = inventario.obtener_estadisticas(productos)
    mostrar_estadisticas_filtro(stats_filtro, len(productos))
    
    if productos:
        # Selección de vista
        vista = st.radio("Tipo de vista:", ["Vista Tabla", "Vista Tarjetas"], horizontal=True)
        
        if vista == "Vista Tabla":
            mostrar_vista_tabla(inventario, productos)
        else:
            mostrar_vista_tarjetas(inventario, productos)
        
        # Exportar datos
        mostrar_opciones_exportacion(productos)
        
    else:
        st.info("🚫 No se encontraron productos con los filtros aplicados")

def mostrar_estadisticas_filtro(stats, total_productos):
    """Muestra estadísticas del filtro aplicado"""
    if stats:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Productos", total_productos)
        
        with col2:
            st.metric("🔴 Sin Stock", stats['sin_stock'])
        
        with col3:
            st.metric("🟡 Stock Bajo", stats['stock_bajo'])
        
        with col4:
            st.metric("🟢 Stock OK", stats['productos_ok'])
        
        with col5:
            st.metric("💰 Valor Total", f"${stats['valor_total']:,.0f}")

def mostrar_vista_tabla(inventario, productos):
    """Muestra los productos en formato tabla"""
    
    # Crear DataFrame mejorado
    datos = []
    for p in productos:
        estado_emoji = "🔴" if p['estado_stock'] == 'SIN_STOCK' else "🟡" if p['estado_stock'] == 'STOCK_BAJO' else "🟢"
        
        datos.append({
            'ID': p['id'],
            'Producto': p['nombre'],
            'Categoría': p.get('categoria', 'Sin categoría'),
            'Stock': p['stock'],
            'Medida': p['medida_display'],
            'Mínimo': p.get('stock_minimo', ''),
            'P. Compra': f"${p.get('precio_compra', 0):,.0f}",
            'P. Venta': f"${p.get('precio_venta', 0):,.0f}",
            'Valor Total': f"${p['valor_total']:,.0f}",
            'Ubicación': p.get('ubicacion', ''),
            'Días Stock': p.get('dias_stock', 'N/A'),
            'Estado': estado_emoji
        })
    
    df = pd.DataFrame(datos)
    
    # Configurar la visualización de la tabla
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Stock": st.column_config.ProgressColumn(
                "Stock",
                help="Nivel de stock actual",
                format="%d",
                min_value=0,
                max_value=max(p['stock'] for p in productos) if productos else 100
            ),
            "Estado": st.column_config.TextColumn(
                "Estado",
                help="Estado del stock"
            )
        }
    )

def mostrar_vista_tarjetas(inventario, productos):
    """Muestra los productos en formato tarjetas"""
    
    # Configurar columnas responsivas
    cols = st.columns(3)
    
    for idx, producto in enumerate(productos):
        col = cols[idx % 3]
        
        with col:
            with st.container():
                # Color de la tarjeta según estado
                if producto['estado_stock'] == 'SIN_STOCK':
                    st.markdown("""
                    <style>
                    .sin-stock {
                        background-color: #ffebee;
                        border: 2px solid #f44336;
                        border-radius: 10px;
                        padding: 15px;
                        margin: 10px 0px;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    card_class = "sin-stock"
                elif producto['estado_stock'] == 'STOCK_BAJO':
                    st.markdown("""
                    <style>
                    .stock-bajo {
                        background-color: #fff3e0;
                        border: 2px solid #ff9800;
                        border-radius: 10px;
                        padding: 15px;
                        margin: 10px 0px;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    card_class = "stock-bajo"
                else:
                    st.markdown("""
                    <style>
                    .stock-ok {
                        background-color: #e8f5e8;
                        border: 2px solid #4caf50;
                        border-radius: 10px;
                        padding: 15px;
                        margin: 10px 0px;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    card_class = "stock-ok"
                
                st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)
                
                # Información del producto
                st.subheader(f"📦 {producto['nombre']}")
                
                col_info1, col_info2 = st.columns(2)
                
                with col_info1:
                    st.write(f"**Stock:** {producto['stock']} {producto['medida_display']}")
                    st.write(f"**Mínimo:** {producto.get('stock_minimo', 'N/A')}")
                    st.write(f"**Categoría:** {producto.get('categoria', 'N/A')}")
                
                with col_info2:
                    st.write(f"**P. Venta:** ${producto.get('precio_venta', 0):,.0f}")
                    st.write(f"**Valor:** ${producto['valor_total']:,.0f}")
                    st.write(f"**Ubicación:** {producto.get('ubicacion', 'N/A')}")
                
                # Botones de acción
                col_btn1, col_btn2 = st.columns(2)
                
                with col_btn1:
                    if st.button("📝 Ajustar", key=f"ajustar_{producto['id']}", use_container_width=True):
                        st.session_state.ajustar_producto = producto
                        st.rerun()
                
                with col_btn2:
                    if st.button("✏️ Editar", key=f"editar_{producto['id']}", use_container_width=True):
                        st.session_state.editar_producto = producto
                        st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)

def mostrar_opciones_exportacion(productos):
    """Muestra opciones para exportar datos"""
    st.markdown("---")
    st.subheader("📤 Exportar Datos")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Exportar a CSV
        df_csv = pd.DataFrame([{
            'Nombre': p['nombre'],
            'Categoría': p.get('categoria', ''),
            'Stock': p['stock'],
            'Stock_Mínimo': p.get('stock_minimo', ''),
            'Precio_Compra': p.get('precio_compra', 0),
            'Precio_Venta': p.get('precio_venta', 0),
            'Tipo_Medida': p['tipo_medida'],
            'Ubicación': p.get('ubicacion', ''),
            'Valor_Total': p['valor_total'],
            'Estado': p['estado_stock']
        } for p in productos])
        
        csv = df_csv.to_csv(index=False)
        st.download_button(
            label="📥 Descargar CSV",
            data=csv,
            file_name=f"inventario_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col2:
        # Exportar a Excel
        @st.cache_data
        def to_excel(df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Inventario')
            return output.getvalue()
        
        excel_data = to_excel(df_csv)
        st.download_button(
            label="📊 Descargar Excel",
            data=excel_data,
            file_name=f"inventario_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.ms-excel",
            use_container_width=True
        )
    
    with col3:
        # Generar reporte rápido
        if st.button("📋 Generar Reporte", use_container_width=True):
            generar_reporte_rapido(productos)

def generar_reporte_rapido(productos):
    """Genera un reporte rápido del inventario"""
    if not productos:
        return
    
    stats = {
        'total': len(productos),
        'sin_stock': len([p for p in productos if p['estado_stock'] == 'SIN_STOCK']),
        'stock_bajo': len([p for p in productos if p['estado_stock'] == 'STOCK_BAJO']),
        'valor_total': sum(p['valor_total'] for p in productos)
    }
    
    reporte = f"""
    📊 REPORTE RÁPIDO DE INVENTARIO
    Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}
    
    📦 RESUMEN:
    • Total productos: {stats['total']}
    • Sin stock: {stats['sin_stock']} 🔴
    • Stock bajo: {stats['stock_bajo']} 🟡
    • Valor total: ${stats['valor_total']:,.0f}
    
    🚨 PRODUCTOS CRÍTICOS:
    """
    
    productos_criticos = [p for p in productos if p['estado_stock'] in ['SIN_STOCK', 'STOCK_BAJO']]
    for i, producto in enumerate(productos_criticos[:5], 1):
        estado = "SIN STOCK" if producto['estado_stock'] == 'SIN_STOCK' else f"STOCK BAJO ({producto['stock']})"
        reporte += f"{i}. {producto['nombre']} - {estado}\n"
    
    st.text_area("Reporte Generado", reporte, height=300)

# ... (las otras funciones del main y navegación permanecen igual)

def main():
    # Sidebar con navegación
    st.sidebar.title("🧭 Navegación")
    
    menu = st.sidebar.radio(
        "Selecciona una sección:",
        ["📊 Dashboard", "📋 Inventario", "🛠️ Gestión", "⚡ Ajustes"]
    )
    
    # Inicializar sistema
    try:
        db_manager = DatabaseManager()
        inventario = InventarioManager(db_manager)
        
        # Navegación
        if menu == "📊 Dashboard":
            # Función del dashboard (simplificada para este ejemplo)
            st.header("📊 Dashboard")
            st.info("Esta es una versión mejorada del sistema de inventario")
        elif menu == "📋 Inventario":
            mostrar_inventario(inventario)
        elif menu == "🛠️ Gestión":
            # Función de gestión (simplificada)
            st.header("🛠️ Gestión de Productos")
            st.info("Módulo de gestión de productos")
        elif menu == "⚡ Ajustes":
            # Función de ajustes (simplificada)
            st.header("⚡ Ajustes Rápidos")
            st.info("Módulo de ajustes de stock")
        
        # Información en sidebar
        st.sidebar.markdown("---")
        st.sidebar.info("""
        **Credenciales de acceso:**
        - Usuario: `admin`
        - Contraseña: `admin`
        
        *Sistema hosteado en Streamlit Cloud*
        """)
        
    except Exception as e:
        st.error(f"❌ Error inicializando la aplicación: {e}")
        st.info("Por favor, recarga la página o contacta al administrador.")

if __name__ == "__main__":
    main()
