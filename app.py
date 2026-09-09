import streamlit as st
import requests

# --- CONFIGURACIÓN DE PARÁMETROS MELI (2026) ---
UMBRAL_ENVIO_GRATIS = 33000
COSTO_FIJO_UNIDAD = 900
UMBRAL_COSTO_FIJO = 12000
COSTO_ENVIO_PROMEDIO = 4500

def predecir_categoria(titulo):
    url = "https://api.mercadolibre.com/sites/MLA/domain_discovery/search"
    try:
        response = requests.get(url, params={"q": titulo, "limit": 1})
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return data[0].get("domain_name", "Desconocida")
        return "No encontrada"
    except:
        return "Error API"

def calcular_precio_sugerido(costo, tipo, cond, envio_gratis, margen_deseado, acos_pct):
    porcentaje_comision = 0.15 if tipo == "Clásica" else 0.25
    porcentaje_impuestos = 0.03 if cond == "Monotributo" else 0.135
    margen_decimal = margen_deseado / 100.0
    porcentaje_ads = acos_pct / 100.0
    
    denominador = 1 - porcentaje_comision - porcentaje_impuestos - porcentaje_ads - margen_decimal
    
    if denominador <= 0:
        return 0  
        
    precio_sug = costo / denominador
    for _ in range(5):  
        fijo = COSTO_FIJO_UNIDAD if precio_sug < UMBRAL_COSTO_FIJO else 0
        envio = COSTO_ENVIO_PROMEDIO if (envio_gratis or precio_sug >= UMBRAL_ENVIO_GRATIS) else 0
        precio_sug = (costo + fijo + envio) / denominador
        
    return precio_sug

def calcular_metricas(costo, precio, tipo, cond, envio_gratis, acos_pct):
    porcentaje_comision = 0.15 if tipo == "Clásica" else 0.25
    porcentaje_impuestos = 0.03 if cond == "Monotributo" else 0.135
    porcentaje_ads = acos_pct / 100.0

    comision = precio * porcentaje_comision
    fijo = COSTO_FIJO_UNIDAD if precio < UMBRAL_COSTO_FIJO else 0
    envio = COSTO_ENVIO_PROMEDIO if (envio_gratis or precio >= UMBRAL_ENVIO_GRATIS) else 0
    impuestos = precio * porcentaje_impuestos
    costo_ads = precio * porcentaje_ads
    
    costos_meli = comision + fijo + envio + impuestos + costo_ads
    ganancia = precio - costo - costos_meli
    
    margen = (ganancia / precio) * 100 if precio > 0 else 0
    markup = (ganancia / costo) * 100 if costo > 0 else 0
    roas = (100 / acos_pct) if acos_pct > 0 else 0
    
    denominador = 1 - porcentaje_comision - porcentaje_impuestos - porcentaje_ads
    quiebre = (costo + envio + fijo) / denominador if denominador > 0 else 0

    return comision, fijo, envio, impuestos, costo_ads, costos_meli, ganancia, margen, markup, quiebre, roas

# --- CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(page_title="Calculadora ML", layout="wide", initial_sidebar_state="expanded")

# CSS para compactar el panel lateral y ajustar tipografías
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    h1 { font-size: 1.8rem !important; margin-bottom: 0; }
    h3 { font-size: 1.5rem !important; }
    /* Compactar panel lateral */
    [data-testid="stSidebar"] .stMarkdown { margin-bottom: -15px; }
    [data-testid="stSidebar"] .stSlider { margin-top: -15px; margin-bottom: -20px;}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.5rem; }
    </style>
""", unsafe_allow_html=True)

# --- PANEL LATERAL COMPACTO ---
with st.sidebar:
    st.markdown("### ⚙️ Ingreso de Datos")
    
    producto = st.text_input("Producto:")
    if producto:
        st.caption(f"🏷️ Categoría: {predecir_categoria(producto)}")
        
    # Costo y Precio en una sola fila
    colA, colB = st.columns(2)
    with colA:
        costo_input = st.number_input("Costo ($)", min_value=0.0, value=None, step=100.0, placeholder="Ej: 15000")
    with colB:
        precio_input = st.number_input("Venta ($)", min_value=0.0, value=None, step=100.0, placeholder="Ej: 45000")
    
    # Publicación e Impuestos en una fila
    colC, colD = st.columns(2)
    with colC:
        tipo_pub = st.selectbox("Publicación", ["Clásica", "Premium"])
    with colD:
        cond_fiscal = st.selectbox("Impuestos", ["Monotributo", "Inscripto"])
    
    precio_ref = precio_input if precio_input is not None else 0
    envio = st.checkbox("Ofrecer Envío Gratis", value=(precio_ref >= UMBRAL_ENVIO_GRATIS))

    st.divider()
    
    st.markdown("### 🎯 Objetivos y Ads")
    margen_obj = st.slider("Margen Deseado (%)", min_value=1, max_value=60, value=20)
    acos_input = st.slider("ACOS - Ads (%)", min_value=0, max_value=40, value=0)
    
    if acos_input == 0:
        st.info("💡 **Sin Ads:** Ideal probar con 5-10%.")
    elif acos_input <= 15:
        st.success("🟢 **ACOS Sano:** Mantenlo debajo de 15%.")
    elif acos_input <= 25:
        st.warning("🟠 **ACOS Riesgoso:** Baja tu inversión.")
    else:
        st.error("🔴 **ACOS Crítico:** Apaga o ajusta la campaña.")

# --- PANTALLA PRINCIPAL ---
st.title("📊 Panel de Decisión")

if costo_input is None:
    st.info("👈 Ingresa tu **Costo de Compra** en el panel izquierdo para calcular el Precio Sugerido.")
    st.stop()

costo = costo_input
precio_sugerido = calcular_precio_sugerido(costo, tipo_pub, cond_fiscal, envio, margen_obj, acos_input)

if precio_sugerido > 0:
    st.success(f"💡 **Precio Sugerido:** Para lograr un **{margen_obj}%** de ganancia invirtiendo {acos_input}% en Ads, publica a **${precio_sugerido:,.0f}**")
else:
    st.error(f"❌ Es matemáticamente imposible sacar un {margen_obj}% de margen.")

if precio_input is None:
    st.info("👈 Ahora ingresa **Tu Precio de Venta** en el panel izquierdo para ver el análisis de rentabilidad.")
    st.stop()

precio = precio_input

# Cálculos
com, fijo, env, imp, costo_ads, tot_meli, gan, mar, mkp, quieb, roas = calcular_metricas(costo, precio, tipo_pub, cond_fiscal, envio, acos_input)

# --- MÉTRICAS CLAVE (CAJAS VISUALES) ---
st.write("") # Espaciador
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    if gan > 0:
        st.success(f"**Ganancia**\n### ${gan:,.0f}")
    else:
        st.error(f"**Pérdida**\n### ${gan:,.0f}")

with col2:
    if mar >= 15:
        st.success(f"**Margen**\n### {mar:.1f}%")
    elif mar >= 10:
        st.warning(f"**Margen**\n### {mar:.1f}%")
    else:
        st.error(f"**Margen**\n### {mar:.1f}%")

with col3:
    st.info(f"**Markup**\n### {mkp:.1f}%")

with col4:
    st.info(f"**Quiebre (0%)**\n### ${quieb:,.0f}")

with col5:
    if acos_input == 0:
        st.info(f"**ROAS (Ads)**\n### N/A")
    elif roas >= 10:
        st.success(f"**ROAS (Ads)**\n### {roas:.1f}x")
    elif roas >= 6.6:
        st.warning(f"**ROAS (Ads)**\n### {roas:.1f}x")
    else:
        st.error(f"**ROAS (Ads)**\n### {roas:.1f}x")

st.divider()

# --- DESGLOSE DEL DINERO ---
st.subheader("¿A dónde va el dinero de tu venta actual?")
c1, c2, c3 = st.columns(3)

with c1:
    st.info(f"**Tu Costo (Mercadería):**\n### ${costo:,.0f}")
with c2:
    st.warning(f"**Se lo queda ML / AFIP / Ads:**\n### ${tot_meli:,.0f}")
    st.caption(f"Comisión: ${com:,.0f} | Envío: ${env:,.0f} | Fijo: ${fijo:,.0f} | Imp: ${imp:,.0f} | Ads: ${costo_ads:,.0f}")
with c3:
    if gan > 0:
        st.success(f"**Tu Ganancia (Bolsillo):**\n### ${gan:,.0f}")
    else:
        st.error(f"**Tu Ganancia (Bolsillo):**\n### ${gan:,.0f}")
