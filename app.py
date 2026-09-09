import streamlit as st
import requests

# --- CONFIGURACIÓN DE PARÁMETROS MELI (2026) ---
UMBRAL_ENVIO_GRATIS = 33000  # A partir de este monto, el envío gratis es obligatorio
COSTO_FIJO_UNIDAD = 900      # Costo fijo para productos menores a $12,000
UMBRAL_COSTO_FIJO = 12000
COSTO_ENVIO_PROMEDIO = 4500  # Costo estimado que te cobra ML por Mercado Envíos

def predecir_categoria(titulo):
    """Consulta a la API de Mercado Libre para predecir la categoría"""
    url = f"https://api.mercadolibre.com/sites/MLA/category_predictor/predict?title={titulo}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data.get("domain_name", "Categoría no encontrada"), data.get("id", "Sin ID")
        return "Error en API", None
    except:
        return "Error de conexión", None

def calcular_metricas(costo_producto, precio_venta, tipo_pub, condicion_fiscal, ofrece_envio):
    # 1. Comisiones
    porcentaje_comision = 0.15 if tipo_pub == "Clásica" else 0.25
    comision_meli = precio_venta * porcentaje_comision
    
    # 2. Costo Fijo Unitario
    costo_fijo = COSTO_FIJO_UNIDAD if precio_venta < UMBRAL_COSTO_FIJO else 0
    
    # 3. Costo de Envío
    costo_envio = 0
    if ofrece_envio or precio_venta >= UMBRAL_ENVIO_GRATIS:
        costo_envio = COSTO_ENVIO_PROMEDIO
        
    # 4. Impuestos (IIBB + IVA si corresponde)
    porcentaje_impuestos = 0.03 if condicion_fiscal == "Monotributo" else 0.135
    impuestos = precio_venta * porcentaje_impuestos
    
    # 5. Ecuación de Ganancia
    costo_total_venta = costo_producto + comision_meli + costo_fijo + costo_envio + impuestos
    ganancia_neta = precio_venta - costo_total_venta
    
    # 6. Márgenes
    margen_ventas = (ganancia_neta / precio_venta) * 100 if precio_venta > 0 else 0
    markup = (ganancia_neta / costo_producto) * 100 if costo_producto > 0 else 0
    
    # 7. Punto de Quiebre (Break-even)
    # Ecuación: Precio = Costo_Prod + Envío + Costo_Fijo + (Precio * %Comision) + (Precio * %Impuestos)
    denominador_quiebre = 1 - porcentaje_comision - porcentaje_impuestos
    punto_quiebre = (costo_producto + costo_envio + costo_fijo) / denominador_quiebre if denominador_quiebre > 0 else 0

    return {
        "comision_meli": comision_meli,
        "costo_fijo": costo_fijo,
        "costo_envio": costo_envio,
        "impuestos": impuestos,
        "ganancia_neta": ganancia_neta,
        "margen_ventas": margen_ventas,
        "markup": markup,
        "punto_quiebre": punto_quiebre
    }

# --- INTERFAZ WEB APP CON STREAMLIT ---
st.set_page_config(page_title="Calculadora Mercado Libre", layout="wide")
st.title("📦 Calculadora de Rentabilidad - Mercado Libre")

# Sección 1: Búsqueda y Producto
st.header("1. Identificación del Producto")
col1, col2 = st.columns(2)
with col1:
    producto_nombre = st.text_input("Ingresa el nombre del producto (ej: Bebedero Automático Perro):")
with col2:
    if producto_nombre:
        categoria_nombre, categoria_id = predecir_categoria(producto_nombre)
        st.info(f"**Categoría ML detectada:** {categoria_nombre}")

# Sección 2: Costos y Precios
st.header("2. Estructura de Costos")
col3, col4, col5 = st.columns(3)
with col3:
    costo_producto = st.number_input("Costo de compra del producto ($)", min_value=0.0, value=22730.0, step=100.0)
with col4:
    precio_venta = st.number_input("Precio de venta publicado ($)", min_value=0.0, value=45000.0, step=100.0)
with col5:
    condicion_fiscal = st.selectbox("Condición Fiscal", ["Monotributo", "Responsable Inscripto"])

# Sección 3: Publicación y Envíos
st.header("3. Parámetros de Publicación")
col6, col7 = st.columns(2)
with col6:
    tipo_pub = st.radio("Tipo de Publicación", ["Clásica", "Premium (Cuotas)"])
with col7:
    ofrece_envio = st.checkbox("Ofrecer Envío Gratis", value=(precio_venta >= UMBRAL_ENVIO_GRATIS))
    if precio_venta >= UMBRAL_ENVIO_GRATIS:
        st.warning("⚠️ Envío gratis obligatorio por superar los $33,000")

# Ejecutar Cálculos
if st.button("Calcular Rentabilidad", type="primary"):
    resultados = calcular_metricas(costo_producto, precio_venta, tipo_pub, condicion_fiscal, ofrece_envio)
    
    st.divider()
    st.header("📊 Resultados del Análisis")
    
    # Tarjetas de métricas principales
    m1, m2, m3 = st.columns(3)
    m1.metric("Ganancia Neta Limpia", f"${resultados['ganancia_neta']:,.2f}")
    m2.metric("Markup (Retorno sobre Costo)", f"{resultados['markup']:.1f}%")
    m3.metric("Margen sobre Venta", f"{resultados['margen_ventas']:.1f}%")
    
    # Desglose de Gastos y Riesgo
    col8, col9 = st.columns(2)
    with col8:
        st.subheader("Desglose de Descuentos")
        st.markdown(f"""
        * **Comisión ML ({tipo_pub}):** ${resultados['comision_meli']:,.2f}
        * **Costo Fijo Unitario:** ${resultados['costo_fijo']:,.2f}
        * **Costo de Envío:** ${resultados['costo_envio']:,.2f}
        * **Retenciones/Impuestos:** ${resultados['impuestos']:,.2f}
        * **Total Descontado por ML:** ${(resultados['comision_meli'] + resultados['costo_fijo'] + resultados['costo_envio'] + resultados['impuestos']):,.2f}
        """)
        
    with col9:
        st.subheader("Gestión de Riesgo")
        if resultados['ganancia_neta'] < 0:
            st.error("🚨 ESTÁS VENDIENDO A PÉRDIDA. Debes subir el precio o bajar el costo.")
        else:
            st.success("✅ Venta rentable.")
        
        st.info(f"**Punto de Quiebre:** ${resultados['punto_quiebre']:,.2f} \n\n *(Si publicas por debajo de este monto, perderás dinero)*")
