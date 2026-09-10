import streamlit as st
import requests
import math
import pandas as pd
import urllib.parse
import re
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN DE PARÁMETROS MELI ACTUALIZADOS ---
UMBRAL_ENVIO_GRATIS = 33000
COSTO_ENVIO_PROMEDIO = 7790  

# --- INICIALIZAR MEMORIA DEL PORTAFOLIO ---
if 'portafolio' not in st.session_state:
    st.session_state.portafolio = []

def limpiar_nombre_producto(texto):
    if not texto: return ""
    texto = texto.strip()
    
    if "mercadolibre.com" in texto or "http" in texto:
        try:
            parsed = urllib.parse.urlparse(texto)
            if parsed.fragment and "D[A:" in parsed.fragment:
                match = re.search(r'D\[A:(.*?)\]', parsed.fragment)
                if match:
                    busqueda = urllib.parse.unquote(match.group(1))
                    return busqueda.strip().title()
            
            qs = urllib.parse.parse_qs(parsed.query)
            if 'q' in qs:
                busqueda = urllib.parse.unquote(qs['q'][0])
                return busqueda.strip().title()
            
            path_parts = [p for p in parsed.path.split('/') if p]
            if path_parts:
                busqueda = path_parts[1] if path_parts[0] == 'listado' and len(path_parts) > 1 else path_parts[0]
                busqueda = re.sub(r'^MLA-?\d+-?', '', busqueda, flags=re.IGNORECASE)
                busqueda = busqueda.split('_')[0].replace('-', ' ')
                busqueda = urllib.parse.unquote(busqueda)
                if len(busqueda.strip()) > 2:
                    return busqueda.strip().title()
        except:
            pass 
    return texto.strip().title()

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

def analizar_competencia_api(busqueda_limpia):
    if not busqueda_limpia: return None
    url = "https://api.mercadolibre.com/sites/MLA/search"
    try:
        response = requests.get(url, params={"q": busqueda_limpia, "limit": 15})
        if response.status_code == 200:
            resultados = response.json().get("results", [])
            
            if not resultados:
                palabras = busqueda_limpia.split()
                if len(palabras) > 3:
                    busqueda_corta = " ".join(palabras[:3]) 
                    response = requests.get(url, params={"q": busqueda_corta, "limit": 15})
                    if response.status_code == 200:
                        resultados = response.json().get("results", [])
                        busqueda_limpia = busqueda_corta 
                        
            if not resultados:
                return "SIN_RESULTADOS"
            
            mercado_lideres = 0
            envios_full = 0
            precios = []
            
            for item in resultados:
                precios.append(item.get("price", 0))
                seller = item.get("seller", {})
                reputacion = seller.get("seller_reputation", {}).get("power_seller_status")
                if reputacion in ["platinum", "gold", "silver"]: mercado_lideres += 1
                if item.get("shipping", {}).get("logistic_type") == "fulfillment": envios_full += 1
                    
            precio_promedio = sum(precios) / len(precios) if precios else 0
            return {
                "termino_buscado": busqueda_limpia,
                "total_analizados": len(resultados),
                "mercado_lideres": mercado_lideres,
                "envios_full": envios_full,
                "precio_promedio": precio_promedio
            }
    except Exception:
        return None

def obtener_comision(tipo_pub):
    if tipo_pub == "Clásica (Sin cuotas)": return 0.15
    elif tipo_pub == "Premium (3 Cuotas)": return 0.20
    else: return 0.25

def obtener_cargo_fijo(precio):
    if precio >= UMBRAL_ENVIO_GRATIS: return 0
    elif precio >= 24000: return 3320
    elif precio >= 15000: return 2740
    else: return 1330

def calcular_precio_sugerido(costo, tipo, cond, envio_gratis, margen_deseado, acos_pct):
    porcentaje_comision = obtener_comision(tipo)
    porcentaje_impuestos = 0.03 if cond == "Monotributo" else 0.0  
    margen_decimal = margen_deseado / 100.0
    porcentaje_ads = acos_pct / 100.0
    factor_iva_meli = 1.21 if cond == "Monotributo" else 1.0 
    
    denominador = 1 - (porcentaje_comision * factor_iva_meli) - porcentaje_impuestos - porcentaje_ads - margen_decimal
    if denominador <= 0: return 0  
        
    precio_sug = costo / denominador
    for _ in range(5):  
        fijo = obtener_cargo_fijo(precio_sug)
        envio = COSTO_ENVIO_PROMEDIO if (envio_gratis or precio_sug >= UMBRAL_ENVIO_GRATIS) else 0
        precio_sug = (costo + envio + (fijo * factor_iva_meli)) / denominador
    return precio_sug

def calcular_metricas(costo, precio, tipo, cond, envio_gratis, acos_pct):
    porcentaje_comision = obtener_comision(tipo)
    comision_base = precio * porcentaje_comision
    fijo = obtener_cargo_fijo(precio)
    envio = COSTO_ENVIO_PROMEDIO if (envio_gratis or precio >= UMBRAL_ENVIO_GRATIS) else 0
    iva_meli = (comision_base + fijo) * 0.21 if cond == "Monotributo" else 0 
    costo_ads = precio * (acos_pct / 100.0)
    impuestos_propios = precio * 0.03 if cond == "Monotributo" else 0
    
    costos_meli = comision_base + fijo + envio + iva_meli + costo_ads
    ganancia = precio - comision_base - fijo - envio - iva_meli - impuestos_propios - costo - costo_ads
    margen = (ganancia / precio) * 100 if precio > 0 else 0
    markup = (ganancia / costo) * 100 if costo > 0 else 0
    roas = (100 / acos_pct) if acos_pct > 0 else 0
    
    factor_iva_meli = 1.21 if cond == "Monotributo" else 1.0
    denominador = 1 - (porcentaje_comision * factor_iva_meli) - (0.03 if cond == "Monotributo" else 0) - (acos_pct / 100.0)
    quiebre = (costo + envio + (fijo * factor_iva_meli)) / denominador if denominador > 0 else 0

    return comision_base, fijo, envio, iva_meli, impuestos_propios, costo_ads, costos_meli, ganancia, margen, markup, quiebre, roas

def guardar_producto(nombre, costo, precio, ganancia, margen, roi, unidades, inversion, facturacion):
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

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor de Portafolio ML", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600&family=Playfair+Display:ital,wght@0,600;0,700;1,600&display=swap');
    html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
    h1, h2, h3 { font-family: 'Playfair Display', serif !important; color: #1a202c !important; letter-spacing: -0.5px; }
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; }
    </style>
""", unsafe_allow_html=True)

# --- PANEL LATERAL ---
with st.sidebar:
    st.markdown("### ⚙️ 1. Producto y Precios")
    
    producto_input = st.text_input("Nombre o Link del Producto:", help="Pega el link de ML o escribe el nombre.")
    producto_nombre = limpiar_nombre_producto(producto_input)
    
    if producto_nombre:
        if "http" in producto_input:
            st.success(f"🔗 Link convertido a: **{producto_nombre}**")
        st.caption(f"📂 Categoría: {predecir_categoria(producto_nombre)}")
        
    colA, colB = st.columns(2)
    with colA: costo_input = st.number_input("Costo ($)", min_value=0.0, value=None, step=100.0)
    with colB: precio_input = st.number_input("Venta ($)", min_value=0.0, value=None, step=100.0)
    
    st.divider()
    st.markdown("### 🏷️ 2. Publicación e Impuestos")
    tipo_pub = st.selectbox("Modalidad de Publicación", ["Clásica (Sin cuotas)", "Premium (3 Cuotas)", "Premium (6 Cuotas)"])
    cond_fiscal = st.selectbox("Condición Fiscal (ARCA)", ["Monotributo", "Inscripto"])
    precio_ref = precio_input if precio_input is not None else 0
    envio = st.checkbox("Ofrecer Envío Gratis", value=(precio_ref >= UMBRAL_ENVIO_GRATIS))

    st.divider()
    st.markdown("### 🎯 3. Objetivos y Ads")
    meta_ganancia = st.number_input("Meta Mensual ($)", min_value=0, value=500000, step=50000)
    margen_obj = st.slider("Margen Deseado (%)", min_value=1, max_value=60, value=20)
    acos_input = st.slider("ACOS - Ads (%)", min_value=0, max_value=40, value=0)

st.title("Business Dashboard")
tab1, tab2, tab3, tab4 = st.tabs(["📊 Análisis Individual", "🚀 Proyección y Envíos", "💼 Portafolio", "🛒 Compras"])

if costo_input is None:
    with tab1: st.info("👈 Ingresa tu **Costo ($)** en el menú lateral para analizar la rentabilidad.")
else:
    costo = costo_input
    precio_sugerido = calcular_precio_sugerido(costo, tipo_pub, cond_fiscal, envio, margen_obj, acos_input)
    if precio_input is None or precio_input == 0:
        if precio_sugerido > 0:
            precio = precio_sugerido
            modo_color, modo_msj = "success", f"🤖 **Modo Automático:** Analizando precio sugerido de **${precio:,.0f}**"
        else:
            st.error(f"❌ Imposible alcanzar {margen_obj}% de margen.")
            st.stop()
    else:
        precio = precio_input
        modo_color, modo_msj = "info", f"⚙️ **Modo Manual:** Analizando precio de **${precio:,.0f}**"

    com_base, fijo, env, iva_meli, imp_propios, costo_ads, tot_meli, gan, mar, mkp, quieb, roas = calcular_metricas(costo, precio, tipo_pub, cond_fiscal, envio, acos_input)
    unidades_mes = math.ceil(meta_ganancia / gan) if gan > 0 else 0
    inversion_inicial, facturacion_mes = unidades_mes * costo, unidades_mes * precio

    # ================= PESTAÑA 1 =================
    with tab1:
        if modo_color == "success": st.success(modo_msj)
        else: st.info(modo_msj)

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            if gan > 0: st.success(f"**Ganancia**\n### ${gan:,.0f}")
            else: st.error(f"**Pérdida**\n### ${gan:,.0f}")
        with col2:
            if mar >= 15: st.success(f"**Margen**\n### {mar:.1f}%")
            elif mar >= 10: st.warning(f"**Margen**\n### {mar:.1f}%")
            else: st.error(f"**Margen**\n### {mar:.1f}%")
        with col3:
            if mkp >= 30: st.info(f"**Markup**\n### {mkp:.1f}%")
            else: st.warning(f"**Markup**\n### {mkp:.1f}%")
        with col4: st.info(f"**Quiebre**\n### ${quieb:,.0f}")
        with col5:
            if acos_input == 0: st.info("**ROAS**\n### N/A")
            elif roas >= 6.6: st.success(f"**ROAS**\n### {roas:.1f}x")
            else: st.error(f"**ROAS**\n### {roas:.1f}x")

        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1: st.info(f"**Tu Costo (Mercadería):**\n### ${costo:,.0f}")
        with c2:
            st.warning(f"**Se lo queda ML / ARCA / Ads:**\n### ${tot_meli:,.0f}")
            st.markdown(f"""<ul style="font-size: 0.9rem; color: #555; margin-top: -10px;">
                <li><b>Comisión ML:</b> ${com_base:,.0f}</li><li><b>Cargo Fijo ML:</b> ${fijo:,.0f}</li>
                <li><b>Envío ML:</b> ${env:,.0f}</li><li><b style='color:#d9534f;'>IVA ML (21%):</b> ${iva_meli:,.0f}</li>
                <li><b>IIBB Propios (ARCA):</b> ${imp_propios:,.0f}</li><li><b>Mercado Ads:</b> ${costo_ads:,.0f}</li></ul>""", unsafe_allow_html=True)
        with c3:
            if gan > 0: st.success(f"**Tu Ganancia (Bolsillo):**\n### ${gan:,.0f}")
            else: st.error(f"**Pérdida:**\n### ${gan:,.0f}")

        # --- EVALUACIÓN DE MERCADO ---
        st.divider()
        st.subheader("🕵️‍♂️ Evaluación de Mercado (API Mercado Libre)")
        
        datos_api = analizar_competencia_api(producto_nombre)
        
        if datos_api == "SIN_RESULTADOS":
            st.error("🚨 **Cero Resultados:** El título extraído tiene información demasiado específica. Ve al menú izquierdo y acorta el texto manualmente (Ej: deja solo 'Rascador Adhesivo Gatos').")
        elif datos_api:
            st.info(f"🔎 Analizando competidores reales bajo el término: **'{datos_api['termino_buscado']}'**")
            api_c1, api_c2, api_c3 = st.columns(3)
            pct_lid = (datos_api['mercado_lideres'] / datos_api['total_analizados']) * 100
            pct_full = (datos_api['envios_full'] / datos_api['total_analizados']) * 100
            prom = datos_api['precio_promedio']
            
            with api_c1: st.metric("Precio Promedio Top 15", f"${prom:,.0f}")
            with api_c2: st.metric("MercadoLíderes", f"{pct_lid:.0f}%")
            with api_c3: st.metric("Envíos por Full", f"{pct_full:.0f}%")
            
            st.write("")
            comp_dif = st.radio("¿Tu producto ofrece un diferencial frente a ellos?", ["Sí (Es un Combo/Kit, mejor calidad)", "No (Es el mismo producto genérico)"])
            
            st.divider()
            
            # --- NUEVO REPORTE DEL ANALISTA EXPERTO ---
            st.subheader("🤖 Reporte del Analista Experto")
            
            es_estrella = (mar >= 15) and (mkp >= 30) and ("Sí" in comp_dif)
            es_riesgoso = (mar < 15) and ("No" in comp_dif or pct_lid > 50)
            
            if es_estrella:
                st.success(f"🌟 **EL PRODUCTO ESTRELLA: {producto_nombre.upper()}**\n\nEste es un ejemplo de manual de un producto con alta viabilidad por estas tres razones:")
                st.markdown("**🛡️ Escudo contra la guerra de precios:** Al indicar que armaste un Kit/Combo o que ofreces una calidad superior, creaste un diferencial claro. El cliente ya no puede comparar tu precio directamente con el del competidor de al lado. Esto anula la sobresaturación y te saca de la pelea por centavos.")
                st.markdown(f"**📈 Salud Financiera Robusta:** Con tu costo de ${costo:,.0f} y venta a ${precio:,.0f}, sacas un Margen del {mar:.1f}% y un ROI del {mkp:.1f}%. Son números brillantes. Tienes tanto margen que podrías encender campañas de Mercado Ads al 10% o 15% para impulsar la salida de las unidades, y seguirías ganando dinero limpio.")
                st.markdown("**📦 Ventaja Logística:** Recuerda mantener el paquete lo más pequeño y liviano posible para pagar la tarifa mínima de almacenamiento en Mercado Envíos Full y evitar que los costos logísticos ocultos se coman esta excelente ganancia.")
            
            elif es_riesgoso:
                st.error(f"🚨 **EL PRODUCTO DE RIESGO: {producto_nombre.upper()}**\n\nRepresenta un escenario peligroso si lo vendes así como viene, sin estrategias adicionales:")
                st.markdown(f"**⚔️ Alta saturación y competencia:** Estos son artículos genéricos de importación masiva. La primera página de Mercado Libre está minada con un {pct_lid:.0f}% de MercadoLíderes peleando por el precio más bajo. Entrar a vender el mismo producto exacto te obligará a sacrificar tu margen (actualmente en un nivel riesgoso del {mar:.1f}%) solo para lograr tus primeras ventas.")
                if pct_full >= 40:
                    st.markdown(f"**🏢 Costos de Bodega Obligatorios:** El {pct_full:.0f}% de tus competidores usa Envíos Full. Estarás obligado a usarlo para no desaparecer en las búsquedas. Si el producto resulta pesado o mal empacado, caerá en categoría 'Mediano/Grande', triplicando tu costo de almacenamiento oculto.")
                st.markdown("**💡 Cómo salvarlo:** Si vendes el producto solo, es de alto riesgo financiero. Para transformarlo en un buen negocio, debes aplicar la estrategia de diferenciación. Súmale un accesorio de bajo costo relacionado, arma un combo cerrado, y así dejas de competir por centavos, justificando un precio más alto para sanear tu rentabilidad.")

            else:
                st.warning(f"⚖️ **MERCADO EN DISPUTA: {producto_nombre.upper()}**\n\nEs un producto con viabilidad media. No es una mina de oro automática, pero tampoco es un desastre total. Requerirá gestión profesional:")
                if precio < (prom * 0.8):
                    st.markdown(f"- 📉 **Guerra de precios:** Estás vendiendo muy barato respecto al promedio del mercado (${prom:,.0f}). Si tu margen del {mar:.1f}% lo soporta, ganarás ventas por precio, pero cuidado con desangrar tu capital ante imprevistos.")
                elif precio > (prom * 1.2):
                    st.markdown(f"- 💎 **Precio Premium:** Tu precio es alto respecto al promedio (${prom:,.0f}). El mercado exige que justifiques esto con una calidad visiblemente superior, fotos de estudio o excelente atención.")
                else:
                    st.markdown("- 🎯 **Precio Competitivo:** Estás alineado con lo que el mercado está dispuesto a pagar hoy.")
                
                if pct_lid > 50:
                    st.markdown(f"- 🦈 **Competencia Fuerte:** El {pct_lid:.0f}% del nicho lo dominan profesionales. Posicionar orgánicamente será lento. Destina presupuesto a Mercado Ads.")
                else:
                    st.markdown("- 🟢 **Oportunidad de Nicho:** Hay baja profesionalización en tu competencia. Mejora las descripciones y fotos de los líderes actuales, y ganarás posiciones fácilmente.")
        else:
            st.warning("Escribe un producto en el menú izquierdo para escanear a la competencia.")

    # ================= PESTAÑA 2, 3, 4 (Resto intacto) =================
    with tab2:
        st.markdown("### Planificación Financiera y Stock")
        if gan > 0:
            c1, c2 = st.columns(2)
            with c1:
                st.success(f"Vende **{unidades_mes} unidades/mes** para ganar **${meta_ganancia:,.0f}** limpios.")
                st.info(f"**Inversión:** ${inversion_inicial:,.0f} | **Facturación:** ${facturacion_mes:,.0f}")
                if st.button("💾 Añadir producto", type="primary", use_container_width=True):
                    guardar_producto(producto_nombre, costo, precio, gan, mar, mkp, unidades_mes, inversion_inicial, facturacion_mes)
                    st.toast('Guardado!', icon='✅')
            with c2:
                tf = st.selectbox("Tamaño (Costo Bodega/Mes)", ["Pequeño ($150)", "Mediano ($450)", "Grande ($1200)"])
                c_full = unidades_mes * (150 if "Pequeño" in tf else 450 if "Mediano" in tf else 1200)
                g_full = meta_ganancia - c_full
                st.warning(f"**Costo Bodega Full (Total Mes):** ${c_full:,.0f}")
                if g_full > 0: st.success(f"**Ganancia Neta en Full:** ${g_full:,.0f}")
                else: st.error(f"🚨 Full consume tu ganancia. Pierdes ${abs(g_full):,.0f}.")

    with tab3:
        if len(st.session_state.portafolio) == 0: st.info("Tu portafolio está vacío.")
        else:
            df = pd.DataFrame(st.session_state.portafolio)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Capital a Invertir", f"${df['Inversión Req.'].sum():,.0f}")
            m2.metric("Facturación Proy.", f"${df['Facturación Est.'].sum():,.0f}")
            m3.metric("Ganancia Global", f"${(df['Ganancia Unit.'] * df['Unidades/Mes']).sum():,.0f}")
            m4.metric("Volumen (Unid.)", f"{df['Unidades/Mes'].sum()}")
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab4:
        if len(st.session_state.portafolio) == 0: st.info("Agrega productos.")
        else:
            df = pd.DataFrame(st.session_state.portafolio)
            inv = df['Inversión Req.'].sum()
            pres = st.number_input("Capital disponible ($)", value=inv, step=50000.0)
            bal = pres - inv
            if bal >= 0: st.success(f"✅ Te sobran **${bal:,.0f}**."); st.progress(min(inv/pres, 1.0))
            else: st.error(f"🚨 Te faltan **${abs(bal):,.0f}**."); st.progress(1.0)
            st.divider()
            df_oc = df[['Producto', 'Costo Unit.', 'Unidades/Mes', 'Inversión Req.']].copy()
            df_oc.columns = ['Producto', 'Costo Unitario ($)', 'Cantidad', 'Total a Pagar ($)']
            st.dataframe(df_oc, use_container_width=True, hide_index=True)
            st.download_button("📥 Orden de Compra", data=df_oc.to_csv(index=False).encode('utf-8'), file_name='orden.csv', mime='text/csv')
