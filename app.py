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

# --- CONFIGURACIÓN DE PÁGINA (COMPACTA) ---
st.set_page_config(page_title="Calculadora ML", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    h1 { font-size: 1.8rem !important; }
    </style>
""", unsafe_allow_html=True)

# --- PANEL LATERAL (INPUTS) ---
with st.sidebar:
    st.header("⚙️ Ingreso de Datos")
    
    producto = st.text_input("Producto:")
    if producto:
        cat = predecir_categoria(producto)
        st.caption(f"🏷️ Categoría: {cat}")
    else:
        st.caption("🏷️ Categoría: Ingresa un producto")
        
    st.divider()
    costo = st.number_input("Costo de Compra ($)", min_value=0.0, value=22730.0, step=100.0)
    precio = st.number_input("Tu Precio de Venta ($)", min_value=0.0, value=45000.0, step=100.0)
    
    st.divider()
    st.subheader("🎯 Objetivos y Ads")
    margen_obj = st.slider("Margen Limpio Deseado (%)", min_value=1, max_value=60, value=20)
    
    acos_input = st.slider("ACOS - Mercado Ads (%)", min_value=0, max_value=40, value=0, help="Porcentaje del precio destinado a publicidad. Ej: 10% ACOS equivale a un ROAS de 10.")
    
    # --- INDICADOR DE ACOS SANO ---
    if acos_input == 0:
        st.caption("⚪ Sin inversión en Ads activa.")
    elif acos_input <= 10:
        st.caption("🟢 **ACOS Excelente:** Alta rentabilidad asegurada.")
    elif acos_input <= 15:
        st.caption("🟡 **ACOS Sano:** Promedio ideal del mercado.")
    elif acos_input <= 25:
        st.caption("🟠 **ACOS Alto:** Riesgoso, vigila tu margen de ganancia.")
    else:
        st.caption("🔴 **ACOS Crítico:** Probabilidad alta de vender a pérdida.")
    
    st.divider()
    tipo_pub = st.selectbox("Publicación", ["Clásica", "Premium"])
    cond_fiscal = st.selectbox("Impuestos", ["Monotributo", "Responsable Inscripto"])
    envio = st.checkbox("Ofrecer Envío Gratis", value=(precio >= UMBRAL_ENVIO_GRATIS))

# --- CÁLCULOS ---
com, fijo, env, imp, costo_ads, tot_meli, gan, mar, mkp, quieb, roas = calcular_metricas(costo, precio, tipo_pub, cond_fiscal, envio, acos_input)
precio_sugerido = calcular_precio_sugerido(costo, tipo_pub, cond_fiscal, envio, margen_obj, acos_input)

# --- DETERMINAR COLOR DEL ROAS ---
if acos_input == 0:
    roas_display = "N/A"
elif roas >= 10:
    roas_display = f"{roas:.1f}x 🟢"  # Excelente (ACOS <= 10%)
elif roas >= 6.6:
    roas_display = f"{roas:.1f}x 🟡"  # Sano (ACOS <= 15%)
elif roas >= 4:
    roas_display = f"{roas:.1f}x 🟠"  # Riesgoso (ACOS <= 25%)
else:
    roas_display = f"{roas:.1f}x 🔴"  # Crítico (ACOS > 25%)

# --- PANTALLA PRINCIPAL ---
st.title("📊 Panel de Decisión")

# 1. SEMÁFORO Y PRECIO SUGERIDO
if gan <= 0:
    st.error(f"🚨 NO RENTABLE: Estás perdiendo ${abs(gan):,.0f} por unidad.")
elif mar < 10:
    st.warning(f"⚠️ RENTABILIDAD BAJA: Margen muy ajustado ({mar:.1f}%).")
else:
    st.success(f"✅ PRODUCTO RENTABLE: Margen saludable ({mar:.1f}%).")

if precio_sugerido > 0:
    st.info(f"💡 **Precio Sugerido:** Para lograr un **{margen_obj}%** de ganancia limpia invirtiendo {acos_input}% en Ads, debes publicar a **${precio_sugerido:,.0f}**")
else:
    st.error(f"❌ Es matemáticamente imposible sacar un {margen_obj}% de margen con las retenciones y la inversión en Ads actual.")

# 2. MÉTRICAS CLAVE
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Ganancia Limpia", f"${gan:,.0f}")
col2.metric("Margen Actual", f"{mar:.1f}%")
col3.metric("Markup (Retorno)", f"{mkp:.1f}%")
col4.metric("Punto de Quiebre", f"${quieb:,.0f}")
col5.metric("ROAS (Ads)", roas_display)

st.divider()

# 3. DESGLOSE DEL DINERO
st.subheader("¿A dónde va el dinero de tu venta actual?")
c1, c2, c3 = st.columns(3)

with c1:
    st.info(f"**Tu Costo (Mercadería):**\n### ${costo:,.0f}")
with c2:
    st.warning(f"**Se lo queda ML / AFIP / Ads:**\n### ${tot_meli:,.0f}")
    st.caption(f"Comisión: ${com:,.0f} | Envío: ${env:,.0f} | Fijo: ${fijo:,.0f} | Impuestos: ${imp:,.0f} | Ads: ${costo_ads:,.0f}")
with c3:
    st.success(f"**Tu Ganancia (Bolsillo):**\n### ${gan:,.0f}")
