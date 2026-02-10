import os
import time
from datetime import datetime, timedelta
from tuya_connector import TuyaOpenAPI
from supabase import create_client, Client

# --- ОТРИМУЄМО КЛЮЧІ З НАЛАШТУВАНЬ GITHUB ---
ACCESS_ID = os.environ.get("TUYA_ACCESS_ID")
ACCESS_KEY = os.environ.get("TUYA_ACCESS_KEY")
ENDPOINT = "https://openapi.tuyaeu.com"
DEVICE_ID = os.environ.get("TUYA_DEVICE_ID")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# --- ЛОГІКА ---
def run_cloud_sync():
    print(f"🚀 Запуск хмарної синхронізації...")
    
    # Ініціалізація
    openapi = TuyaOpenAPI(ENDPOINT, ACCESS_ID, ACCESS_KEY)
    openapi.connect()
    
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Беремо інтервал за останні 60 хвилин (із запасом)
    now_ts = int(datetime.now().timestamp() * 1000)
    start_ts = int((datetime.now() - timedelta(minutes=60)).timestamp() * 1000)
    
    print(f"🕒 Період: останні 60 хвилин")
    
    params_codes = "ph_current,orp_current"
    all_logs = []
    last_row_key = None
    
    # Витягуємо дані
    while True:
        params = {
            "codes": params_codes,
            "start_time": start_ts,
            "end_time": now_ts,
            "size": 100,
            "type": 7
        }
        if last_row_key: params["last_row_key"] = last_row_key

        try:
            res = openapi.get(f"/v2.1/cloud/thing/{DEVICE_ID}/report-logs", params=params)
        except Exception as e:
            print(f"❌ Помилка: {e}")
            break
            
        if not res.get("success"): break
        
        logs = res.get("result", {}).get("logs", [])
        if not logs: break
        
        all_logs.extend(logs)
        if not res["result"].get("hasMore"): break
        last_row_key = res["result"].get("lastRowKey")
        time.sleep(0.5)

    if not all_logs:
        print("📭 Немає нових даних.")
        return

    # Обробка та запис
    ph_data, orp_data = [], []
    seen_ph, seen_orp = set(), set()
    
    # Сортуємо
    all_logs.sort(key=lambda x: int(x['eventTime']))

    for log in all_logs:
        e_time = int(log['eventTime'])
        dt_str = datetime.fromtimestamp(e_time/1000).strftime('%Y-%m-%d %H:%M:%S')
        min_key = dt_str[:16] # хвилина
        
        val = log.get('value')
        code = log.get('code')
        
        if code == 'ph_current' and min_key not in seen_ph:
            try:
                v = float(val) / 100.0
                if 0 < v < 14:
                    ph_data.append({"event_time": e_time, "datetime_str": dt_str, "ph": v})
                    seen_ph.add(min_key)
            except: pass
            
        elif code == 'orp_current' and min_key not in seen_orp:
            try:
                v = float(val)
                if -1000 < v < 1000:
                    orp_data.append({"event_time": e_time, "datetime_str": dt_str, "orp": v})
                    seen_orp.add(min_key)
            except: pass

    # Відправка в базу
    if ph_data:
        try:
            supabase.table("ph_logs").upsert(ph_data).execute()
            print(f"✅ pH: {len(ph_data)} записано")
        except Exception as e: print(f"Err pH: {e}")

    if orp_data:
        try:
            supabase.table("orp_logs").upsert(orp_data).execute()
            print(f"✅ ORP: {len(orp_data)} записано")
        except Exception as e: print(f"Err ORP: {e}")

if __name__ == "__main__":
    run_cloud_sync()