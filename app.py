import streamlit as st
import requests
import math
import pandas as pd
import urllib.parse
import re
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN DE PARÁMETROS MELI ACTUALIZADOS ---
UMBRAL_ENVIO_GRATIS = 33000
COSTO_ENVIO_PROMEDIO = 7790  # Base promedio MercadoLíder 0.5-1kg

# --- INICIALIZAR MEMORIA DEL PORTAFOLIO ---
if 'portafolio' not in st.session_state:
    st.session_state.portafolio = []

def limpiar_nombre_producto(texto):
    """Extrae el nombre limpio ya sea de texto plano o de un link complejo de ML"""
    if not texto: return ""
    
    if "mercadolibre.com" in texto or "http" in texto:
        try:
            parsed = urllib.parse.urlparse(texto)
            
            # 1er intento: Extraer del fragmento especial de búsqueda de ML (#D[A:TERMINO])
            if parsed.fragment and parsed.fragment.startswith("D[A:"):
                match = re.search(r'D\[A:(.*?)\]', parsed.fragment)
                if match:
                    busqueda = urllib.parse.unquote(match.group(1))
                    return busqueda.strip().title()
            
            # 2do intento: Extraer de los parámetros (?q=termino)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'q' in qs:
                busqueda = qs['q'][0]
                busqueda = urllib.parse.unquote(busqueda)
                return busqueda.strip().title()
            
            # 3er intento: Extraer de la URL principal (/funda-de-auto-para-perro)
            path = parsed.path.split('/')[-1]
            busqueda = re.sub(r'^MLA-\d+-', '', path) # Quita códigos como MLA-123-
            busqueda = busqueda.split('_')[0].replace('-', ' ') # Quita _NoIndex y guiones
            busqueda = urllib.parse.unquote(busqueda)
            
            return busqueda.strip().title()
        except:
            pass # Si todo falla, devuelve el texto plano limpio
            
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
    """Consulta la API pública de ML usando el término limpio"""
    if not busqueda_limpia:
        return None

    url = "https://api.mercadolibre.com/sites/MLA/search"
    try:
        response = requests.get(url, params={"q": busqueda_limpia, "limit": 15})
        if response.status_code == 200:
            resultados = response.json().get("results", [])
            if not resultados:
                return None
            
            mercado_lideres = 0
            envios_full = 0
            precios = []
            
            for item in resultados:
                precios.append(item.get("price", 0))
                # Revisar reputación
                seller = item.get("seller", {})
                reputacion = seller.get("seller_reputation", {}).get("power_seller_status")
                if reputacion in ["platinum", "gold", "silver"]:
                    mercado_lideres += 1
                
                # Revisar envíos full
                if item.get("shipping", {}).get("logistic_type") == "fulfillment":
                    envios_full += 1
                    
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
    """Calcula el cargo fijo exacto por unidad vendida según el tramo de precio"""
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

# --- CONFIGURACIÓN DE PÁGINA Y DISEÑO ---
st.set_page_config(page_title="Gestor de Portafolio ML", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600&family=Playfair+Display:ital,wght@0,600;0,700;1,600&display=swap');
    
    html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
    h1, h2, h3 { font-family: 'Playfair Display', serif !important; color: #1a202c !important; letter-spacing: -0.5px; }
    .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; }
    </style>
""", unsafe_allow_html=True)

# --- PANEL LATERAL ORGANIZADO ---
with st.sidebar:
    st.markdown("### ⚙️ 1. Producto y Precios")
    
    # --- AQUÍ ESTÁ LA CORRECCIÓN: CONECTAMOS EL TEXT_INPUT AL LIMPIADOR ---
    producto_input = st.text_input("Nombre o Link del Producto:", help="Pega el link completo de Mercado Libre o escribe el nombre a mano.")
    producto_nombre = limpiar_nombre_producto(producto_input)
    
    if producto_nombre:
        if "http" in producto_input:
            st.success(f"🔗 Link convertido a: **{producto_nombre}**")
        st.caption(f"📂 Categoría: {predecir_categoria(producto_nombre)}")
        
    colA, colB = st.columns(2)
    with colA:
        costo_input = st.number_input("Costo ($)", min_value=0.0, value=None, step=100.0, placeholder="Obligatorio")
    with colB:
        precio_input = st.number_input("Venta ($)", min_value=0.0, value=None, step=100.0, placeholder="Opcional")
    
    st.divider()
    st.markdown("### 🏷️ 2. Publicación e Impuestos")
    tipo_pub = st.selectbox("Modalidad de Publicación", ["Clásica (Sin cuotas)", "Premium (3 Cuotas)", "Premium (6 Cuotas)"])
    cond_fiscal = st.selectbox("Condición Fiscal (ARCA)", ["Monotributo", "Inscripto"], help="Monotributistas absorben el 21% de IVA de Meli como costo puro.")
    
    precio_ref = precio_input if precio_input is not None else 0
    envio = st.checkbox("Ofrecer Envío Gratis", value=(precio_ref >= UMBRAL_ENVIO_GRATIS))

    st.divider()
    st.markdown("### 🎯 3. Objetivos y Ads")
    meta_ganancia = st.number_input("Meta de Ganancia Mensual ($)", min_value=0, value=500000, step=50000)
    margen_obj = st.slider("Margen Deseado (%)", min_value=1, max_value=60, value=20)
    
    acos_input = st.slider("ACOS - Inversión Ads (%)", min_value=0, max_value=40, value=0)
    if acos_input == 0:
        st.info("⚪ **Sin Ads:** Ideal probar con 5-10% al inicio.")
    elif acos_input <= 15:
        st.success("🟢 **ACOS Sano:** Mantenlo debajo del 15%.")
    elif acos_input <= 25:
        st.warning("🟠 **ACOS Riesgoso:** Afecta tu margen.")
    else:
        st.error("🔴 **ACOS Crítico:** Ajusta la campaña urgente.")

# --- PANTALLA PRINCIPAL ---
st.title("Business Dashboard")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Análisis Individual", "🚀 Proyección y Envíos", "💼 Portafolio", "🛒 Compras y Presupuesto"])

if costo_input is None:
    with tab1:
        st.info("👈 Ingresa tu **Costo ($)** en el menú lateral para comenzar a analizar la rentabilidad.")
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

    com_base, fijo, env, iva_meli, imp_propios, costo_ads, tot_meli, gan, mar, mkp, quieb, roas = calcular_metricas(costo, precio, tipo_pub, cond_fiscal, envio, acos_input)
    unidades_mes = math.ceil(meta_ganancia / gan) if gan > 0 else 0
    unidades_dia = math.ceil(unidades_mes / 30) if unidades_mes > 0 else 0
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
            if gan > 0: st.success(f"**Ganancia**\n### ${gan:,.0f}")
            else: st.error(f"**Pérdida**\n### ${gan:,.0f}")
            st.caption("💵 Dinero neto al bolsillo.")
        with col2:
            if mar >= 15: st.success(f"**Margen**\n### {mar:.1f}%")
            elif mar >= 10: st.warning(f"**Margen**\n### {mar:.1f}%")
            else: st.error(f"**Margen**\n### {mar:.1f}%")
            st.caption("💡 **Sano:** > 15%")
        with col3:
            if mkp >= 30: st.info(f"**Markup**\n### {mkp:.1f}%")
            else: st.warning(f"**Markup**\n### {mkp:.1f}%")
            st.caption("💡 **Sano:** > 30% (ROI)")
        with col4:
            st.info(f"**Quiebre**\n### ${quieb:,.0f}")
            st.caption("⚖️ Precio para ganar $0.")
        with col5:
            if acos_input == 0: 
                st.info("**ROAS**\n### N/A")
                st.caption("⚪ Sin publicidad.")
            elif roas >= 6.6: 
                st.success(f"**ROAS**\n### {roas:.1f}x")
                st.caption("🟢 **Sano:** > 6.6x")
            else: 
                st.error(f"**ROAS**\n### {roas:.1f}x")
                st.caption("🔴 Riesgo de pérdida.")

        st.divider()
        st.subheader("¿A dónde va el dinero de tu venta actual?")
        c1, c2, c3 = st.columns(3)
        with c1: 
            st.info(f"**Tu Costo (Mercadería):**\n### ${costo:,.0f}")
        with c2:
            st.warning(f"**Se lo queda ML / ARCA / Ads:**\n### ${tot_meli:,.0f}")
            st.markdown(f"""
            <ul style="font-size: 0.9rem; color: #555; margin-top: -10px;">
                <li><b>Comisión ML:</b> ${com_base:,.0f}</li>
                <li><b>Cargo Fijo ML:</b> ${fijo:,.0f}</li>
                <li><b>Envío ML:</b> ${env:,.0f}</li>
                <li><b style='color:#d9534f;'>IVA ML (21% sobre cargos):</b> ${iva_meli:,.0f}</li>
                <li><b>IIBB Propios (ARCA):</b> ${imp_propios:,.0f}</li>
                <li><b>Mercado Ads:</b> ${costo_ads:,.0f}</li>
            </ul>
            """, unsafe_allow_html=True)
        with c3:
            if gan > 0: st.success(f"**Tu Ganancia (Bolsillo):**\n### ${gan:,.0f}")
            else: st.error(f"**Pérdida:**\n### ${gan:,.0f}")

        st.divider()
        st.subheader("🧠 Diagnóstico Financiero")
        _, _, _, _, _, _, _, gan_stress, mar_stress, _, _, _ = calcular_metricas(costo, precio, tipo_pub, cond_fiscal, envio, max(10, acos_input))
        diag1, diag2, diag3 = st.columns(3)
        with diag1:
            if mar >= 15: st.success("✅ **Margen Óptimo:**\n\nTienes colchón ante imprevistos.")
            elif mar >= 10: st.warning("⚠️ **Margen Justo:**\n\nPoco margen de error.")
            else: st.error("❌ **Margen Crítico:**\n\nMuy poca ganancia.")
        with diag2:
            if mkp >= 30: st.success("✅ **ROI Sano:**\n\nTu capital se multiplica bien.")
            else: st.warning("⚠️ **ROI Bajo:**\n\nInmovilizas mucho capital.")
        with diag3:
            if gan_stress > 0 and mar_stress >= 5: st.success("✅ **Resiliencia (Ads):**\n\nSoporta Ads al 10%.")
            else: st.error("❌ **Dependencia Orgánica:**\n\nSi enciendes Ads al 10%, pierdes dinero.")

        # --- TEST DE MERCADO API ---
        st.divider()
        st.subheader("🕵️‍♂️ Evaluación de Mercado (API Mercado Libre)")
        
        datos_api = analizar_competencia_api(producto_nombre)
        
        if datos_api:
            st.info(f"🔎 **Analizando la primera página de resultados para: '{datos_api['termino_buscado']}'**")
            api_c1, api_c2, api_c3 = st.columns(3)
            
            porcentaje_lideres = (datos_api['mercado_lideres'] / datos_api['total_analizados']) * 100
            porcentaje_full = (datos_api['envios_full'] / datos_api['total_analizados']) * 100
            
            with api_c1:
                st.metric("Precio Promedio Top 15", f"${datos_api['precio_promedio']:,.0f}")
                if precio > (datos_api['precio_promedio'] * 1.2):
                    st.error("Estás un 20% más caro que el promedio.")
                elif precio < (datos_api['precio_promedio'] * 0.8):
                    st.warning("Estás muy barato, podrías subir el precio.")
                else:
                    st.success("Tu precio está en el rango competitivo.")
                    
            with api_c2:
                st.metric("Vendedores MercadoLíder", f"{datos_api['mercado_lideres']} de {datos_api['total_analizados']}")
                if porcentaje_lideres > 70:
                    st.error("Nicho dominado por profesionales (Alta competencia).")
                else:
                    st.success("Baja profesionalización. Oportunidad de ganar con buenas fotos.")
                    
            with api_c3:
                st.metric("Envíos por Full", f"{datos_api['envios_full']} de {datos_api['total_analizados']}")
                if porcentaje_full > 60:
                    st.warning("Obligatorio enviar a Full para competir en este nicho.")
                else:
                    st.info("Pocos usan Full. Si tú lo usas, destacarás rápidamente.")
            
            st.write("")
            st.markdown("#### ¿Tienes un diferencial?")
            comp_dif = st.radio("Frente a esta competencia que ves, ¿Tu producto ofrece algo distinto?", 
                               ["Sí (Es un Combo/Kit, mejor calidad, diseño único)", "No (Es exactamente el mismo producto genérico)"])
            
            if "Sí" in comp_dif and porcentaje_lideres <= 70:
                st.success("🌟 **Veredicto: Oportunidad de Oro.** ¡Avanza! Tienes un diferencial y la competencia no es invencible.")
            elif "No" in comp_dif and porcentaje_lideres > 70:
                st.error("🚨 **Veredicto: Riesgo Elevado.** Estás vendiendo exactamente lo mismo en un nicho dominado por líderes. Te costará mucho posicionar.")
            else:
                st.warning("⚖️ **Veredicto: Mercado Moderado.** Hay espacio para competir, pero dependerá fuertemente de tu estrategia publicitaria (Ads) y calidad de publicación.")
        else:
            st.warning("Escribe un producto o pega un link válido en el panel de la izquierda para escanear a la competencia.")

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
                st.success(f"Para ganar **${meta_ganancia:,.0f}** limpios, necesitas vender **{unidades_mes} unidades al mes** (aprox. **{unidades_dia} unidades por día**).")
                st.info(f"**Capital necesario (Inversión inicial):** ${inversion_inicial:,.0f}\n\n**Facturación bruta esperada:** ${facturacion_mes:,.0f}")
                
                st.divider()
                if st.button("💾 Añadir producto al Portafolio", type="primary", use_container_width=True):
                    guardar_producto(producto_nombre, costo, precio, gan, mar, mkp, unidades_mes, inversion_inicial, facturacion_mes)
                    st.toast('¡Producto guardado exitosamente!', icon='✅')

            with col_p2:
                tamano_full = st.selectbox("Costo de Mercado Envíos Full (Mensual/Unidad)", ["Pequeño ($150)", "Mediano ($450)", "Grande ($1200)"])
                st.markdown("""
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #00a650;">
                    <h5 style="margin-top: 0; color: #333;">📏 Guía Oficial de Tamaños (Referencia Meli)</h5>
                    <ul style="font-size: 0.85rem; color: #555; margin-bottom: 0;">
                        <li><b>Pequeño:</b> Hasta 1.200 cm³ (Ej: 10x15x8 cm) o peso < 500g. <i>(Fundas, billeteras).</i></li>
                        <li><b>Mediano:</b> Hasta 30.000 cm³ (Ej: 30x30x33 cm) o peso < 5kg. <i>(Cajas de zapatillas).</i></li>
                        <li><b>Grande:</b> Más de 30.000 cm³. <i>(Microondas, sillas).</i></li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)

                costo_full_unitario = 150 if "Pequeño" in tamano_full else 450 if "Mediano" in tamano_full else 1200
                costo_full_total = unidades_mes * costo_full_unitario
                ganancia_post_full = meta_ganancia - costo_full_total
                
                st.warning(f"**Costo estimado de Bodega Full (Total Mensual):** ${costo_full_total:,.0f}")
                if ganancia_post_full > 0: st.success(f"**Ganancia Neta operando en Full:** ${ganancia_post_full:,.0f}")
                else: st.error(f"🚨 Pierdes ${abs(ganancia_post_full):,.0f}.")

    # ==========================================
    # PESTAÑA 3: PORTAFOLIO GLOBAL
    # ==========================================
    with tab3:
        st.markdown("### 💼 Consolidado de Inversiones")
        if len(st.session_state.portafolio) == 0:
            st.info("Tu portafolio está vacío.")
        else:
            df_portafolio = pd.DataFrame(st.session_state.portafolio)
            inversion_total = df_portafolio["Inversión Req."].sum()
            facturacion_total = df_portafolio["Facturación Est."].sum()
            ganancia_total = (df_portafolio["Ganancia Unit."] * df_portafolio["Unidades/Mes"]).sum()
            unidades_totales = df_portafolio["Unidades/Mes"].sum()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Capital a Invertir", f"${inversion_total:,.0f}")
            m2.metric("Facturación Proyectada", f"${facturacion_total:,.0f}")
            m3.metric("Ganancia Neta Global", f"${ganancia_total:,.0f}")
            m4.metric("Volumen (Unidades)", f"{unidades_totales}")

            st.divider()
            st.dataframe(df_portafolio, use_container_width=True, hide_index=True)
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                csv = df_portafolio.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Descargar (CSV)", data=csv, file_name='mi_portafolio.csv', mime='text/csv', use_container_width=True)
            with col_btn2:
                if st.button("☁️ Sincronizar Portafolio (Sheets)", use_container_width=True):
                    with st.spinner("Sincronizando..."):
                        try:
                            conn = st.connection("gsheets", type=GSheetsConnection)
                            conn.update(worksheet="Hoja 1", data=df_portafolio)
                            st.success("¡Éxito! Revisa tu Google Sheet.")
                        except Exception as e:
                            st.error("Configura los st.secrets primero.")

    # ==========================================
    # PESTAÑA 4: PRESUPUESTO Y ORDEN DE COMPRA
    # ==========================================
    with tab4:
        if len(st.session_state.portafolio) == 0:
            st.info("Agrega productos para armar tu presupuesto y orden de compra.")
        else:
            st.markdown("### 💰 Control de Presupuesto")
            df_portafolio = pd.DataFrame(st.session_state.portafolio)
            inversion_total = df_portafolio["Inversión Req."].sum()
            presupuesto = st.number_input("¿Capital total disponible? ($)", min_value=0.0, value=inversion_total, step=50000.0)
            balance = presupuesto - inversion_total
            
            if balance >= 0:
                st.success(f"✅ Te sobran **${balance:,.0f}**.")
                st.progress(min(inversion_total / presupuesto, 1.0))
            else:
                st.error(f"🚨 Te faltan **${abs(balance):,.0f}**.")
                st.progress(1.0)
                
            st.divider()
            st.markdown("### 🛒 Orden de Compra (Proveedores)")
            df_oc = df_portafolio[['Producto', 'Costo Unit.', 'Unidades/Mes', 'Inversión Req.']].copy()
            df_oc.columns = ['Producto', 'Costo Unitario ($)', 'Cantidad', 'Total a Pagar ($)']
            st.dataframe(df_oc, use_container_width=True, hide_index=True)
            csv_oc = df_oc.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descargar Orden de Compra", data=csv_oc, file_name='orden_compra.csv', mime='text/csv')
