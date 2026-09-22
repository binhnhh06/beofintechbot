import asyncio
from datetime import date, datetime
import io
import json
import os
import sqlite3
import matplotlib.pyplot as plt
import pandas as pd
import requests
import ta
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    TA_RSI_BUY,
    TA_RSI_SELL,
    TA_STOP_LOSS_PCT,
    TA_TAKE_PROFIT_PCT,
    TA_VOLUME_RATIO_MIN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
)

SSI_HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}


# ==========================================
# BỘ HÀM ĐÁNH GIÁ TỰ ĐỘNG CHỈ SỐ (FA & TA)
# ==========================================
def eval_roe(val):
    if val >= 15:
        return f"{val:.2f}% ➔ Tốt / Đạt"
    elif val >= 10:
        return f"{val:.2f}% ➔ Trung bình"
    return f"{val:.2f}% ➔ Yếu / Chưa đạt"


def eval_lnst(val_ty, growth=0):
    if val_ty > 0 and growth >= 15:
        return f"{val_ty:,.1f} tỷ ➔ Tăng trưởng tốt / Đạt"
    elif val_ty > 0:
        return f"{val_ty:,.1f} tỷ ➔ Đạt"
    return f"{val_ty:,.1f} tỷ ➔ Chưa đạt (Thua lỗ)"


def eval_margin(val):
    if val >= 30:
        return f"{val:.2f}% ➔ Tốt / Cao"
    elif val >= 15:
        return f"{val:.2f}% ➔ Trung bình"
    return f"{val:.2f}% ➔ Thấp / Mỏng"


def eval_de(val):
    if val <= 1.0:
        return f"{val:.2f} lần ➔ An toàn"
    elif val <= 1.8:
        return f"{val:.2f} lần ➔ Tương đối cao"
    return f"{val:.2f} lần ➔ Rủi ro cao"


def eval_ema(price, ema20):
    if price >= ema20:
        return f"{ema20:.2f} VNĐ ➔ Uptrend (Giá trên EMA20)"
    return f"{ema20:.2f} VNĐ ➔ Downtrend (Giá dưới EMA20)"


def eval_rsi(rsi_val):
    if rsi_val >= 70:
        return f"{rsi_val:.1f} — Vùng quá mua (Cảnh báo rủi ro)"
    elif rsi_val >= 50:
        return f"{rsi_val:.1f} — Động lượng Tốt"
    elif rsi_val >= 35:
        return f"{rsi_val:.1f} — Tích lũy / Động lượng Yếu"
    return f"{rsi_val:.1f} — Vùng quá bán"


def eval_volume(vol, vol_ratio):
    if vol_ratio >= 1.5:
        return f"{int(vol):,} cp ➔ Dòng tiền vào mạnh ({vol_ratio:.1f}x MA20)"
    elif vol_ratio >= 1.0:
        return f"{int(vol):,} cp ➔ Khối lượng đạt TB ({vol_ratio:.1f}x MA20)"
    return f"{int(vol):,} cp ➔ Khối lượng thấp ({vol_ratio:.1f}x MA20)"


# ==========================================
# CÁC HÀM TRUY XUẤT DỮ LIỆU & QUẢN LÝ VỊ THẾ
# ==========================================
def get_company_info(ticker):
    try:
        url = f"https://iboard-api.ssi.com.vn/statistics/company/ssmi/company-profile?symbol={ticker}&language=vn"
        r = requests.get(url, headers=SSI_HEADERS, timeout=5)
        data = r.json().get("data", {})
        return {
            "name": data.get("companyName", ticker),
            "exchange": data.get("exchange", "HOSE"),
            "sector": data.get("sector", "Ngân hàng/Tài chính"),
        }
    except:
        return {"name": ticker, "exchange": "HOSE", "sector": "Chưa xác định"}


def get_last_trading_date(ticker):
    try:
        conn = sqlite3.connect("data/market_data.db")
        df = pd.read_sql_query(
            f"SELECT date FROM historical_ohlcv WHERE symbol = '{ticker}' ORDER BY date DESC LIMIT 1",
            conn,
        )
        conn.close()
        return df["date"].iloc[0]
    except:
        return str(date.today())


def load_trade_history():
    try:
        with open("data/trade_history.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_trade_history(history):
    with open("data/trade_history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_active_trade(ticker):
    history = load_trade_history()
    for t in history:
        if t["ticker"] == ticker and t["status"] == "OPEN":
            return t
    return None


def open_trade(ticker, price, stop_loss, take_profit, rr_ratio):
    history = load_trade_history()
    entry_date = get_last_trading_date(ticker)
    for t in history:
        if t["ticker"] == ticker and t["status"] == "OPEN":
            t["status"] = "CLOSED"
    history.append(
        {
            "ticker": ticker,
            "entry_price": price,
            "entry_date": entry_date,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "rr_ratio": rr_ratio,
            "status": "OPEN",
        }
    )
    save_trade_history(history)


def calc_trade_stats(trade, current_price):
    try:
        conn = sqlite3.connect("data/market_data.db")
        df = pd.read_sql_query(
            f"SELECT date FROM historical_ohlcv WHERE symbol = '{trade['ticker']}' AND date >= '{trade['entry_date']}' ORDER BY date ASC",
            conn,
        )
        conn.close()
        t_plus = len(df) - 1
    except:
        t_plus = 0
    pnl_pct = (current_price - trade["entry_price"]) / trade["entry_price"] * 100
    return max(0, t_plus), round(pnl_pct, 1)


def calc_smartscore(ticker, df, fa_data=None):
    latest = df.iloc[-1]
    rsi_score = min(latest["RSI_14"], 100)
    ema_score = 100 if latest["EMA20"] > latest["EMA50"] else 30
    vol_score = min(latest["volume_ratio"] * 50, 100)
    dong_luong = int(rsi_score * 0.4 + ema_score * 0.4 + vol_score * 0.2)

    if fa_data:
        roe_score = min(float(fa_data.get("ROE", 15)) * 2, 100)
        de_score = max(100 - float(fa_data.get("DE_ratio", 1)) * 50, 0)
        chat_luong = int(roe_score * 0.6 + de_score * 0.4)
        pe = float(fa_data.get("pe", 15))
        dinh_gia = int(max(100 - pe * 3, 30))
    else:
        chat_luong = 70
        dinh_gia = 75

    tong = int(dinh_gia * 0.3 + chat_luong * 0.35 + dong_luong * 0.35)
    return dinh_gia, chat_luong, dong_luong, tong


def get_fa_data(ticker):
    try:
        with open("data/watch_list.json", "r", encoding="utf-8") as f:
            watch = json.load(f)
        for item in watch:
            if item["ticker"] == ticker:
                return item
        return None
    except:
        return None


# ==========================================
# HÀM VẼ BIỂU ĐỒ KỸ THUẬT DARK MODE
# ==========================================
def generate_stock_chart(df, symbol):
    plt.style.use("dark_background")
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8, 6), gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )
    fig.patch.set_facecolor("#181818")

    df_plot = df.tail(60).copy().reset_index(drop=True)

    ax1.set_facecolor("#181818")
    ax1.plot(df_plot.index, df_plot["close"], color="#00FF7F", label="Giá đóng cửa", linewidth=1.5)
    ax1.plot(df_plot.index, df_plot["EMA20"], color="#FF8C00", linestyle="--", label="EMA20", linewidth=1.2)
    ax1.set_title(f"Biểu đồ Phân tích Kỹ thuật #{symbol}", color="white", fontsize=11, pad=10)
    ax1.legend(loc="upper left", frameon=True, facecolor="#252525", edgecolor="none", fontsize=8)
    ax1.grid(True, linestyle=":", alpha=0.2, color="#888888")

    ax2.set_facecolor("#181818")
    ax2.plot(df_plot.index, df_plot["RSI_14"], color="#1E90FF", linewidth=1.5)
    ax2.axhline(70, color="#FF4500", linestyle="--", alpha=0.6, linewidth=1)
    ax2.axhline(30, color="#00FA9A", linestyle="--", alpha=0.6, linewidth=1)
    ax2.set_ylabel("RSI(14)", color="white", fontsize=8)
    ax2.set_ylim(0, 100)
    ax2.grid(True, linestyle=":", alpha=0.2, color="#888888")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor="#181818")
    buf.seek(0)
    plt.close(fig)
    return buf


# ==========================================
# HÀM TẠO TIN NHẮN TỔNG HỢP CẢ CỦA CŨ VÀ MỚI
# ==========================================
def get_signal_for_ticker(ticker):
    try:
        conn = sqlite3.connect("data/market_data.db")
        query = f"SELECT date, open, high, low, close, volume FROM historical_ohlcv WHERE symbol = '{ticker.upper()}' ORDER BY date ASC"
        df = pd.read_sql_query(query, conn)
        conn.close()

        if len(df) < 50:
            return None, None, "Không đủ dữ liệu lịch sử"

        # Tính toán Kỹ thuật (TA)
        df["price"] = df["close"]
        df["EMA20"] = ta.trend.ema_indicator(df["price"], window=20)
        df["EMA50"] = ta.trend.ema_indicator(df["price"], window=50)
        df["MA50"] = df["price"].rolling(50).mean()
        df["RSI_14"] = ta.momentum.rsi(df["price"], window=14)
        df["ATR_14"] = ta.volatility.average_true_range(df["high"], df["low"], df["price"], window=14)
        df["volume_MA20"] = df["volume"].rolling(20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_MA20"]
        df["resist_20"] = df["high"].rolling(20).max().shift(1)
        df = df.dropna()

        latest = df.iloc[-1]
        price = latest["price"]
        atr = latest["ATR_14"]
        fa_data = get_fa_data(ticker)
        comp_info = get_company_info(ticker)

        # 1. Tính toán SMARTTRADE
        active_trade = get_active_trade(ticker)
        if active_trade:
            position = "MUA (ĐANG NẮM GIỮ)" if active_trade.get("type") == "BUY" else "BÁN"
            trend = "TĂNG" if position.startswith("MUA") else "GIẢM"
            signal_date = active_trade["entry_date"]
            t_plus, pnl = calc_trade_stats(active_trade, price)
        else:
            position = "THEO DÕI"
            trend = "ĐANG TÍCH LŨY"
            signal_date = latest["date"]
            t_plus = 0
            pnl = 0.0

        pnl_emoji = "🟢" if pnl >= 0 else "🔴"

        # 2. Tính toán SMARTSCORE
        dinh_gia, chat_luong, dong_luong, smart_score = calc_smartscore(ticker, df, fa_data)

        # 3. Lấy dữ liệu FA
        roe_val = float(fa_data.get("ROE", 18.71)) if fa_data else 18.71
        lnst_val = float(fa_data.get("LNST", 2567.6)) if fa_data else 2567.6
        eps_growth = float(fa_data.get("EPS_growth_yoy", 15.0)) if fa_data else 15.0
        margin_val = float(fa_data.get("gross_margin", 37.58)) if fa_data else 37.58
        de_val = float(fa_data.get("DE_ratio", 0.79)) if fa_data else 0.79

        # Khuyến nghị AI
        if latest["RSI_14"] >= 70:
            ai_rec = "CẢNH BÁO QUÁ MUA! Hạn chế mua mới, ưu tiên chốt lời từng phần."
        elif latest["EMA20"] > latest["EMA50"] and latest["volume_ratio"] >= 1.2:
            ai_rec = "XU HƯỚNG TỐT! Dòng tiền vào mạnh, có thể tích lũy theo điểm breakout."
        else:
            ai_rec = "CẦN THEO DÕI! Giá đang tích lũy quanh nền, chờ tín hiệu xác nhận."

        # Biểu đồ
        chart_buffer = generate_stock_chart(df, ticker.upper())

        # GỘP KHUNG THÔNG TIN CỦ & MỚI
        now_str = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
        msg = f"""📊 **{ticker.upper()} - {comp_info['name']} ({comp_info['exchange']})**
⏱ {now_str}

🟠 **SMARTTRADE | Khuyến nghị tự động**
• Vị thế hiện tại: **{position}**
• Xu hướng: **{trend}**
• Ngày tín hiệu: {signal_date}
• Giá hiện tại: {price * 1000:,.0f} đ
• Lãi/Lỗ: {pnl:+0.1f}% {pnl_emoji}
• Số phiên: T + {t_plus}

🟣 **SMARTSCORE | Chấm điểm DN: {smart_score}**
• Điểm Định giá: {dinh_gia} | Điểm Chất lượng: {chat_luong} | Điểm Động lượng: {dong_luong}
• Nhóm ngành: {comp_info['sector']}
• ATR(14): {atr * 1000:,.0f}

🏛️ **Chỉ số Tài chính Trọng yếu (FA):**
• ROE : {eval_roe(roe_val)}
• LNST : {eval_lnst(lnst_val, eps_growth)}
• Biên LN Gộp: {eval_margin(margin_val)}
• Nợ / Vốn chủ (D/E): {eval_de(de_val)}

📈 **Phân tích Dòng tiền & Động lượng (TA):**
• Đường EMA20: {eval_ema(price, latest['EMA20'])}
• Khối lượng: {eval_volume(latest['volume'], latest['volume_ratio'])}
• Chỉ báo RSI(14): {eval_rsi(latest['RSI_14'])}

🎯 **KHUYẾN NGHỊ AI:**
💡 {ai_rec}

_Disclaimer: Phân tích tự động từ AI FinBot, không phải cam kết đầu tư._"""

        return msg, chart_buffer, None
    except Exception as e:
        return None, None, str(e)


# ==========================================
# CÁC LỆNH TELEGRAM BOT
# ==========================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Chào mừng đến với FinTech Stock Bot!\n\n"
        "Các lệnh hỗ trợ:\n"
        "/stock FPT — Phân tích chi tiết mã cổ phiếu\n"
        "/today — Xem tín hiệu thị trường hôm nay\n"
        "/portfolio — Danh mục đang nắm giữ\n"
        "/help — Hướng dẫn sử dụng\n"
    )


async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Vui lòng nhập mã. Ví dụ: /stock VPB")
        return
    ticker = context.args[0].upper()
    await update.message.reply_text(f"🔍 Đang phân tích mã {ticker}...")

    msg, chart_buf, error = get_signal_for_ticker(ticker)
    if error:
        await update.message.reply_text(f"❌ Không phân tích được mã {ticker}: {error}")
    elif chart_buf:
        await update.message.reply_photo(photo=chart_buf, caption=msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open("data/signals.json", "r", encoding="utf-8") as f:
            signals = json.load(f)
        if not signals:
            await update.message.reply_text("📭 Hôm nay không có tín hiệu nào.")
            return
        msg = "📊 TÍN HIỆU HÔM NAY\n" + "=" * 30 + "\n"
        for s in signals:
            emoji = "🟢" if s.get("signal_type") == "BUY" else "🔴"
            msg += f"{emoji} {s['ticker']} — {s.get('signal_type', 'HOLD')} — {s['price'] * 1000:,.0f} đ\n"
        await update.message.reply_text(msg)
    except:
        await update.message.reply_text("❌ Chưa có dữ liệu tín hiệu hôm nay.")


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history = load_trade_history()
    open_trades = [t for t in history if t["status"] == "OPEN"]
    if not open_trades:
        await update.message.reply_text("📭 Chưa có vị thế nào đang mở.")
        return
    msg = "💼 DANH MỤC ĐANG NẮM GIỮ\n" + "=" * 30 + "\n"
    for t in open_trades:
        try:
            conn = sqlite3.connect("data/market_data.db")
            df = pd.read_sql_query(
                f"SELECT close FROM historical_ohlcv WHERE symbol='{t['ticker']}' ORDER BY date DESC LIMIT 1",
                conn,
            )
            conn.close()
            current_price = float(df["close"].iloc[0])
        except:
            current_price = t["entry_price"]
        t_plus, pnl = calc_trade_stats(t, current_price)
        emoji = "🟢" if pnl >= 0 else "🔴"
        msg += (
            f"\n{emoji} {t['ticker']}\n"
            f"- Ngày mua: {t['entry_date']}\n"
            f"- Giá vào: {t['entry_price'] * 1000:,.0f} đ\n"
            f"- Giá hiện tại: {current_price * 1000:,.0f} đ\n"
            f"- Lãi/Lỗ: {pnl:+.1f}% {emoji}\n"
            f"- Số phiên: T+{t_plus}\n"
        )
    await update.message.reply_text(msg)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 HƯỚNG DẪN SỬ DỤNG\n\n"
        "/stock <mã> — Tra cứu & Phân tích chi tiết cổ phiếu\n"
        "/today — Tín hiệu giao dịch hôm nay\n"
        "/portfolio — Xem danh mục mở\n"
    )


def start_bot_polling():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stock", cmd_stock))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("help", cmd_help))
    print("🤖 Bot đang lắng nghe lệnh...")
    app.run_polling()


if __name__ == "__main__":
    start_bot_polling()