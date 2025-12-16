# main.py
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import datetime

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- CODE CHẠY KHI KHỞI ĐỘNG (STARTUP) ---
    print("\n------------------------------------------------")
    print("🚀 HỆ THỐNG ĐANG KHỞI TẠO (SYSTEM STARTUP)...")
    print("   - Đang kết nối Database...")
    init_db() # Gọi hàm tạo bảng ngay khi server bật
    print("   - Đã tạo bảng 'sensors' và 'alerts' thành công!")
    print("   - Server đã sẵn sàng nhận dữ liệu từ ESP32.")
    print("------------------------------------------------\n")
    
    yield # Điểm phân cách: Web chạy bình thường ở đây
    
    # --- CODE CHẠY KHI TẮT HỆ THỐNG (SHUTDOWN) ---
    print("\n------------------------------------------------")
    print("🛑 HỆ THỐNG ĐANG TẮT (SYSTEM SHUTDOWN)...")
    print("   - Đang đóng các kết nối ngầm...")
    print("   - Đang dọn dẹp bộ nhớ đệm...")
    print("👋 Tạm biệt! Hẹn gặp lại.")
    print("------------------------------------------------\n")

app = FastAPI(lifespan=lifespan)

#app.mount("/static", StaticFiles(directory="static"), name="static")

# 1. Cấu hình Template (để render file HTML)
templates = Jinja2Templates(directory="templates")

# 2. Cấu hình CORS (Cho phép truy cập từ mọi nơi - Dev mode)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Khởi tạo Database SQLite
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sensors 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  temp REAL, hum REAL, pm25 INTEGER, gas INTEGER, 
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  message TEXT, level TEXT, 
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# 4. Model dữ liệu đầu vào từ ESP32
class SensorPayload(BaseModel):
    temp: float
    hum: float
    pm25: int
    gas: int

# --- LOGIC XỬ LÝ CHÍNH ---
@app.post("/api/update")
async def update_data(data: SensorPayload):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Lưu dữ liệu cảm biến
    c.execute("INSERT INTO sensors (temp, hum, pm25, gas, timestamp) VALUES (?, ?, ?, ?, ?)",
              (data.temp, data.hum, data.pm25, data.gas, now_str))
    
    # Xử lý Logic điều khiển & Cảnh báo
    fan_status = "OFF"
    pump_status = "OFF"
    alert_msg = ""
    
    # Ngưỡng (Threshold)
    GAS_THRESHOLD = 2000
    PM25_THRESHOLD = 100
    TEMP_THRESHOLD = 50

    # Logic 1: Bụi cao -> Bật Quạt
    if data.pm25 > PM25_THRESHOLD:
        fan_status = "ON"
        
    # Logic 2: Có Gas -> Cảnh báo
    if data.gas > GAS_THRESHOLD:
        alert_msg = "Phát hiện rò rỉ khí Gas!"
        # Ghi log cảnh báo
        c.execute("INSERT INTO alerts (message, level, timestamp) VALUES (?, ?, ?)", (alert_msg, "WARNING", now_str))

    # Logic 3: Cháy (Gas + Nhiệt) -> Bật Bơm
    if data.gas > GAS_THRESHOLD and data.temp > TEMP_THRESHOLD:
        pump_status = "ON"
        alert_msg = "CẢNH BÁO CHÁY! Đã kích hoạt máy bơm!"
        c.execute("INSERT INTO alerts (message, level, timestamp) VALUES (?, ?, ?)", (alert_msg, "DANGER", now_str))

    conn.commit()
    conn.close()

    # Trả về lệnh điều khiển cho ESP32
    return {
        "fan": fan_status,
        "pump": pump_status,
        "status": "success"
    }

# --- API CHO WEB DASHBOARD ---

# Render trang chủ
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# API lấy dữ liệu mới nhất để hiển thị số đo
@app.get("/api/current")
async def get_current():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT temp, hum, pm25, gas, timestamp FROM sensors ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    
    if row:
        return {"temp": row[0], "hum": row[1], "pm25": row[2], "gas": row[3], "time": row[4]}
    return {"temp": 0, "hum": 0, "pm25": 0, "gas": 0, "time": "N/A"}

# API lấy lịch sử cảnh báo
@app.get("/api/alerts")
async def get_alerts():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT message, level, timestamp FROM alerts ORDER BY id DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    
    alerts = [{"msg": r[0], "level": r[1], "time": r[2]} for r in rows]
    return alerts

if __name__ == "__main__":
    import uvicorn
    # Chạy server trên cổng 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)