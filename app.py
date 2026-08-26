import math
import io
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pulp


# Importación de módulos locales
from erlang_core import calculate_required_agents
from shift_engine import calculate_shift_requirements

# Configuración inicial de la página
st.set_page_config(page_title="Erlang C & WFM Call Center", layout="wide")

st.title("📞 Calculadora Erlang C & Intraday WFM")
st.markdown("Herramienta *Open Source* para dimensionamiento de personal y optimización de horarios.")

# --- BARRA LATERAL ---
st.sidebar.header("⚙️ Parámetros Globales")
aht_global = st.sidebar.number_input("AHT - Tiempo Promedio de Operación (seg)", value=240, step=10)
target_sla = st.sidebar.slider("Objetivo Nivel de Servicio (SLA %)", 50, 100, 80) / 100.0
target_time = st.sidebar.number_input("Tiempo Objetivo SLA (seg)", value=20, step=5)
max_occ = st.sidebar.slider("Límite de Ocupación Máxima (%)", 50, 95, 85) / 100.0
shrinkage = st.sidebar.slider("Merma / Shrinkage (%)", 0, 50, 20) / 100.0

st.sidebar.header("📂 Modo de Ingreso de Datos")
data_mode = st.sidebar.radio("Selecciona el origen de los datos:", ["Simulación (Curva Teórica)", "Cargar Archivo (CSV / Excel)"])

df_input = None
interval_min = 30
volume_period = "Diario"

if data_mode == "Simulación (Curva Teórica)":
    interval_min = st.sidebar.selectbox("Intervalo (Minutos)", [15, 30, 60], index=1)
    
    # Selección de periodo de volumen
    volume_period = st.sidebar.radio(
        "Periodo del Volumen de Entrada:",
        ["Diario", "Mensual"],
        help="Elige si ingresarás el volumen promedio diario o proyectarás a partir de un total mensual."
    )

    daily_weights = {}

    if volume_period == "Diario":
        input_volume = st.sidebar.number_input("Volumen Diario (Llamadas/Día):", min_value=1, value=1200, step=50)
    else:
        total_monthly_volume = st.sidebar.number_input("Volumen Total Mensual (Llamadas/Mes):", min_value=1, value=30000, step=500)
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("📅 Pesos por Día de la Semana (%)")
        st.sidebar.caption("Asigna el % de tráfico correspondiente a cada día:")

        col_w1, col_w2 = st.sidebar.columns(2)
        with col_w1:
            w_lun = st.number_input("Lunes (%)", min_value=0.0, max_value=100.0, value=20.0, step=1.0)
            w_mar = st.number_input("Martes (%)", min_value=0.0, max_value=100.0, value=18.0, step=1.0)
            w_mie = st.number_input("Miércoles (%)", min_value=0.0, max_value=100.0, value=17.0, step=1.0)
            w_jue = st.number_input("Jueves (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0)
        with col_w2:
            w_vie = st.number_input("Viernes (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0)
            w_sab = st.number_input("Sábado (%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0)
            w_dom = st.number_input("Domingo (%)", min_value=0.0, max_value=100.0, value=5.0, step=1.0)

        total_weight = w_lun + w_mar + w_mie + w_jue + w_vie + w_sab + w_dom

        if round(total_weight, 2) != 100.0:
            st.sidebar.error(f"⚠️ La suma de pesos es **{total_weight:.1f}%**. Debe ser exactamente **100%**.")
        else:
            st.sidebar.success("✅ Distribución del 100% validada.")

        daily_weights = {
            "Lunes": w_lun / 100.0,
            "Martes": w_mar / 100.0,
            "Miércoles": w_mie / 100.0,
            "Jueves": w_jue / 100.0,
            "Viernes": w_vie / 100.0,
            "Sábado": w_sab / 100.0,
            "Domingo": w_dom / 100.0
        }
        
        # Proyección de volumen diario para Lunes (representativo)
        avg_weekly_volume = total_monthly_volume / 4.33
        input_volume = int(avg_weekly_volume * daily_weights["Lunes"])

    intervals_count = int((24 * 60) / interval_min)
    time_labels = [f"{i * interval_min // 60:02d}:{i * interval_min % 60:02d}" for i in range(intervals_count)]

    # Curva gaussiana teórica aplicada al volumen calculado
    x = np.linspace(-2, 2, intervals_count)
    dist = np.exp(-x**2)
    dist_pct = dist / dist.sum()
    calls_per_interval = np.round(input_volume * dist_pct)

    df_input = pd.DataFrame({
        "Intervalo": time_labels,
        "Llamadas": calls_per_interval,
        "AHT": [aht_global] * intervals_count
    })

else:
    st.sidebar.subheader("Subir Archivo de Operación")
    uploaded_file = st.sidebar.file_uploader("Carga tu archivo CSV o XLSX", type=["csv", "xlsx"])
    interval_min = st.sidebar.selectbox("Duración del Intervalo del Archivo (Min)", [15, 30, 60], index=1)

    # Generación de plantilla descargable
    intervals_count = int((24 * 60) / interval_min)
    sample_times = [f"{i * interval_min // 60:02d}:{i * interval_min % 60:02d}" for i in range(intervals_count)]
    sample_df = pd.DataFrame({
        "Intervalo": sample_times,
        "Llamadas": [int(10 + 50 * np.exp(-((i - intervals_count/2)/5)**2)) for i in range(intervals_count)],
        "AHT": [aht_global] * intervals_count
    })

    csv_buffer = io.StringIO()
    sample_df.to_csv(csv_buffer, index=False)
    st.sidebar.download_button(
        label="📥 Descargar Plantilla CSV de Ejemplo",
        data=csv_buffer.getvalue(),
        file_name="plantilla_intraday_erlang.csv",
        mime="text/csv"
    )

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                df_input = pd.read_csv(uploaded_file)
            else:
                df_input = pd.read_excel(uploaded_file)
            
            if "Intervalo" not in df_input.columns or "Llamadas" not in df_input.columns:
                st.error("El archivo debe contener al menos las columnas: 'Intervalo' y 'Llamadas'.")
                df_input = None
            if "AHT" not in df_input.columns:
                df_input["AHT"] = aht_global
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")
            df_input = None

# --- VISTA PREVIA DE PONDERACIÓN SEMANAL (SI ES MODALIDAD MENSUAL) ---
if data_mode == "Simulación (Curva Teórica)" and volume_period == "Mensual" and daily_weights:
    st.subheader("📊 Distribución Semanal Estimada por Pesos")
    weekly_vol_calc = total_monthly_volume / 4.33
    df_distribution = pd.DataFrame({
        "Día": list(daily_weights.keys()),
        "Peso (%)": [v * 100 for v in daily_weights.values()],
        "Volumen Semanal Est. (Llamadas)": [int(weekly_vol_calc * v) for v in daily_weights.values()]
    })
    
    col_chart, col_table = st.columns([2, 1])
    with col_chart:
        fig_weights = px.bar(
            df_distribution,
            x="Día",
            y="Volumen Semanal Est. (Llamadas)",
            text="Peso (%)",
            title="Distribución Estimada de Llamadas por Día de la Semana",
            color="Peso (%)",
            color_continuous_scale="Blues"
        )
        fig_weights.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        st.plotly_chart(fig_weights, use_container_width=True)
        
    with col_table:
        st.markdown("**Desglose por Día:**")
        st.dataframe(df_distribution, hide_index=True, use_container_width=True)

# --- PROCESAMIENTO MATEMÁTICO ERANG C ---
if df_input is not None:
    results = []
    for idx, row in df_input.iterrows():
        c = float(row["Llamadas"])
        current_aht = float(row["AHT"]) if pd.notnull(row["AHT"]) and float(row["AHT"]) > 0 else aht_global
        
        m_net, sla, occ = calculate_required_agents(c, interval_min, current_aht, target_sla, target_time, max_occ)
        m_gross = math.ceil(m_net / (1 - shrinkage)) if m_net > 0 else 0
        
        results.append({
            "Intervalo": str(row["Intervalo"]),
            "Llamadas": int(c),
            "AHT (seg)": int(current_aht),
            "FTE Netos": m_net,
            "Agentes Brutos (Headcount)": m_gross,
            "SLA Logrado (%)": round(sla * 100, 1),
            "Ocupación (%)": round(occ * 100, 1)
        })

    df_results = pd.DataFrame(results)

    # Cálculo de Horarios de Turno
    hours_per_interval = interval_min / 60.0
    total_fte_hours = (df_results['FTE Netos'] * hours_per_interval).sum()
    peak_fte = df_results['FTE Netos'].max()
    shift_summary = calculate_shift_requirements(peak_fte, total_fte_hours, shrinkage)
    df_shifts = pd.DataFrame(shift_summary).T


    # --- PARÁMETROS DE COSTO Y PRESUPUESTO ---
    st.sidebar.markdown("---")
    st.sidebar.header("💰 Presupuesto & Nómina")
    cost_per_hour = st.sidebar.number_input("Costo Promedio por Hora / Agente ($)", min_value=1.0, value=15.0, step=1.0)


    # --- SECCIÓN DE EXPORTACIÓN ---
    st.sidebar.markdown("---")
    st.sidebar.header("💾 Exportar Resultados")

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df_results.to_excel(writer, sheet_name='Intraday Erlang C', index=False)
        df_shifts.to_excel(writer, sheet_name='Requerimiento de Turnos', index=True)

    st.sidebar.download_button(
        label="📊 Descargar Reporte Excel (.xlsx)",
        data=excel_buffer.getvalue(),
        file_name="dimensionamiento_call_center.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # --- INTERFAZ DE RESULTADOS ---
    tab1, tab2 = st.tabs(["📊 Curva Intraday & Erlang C", "⏰ Requerimiento por Horarios de Agentes"])

    with tab1:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Volumen Día Representativo", f"{int(df_results['Llamadas'].sum()):,} llamadas")
        col2.metric("Peak FTE Netos", f"{df_results['FTE Netos'].max()} agentes")
        col3.metric("Peak Agentes Brutos", f"{df_results['Agentes Brutos (Headcount)'].max()} agentes")
        col4.metric("SLA Promedio", f"{round(df_results['SLA Logrado (%)'].mean(), 1)}%")

        st.subheader("Distribución Intraday: Volumen vs Agentes Requeridos")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_results['Intervalo'], y=df_results['Llamadas'], name='Volumen Llamadas', yaxis='y1', opacity=0.4))
        fig.add_trace(go.Scatter(x=df_results['Intervalo'], y=df_results['FTE Netos'], name='FTE Netos', mode='lines+markers', yaxis='y2'))
        fig.add_trace(go.Scatter(x=df_results['Intervalo'], y=df_results['Agentes Brutos (Headcount)'], name='Agentes Brutos (c/ Merma)', mode='lines', yaxis='y2', line=dict(dash='dash')))

        fig.update_layout(
            xaxis=dict(title="Hora del Día"),
            yaxis=dict(title="Número de Llamadas", side="left"),
            yaxis2=dict(title="Cantidad de Agentes", side="right", overlaying="y"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=480
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📄 Ver Tabla de Datos Intraday Procesada"):
            st.dataframe(df_results, use_container_width=True)

    with tab2:
        st.subheader("🗓️ Optimización de Malla de Turnos & Presupuesto (PuLP Solver)")
        st.markdown("""
        Esta sección utiliza **programación lineal entera (PuLP)** para calcular la distribución exacta de inicios de turno 
        minimizando el costo total de nómina y garantizando la cobertura de la curva Erlang C.
        """)
        
        # 1. Definición del problema de optimización en PuLP
        prob = pulp.LpProblem("WFM_Shift_Scheduling", pulp.LpMinimize)
        
        # Tipos de turno disponibles (duración en horas)
        shift_types = {
            "Jornada 6.5h (6x1)": 6.5,
            "Jornada 8.0h (6x1)": 8.0,
            "Jornada 9.0h (5x2)": 9.0
        }
        
        num_intervals = len(df_results)
        hours_per_int = interval_min / 60.0
        
        # Variables de decisión: cuántos agentes inician turno de tipo 's' en el intervalo 'i'
        shift_vars = {}
        for s in shift_types:
            for i in range(num_intervals):
                shift_vars[(s, i)] = pulp.LpVariable(f"shift_{s}_{i}", lowBound=0, cat=pulp.LpInteger)
        
        # Función Objetivo: Minimizar costo total de horas pagadas
        prob += pulp.lpSum([
            shift_vars[(s, i)] * shift_types[s] * cost_per_hour
            for s in shift_types for i in range(num_intervals)
        ])
        
        # Restricciones: Cobertura de la curva (Agentes presentes >= FTE Netos requeridos)
        for i in range(num_intervals):
            coverage = []
            for s, duration in shift_types.items():
                intervals_covered = int(duration / hours_per_int)
                # Sumar turnos que iniciaron en intervalos previos y aún están activos
                for start_i in range(max(0, i - intervals_covered + 1), i + 1):
                    coverage.append(shift_vars[(s, start_i)])
            
            prob += pulp.lpSum(coverage) >= df_results.loc[i, "FTE Netos"], f"Coverage_Interval_{i}"
        
        # Resolver el modelo matemático
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        
        if pulp.LpStatus[prob.status] == "Optimal":
            # Extraer resultados de inicios de turno
            schedule_data = []
            for (s, i), var in shift_vars.items():
                val = int(var.varValue)
                if val > 0:
                    schedule_data.append({
                        "Hora Inicio": df_results.loc[i, "Intervalo"],
                        "Tipo de Turno": s,
                        "Agentes a Ingresar": val,
                        "Costo Estimado / Día ($)": round(val * shift_types[s] * cost_per_hour, 2)
                    })
            
            df_schedule = pd.DataFrame(schedule_data)
            
            # Métrica de costos globales
            total_daily_cost = sum([row["Costo Estimado / Día ($)"] for row in schedule_data]) if schedule_data else 0
            total_monthly_cost = total_daily_cost * 30.4
            total_agents_scheduled = sum([row["Agentes a Ingresar"] for row in schedule_data]) if schedule_data else 0

            col_c1, col_c2, col_c3 = st.columns(3)
            col_c1.metric("Headcount Requerido (Programado)", f"{total_agents_scheduled} agentes")
            col_c2.metric("Presupuesto Diario Estimado", f"${total_daily_cost:,.2f} MXN")
            col_c3.metric("Presupuesto Mensual Proyectado", f"${total_monthly_cost:,.2f} MXN")
            
            st.markdown("---")
            st.markdown("**📋 Programación Sugerida de Ingresos de Turnos:**")
            if not df_schedule.empty:
                st.dataframe(df_schedule, use_container_width=True)
            else:
                st.info("No se requieren agentes para la carga operativa actual.")
        else:
            st.error("⚠️ No se encontró una solución óptima para la combinación de turnos.")
        
        st.markdown("---")
        st.markdown("**📊 Resumen Convencional por Tipo de Jornada:**")
        st.dataframe(df_shifts, use_container_width=True)
        
        st.info("""
        💡 **Nota de Optimización WFM:**
        * El solver matemático **PuLP** programa las entradas de los agentes evaluando las coberturas exactas por intervalo para evitar sobrecostos por exceso de personal (*overstaffing*).
        """)

else:
    st.info("👈 Por favor, selecciona una opción de datos en la barra lateral para procesar el dimensionamiento.")
