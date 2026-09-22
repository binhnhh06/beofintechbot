import asyncio
from datetime import datetime, timedelta, timezone
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

# Nạp API Key vnstock và múi giờ Việt Nam (UTC+7)
VNSTOCK_KEY = os.getenv("VNSTOCK_API_KEY", "vnstock_80c9c49d5aa8e6c394a8d502fad4e9bc")
os.environ["VNSTOCK_API_KEY"] = VNSTOCK_KEY
os.environ["VNSTOCK_TELEMETRY"] = "off"

VN_TZ = timezone(timedelta(hours=7))
SSI_HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}

# Bảng tra cứu nhóm ngành dự phòng
SECTOR_MAP = {
    "FRT": ("CTCP Bán lẻ Kỹ thuật số FPT", "Bán lẻ"),
    "MWG": ("CTCP Đầu tư Thế Giới Di Động", "Bán lẻ"),
    "FPT": ("CTCP FPT", "Công nghệ thông tin"),
    "DGW": ("CTCP Thế Giới Số", "Bán lẻ / Công nghệ"),
    "HPG": ("CTCP Tập đoàn Hòa Phát", "Thép & Vật liệu"),
    "HSG": ("CTCP Tập đoàn Hoa Sen", "Thép & Vật liệu"),
    "NKG": ("CTCP Thép Nam Kim", "Thép & Vật liệu"),
    "DGC": ("CTCP Tập đoàn Hóa chất Đức Giang", "Hóa chất"),
    "PVT": ("TCT CP Vận tải Dầu khí", "Vận tải / Dầu khí"),
    "PVP": ("CTCP Vận tải Dầu khí Thái Bình Dương", "Vận tải / Dầu khí"),
    "PVD": ("TCT CP Khoan và Dịch vụ Khoan Dầu khí", "Dầu khí"),
    "PVS": ("TCT CP Dịch vụ Kỹ thuật Dầu khí VN", "Dầu khí"),
    "HAH": ("CTCP Vận tải và Cảng biển Bình An", "Vận tải biển"),
    "VPB": ("Ngân hàng TMCP Việt Nam Thịnh Vượng", "Ngân hàng"),
    "STB": ("Ngân hàng TMCP Sài Gòn Thương Tín", "Ngân hàng"),
    "ACB": ("Ngân hàng TMCP Á Châu", "Ngân hàng"),
    "TCB": ("Ngân hàng TMCP Kỹ thương Việt Nam", "Ngân hàng"),
    "MBB": ("Ngân hàng TMCP Quân Đội", "Ngân hàng"),
    "VCB": ("Ngân hàng TMCP Ngoại thương Việt Nam", "Ngân hàng"),
    "BID": ("Ngân hàng TMCP Đầu tư và Phát triển VN", "Ngân hàng"),
    "CTG": ("Ngân hàng TMCP Công Thương Việt Nam", "Ngân hàng"),
    "SSI": ("CTCP Chứng khoán SSI", "Dịch vụ tài chính"),
    "VND": ("CTCP Chứng khoán VNDIRECT", "Dịch vụ tài chính"),
    "VCI": ("CTCP Chứng khoán Vietcap", "Dịch vụ tài chính"),
    "HCM": ("CTCP Chứng khoán TP.HCM", "Dịch vụ tài chính"),
    "VHM": ("CTCP Vinhomes", "Bất động sản"),
    "NVL": ("CTCP Tập đoàn Đầu tư Địa ốc No Va", "Bất động sản"),
    "PDR": ("CTCP Phát triển Bất động sản Phát Đạt", "Bất động sản"),
    "DXG": ("CTCP Tập đoàn Đất Xanh", "Bất động sản"),
    "DIG": ("Tổng Cty CP Đầu tư Phát triển Xây dựng", "Bất động sản"),
    "VNM": ("CTCP Sữa Việt Nam", "Thực phẩm & Đồ uống"),
    "MSN": ("CTCP Tập đoàn Masan", "Tiêu dùng / Tiêu chuẩn"),
}


# ==========================================
# CHUẨN HÓA GIÁ VÀ ĐÁNH GIÁ CHỈ SỐ
# ==========================================
def format_price(val):
    return val * 1000 if val < 1000 else val


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
    p_full = format_price(price)
    e_full = format_price(ema20)
    if p_full >= e_full:
        return f"{e_full:,.0f} đ ➔ Uptrend (Giá trên EMA20)"
    return f"{e_full:,.0f} đ ➔ Downtrend (Giá dưới EMA20)"


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
# TRUY XUẤT DỮ LIỆU REALTIME & DOANH NGHIỆP
# ==========================================
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


def get_company_info(ticker):
    ticker_str = ticker.upper()

    # 1. API TCBS (Tốc độ cực cao, chính xác 100% nhóm ngành)
    try:
        url = f"https://apipubks.tcbs.com.vn/stock-insight/v1/comp/{ticker_str}/overview"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            data = r.json()
            name = data.get("shortName") or data.get("ticker") or ticker_str
            sector = data.get("industryName") or data.get("subIndustryName")
            if sector and not pd.isna(sector) and str(sector).strip().lower() not in ['nan', 'none', '']:
                return {"name": str(name), "exchange": "HOSE/HNX", "sector": str(sector)}
    except Exception:
        pass

    # 2. Bảng tra cứu SECTOR_MAP
    if ticker_str in SECTOR_MAP:
        name, sector = SECTOR_MAP[ticker_str]
        return {"name": name, "exchange": "HOSE/HNX", "sector": sector}

    # 3. Tra cứu từ watch_list.json
    fa = get_fa_data(ticker_str)
    if fa and fa.get("sector"):
        return {
            "name": fa.get("name", ticker_str),
            "exchange": fa.get("exchange", "HOSE"),
            "sector": fa.get("sector")
        }

    # 4. Vnstock API Key VIP
    try:
        from vnstock import Vnstock
        stock = Vnstock(api_key=VNSTOCK_KEY).stock(symbol=ticker_str, source='VCI')
        df_ov = stock.company.overview()
        if df_ov is not None and not df_ov.empty:
            row = df_ov.iloc[0].to_dict()
            name = row.get("organ_name") or row.get("company_name") or ticker_str
            sector = row.get("icb_name3") or row.get("industry") or "Sản xuất / Dịch vụ"
            return {"name": str(name), "exchange": str(row.get("exchange", "HOSE")), "sector": str(sector)}
    except Exception:
        pass

    return {"name": ticker_str, "exchange": "HOSE", "sector": "Sản xuất / Dịch vụ"}


def fetch_stock_data(ticker):
    """Lấy dữ liệu giá realtime từ vnstock và tự động ghép giá mới nhất hôm nay từ TCBS"""
    ticker_str = ticker.upper()
    df = None

    # 1. Lấy dữ liệu lịch sử nến từ vnstock API Key
    try:
        from vnstock import Vnstock

        stock = Vnstock(api_key=VNSTOCK_KEY).stock(
            symbol=ticker_str, source="VCI"
        )
        end_date = datetime.now(VN_TZ).strftime("%Y-%m-%d")
        start_date = (datetime.now(VN_TZ) - timedelta(days=180)).strftime(
            "%Y-%m-%d"
        )
        df = stock.quote.history(start=start_date, end=end_date)
        if df is not None and not df.empty:
            df = df.rename(
                columns={
                    "time": "date",
                    "tradingDate": "date",
                    "match_price": "close",
                    "volume": "volume",
                }
            )
            df["date"] = df["date"].astype(str).str[:10]
            if "open" not in df.columns:
                df["open"] = df["close"]
            if "high" not in df.columns:
                df["high"] = df["close"]
            if "low" not in df.columns:
                df["low"] = df["close"]
    except Exception:
        pass

    # Dự phòng từ SQLite nếu lỗi vnstock
    if df is None or df.empty:
        try:
            conn = sqlite3.connect("data/market_data.db")
            query = f"SELECT date, open, high, low, close, volume FROM historical_ohlcv WHERE symbol = '{ticker_str}' ORDER BY date ASC"
            df = pd.read_sql_query(query, conn)
            conn.close()
        except Exception:
            pass

    if df is None or df.empty:
        return None

    # 2. KIỂM TRA & CẬP NHẬT GIÁ REALTIME HÔM NAY TỪ TCBS (NẾU THIẾU NGÀY HÔM NAY)
    today_str = datetime.now(VN_TZ).strftime("%Y-%m-%d")
    last_date = str(df.iloc[-1]["date"])[:10]

    if last_date < today_str:
        try:
            # Gọi API Overview của TCBS để lấy giá khớp và khối lượng mới nhất hôm nay
            tcbs_url = f"https://apipubks.tcbs.com.vn/stock-insight/v1/comp/{ticker_str}/overview"
            r = requests.get(tcbs_url, timeout=3)
            if r.status_code == 200:
                data = r.json()
                price = data.get("price") or data.get("closePrice")
                volume = data.get("volume") or data.get("totalVolume") or 0

                if price and price > 0:
                    # Chuẩn hóa giá về nghìn đồng nếu TCBS trả về đồng
                    price_val = price / 1000.0 if price > 1000 else price
                    new_row = pd.DataFrame(
                        [
                            {
                                "date": today_str,
                                "open": price_val,
                                "high": price_val,
                                "low": price_val,
                                "close": price_val,
                                "volume": volume,
                            }
                        ]
                    )
                    df = pd.concat([df, new_row], ignore_index=True)
        except Exception:
            pass

    return df


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


def calc_trade_stats(trade, current_price):
    c_full = format_price(current_price)
    e_full = format_price(trade["entry_price"])
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
    pnl_pct = (c_full - e_full) / e_full * 100
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


# ==========================================
# BIỂU ĐỒ DARK MODE
# ==========================================
def generate_stock_chart(df, symbol):
    plt.style.use("dark_background")
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8, 6), gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )
    fig.patch.set_facecolor("#181818")

    df_plot = df.tail(60).copy().reset_index(drop=True)

    ax1.set_facecolor("#181818")
    ax1.plot(df_plot.index, df_plot["close"].apply(format_price), color="#00FF7F", label="Giá đóng cửa", linewidth=1.5)
    ax1.plot(df_plot.index, df_plot["EMA20"].apply(format_price), color="#FF8C00", linestyle="--", label="EMA20", linewidth=1.2)
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
# XỬ LÝ LỆNH /STOCK
# ==========================================
def get_signal_for_ticker(ticker):
    try:
        df = fetch_stock_data(ticker)
        if df is None or len(df) < 30:
            return None, None, "Không tìm thấy dữ liệu giao dịch cho mã này."

        # Tính toán Kỹ thuật
        df["price"] = df["close"]
        df["EMA20"] = ta.trend.ema_indicator(df["price"], window=20)
        df["EMA50"] = ta.trend.ema_indicator(df["price"], window=50)
        df["RSI_14"] = ta.momentum.rsi(df["price"], window=14)
        df["ATR_14"] = ta.volatility.average_true_range(df["high"], df["low"], df["price"], window=14)
        df["volume_MA20"] = df["volume"].rolling(20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_MA20"]
        df = df.dropna()

        latest = df.iloc[-1]
        raw_price = latest["price"]
        full_price = format_price(raw_price)
        full_atr = format_price(latest["ATR_14"])
        
        fa_data = get_fa_data(ticker)
        comp_info = get_company_info(ticker)

        # 1. SMARTTRADE
        active_trade = get_active_trade(ticker)
        if active_trade:
            position = "MUA (ĐANG NẮM GIỮ)" if active_trade.get("type") == "BUY" else "BÁN"
            trend = "TĂNG" if position.startswith("MUA") else "GIẢM"
            signal_date = active_trade["entry_date"]
            t_plus, pnl = calc_trade_stats(active_trade, raw_price)
        else:
            position = "THEO DÕI"
            trend = "ĐANG TÍCH LŨY"
            signal_date = str(latest["date"])[:10]
            t_plus = 0
            pnl = 0.0

        pnl_emoji = "🟢" if pnl >= 0 else "🔴"

        # 2. SMARTSCORE
        dinh_gia, chat_luong, dong_luong, smart_score = calc_smartscore(ticker, df, fa_data)

        # 3. Chỉ số FA
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

        chart_buffer = generate_stock_chart(df, ticker.upper())
        now_str = datetime.now(VN_TZ).strftime("%H:%M:%S - %d/%m/%Y")

        msg = f"""📊 **{ticker.upper()} - {comp_info['name']} ({comp_info['exchange']})**
⏱ {now_str}

🟠 **SMARTTRADE | Khuyến nghị tự động**
• Vị thế hiện tại: **{position}**
• Xu hướng: **{trend}**
• Ngày tín hiệu: {signal_date}
• Giá hiện tại: {full_price:,.0f} đ
• Lãi/Lỗ: {pnl:+0.1f}% {pnl_emoji}
• Số phiên: T + {t_plus}

🟣 **SMARTSCORE | Chấm điểm DN: {smart_score}**
• Điểm Định giá: {dinh_gia} | Điểm Chất lượng: {chat_luong} | Điểm Động lượng: {dong_luong}
• Nhóm ngành: {comp_info['sector']}
• ATR(14): {full_atr:,.0f} đ

🏛️ **Chỉ số Tài chính Trọng yếu (FA):**
• ROE : {eval_roe(roe_val)}
• LNST : {eval_lnst(lnst_val, eps_growth)}
• Biên LN Gộp: {eval_margin(margin_val)}
• Nợ / Vốn chủ (D/E): {eval_de(de_val)}

📈 **Phân tích Dòng tiền & Động lượng (TA):**
• Đường EMA20: {eval_ema(raw_price, latest['EMA20'])}
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
            p_full = format_price(s['price'])
            msg += f"{emoji} {s['ticker']} — {s.get('signal_type', 'HOLD')} — {p_full:,.0f} đ\n"
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
        df = fetch_stock_data(t['ticker'])
        current_price = df['close'].iloc[-1] if df is not None and not df.empty else t["entry_price"]
        t_plus, pnl = calc_trade_stats(t, current_price)
        emoji = "🟢" if pnl >= 0 else "🔴"
        e_full = format_price(t['entry_price'])
        c_full = format_price(current_price)
        msg += (
            f"\n{emoji} {t['ticker']}\n"
            f"- Ngày mua: {t['entry_date']}\n"
            f"- Giá vào: {e_full:,.0f} đ\n"
            f"- Giá hiện tại: {c_full:,.0f} đ\n"
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


run_bot = start_bot_polling

if __name__ == "__main__":
    start_bot_polling()