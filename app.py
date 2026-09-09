import streamlit as st
import requests
import math
import pandas as pd

# --- CONFIGURACIÓN DE PARÁMETROS MELI (2026) ---
UMBRAL_ENVIO_GRATIS = 33000
COSTO_FIJO_UNIDAD = 900
UMBRAL_COSTO_FIJO = 12000
COSTO_ENVIO_PROMEDIO = 4500

# --- INICIALIZAR MEMORIA DEL PORTAFOLIO ---
if 'portafolio' not in st.session_state:
    st.session_state.portafolio = []

def predecir_categoria(titulo):
    url = "https://api.mercadolibre.com/sites/MLA/domain_discovery/search"
    try:
        response = requests.get(url, params={"q": titulo, "limit": 1})
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                categoria = data[0].get("domain_name", "Desconocida")
                rubros_tecnologia = ["celulares", "computación", "notebooks", "televisores", "tablets", "consolas"]
                iva = "10.5%" if any(tech in categoria.lower() for tech in rubros_tecnologia) else "21%"
                return f"{categoria} (IVA {iva})"
        return "No encontrada"
    except:
        return "Error API"

def obtener_comision(tipo_pub):
    if tipo_pub == "Clásica (Sin cuotas)": return 0.15
    elif tipo_pub == "Premium (3 Cuotas)": return 0.20
    else: return 0.25

def calcular_precio_sugerido(costo, tipo, cond, envio_gratis, margen_deseado, acos_pct):
    porcentaje_comision = obtener_comision(tipo)
    porcentaje_impuestos = 0.03 if cond == "Monotributo" else 0.135
    margen_decimal = margen_deseado / 100.0
    porcentaje_ads = acos_pct / 100.0
    
    denominador = 1 - porcentaje_comision - porcentaje_impuestos - porcentaje_ads - margen_decimal
    if denominador <= 0: return 0  
        
    precio_sug = costo / denominador
    for _ in range(5):  
        fijo = COSTO_FIJO_UNIDAD if precio_sug < UMBRAL_COSTO_FIJO else 0
        envio = COSTO_ENVIO_PROMEDIO if (envio_gratis or precio_sug >= UMBRAL_ENVIO_GRATIS) else 0
        precio_sug = (costo + fijo + envio) / denominador
    return precio_sug

def calcular_metricas(costo, precio, tipo, cond, envio_gratis, acos_pct):
    porcentaje_comision = obtener_comision(tipo)
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

def guardar_producto(nombre, costo, precio, ganancia, margen, roi, unidades, inversion, facturacion):
    """Guarda el producto en la memoria temporal de la sesión"""
    st.session_state.portafolio.append({
        "Producto": nombre if nombre else "Sin Nombre",
        "Costo Unit.": costo,
        "Precio Venta": precio,
        "Ganancia Unit.": round(ganancia, 2),
        "Margen (%)": round(margen, 1),
        "ROI (%)": round(roi, 1),
        "Unidades/Mes": unidades,
        "Inversión Req.": inversion,
        "Facturación Est.": facturacion
    })

# --- CONFIGURACIÓN DE PÁGINA Y DISEÑO TIPOGRÁFICO ---
st.set_page_config(page_title="Calculadora ML", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600&family=Playfair+Display:ital,wght@0,600;0,700;1,600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Montserrat', sans-serif;
    }
    h1, h2, h3 {
        font-family: 'Playfair Display', serif !important;
        color: #1a202c !important;
        letter-spacing: -0.5px;
    }
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; }
    </style>
""", unsafe_allow_html=True)

# --- PANEL LATERAL ORGANIZADO ---
with st.sidebar:
    st.markdown("### ⚙️ Parámetros de Venta")
    
    producto_nombre = st.text_input("Nombre del Producto:")
    if producto_nombre:
        st.caption(f"🏷️ {predecir_categoria(producto_nombre)}")
        
    colA, colB = st.columns(2)
    with colA:
        costo_input = st.number_input("Costo ($)", min_value=0.0, value=None, step=100.0, placeholder="Obligatorio")
    with colB:
        precio_input = st.number_input("Venta ($)", min_value=0.0, value=None, step=100.0, placeholder="Opcional")
    
    tipo_pub = st.selectbox("Publicación y Cuotas", ["Clásica (Sin cuotas)", "Premium (3 Cuotas)", "Premium (6 Cuotas)"])
    cond_fiscal = st.selectbox("Impuestos", ["Monotributo", "Inscripto"])
    
    precio_ref = precio_input if precio_input is not None else 0
    envio = st.checkbox("Ofrecer Envío Gratis", value=(precio_ref >= UMBRAL_ENVIO_GRATIS))

    st.divider()
    
    st.markdown("### 🎯 Objetivos y Ads")
    meta_ganancia = st.number_input("Meta de Ganancia Mensual ($)", min_value=0, value=500000, step=50000, help="¿Cuánto dinero neto quieres ganar al mes con este producto?")
    margen_obj = st.slider("Margen Deseado (%)", min_value=1, max_value=60, value=20)
    acos_input = st.slider("ACOS - Ads (%)", min_value=0, max_value=40, value=0)

# --- PANTALLA PRINCIPAL CON TABS ---
st.title("Business Dashboard")

# Creación de 3 Pestañas
tab1, tab2, tab3 = st.tabs(["📊 Análisis Individual", "🚀 Proyección y Envíos Full", "💼 Mi Portafolio (Global)"])

# Validación para las primeras 2 pestañas
if costo_input is None:
    with tab1:
        st.info("👈 Ingresa tu **Costo ($)** en el menú lateral para comenzar a analizar la rentabilidad.")
    with tab3:
        pass # Permitir ver el portafolio aunque no haya costo ingresado
else:
    costo = costo_input
    precio_sugerido = calcular_precio_sugerido(costo, tipo_pub, cond_fiscal, envio, margen_obj, acos_input)

    if precio_input is None or precio_input == 0:
        if precio_sugerido > 0:
            precio = precio_sugerido
            modo_msj = f"🤖 **Modo Automático:** Analizando precio sugerido de **${precio:,.0f}**"
            modo_color = "success"
        else:
            st.error(f"❌ Imposible alcanzar {margen_obj}% de margen. Reduce tu expectativa.")
            st.stop()
    else:
        precio = precio_input
        modo_msj = f"⚙️ **Modo Manual:** Analizando precio de **${precio:,.0f}**"
        modo_color = "info"

    com, fijo, env, imp, costo_ads, tot_meli, gan, mar, mkp, quieb, roas = calcular_metricas(costo, precio, tipo_pub, cond_fiscal, envio, acos_input)
    unidades_mes = math.ceil(meta_ganancia / gan) if gan > 0 else 0
    inversion_inicial = unidades_mes * costo
    facturacion_mes = unidades_mes * precio

    # ==========================================
    # PESTAÑA 1: ANÁLISIS DE PRODUCTO
    # ==========================================
    with tab1:
        if modo_color == "success": st.success(modo_msj)
        else: st.info(modo_msj)

        st.write("") 
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.success(f"**Ganancia**\n### ${gan:,.0f}") if gan > 0 else st.error(f"**Pérdida**\n### ${gan:,.0f}")
        with col2:
            if mar >= 15: st.success(f"**Margen**\n### {mar:.1f}%")
            elif mar >= 10: st.warning(f"**Margen**\n### {mar:.1f}%")
            else: st.error(f"**Margen**\n### {mar:.1f}%")
        with col3:
            st.info(f"**Markup**\n### {mkp:.1f}%")
        with col4:
            st.info(f"**Quiebre**\n### ${quieb:,.0f}")
        with col5:
            st.info(f"**ROAS**\n### {roas:.1f}x" if acos_input > 0 else "**ROAS**\n### N/A")

        st.divider()
        st.subheader("¿A dónde va el dinero de tu venta actual?")
        c1, c2, c3 = st.columns(3)
        with c1: st.info(f"**Tu Costo (Mercadería):**\n### ${costo:,.0f}")
        with c2:
            st.warning(f"**Se lo queda ML / ARCA / Ads:**\n### ${tot_meli:,.0f}")
            st.caption(f"Comisión: ${com:,.0f} | Envío: ${env:,.0f} | Fijo: ${fijo:,.0f} | Imp: ${imp:,.0f} | Ads: ${costo_ads:,.0f}")
        with c3:
            st.success(f"**Tu Ganancia (Bolsillo):**\n### ${gan:,.0f}") if gan > 0 else st.error(f"**Pérdida:**\n### ${gan:,.0f}")

    # ==========================================
    # PESTAÑA 2: PROYECCIÓN Y ENVÍOS FULL
    # ==========================================
    with tab2:
        st.markdown("### Planificación Financiera y Stock")
        if gan <= 0:
            st.error("⚠️ El producto genera pérdida. No se puede proyectar volumen de ventas.")
        else:
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.success(f"Para ganar **${meta_ganancia:,.0f}** limpios, necesitas vender **{unidades_mes} unidades** al mes.")
                st.info(f"**Capital necesario (Inversión):** ${inversion_inicial:,.0f}\n\n**Facturación bruta esperada:** ${facturacion_mes:,.0f}")
                
                # --- BOTÓN PARA GUARDAR EN PORTAFOLIO ---
                st.divider()
                if st.button("💾 Añadir producto al Portafolio", type="primary", use_container_width=True):
                    guardar_producto(producto_nombre, costo, precio, gan, mar, mkp, unidades_mes, inversion_inicial, facturacion_mes)
                    st.toast('¡Producto guardado exitosamente en tu Portafolio!', icon='✅')

            with col_p2:
                tamano_full = st.selectbox("Costo de Mercado Envíos Full (Mensual/Unidad)", ["Pequeño ($150)", "Mediano ($450)", "Grande ($1200)"])
                costo_full_unitario = 150 if "Pequeño" in tamano_full else 450 if "Mediano" in tamano_full else 1200
                costo_full_total = unidades_mes * costo_full_unitario
                ganancia_post_full = meta_ganancia - costo_full_total
                
                st.warning(f"**Costo de bodega Full (Total Mensual):** ${costo_full_total:,.0f}")
                if ganancia_post_full > 0: st.success(f"**Ganancia Neta operando en Full:** ${ganancia_post_full:,.0f}")
                else: st.error(f"🚨 Operar en Full consumirá tu ganancia. Pierdes ${abs(ganancia_post_full):,.0f}.")

# ==========================================
# PESTAÑA 3: PORTAFOLIO GLOBAL
# ==========================================
with tab3:
    st.markdown("### 💼 Consolidado de Inversiones")
    
    if len(st.session_state.portafolio) == 0:
        st.info("Tu portafolio está vacío. Ve a la pestaña 'Proyección y Envíos Full' y guarda algunos productos para ver el análisis global.")
    else:
        # Convertir datos a Pandas DataFrame
        df_portafolio = pd.DataFrame(st.session_state.portafolio)
        
        # Calcular Totales Globales
        inversion_total = df_portafolio["Inversión Req."].sum()
        facturacion_total = df_portafolio["Facturación Est."].sum()
        ganancia_total = (df_portafolio["Ganancia Unit."] * df_portafolio["Unidades/Mes"]).sum()
        unidades_totales = df_portafolio["Unidades/Mes"].sum()

        # Métricas Globales
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Capital Total a Invertir", f"${inversion_total:,.0f}")
        m2.metric("Facturación Proyectada", f"${facturacion_total:,.0f}")
        m3.metric("Ganancia Neta Global", f"${ganancia_total:,.0f}")
        m4.metric("Volumen Físico (Unidades)", f"{unidades_totales}")

        st.divider()
        st.markdown("#### Detalle de Productos Activos")
        # Mostrar tabla interactiva (el usuario puede ordenar por ROI, Ganancia, etc.)
        st.dataframe(df_portafolio, use_container_width=True, hide_index=True)
        
        # Botones de Exportación
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            # Opción 1: Descargar CSV (Funciona inmediatamente sin configuraciones)
            csv = df_portafolio.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar Portafolio (Excel/CSV)",
                data=csv,
                file_name='mi_portafolio_meli.csv',
                mime='text/csv',
                use_container_width=True
            )
        with col_btn2:
            # Opción 2: Placeholder para Google Sheets
            if st.button("☁️ Sincronizar con Google Sheets", use_container_width=True):
                st.warning("⚠️ Para activar la conexión con Google Sheets, debes configurar tus credenciales en `st.secrets`. Lee las instrucciones debajo.")

        st.expander("¿Cómo conectar esta tabla a mi Google Sheets real?").markdown("""
        **Para guardar estos datos automáticamente en la nube, requieres 3 pasos:**
        1. Crear un archivo en Google Sheets y compartirlo con el correo de un **Service Account** de Google Cloud.
        2. Instalar la librería de conexión en tu `requirements.txt`: `st-gsheets-connection`
        3. Copiar las claves JSON que te da Google y pegarlas en la sección **Settings > Secrets** de tu app en Streamlit Cloud.
        
        *Debido a la sensibilidad de las claves bancarias y de cuenta, Streamlit bloquea estas conexiones si no se configuran desde el panel de control privado de tu repositorio.*
        """)
