import asyncio
import json
import os
import schedule
import ssl
import subprocess
import threading
import time
import urllib.request

from bot.telegram_bot import run_bot, start_bot_polling
from data.updater import update_prices
from strategies.fa_strategy import run_fa_filter
from strategies.ta_strategy import run_ta_filter


def ensure_company_info():
    """Tự động kiểm tra và cào 1.600+ mã chứng khoán khi khởi động server trên Railway."""
    file_path = os.path.join("data", "company_info.json")

    # Nếu đã có cache sẵn trên 1.000 mã thì bỏ qua
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if len(data) > 1000:
                    print(f"📦 [CACHE] Đã có sẵn {len(data)} mã trong hệ thống.")
                    return
        except Exception:
            pass

    print(
        "🔄 [RAILWAY STARTUP] Đang tải danh sách 1.600+ mã chứng khoán từ"
        " API..."
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    company_dict = {}

    try:
        url = (
            "https://finfo-api.vndirect.com.vn/v4/stocks?q=type:stock,ETF~status:LISTED&size=3000"
        )
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as res:
            raw = json.loads(res.read().decode("utf-8"))
            for item in raw.get("data", []):
                ticker = str(item.get("code", "")).strip().upper()
                if ticker and len(ticker) == 3:
                    company_dict[ticker] = {
                        "name": (
                            item.get("companyName")
                            or f"Công ty Cổ phần {ticker}"
                        ),
                        "sector": (
                            item.get("industryName") or "Cổ phiếu niêm yết"
                        ),
                    }
        print(
            "✅ [RAILWAY STARTUP] Tải thành công"
            f" {len(company_dict)} mã chứng khoán!"
        )
    except Exception as e:
        print(f"⚠️ [RAILWAY STARTUP] Lỗi tải dữ liệu: {e}")

    if company_dict:
        os.makedirs("data", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(company_dict, f, ensure_ascii=False, indent=2)


def run_cap_nhat_toan_bo():
    """Chạy quy trình khép kín: Cập nhật giá -> Tính chỉ số TA/FA -> Tạo tín hiệu mới"""
    print("\n" + "=" * 50)
    print("🔄 [TIẾN TRÌNH] BẮT ĐẦU CẬP NHẬT GIÁ VÀ TÍN HIỆU")
    print("=" * 50)
    try:
        # 1. Cập nhật giá mới nhất
        update_prices()

        # 2. Chạy chiến lược lọc TA / FA
        run_fa_filter()
        run_ta_filter()

        # 3. Chạy file tạo file signals.json (nếu có)
        if os.path.exists("signal_generator.py"):
            subprocess.run(["python", "signal_generator.py"])

        print("✅ [TIẾN TRÌNH] Đã cập nhật xong toàn bộ dữ liệu mới nhất!\n")
    except Exception as e:
        print(f"❌ [TIẾN TRÌNH] Lỗi khi cập nhật dữ liệu: {e}\n")


# 1. Tự động kiểm tra danh sách mã khi khởi động
ensure_company_info()

# 2. Tự động chạy cập nhật giá + tạo tín hiệu NGAY KHI KHỞI ĐỘNG SERVER
run_cap_nhat_toan_bo()

# 3. Lên lịch tự động chạy hàng ngày
schedule.every().day.at("09:00").do(
    run_cap_nhat_toan_bo
)  # Quét lại trước phiên sáng
schedule.every().day.at("15:30").do(
    run_cap_nhat_toan_bo
)  # Quét lại sau giờ ATC chiều


def scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(60)


# Chạy bộ hẹn giờ ở luồng ngầm (Daemon Thread)
t = threading.Thread(target=scheduler_loop, daemon=True)
t.start()

print("\n⏰ Lịch chạy tự động:")
print("  09:00 — Cập nhật & Phát tín hiệu đầu ngày")
print("  15:30 — Cập nhật giá & Tín hiệu sau giờ đóng cửa")
print("🤖 Bot đang lắng nghe lệnh...\n")

# Bắt đầu chạy Telegram Bot ở luồng chính
start_bot_polling()