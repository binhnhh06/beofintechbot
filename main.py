import asyncio
import threading
import schedule
import time
from strategies.fa_strategy import run_fa_filter
from strategies.ta_strategy import run_ta_filter
from bot.telegram_bot import run_bot, start_bot_polling
from data.updater import update_prices

def run_daily():
    print("\n" + "=" * 50)
    print("FINTECH BOT BẮT ĐẦU CHẠY")
    print("=" * 50)
    run_fa_filter()
    run_ta_filter()
    asyncio.run(run_bot())
    print("XONG! Chờ đến lần chạy tiếp theo...")

def run_updater():
    print("\n⏰ Cập nhật giá sau phiên giao dịch...")
    update_prices()

# Chạy pipeline ngay khi khởi động
run_daily()

# Len lich tu dong
schedule.every().day.at("09:00").do(run_daily)    # Phat tin hieu luc 9h sang
schedule.every().day.at("15:30").do(run_updater)  # Cap nhat gia luc 15h30

def scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(60)

t = threading.Thread(target=scheduler_loop, daemon=True)
t.start()

print("\n⏰ Lịch chạy tự động:")
print("  09:00 — Phát tín hiệu mua/bán")
print("  15:30 — Cập nhật giá sau phiên")
print("🤖 Bot đang lắng nghe lệnh...\n")

start_bot_polling()