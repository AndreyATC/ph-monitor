import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, time, timedelta
import io

# Налаштування сторінки (робимо її широкою і прибираємо зайві відступи)
st.set_page_config(page_title="pH Monitor", layout="wide", page_icon="🐠")

# Стиль для зменшення відступів зверху
st.markdown("""
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 0rem;}
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

def get_data(start_dt, end_dt):
    conn = sqlite3.connect("aquarium.db")
    query = f"""
        SELECT datetime_str as datetime, ph 
        FROM ph_logs 
        WHERE datetime >= '{start_dt}' AND datetime <= '{end_dt}'
        ORDER BY event_time ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# --- БІЧНА ПАНЕЛЬ (Керування) ---
st.sidebar.header("⚙️ Налаштування")

# Вибір інтервалу дат
d_range = st.sidebar.date_input(
    "Оберіть інтервал дат",
    value=(datetime.now() - timedelta(days=2), datetime.now()),
    max_value=datetime.now()
)

# Перевірка, чи обрано обидві дати (початок і кінець)
if isinstance(d_range, tuple) and len(d_range) == 2:
    start_date, end_date = d_range
else:
    start_date = end_date = d_range[0] if isinstance(d_range, tuple) else d_range

col_t1, col_t2 = st.sidebar.columns(2)
start_t = col_t1.time_input("З часу", time(0, 0))
end_t = col_t2.time_input("До часу", time(23, 59))

start_dt = datetime.combine(start_date, start_t)
end_dt = datetime.combine(end_date, end_t)

# --- ОСНОВНИЙ БЛОК ---
df = get_data(start_dt, end_dt)

if not df.empty:
    df['datetime'] = pd.to_datetime(df['datetime'])
    
    # Компактна статистика в один рядок зверху
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Середній pH", f"{df['ph'].mean():.2f}")
    m2.metric("Максимум", f"{df['ph'].max():.2f}")
    m3.metric("Мінімум", f"{df['ph'].min():.2f}")
    m4.metric("Точок", len(df))

    # Побудова графіка
    fig = go.Figure()

    # Основна лінія
    fig.add_trace(go.Scatter(
        x=df['datetime'], y=df['ph'],
        mode='lines',
        line=dict(color='#007acc', width=2),
        fill='tozeroy',
        fillcolor='rgba(0, 122, 204, 0.05)',
        name="Поточний pH"
    ))

    # Додаємо критичні зони (червоні лінії)
    fig.add_hline(y=8.3, line_dash="dot", line_color="red", annotation_text="Критично високий")
    fig.add_hline(y=7.8, line_dash="dot", line_color="red", annotation_text="Критично низький")
    # Оптимальна зона (зелена)
    fig.add_hrect(y0=7.9, y1=8.2, line_width=0, fillcolor="green", opacity=0.05, annotation_text="Оптимально")

    fig.update_layout(
        height=700,
        margin=dict(l=20, r=20, t=10, b=20),
        yaxis=dict(range=[7.7, 8.5], title="pH"),
        xaxis_title=None,
        hovermode="x unified",
        template="plotly_white"
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # Експорт у бічній панелі
    st.sidebar.markdown("---")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    
    st.sidebar.download_button("📥 Завантажити Excel", buffer.getvalue(), 
                             file_name=f"pH_report_{start_date}_{end_date}.xlsx")
else:
    st.info("Оберіть інший діапазон. Даних не знайдено.")