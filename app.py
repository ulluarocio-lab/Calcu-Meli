import streamlit as st
import requests
import math
import pandas as pd
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURACIÓN DE PARÁMETROS MELI ACTUALIZADOS ---
UMBRAL_ENVIO_GRATIS = 33000
COSTO_ENVIO_PROMEDIO = 7790  # Base promedio MercadoLíder 0.5-1kg

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
    
    producto_nombre = st.text_input("Nombre del Producto:")
    if producto_nombre:
        st.caption(f"🏷️ {predecir_categoria(producto_nombre)}")
        
    colA, colB = st.columns(2)
    with colA:
        costo_input = st.number_input("Costo ($)", min_value=0.0, value=None, step=100.0, placeholder="Obligatorio", help="Costo de compra al proveedor.")
    with colB:
        precio_input = st.number_input("Venta ($)", min_value=0.0, value=None, step=100.0, placeholder="Opcional", help="Déjalo vacío para calcular el precio ideal.")
    
    st.divider()
    st.markdown("### 🏷️ 2. Publicación e Impuestos")
    tipo_pub = st.selectbox("Modalidad de Publicación", ["Clásica (Sin cuotas)", "Premium (3 Cuotas)", "Premium (6 Cuotas)"])
    cond_fiscal = st.selectbox("Condición Fiscal (ARCA)", ["Monotributo", "Inscripto"], help="Monotributistas absorben el 21% de IVA de Meli como costo puro.")
    
    precio_ref = precio_input if precio_input is not None else 0
    envio = st.checkbox("Ofrecer Envío Gratis", value=(precio_ref >= UMBRAL_ENVIO_GRATIS))

    st.divider()
    st.markdown("### 🎯 3. Objetivos y Ads")
    meta_ganancia = st.number_input("Meta de Ganancia Mensual ($)", min_value=0, value=500000, step=50000, help="Ganancia neta mensual esperada.")
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

        # --- DIAGNÓSTICO FINANCIERO ---
        st.divider()
        st.subheader("🧠 Diagnóstico Financiero")
        
        _, _, _, _, _, _, _, gan_stress, mar_stress, _, _, _ = calcular_metricas(costo, precio, tipo_pub, cond_fiscal, envio, max(10, acos_input))
        
        diag1, diag2, diag3 = st.columns(3)
        with diag1:
            if mar >= 15: st.success("✅ **Margen Óptimo:**\n\nTienes colchón ante imprevistos o devoluciones.")
            elif mar >= 10: st.warning("⚠️ **Margen Justo:**\n\nTienes poco margen de error ante aumentos de comisiones.")
            else: st.error("❌ **Margen Crítico:**\n\nEstás asumiendo todo el riesgo logístico por muy poca ganancia.")
        
        with diag2:
            if mkp >= 30: st.success("✅ **ROI Sano:**\n\nTu capital se multiplica a un buen ritmo por cada peso invertido.")
            else: st.warning("⚠️ **ROI Bajo:**\n\nRequieres inmovilizar mucho capital para sacar una ganancia relativamente baja.")
                
        with diag3:
            if gan_stress > 0 and mar_stress >= 5: st.success("✅ **Resiliencia (Soporta Ads):**\n\nSi necesitas encender Ads al 10% para impulsar tus ventas, sigues siendo rentable.")
            else: st.error("❌ **Dependencia Orgánica:**\n\nSi te ves obligado a encender publicidad (10% ACOS) para vender, perderás dinero.")

        # --- TEST DE MERCADO INTERACTIVO (MANUAL) ---
        st.divider()
        st.subheader("🕵️‍♂️ Evaluación de Mercado (Competencia)")
        st.caption("Responde estas 3 preguntas mirando a tus principales competidores en Mercado Libre para obtener un veredicto de viabilidad.")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            comp_ventas = st.selectbox("1. ¿Qué volumen de ventas tienen los líderes (primeros 3)?", ["Altas (Más de 1000 vendidos)", "Medias (Cientos vendidos)", "Bajas (Pocos o sin ventas)"])
            comp_calidad = st.selectbox("2. ¿Cómo es la calidad de sus publicaciones (fotos, descripción)?", ["Mala (Fotos feas, descripciones vacías)", "Normal (Fotos de catálogo, decente)", "Excelente (Videos, Mercado Líder, diseño pro)"])
        with col_m2:
            comp_dif = st.radio("3. ¿Tu producto tiene un diferencial claro?", ["Sí (Es un Combo/Kit, mejor calidad, diseño único)", "No (Es exactamente el mismo producto genérico)"])
            
            # Algoritmo de Score
            score_mercado = 0
            if "Altas" in comp_ventas: score_mercado += 1
            elif "Medias" in comp_ventas: score_mercado += 0.5
            
            if "Mala" in comp_calidad: score_mercado += 2
            elif "Normal" in comp_calidad: score_mercado += 1
            
            if "Sí" in comp_dif: score_mercado += 2
            
            st.write("") 
            if score_mercado >= 4:
                st.success("🌟 **Veredicto: Oportunidad de Oro.** ¡Avanza! Hay demanda demostrada, competidores débiles a los que puedes ganarles, y tienes un diferencial.")
            elif score_mercado >= 2.5:
                st.warning("⚖️ **Veredicto: Mercado Competitivo.** El nicho funciona, pero hay competencia. Tu éxito dependerá de hacer mejores fotos y tener buen presupuesto de Ads.")
            else:
                st.error("🚨 **Veredicto: Riesgo Elevado.** No hay demanda clara o la competencia es muy fuerte e idéntica a ti. Revalúa la idea antes de comprar stock.")

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
                st.success(f"Vende **{unidades_mes} unidades/mes** (aprox. **{unidades_dia} por día**) para ganar **${meta_ganancia:,.0f}** limpios.")
                st.info(f"**Inversión:** ${inversion_inicial:,.0f} | **Facturación:** ${facturacion_mes:,.0f}")
                
                st.divider()
                if st.button("💾 Añadir producto al Portafolio", type="primary", use_container_width=True):
                    guardar_producto(producto_nombre, costo, precio, gan, mar, mkp, unidades_mes, inversion_inicial, facturacion_mes)
                    st.toast('¡Producto guardado exitosamente en tu Portafolio!', icon='✅')

            with col_p2:
                # --- REFERENCIAS DE TAMAÑO FULL ---
                tamano_full = st.selectbox("Tamaño (Costo Bodega/Mes)", [
                    "Pequeño ($150)", 
                    "Mediano ($450)", 
                    "Grande ($1200)"
                ])
                
                st.markdown("""
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 15px; border-left: 4px solid #00a650;">
                    <h5 style="margin-top: 0; color: #333;">📏 Guía Oficial de Tamaños (Referencia Meli)</h5>
                    <ul style="font-size: 0.85rem; color: #555; margin-bottom: 0;">
                        <li><b>Pequeño:</b> Hasta 1.200 cm³ (Ej: 10 x 15 x 8 cm) o peso < 500g. <i>(Fundas, billeteras, joyas).</i></li>
                        <li><b>Mediano:</b> Hasta 30.000 cm³ (Ej: 30 x 30 x 33 cm) o peso < 5kg. <i>(Cajas de zapatillas, pavas).</i></li>
                        <li><b>Grande:</b> Más de 30.000 cm³. <i>(Microondas, sillas, electrodomésticos).</i></li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)

                costo_full_unitario = 150 if "Pequeño" in tamano_full else 450 if "Mediano" in tamano_full else 1200
                costo_full_total = unidades_mes * costo_full_unitario
                ganancia_post_full = meta_ganancia - costo_full_total
                
                st.warning(f"**Costo Bodega Full (Total Mes):** ${costo_full_total:,.0f}")
                if ganancia_post_full > 0:
                    st.success(f"**Ganancia Neta en Full:** ${ganancia_post_full:,.0f}")
                else:
                    st.error(f"🚨 Operar en Full consumirá tu ganancia mensual. Pierdes ${abs(ganancia_post_full):,.0f}.")

    # ==========================================
    # PESTAÑA 3: PORTAFOLIO GLOBAL
    # ==========================================
    with tab3:
        st.markdown("### 💼 Consolidado de Inversiones")
        if len(st.session_state.portafolio) == 0:
            st.info("Tu portafolio está vacío. Ve a la pestaña 'Proyección' y guarda algunos productos.")
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
                st.download_button("📥 Descargar Portafolio (CSV)", data=csv, file_name='mi_portafolio.csv', mime='text/csv', use_container_width=True)
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
            st.info("Agrega productos al portafolio para armar tu presupuesto y orden de compra.")
        else:
            st.markdown("### 💰 Control de Presupuesto")
            
            df_portafolio = pd.DataFrame(st.session_state.portafolio)
            inversion_total = df_portafolio["Inversión Req."].sum()
            
            presupuesto = st.number_input("¿De cuánto capital total dispones para comprar stock? ($)", min_value=0.0, value=inversion_total, step=50000.0)
            
            balance = presupuesto - inversion_total
            porcentaje_uso = (inversion_total / presupuesto) * 100 if presupuesto > 0 else 100
            
            if balance >= 0:
                st.success(f"✅ **Presupuesto Sano:** Te sobran **${balance:,.0f}** de tu capital disponible.")
                st.progress(min(inversion_total / presupuesto, 1.0))
            else:
                st.error(f"🚨 **¡Presupuesto Excedido!** Te faltan **${abs(balance):,.0f}**. Debes inyectar más capital o eliminar unidades de tu portafolio.")
                st.progress(1.0)
                
            st.caption(f"Has comprometido el **{porcentaje_uso:.1f}%** de tu capital en tu portafolio actual (${inversion_total:,.0f}).")
            
            st.divider()
            
            st.markdown("### 🛒 Orden de Compra (Proveedores)")
            st.caption("Esta tabla filtra solo la información que necesita tu proveedor: Nombre, Costo Unitario, Cantidad a comprar y Total a pagar.")
            
            df_oc = df_portafolio[['Producto', 'Costo Unit.', 'Unidades/Mes', 'Inversión Req.']].copy()
            df_oc.columns = ['Producto a Comprar', 'Costo Unitario ($)', 'Cantidad', 'Total a Pagar ($)']
            
            st.dataframe(df_oc, use_container_width=True, hide_index=True)
            
            csv_oc = df_oc.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Descargar Orden de Compra (CSV)",
                data=csv_oc,
                file_name='orden_de_compra_proveedores.csv',
                mime='text/csv',
                use_container_width=True
            )
