# app.py
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
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
        """Inicializa la base de datos en memoria (funciona en la nube)"""
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
                ('Jabón Líquido', 'Limpieza', 35, 8, 2500, 3800, 'LITRO', 'Estante D-3')
            ]
            
            cursor.executemany('''
                INSERT INTO productos 
                (nombre, categoria, stock, stock_minimo, precio_compra, precio_venta, tipo_medida, ubicacion) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', productos_ejemplo)
        
        conn.commit()
        conn.close()
    
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
    
    def obtener_productos(self, filtro_categoria=None, filtro_estado=None):
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
        
        query += ' ORDER BY nombre'
        
        productos = self.ejecutar_consulta(query, params)
        
        if productos:
            for producto in productos:
                producto['medida_display'] = self._obtener_medida_display(producto['tipo_medida'])
                producto['valor_total'] = producto['stock'] * producto.get('precio_compra', 0)
        
        return productos or []
    
    def _obtener_medida_display(self, tipo_medida):
        medidas = {
            'UNIDAD': 'unid',
            'KILO': 'kg',
            'LITRO': 'lt',
            'METRO': 'm'
        }
        return medidas.get(tipo_medida, 'unid')
    
    def obtener_categorias(self):
        categorias = self.ejecutar_consulta('''
            SELECT DISTINCT categoria 
            FROM productos 
            WHERE categoria IS NOT NULL AND categoria != '' 
            ORDER BY categoria
        ''')
        return [cat['categoria'] for cat in categorias] if categorias else []
    
    def obtener_estadisticas(self):
        productos = self.obtener_productos()
        
        if not productos:
            return {}
        
        total_productos = len(productos)
        productos_sin_stock = len([p for p in productos if p['estado_stock'] == 'SIN_STOCK'])
        productos_stock_bajo = len([p for p in productos if p['estado_stock'] == 'STOCK_BAJO'])
        valor_total = sum(p['stock'] * p.get('precio_compra', 0) for p in productos)
        stock_total = sum(p['stock'] for p in productos)
        
        return {
            'total_productos': total_productos,
            'sin_stock': productos_sin_stock,
            'stock_bajo': productos_stock_bajo,
            'valor_total': valor_total,
            'stock_total': stock_total,
            'productos_ok': total_productos - productos_sin_stock - productos_stock_bajo
        }
    
    def agregar_producto(self, datos):
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
    
    def ajustar_stock(self, producto_id, cantidad, tipo, motivo="Ajuste manual"):
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
    
    def registrar_movimiento(self, producto_id, tipo, cantidad, motivo):
        query = """
            INSERT INTO movimientos (tipo, producto_id, cantidad, motivo)
            VALUES (?, ?, ?, ?)
        """
        return self.ejecutar_consulta(query, (tipo, producto_id, cantidad, motivo), commit=True)
    
    def obtener_movimientos(self, dias=30):
        query = """
            SELECT m.*, p.nombre as producto_nombre
            FROM movimientos m
            JOIN productos p ON m.producto_id = p.id
            WHERE m.fecha >= datetime('now', '-{} days')
            ORDER BY m.fecha DESC
        """.format(dias)
        
        return self.ejecutar_consulta(query) or []

# FUNCIONES DE LA INTERFAZ
def mostrar_dashboard(inventario):
    st.header("📊 Dashboard Principal")
    
    # Estadísticas en tiempo real
    stats = inventario.obtener_estadisticas()
    
    # KPIs principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Total Productos", 
            value=stats['total_productos'],
            delta=f"{stats['productos_ok']} OK"
        )
    
    with col2:
        st.metric(
            label="🔴 Sin Stock", 
            value=stats['sin_stock'],
            delta_color="inverse"
        )
    
    with col3:
        st.metric(
            label="🟡 Stock Bajo", 
            value=stats['stock_bajo'],
            delta_color="inverse"
        )
    
    with col4:
        st.metric(
            label="💰 Valor Total", 
            value=f"${stats['valor_total']:,.0f}"
        )
    
    st.markdown("---")
    
    # Productos que necesitan atención
    st.subheader("🚨 Productos que Necesitan Atención")
    
    productos_criticos = inventario.obtener_productos(filtro_estado='Stock Bajo')
    productos_criticos += inventario.obtener_productos(filtro_estado='Sin Stock')
    
    if productos_criticos:
        for producto in productos_criticos[:10]:  # Mostrar máximo 10
            with st.container():
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    if producto['estado_stock'] == 'SIN_STOCK':
                        st.error(f"**{producto['nombre']}** - 🔴 SIN STOCK")
                    else:
                        st.warning(f"**{producto['nombre']}** - 🟡 Stock bajo: {producto['stock']} {producto['medida_display']}")
                
                with col2:
                    st.write(f"Stock mínimo: {producto.get('stock_minimo', 'N/A')}")
                    st.write(f"Ubicación: {producto.get('ubicacion', 'N/A')}")
                
                with col3:
                    if st.button("📝 Ajustar", key=f"btn_{producto['id']}"):
                        st.session_state.ajustar_producto = producto
                        st.rerun()
                
                st.markdown("---")
    else:
        st.success("🎉 ¡Todos los productos tienen stock suficiente!")
    
    # Gráfico simple de distribución
    st.subheader("📈 Distribución de Stock")
    
    if stats['total_productos'] > 0:
        datos_chart = {
            'Estado': ['Stock OK', 'Stock Bajo', 'Sin Stock'],
            'Cantidad': [stats['productos_ok'], stats['stock_bajo'], stats['sin_stock']]
        }
        
        df_chart = pd.DataFrame(datos_chart)
        st.bar_chart(df_chart.set_index('Estado'))

def mostrar_inventario_completo(inventario):
    st.header("📋 Inventario Completo")
    
    # Filtros
    col1, col2, col3 = st.columns(3)
    
    with col1:
        categorias = ['Todas'] + inventario.obtener_categorias()
        filtro_categoria = st.selectbox("Filtrar por categoría", categorias)
    
    with col2:
        filtro_estado = st.selectbox("Filtrar por estado", 
                                   ['Todos', 'Stock OK', 'Stock Bajo', 'Sin Stock'])
    
    with col3:
        if st.button("🔄 Actualizar Vista", type="secondary"):
            st.rerun()
    
    # Obtener productos filtrados
    productos = inventario.obtener_productos(filtro_categoria, filtro_estado)
    
    if productos:
        # Crear DataFrame para mostrar
        datos = []
        for p in productos:
            estado_emoji = "🔴" if p['estado_stock'] == 'SIN_STOCK' else "🟡" if p['estado_stock'] == 'STOCK_BAJO' else "🟢"
            
            datos.append({
                'ID': p['id'],
                'Producto': p['nombre'],
                'Categoría': p.get('categoria', ''),
                'Stock': f"{p['stock']} {p['medida_display']}",
                'Mínimo': p.get('stock_minimo', ''),
                'Precio Compra': f"${p.get('precio_compra', 0):,.0f}",
                'Precio Venta': f"${p.get('precio_venta', 0):,.0f}",
                'Valor Total': f"${p['valor_total']:,.0f}",
                'Ubicación': p.get('ubicacion', ''),
                'Estado': f"{estado_emoji} {p['estado_stock']}"
            })
        
        df = pd.DataFrame(datos)
        
        # Mostrar tabla
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Estadísticas del filtro
        total_valor = sum(p['valor_total'] for p in productos)
        st.info(f"**Mostrando {len(productos)} productos | Valor total: ${total_valor:,.0f}**")
        
        # Botón de exportación
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Descargar CSV",
            data=csv,
            file_name=f"inventario_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No hay productos que coincidan con los filtros seleccionados")

def mostrar_gestion_productos(inventario):
    st.header("🛠️ Gestión de Productos")
    
    tab1, tab2, tab3 = st.tabs(["➕ Agregar Producto", "✏️ Editar Productos", "📋 Lista Completa"])
    
    with tab1:
        st.subheader("Agregar Nuevo Producto")
        
        with st.form("form_agregar_producto"):
            col1, col2 = st.columns(2)
            
            with col1:
                nombre = st.text_input("Nombre del Producto*", placeholder="Ej: Arroz Integral")
                categoria = st.text_input("Categoría", placeholder="Ej: Granos, Lácteos, etc.")
                tipo_medida = st.selectbox("Tipo de Medida*", ["UNIDAD", "KILO", "LITRO", "METRO"])
                ubicacion = st.text_input("Ubicación", placeholder="Ej: Estante A-1")
            
            with col2:
                stock = st.number_input("Stock Inicial*", min_value=0, value=0)
                stock_minimo = st.number_input("Stock Mínimo*", min_value=0, value=5)
                precio_compra = st.number_input("Precio Compra ($)", min_value=0.0, value=0.0, step=100.0)
                precio_venta = st.number_input("Precio Venta ($)", min_value=0.0, value=0.0, step=100.0)
            
            submitted = st.form_submit_button("➕ Agregar Producto", type="primary")
            
            if submitted:
                if not nombre.strip():
                    st.error("❌ El nombre del producto es obligatorio")
                else:
                    datos = {
                        'nombre': nombre,
                        'categoria': categoria,
                        'stock': stock,
                        'stock_minimo': stock_minimo,
                        'precio_compra': precio_compra,
                        'precio_venta': precio_venta,
                        'tipo_medida': tipo_medida,
                        'ubicacion': ubicacion
                    }
                    
                    exito, mensaje = inventario.agregar_producto(datos)
                    if exito:
                        st.success(mensaje)
                        st.balloons()
                    else:
                        st.error(mensaje)
    
    with tab2:
        st.subheader("Editar Productos Existente")
        
        productos = inventario.obtener_productos()
        if productos:
            producto_seleccionado = st.selectbox(
                "Selecciona el producto a editar:",
                options=productos,
                format_func=lambda x: f"{x['nombre']} (Stock: {x['stock']} {x['medida_display']})"
            )
            
            if producto_seleccionado:
                st.write(f"**Editando:** {producto_seleccionado['nombre']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    nuevo_stock = st.number_input("Nuevo Stock", 
                                                min_value=0, 
                                                value=producto_seleccionado['stock'])
                    nuevo_minimo = st.number_input("Nuevo Stock Mínimo", 
                                                 min_value=0, 
                                                 value=producto_seleccionado['stock_minimo'])
                
                with col2:
                    nuevo_precio_compra = st.number_input("Nuevo Precio Compra", 
                                                        min_value=0.0, 
                                                        value=float(producto_seleccionado['precio_compra']))
                    nuevo_precio_venta = st.number_input("Nuevo Precio Venta", 
                                                       min_value=0.0, 
                                                       value=float(producto_seleccionado['precio_venta']))
                
                if st.button("💾 Guardar Cambios", type="primary"):
                    # Aquí iría la función de actualización
                    st.success("✅ Funcionalidad de edición en desarrollo")
        else:
            st.info("No hay productos para editar")
    
    with tab3:
        mostrar_inventario_completo(inventario)

def mostrar_ajustes_stock(inventario):
    st.header("⚡ Ajustes Rápidos de Stock")
    
    if 'ajustar_producto' in st.session_state:
        producto = st.session_state.ajustar_producto
        st.subheader(f"Ajustando: {producto['nombre']}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info(f"**Stock actual:** {producto['stock']} {producto['medida_display']}")
            st.info(f"**Stock mínimo:** {producto.get('stock_minimo', 'N/A')}")
            
            with st.form(f"entrada_{producto['id']}"):
                cantidad_entrada = st.number_input("Cantidad a ingresar", min_value=1, value=1, key="entrada")
                motivo_entrada = st.text_input("Motivo de entrada", placeholder="Compra, devolución, etc.")
                
                if st.form_submit_button("➕ Registrar Entrada"):
                    exito, mensaje = inventario.ajustar_stock(
                        producto['id'], cantidad_entrada, "ENTRADA", 
                        motivo_entrada or "Entrada de stock"
                    )
                    if exito:
                        st.success(mensaje)
                        del st.session_state.ajustar_producto
                        st.rerun()
                    else:
                        st.error(mensaje)
        
        with col2:
            with st.form(f"salida_{producto['id']}"):
                cantidad_salida = st.number_input("Cantidad a retirar", min_value=1, value=1, 
                                                max_value=producto['stock'], key="salida")
                motivo_salida = st.text_input("Motivo de salida", placeholder="Venta, consumo, etc.")
                
                if st.form_submit_button("➖ Registrar Salida"):
                    exito, mensaje = inventario.ajustar_stock(
                        producto['id'], cantidad_salida, "SALIDA",
                        motivo_salida or "Salida de stock"
                    )
                    if exito:
                        st.success(mensaje)
                        del st.session_state.ajustar_producto
                        st.rerun()
                    else:
                        st.error(mensaje)
        
        if st.button("❌ Cancelar"):
            del st.session_state.ajustar_producto
            st.rerun()
    
    else:
        st.subheader("Selecciona un producto para ajustar")
        
        productos = inventario.obtener_productos()
        for producto in productos:
            with st.expander(f"{producto['nombre']} | Stock: {producto['stock']} {producto['medida_display']} | {producto['estado_stock']}"):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.write(f"**Categoría:** {producto.get('categoria', 'N/A')}")
                    st.write(f"**Ubicación:** {producto.get('ubicacion', 'N/A')}")
                with col2:
                    st.write(f"**Precio compra:** ${producto.get('precio_compra', 0):,.0f}")
                    st.write(f"**Precio venta:** ${producto.get('precio_venta', 0):,.0f}")
                with col3:
                    if st.button("📝 Ajustar Stock", key=f"sel_{producto['id']}"):
                        st.session_state.ajustar_producto = producto
                        st.rerun()

def mostrar_reportes(inventario):
    st.header("📈 Reportes y Análisis")
    
    tab1, tab2, tab3 = st.tabs(["📊 Reporte General", "📋 Historial", "📤 Exportar Datos"])
    
    with tab1:
        st.subheader("Reporte General del Inventario")
        
        stats = inventario.obtener_estadisticas()
        productos = inventario.obtener_productos()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Productos Activos", stats['total_productos'])
            st.metric("Valor Total Inventario", f"${stats['valor_total']:,.0f}")
            st.metric("Stock Total", stats['stock_total'])
        
        with col2:
            st.metric("Productos Sin Stock", stats['sin_stock'])
            st.metric("Productos Stock Bajo", stats['stock_bajo'])
            st.metric("Productos Stock OK", stats['productos_ok'])
        
        # Productos más valiosos
        st.subheader("🏆 Productos de Mayor Valor")
        productos_valiosos = sorted(productos, key=lambda x: x['valor_total'], reverse=True)[:5]
        
        for i, producto in enumerate(productos_valiosos, 1):
            st.write(f"{i}. **{producto['nombre']}** - ${producto['valor_total']:,.0f}")
    
    with tab2:
        st.subheader("📋 Historial de Movimientos")
        
        dias = st.selectbox("Período a mostrar", [7, 30, 60, 90], index=1)
        movimientos = inventario.obtener_movimientos(dias)
        
        if movimientos:
            datos_movimientos = []
            for m in movimientos:
                datos_movimientos.append({
                    'Fecha': m['fecha'],
                    'Producto': m['producto_nombre'],
                    'Tipo': m['tipo'],
                    'Cantidad': m['cantidad'],
                    'Motivo': m['motivo']
                })
            
            df_movimientos = pd.DataFrame(datos_movimientos)
            st.dataframe(df_movimientos, use_container_width=True, hide_index=True)
        else:
            st.info("No hay movimientos en el período seleccionado")
    
    with tab3:
        st.subheader("📤 Exportar Datos")
        
        productos = inventario.obtener_productos()
        
        if productos:
            # Exportar productos
            df_productos = pd.DataFrame([
                {
                    'Nombre': p['nombre'],
                    'Categoría': p.get('categoria', ''),
                    'Stock': p['stock'],
                    'Stock_Mínimo': p.get('stock_minimo', ''),
                    'Precio_Compra': p.get('precio_compra', 0),
                    'Precio_Venta': p.get('precio_venta', 0),
                    'Tipo_Medida': p['tipo_medida'],
                    'Ubicación': p.get('ubicacion', ''),
                    'Estado': p['estado_stock']
                } for p in productos
            ])
            
            csv_productos = df_productos.to_csv(index=False)
            st.download_button(
                label="📥 Descargar Productos (CSV)",
                data=csv_productos,
                file_name=f"productos_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
            
            # Vista previa
            st.subheader("Vista Previa de Datos")
            st.dataframe(df_productos.head(10), use_container_width=True)

def main():
    # Sidebar con navegación
    st.sidebar.title("🧭 Navegación")
    
    menu = st.sidebar.radio(
        "Selecciona una sección:",
        ["📊 Dashboard", "📋 Inventario", "🛠️ Gestión", "⚡ Ajustes", "📈 Reportes"]
    )
    
    # Inicializar sistema
    db_manager = DatabaseManager()
    inventario = InventarioManager(db_manager)
    
    # Navegación
    if menu == "📊 Dashboard":
        mostrar_dashboard(inventario)
    elif menu == "📋 Inventario":
        mostrar_inventario_completo(inventario)
    elif menu == "🛠️ Gestión":
        mostrar_gestion_productos(inventario)
    elif menu == "⚡ Ajustes":
        mostrar_ajustes_stock(inventario)
    elif menu == "📈 Reportes":
        mostrar_reportes(inventario)
    
    # Información en sidebar
    st.sidebar.markdown("---")
    st.sidebar.info("""
    **Credenciales de acceso:**
    - Usuario: `admin`
    - Contraseña: `admin`
    
    *Sistema hosteado en Streamlit Cloud*
    """)

if __name__ == "__main__":
    main()