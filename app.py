import math
import io
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from erlang_core import calculate_required_agents
from shift_engine import calculate_shift_requirements

st.set_page_config(page_title="Erlang CCM / WFM ", layout="wide")

st.title("📞 Calculadora Erlang C & Intraday WFM")
st.markdown("Aplicación para dimensionamiento de personal y optimización de horarios.")

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

if data_mode == "Simulación (Curva Teórica)":
    interval_min = st.sidebar.selectbox("Intervalo (Minutos)", [15, 30, 60], index=1)
    total_calls = st.sidebar.number_input("Volumen Total del Día", value=1200, step=100)

    intervals_count = int((24 * 60) / interval_min)
    time_labels = [f"{i * interval_min // 60:02d}:{i * interval_min % 60:02d}" for i in range(intervals_count)]

    x = np.linspace(-2, 2, intervals_count)
    dist = np.exp(-x**2)
    dist_pct = dist / dist.sum()
    calls_per_interval = np.round(total_calls * dist_pct)

    df_input = pd.DataFrame({
        "Intervalo": time_labels,
        "Llamadas": calls_per_interval,
        "AHT": [aht_global] * intervals_count
    })

else:
    st.sidebar.subheader("Subir Archivo de Operación")
    uploaded_file = st.sidebar.file_uploader("Carga tu archivo CSV o XLSX", type=["csv", "xlsx"])
    interval_min = st.sidebar.selectbox("Duración del Intervalo del Archivo (Min)", [15, 30, 60], index=1)

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

# --- PROCESAMIENTO MATEMÁTICO ---
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

    # --- SECCIÓN DE EXPORTACIÓN ---
    st.sidebar.markdown("---")
    st.sidebar.header("💾 Exportar Resultados")

    # Generar archivo Excel en memoria (BytesIO)
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
        col1.metric("Volumen Total", f"{int(df_results['Llamadas'].sum()):,} llamadas")
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
        st.subheader("🗓️ Cálculo de Plantilla Real según Tipo de Jornada")
        st.markdown("""
        Esta sección traduce la curva de carga operativa a la **cantidad real de contratos (Headcount)** necesarios, 
        considerando el pico de operación, las horas totales a cubrir y los días de descanso.
        """)
        
        st.dataframe(df_shifts, use_container_width=True)
        
        st.info("""
        💡 **Nota WFM:**
        * **Jornadas de 6.5h y 8h:** Esquema 6x1 (6 días de trabajo por 1 descanso).
        * **Jornadas de 9h:** Esquema 5x2 (5 días de trabajo por 2 descansos).
        """)

else:
    st.info("👈 Por favor, selecciona una opción de datos en la barra lateral para procesar el dimensionamiento.")
