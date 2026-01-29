import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, time, timedelta
import io
from supabase import create_client, Client

# --- ІНІЦІАЛІЗАЦІЯ SUPABASE ---
# Переконайтеся, що ви додали ці ключі в Secrets на streamlit.io
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# Налаштування сторінки
st.set_page_config(page_title="Aquarium pH Monitor", layout="wide", page_icon="🐠")

# Стиль
st.markdown("""
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 0rem;}
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

def get_data(start_dt, end_dt):
    # 1. Перетворюємо час у мілісекунди
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    
    all_rows = []
    page_size = 1000  # Розмір порції даних
    offset = 0        # Зміщення (з якого рядка починати)
    
    while True:
        # Запит порції даних від offset до offset + page_size
        response = supabase.table("ph_logs") \
            .select("event_time, ph") \
            .gte("event_time", start_ms) \
            .lte("event_time", end_ms) \
            .order("event_time", desc=False) \
            .range(offset, offset + page_size - 1) \
            .execute()
        
        data = response.data
        if not data:
            break
            
        all_rows.extend(data)
        
        # Якщо отримали менше, ніж просили — значить, дані закінчилися
        if len(data) < page_size:
            break
            
        offset += page_size
    
    df = pd.DataFrame(all_rows)
    
    if not df.empty:
        # Конвертуємо час
        df['datetime'] = pd.to_datetime(df['event_time'], unit='ms', utc=True)
        
        # Оскільки ви тепер пишете дані 1/хв, 
        # додаткова фільтрація (resample) тут вже не обов'язкова,
        # але для швидкості графіка за великий період можна залишити:
        if len(df) > 2000:
            df = df.set_index('datetime').resample('5min').mean().dropna().reset_index()
            
    return df

# --- БІЧНА ПАНЕЛЬ ---
st.sidebar.header("⚙️ Налаштування")

d_range = st.sidebar.date_input(
    "Оберіть інтервал дат",
    value=(datetime.now() - timedelta(days=2), datetime.now()),
    max_value=datetime.now()
)

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
    # Статистика
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Середній pH", f"{df['ph'].mean():.2f}")
    m2.metric("Максимум", f"{df['ph'].max():.2f}")
    m3.metric("Мінімум", f"{df['ph'].min():.2f}")
    m4.metric("Точок", len(df))

    # Побудова графіка
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df['datetime'], y=df['ph'],
        mode='lines',
        line=dict(color='#007acc', width=2),
        fill='tozeroy',
        fillcolor='rgba(0, 122, 204, 0.05)',
        name="pH"
    ))

    # Межі
    fig.add_hline(y=8.3, line_dash="dot", line_color="red", annotation_text="Високий")
    fig.add_hline(y=7.8, line_dash="dot", line_color="red", annotation_text="Низький")
    fig.add_hrect(y0=7.9, y1=8.2, line_width=0, fillcolor="green", opacity=0.05, annotation_text="Оптимально")

    fig.update_layout(
        height=700,
        margin=dict(l=20, r=20, t=10, b=20),
        yaxis=dict(range=[7.6, 8.6], title="pH"),
        xaxis_title=None,
        hovermode="x unified",
        template="plotly_white"
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # Експорт
    st.sidebar.markdown("---")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    
    st.sidebar.download_button("📥 Завантажити Excel", buffer.getvalue(), 
                             file_name=f"pH_report_{start_date}_{end_date}.xlsx")
else:
    st.info("Даних не знайдено. Спробуйте розширити діапазон.")




