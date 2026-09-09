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

def calcular_metricas(costo, precio, tipo, cond, envio_gratis):
    porcentaje_comision = 0.15 if tipo == "Clásica" else 0.25
    comision = precio * porcentaje_comision
    fijo = COSTO_FIJO_UNIDAD if precio < UMBRAL_COSTO_FIJO else 0
    envio = COSTO_ENVIO_PROMEDIO if (envio_gratis or precio >= UMBRAL_ENVIO_GRATIS) else 0
    impuestos = precio * (0.03 if cond == "Monotributo" else 0.135)
    
    costos_meli = comision + fijo + envio + impuestos
    ganancia = precio - costo - costos_meli
    
    margen = (ganancia / precio) * 100 if precio > 0 else 0
    markup = (ganancia / costo) * 100 if costo > 0 else 0
    
    denominador = 1 - porcentaje_comision - (0.03 if cond == "Monotributo" else 0.135)
    quiebre = (costo + envio + fijo) / denominador if denominador > 0 else 0

    return comision, fijo, envio, impuestos, costos_meli, ganancia, margen, markup, quiebre

# --- CONFIGURACIÓN DE PÁGINA (COMPACTA) ---
st.set_page_config(page_title="Calculadora ML", layout="wide", initial_sidebar_state="expanded")

# --- CSS PARA HACERLA MÁS COMPACTA ---
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
    costo = st.number_input("Costo de Compra ($)", min_value=0, value=22730, step=100)
    precio = st.number_input("Precio de Venta ($)", min_value=0, value=45000, step=100)
    
    st.divider()
    tipo_pub = st.selectbox("Publicación", ["Clásica", "Premium"])
    cond_fiscal = st.selectbox("Impuestos", ["Monotributo", "Responsable Inscripto"])
    envio = st.checkbox("Ofrecer Envío Gratis", value=(precio >= UMBRAL_ENVIO_GRATIS))
    if precio >= UMBRAL_ENVIO_GRATIS:
        st.caption("⚠️ Envío gratis obligatorio (>$33.000)")

# --- CÁLCULO EN TIEMPO REAL ---
com, fijo, env, imp, tot_meli, gan, mar, mkp, quieb = calcular_metricas(costo, precio, tipo_pub, cond_fiscal, envio)

# --- PANTALLA PRINCIPAL (DASHBOARD) ---
st.title("📊 Panel de Decisión")

# 1. SEMÁFORO DE DECISIÓN
if gan <= 0:
    st.error(f"🚨 NO RENTABLE: Estás perdiendo ${abs(gan):,.0f} por unidad. ¡Sube el precio o no lo vendas!")
elif mar < 15:
    st.warning(f"⚠️ RENTABILIDAD BAJA: Margen muy ajustado ({mar:.1f}%). Riesgo alto si cambian los costos.")
else:
    st.success(f"✅ PRODUCTO RENTABLE: Margen saludable ({mar:.1f}%). ¡Avanzar con la compra/publicación!")

# 2. MÉTRICAS CLAVE (Una sola fila)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Ganancia Limpia", f"${gan:,.0f}")
col2.metric("Margen de Venta", f"{mar:.1f}%")
col3.metric("Markup (Retorno)", f"{mkp:.1f}%")
col4.metric("Punto de Quiebre (Cero)", f"${quieb:,.0f}", help="Precio mínimo para no perder plata")

st.divider()

# 3. DESGLOSE DEL DINERO (Visualmente claro)
st.subheader("¿A dónde va el dinero de la venta?")
c1, c2, c3 = st.columns(3)

with c1:
    st.info(f"**Tu Costo (Mercadería):**\n### ${costo:,.0f}")
with c2:
    st.warning(f"**Se lo queda Mercado Libre:**\n### ${tot_meli:,.0f}")
    st.caption(f"Comisión: ${com:,.0f} | Envío: ${env:,.0f} | Fijo: ${fijo:,.0f} | Imp: ${imp:,.0f}")
with c3:
    st.success(f"**Tu Ganancia (Bolsillo):**\n### ${gan:,.0f}")
