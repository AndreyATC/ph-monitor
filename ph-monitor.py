import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots  # Потрібно для подвійної осі
from datetime import datetime, time, timedelta
import io
from supabase import create_client, Client

# --- ІНІЦІАЛІЗАЦІЯ SUPABASE ---
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# Налаштування сторінки
st.set_page_config(
    page_title="Aquarium Monitor",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Стиль
st.markdown("""
    <style>
    .block-container {padding-top: 1rem; padding-bottom: 0rem;}
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# Функція для завантаження з конкретної таблиці
def fetch_table_data(table_name, column_name, start_ms, end_ms):
    all_rows = []
    page_size = 1000
    offset = 0
    
    while True:
        response = supabase.table(table_name) \
            .select(f"event_time, {column_name}") \
            .gte("event_time", start_ms) \
            .lte("event_time", end_ms) \
            .order("event_time", desc=False) \
            .range(offset, offset + page_size - 1) \
            .execute()
        
        data = response.data
        if not data:
            break
            
        all_rows.extend(data)
        if len(data) < page_size:
            break
        offset += page_size
        
    return pd.DataFrame(all_rows)

def get_combined_data(start_dt, end_dt):
    # Перетворюємо час у мілісекунди
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    
    # 1. Завантажуємо pH
    df_ph = fetch_table_data("ph_logs", "ph", start_ms, end_ms)
    
    # 2. Завантажуємо ORP
    df_orp = fetch_table_data("orp_logs", "orp", start_ms, end_ms)
    
    # Якщо даних немає взагалі
    if df_ph.empty and df_orp.empty:
        return pd.DataFrame()

    # Обробка pH
    if not df_ph.empty:
        df_ph['datetime'] = pd.to_datetime(df_ph['event_time'], unit='ms', utc=True)
        df_ph = df_ph.set_index('datetime')[['ph']]
    
    # Обробка ORP
    if not df_orp.empty:
        df_orp['datetime'] = pd.to_datetime(df_orp['event_time'], unit='ms', utc=True)
        df_orp = df_orp.set_index('datetime')[['orp']]

    # 3. Об'єднання (Merge) по часу
    # Використовуємо outer join, щоб зберегти дані, навіть якщо час не ідеально збігається
    if not df_ph.empty and not df_orp.empty:
        # Об'єднуємо і сортуємо
        df_combined = pd.concat([df_ph, df_orp], axis=1).sort_index()
    elif not df_ph.empty:
        df_combined = df_ph
        df_combined['orp'] = None # Додаємо пусту колонку
    else:
        df_combined = df_orp
        df_combined['ph'] = None

    # Конвертація часового поясу (Kyiv)
    df_combined.index = df_combined.index.tz_convert('Europe/Kyiv').tz_localize(None)
    
    # 4. Ресемплінг (усереднення) до 5 хвилин
    # Це вирівняє дані pH та ORP на одну часову шкалу і прибере шуми
    df_resampled = df_combined.resample('5min').mean()
    
    # Повертаємо index назад у колонку datetime
    return df_resampled.reset_index()

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
df = get_combined_data(start_dt, end_dt)

if not df.empty:
    st.markdown("""
        <style>
        @media (max-width: 767px) {
            .mobile-hide { display: none !important; }
        }
        </style>
        """, unsafe_allow_html=True)

    # --- ГРАФІК З ДВОМА ОСЯМИ ---
    # Створюємо фігуру з додатковою віссю Y
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Лінія pH (Ліва вісь)
    fig.add_trace(go.Scatter(
        x=df['datetime'], y=df['ph'],
        mode='lines',
        name="pH",
        line=dict(color='#007acc', width=2),
        connectgaps=True # З'єднувати лінії, якщо є пропуски
    ), secondary_y=False)

    # Лінія ORP (Права вісь)
    fig.add_trace(go.Scatter(
        x=df['datetime'], y=df['orp'],
        mode='lines',
        name="ORP (mV)",
        line=dict(color='#ff7f0e', width=2), # Помаранчевий колір
        connectgaps=True
    ), secondary_y=True)

    # Межі для pH
    fig.add_hline(y=8.3, line_dash="dot", line_color="blue", opacity=0.3, annotation_text="pH High", secondary_y=False)
    fig.add_hline(y=7.8, line_dash="dot", line_color="blue", opacity=0.3, annotation_text="pH Low", secondary_y=False)

    # Налаштування макету
    fig.update_layout(
        title="Динаміка pH та ORP",
        height=600,
        hovermode="x unified",
        template="plotly_white",
        legend=dict(orientation="h", y=1.1, x=0.5, xanchor='center'),
        margin=dict(l=20, r=20, t=50, b=20)
    )

    # Налаштування осей
    fig.update_yaxes(title_text="<b>pH</b>", color="#007acc", secondary_y=False, range=[7.5, 8.5])
    fig.update_yaxes(title_text="<b>ORP (mV)</b>", color="#ff7f0e", secondary_y=True, range=[150, 300]) # Підлаштуйте діапазон під свій акваріум

    # Конфігурація для мобільних
    config = {
        'displayModeBar': True,
        'scrollZoom': True,
        'displaylogo': False,
        'modeBarButtonsToRemove': ['lasso2d', 'select2d']
    }

    st.plotly_chart(fig, use_container_width=True, config=config)

    # --- СТАТИСТИКА (pH та ORP) ---
    with st.container():
        st.markdown("### Статистика за період")
        
        # Рядок 1: pH
        st.markdown("**Водневий показник (pH)**")
        c1, c2, c3, c4 = st.columns(4)
        if 'ph' in df and df['ph'].notnull().any():
            c1.metric("Середній", f"{df['ph'].mean():.2f}")
            c2.metric("Макс", f"{df['ph'].max():.2f}")
            c3.metric("Мін", f"{df['ph'].min():.2f}")
            c4.metric("Останній", f"{df['ph'].iloc[-1]:.2f}")
        
        st.divider()
        
        # Рядок 2: ORP
        st.markdown("**Редокс-потенціал (ORP)**")
        k1, k2, k3, k4 = st.columns(4)
        if 'orp' in df and df['orp'].notnull().any():
            k1.metric("Середній", f"{df['orp'].mean():.0f} mV")
            k2.metric("Макс", f"{df['orp'].max():.0f} mV")
            k3.metric("Мін", f"{df['orp'].min():.0f} mV")
            k4.metric("Останній", f"{df['orp'].iloc[-1]:.0f} mV")

    # Експорт
    st.sidebar.markdown("---")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True)
    
    st.sidebar.download_button("📥 Завантажити Excel", buffer.getvalue(), 
                             file_name=f"Aquarium_Report_{start_date}.xlsx")

else:
    st.info("Даних не знайдено. Перевірте підключення або розширте діапазон дат.")



