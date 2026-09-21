import asyncio
import json
import sqlite3
import pandas as pd
import ta
import requests
from datetime import datetime, date
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TA_RSI_BUY, TA_RSI_SELL, TA_VOLUME_RATIO_MIN, TA_STOP_LOSS_PCT, TA_TAKE_PROFIT_PCT

SSI_HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}

def get_company_info(ticker):
    try:
        url  = f"https://iboard-api.ssi.com.vn/statistics/company/ssmi/company-profile?symbol={ticker}&language=vn"
        r    = requests.get(url, headers=SSI_HEADERS, timeout=10)
        data = r.json().get('data', {})
        return {
            'name':       data.get('companyName', ticker),
            'exchange':   data.get('exchange', 'HOSE'),
            'sector':     data.get('sector', 'N/A'),
            'sub_sector': data.get('subSector', 'N/A'),
            'market_cap': float(data.get('listedValue', 0)) / 1e9,
            'free_float': float(data.get('freeFloatRate', 0)) * 100,
        }
    except:
        return {
            'name': ticker, 'exchange': 'N/A',
            'sector': 'N/A', 'sub_sector': 'N/A',
            'market_cap': 0, 'free_float': 0,
        }

def get_last_trading_date(ticker):
    """Lấy ngày giao dịch gần nhất từ DB"""
    try:
        conn = sqlite3.connect('data/market_data.db')
        df   = pd.read_sql_query(f"""
            SELECT date FROM historical_ohlcv
            WHERE symbol = '{ticker}'
            ORDER BY date DESC LIMIT 1
        """, conn)
        conn.close()
        return df['date'].iloc[0]
    except:
        return str(date.today())

def load_trade_history():
    try:
        with open('data/trade_history.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_trade_history(history):
    with open('data/trade_history.json', 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_active_trade(ticker):
    history = load_trade_history()
    for t in history:
        if t['ticker'] == ticker and t['status'] == 'OPEN':
            return t
    return None

def open_trade(ticker, price, stop_loss, take_profit, rr_ratio):
    """Mở lệnh mới với ngày giao dịch thực tế"""
    history    = load_trade_history()
    entry_date = get_last_trading_date(ticker)

    for t in history:
        if t['ticker'] == ticker and t['status'] == 'OPEN':
            t['status'] = 'CLOSED'

    history.append({
        'ticker':      ticker,
        'entry_price': price,
        'entry_date':  entry_date,
        'stop_loss':   stop_loss,
        'take_profit': take_profit,
        'rr_ratio':    rr_ratio,
        'status':      'OPEN',
    })
    save_trade_history(history)

def calc_trade_stats(trade, current_price):
    """Tính T+ theo số phiên giao dịch thực tế"""
    try:
        conn  = sqlite3.connect('data/market_data.db')
        df    = pd.read_sql_query(f"""
            SELECT date FROM historical_ohlcv
            WHERE symbol = '{trade['ticker']}'
            AND date >= '{trade['entry_date']}'
            ORDER BY date ASC
        """, conn)
        conn.close()
        t_plus = len(df) - 1
    except:
        t_plus = 0

    pnl_pct = (current_price - trade['entry_price']) / trade['entry_price'] * 100
    return t_plus, round(pnl_pct, 2)

def calc_smartscore(ticker, df, fa_data=None):
    latest = df.iloc[-1]

    rsi_score  = min(latest['RSI_14'], 100)
    ema_score  = 100 if latest['EMA20'] > latest['EMA50'] else 30
    vol_score  = min(latest['volume_ratio'] * 50, 100)
    dong_luong = int((rsi_score * 0.4 + ema_score * 0.4 + vol_score * 0.2))

    if fa_data:
        roe_score  = min(float(fa_data.get('ROE', 0)) * 2, 100)
        de_score   = max(100 - float(fa_data.get('DE_ratio', 1)) * 50, 0)
        eps_score  = min(float(fa_data.get('EPS_growth_yoy', 0)), 100)
        chat_luong = int((roe_score * 0.4 + de_score * 0.3 + eps_score * 0.3))
    else:
        chat_luong = 50

    if fa_data:
        pe       = float(fa_data.get('pe', 15))
        pb       = float(fa_data.get('pb', 1.5))
        pe_score = max(100 - pe * 2, 0) if pe > 0 else 50
        pb_score = max(100 - pb * 20, 0) if pb > 0 else 50
        dinh_gia = int((pe_score * 0.5 + pb_score * 0.5))
    else:
        dinh_gia = 50

    tong = int((dinh_gia * 0.3 + chat_luong * 0.35 + dong_luong * 0.35))
    return dinh_gia, chat_luong, dong_luong, tong

def get_fa_data(ticker):
    try:
        with open('data/watch_list.json', 'r', encoding='utf-8') as f:
            watch = json.load(f)
        for item in watch:
            if item['ticker'] == ticker:
                return item
        return None
    except:
        return None

def get_signal_for_ticker(ticker):
    try:
        conn  = sqlite3.connect('data/market_data.db')
        query = f"""
            SELECT date, open, high, low, close, volume
            FROM historical_ohlcv
            WHERE symbol = '{ticker.upper()}'
            ORDER BY date ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if len(df) < 50:
            return None, "Không đủ dữ liệu lịch sử"

        df['price']        = df['close']
        df['EMA20']        = ta.trend.ema_indicator(df['price'], window=20)
        df['EMA50']        = ta.trend.ema_indicator(df['price'], window=50)
        df['MA50']         = df['price'].rolling(50).mean()
        df['RSI_14']       = ta.momentum.rsi(df['price'], window=14)
        df['ATR_14']       = ta.volatility.average_true_range(df['high'], df['low'], df['price'], window=14)
        df['volume_MA20']  = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_MA20']
        df['resist_20']    = df['high'].rolling(20).max().shift(1)
        df = df.dropna()

        latest  = df.iloc[-1]
        price   = latest['price']
        atr     = latest['ATR_14']
        company = get_company_info(ticker)
        fa_data = get_fa_data(ticker)
        dinh_gia, chat_luong, dong_luong, tong = calc_smartscore(ticker, df, fa_data)

        buy_ok = (
            latest['price'] >= latest['MA50'] and
            latest['EMA20'] > latest['EMA50'] and
            latest['RSI_14'] > TA_RSI_BUY and
            latest['volume_ratio'] >= TA_VOLUME_RATIO_MIN
        )
        sell_ok = latest['RSI_14'] > TA_RSI_SELL

        if buy_ok:
            stop_loss = price - 2 * atr
            risk      = price - stop_loss
            resist    = latest['resist_20']
            reward    = resist - price
            if reward < 2 * risk:
                reward = 2 * risk
                resist = price + reward
            rr_ratio = reward / risk if risk > 0 else 0
            if rr_ratio < 1.5:
                signal_type = 'HOLD'
            else:
                signal_type = 'BUY'
                open_trade(ticker, price, stop_loss, resist, rr_ratio)
        elif sell_ok:
            signal_type = 'SELL'
            stop_loss   = price - 2 * atr
            resist      = price
            rr_ratio    = 0
        else:
            signal_type = 'HOLD'
            stop_loss   = price - 2 * atr
            resist      = latest['resist_20']
            rr_ratio    = 0

        active_trade    = get_active_trade(ticker)
        t_plus, pnl_pct = (0, 0.0)
        entry_date      = get_last_trading_date(ticker)
        if active_trade:
            t_plus, pnl_pct = calc_trade_stats(active_trade, price)
            entry_date      = active_trade['entry_date']

        now       = datetime.now().strftime('%H:%M:%S - %d/%m/%Y')
        pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"

        if signal_type == 'BUY':
            msg = (
                f"{ticker.upper()} - {company['name']} ({company['exchange']})\n"
                f"{now}\n\n"
                f"🟠 SMARTTRADE | Khuyến nghị tự động\n"
                f"✅ Vị thế hiện tại: MUA\n"
                f"- Xu hướng: TĂNG\n"
                f"- Ngày mua: {entry_date}\n"
                f"- Giá mua: {price * 1000:,.0f} đ\n"
                f"- Lãi/Lỗ: {pnl_pct:+.1f}% {pnl_emoji}\n"
                f"- Số phiên: T + {t_plus}\n"
                f"- Khối lượng: {latest['volume_ratio']:.2f}x Volume MA20\n\n"
                f"🟣 SMARTSCORE | Chấm điểm DN: {tong}\n"
                f"- Điểm Định giá: {dinh_gia}\n"
                f"- Điểm Chất lượng: {chat_luong}\n"
                f"- Điểm Động lượng: {dong_luong}\n"
                f"- Nhóm ngành: {company['sector']}\n"
                f"- Phân ngành: {company['sub_sector']}\n"
                f"- Vốn hóa: {company['market_cap']:,.0f} tỷ đồng\n"
            )
            if fa_data:
                msg += (
                    f"- EPS growth: {float(fa_data.get('EPS_growth_yoy', 0)):.1f}% | "
                    f"P/E: {float(fa_data.get('pe', 0)):.1f} | "
                    f"ROE: {float(fa_data.get('ROE', 0)):.1f}%\n"
                )
            msg += (
                f"\n💡 QUẢN TRỊ VỊ THẾ:\n"
                f"- Cắt lỗ động (2x ATR): {stop_loss * 1000:,.0f} đ ({(stop_loss/price-1)*100:.1f}%)\n"
                f"- Chốt lời kỳ vọng: {resist * 1000:,.0f} đ (+{(resist/price-1)*100:.1f}%)\n"
                f"- Tỷ lệ Risk/Reward: 1 : {rr_ratio:.2f}\n"
            )

        elif signal_type == 'SELL':
            msg = (
                f"{ticker.upper()} - {company['name']} ({company['exchange']})\n"
                f"{now}\n\n"
                f"🟠 SMARTTRADE | Khuyến nghị tự động\n"
                f"🔴 Vị thế hiện tại: BÁN\n"
                f"- Xu hướng: GIẢM\n"
                f"- Ngày tín hiệu: {entry_date}\n"
                f"- Giá hiện tại: {price * 1000:,.0f} đ\n"
                f"- Lãi/Lỗ: {pnl_pct:+.1f}% {pnl_emoji}\n"
                f"- Số phiên: T + {t_plus}\n\n"
                f"🟣 SMARTSCORE | Chấm điểm DN: {tong}\n"
                f"- Điểm Định giá: {dinh_gia}\n"
                f"- Điểm Chất lượng: {chat_luong}\n"
                f"- Điểm Động lượng: {dong_luong}\n"
                f"- Nhóm ngành: {company['sector']}\n"
                f"- RSI(14): {latest['RSI_14']:.1f} — Vùng quá mua\n"
                f"- ATR(14): {atr * 1000:,.0f}\n"
            )

        else:
            msg = (
                f"{ticker.upper()} - {company['name']} ({company['exchange']})\n"
                f"{now}\n\n"
                f"🟠 SMARTTRADE | Khuyến nghị tự động\n"
                f"🟡 Vị thế hiện tại: THEO DÕI\n"
                f"- Giá hiện tại: {price * 1000:,.0f} đ\n"
                f"- RSI(14): {latest['RSI_14']:.1f}\n"
                f"- EMA20: {latest['EMA20'] * 1000:,.0f} | EMA50: {latest['EMA50'] * 1000:,.0f}\n"
                f"- Volume ratio: {latest['volume_ratio']:.2f}x\n\n"
                f"🟣 SMARTSCORE | Chấm điểm DN: {tong}\n"
                f"- Điểm Định giá: {dinh_gia}\n"
                f"- Điểm Chất lượng: {chat_luong}\n"
                f"- Điểm Động lượng: {dong_luong}\n"
                f"- Nhóm ngành: {company['sector']}\n"
                f"📌 Chưa có tín hiệu rõ ràng — Tiếp tục theo dõi\n"
            )

        return msg, None

    except Exception as e:
        return None, str(e)

async def send_signals(signals):
    bot = Bot(token=TELEGRAM_TOKEN)
    if not signals:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 Hôm nay không có tín hiệu nào.")
        return

    buy  = [s for s in signals if s['signal_type'] == 'BUY']
    sell = [s for s in signals if s['signal_type'] == 'SELL']
    now  = datetime.now().strftime('%H:%M:%S - %d/%m/%Y')

    msg = (
        f"📊 TỔNG KẾT TÍN HIỆU\n"
        f"⏱ {now}\n"
        f"{'='*30}\n"
        f"🟢 Mua: {len(buy)} mã\n"
        f"🔴 Bán: {len(sell)} mã\n"
        f"📌 Tổng: {len(signals)} tín hiệu\n"
    )
    if buy:
        msg += "\nDanh sách MUA:\n"
        for s in buy:
            msg += f"  • {s['ticker']} — {s['price'] * 1000:,.0f} đ\n"
    if sell:
        msg += "\nDanh sách BÁN:\n"
        for s in sell:
            msg += f"  • {s['ticker']} — {s['price'] * 1000:,.0f} đ\n"

    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)

    for s in signals:
        detail_msg, _ = get_signal_for_ticker(s['ticker'])
        if detail_msg:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=detail_msg)
            await asyncio.sleep(1)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Chào mừng đến với FinTech Stock Bot!\n\n"
        "Các lệnh:\n"
        "/stock FPT — Xem tín hiệu mã FPT\n"
        "/today — Tín hiệu hôm nay\n"
        "/portfolio — Danh mục đang nắm giữ\n"
        "/help — Hướng dẫn\n"
    )

async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Ví dụ: /stock FPT")
        return
    ticker = context.args[0].upper()
    await update.message.reply_text(f"🔍 Đang tra cứu {ticker}...")
    msg, error = get_signal_for_ticker(ticker)
    if error:
        await update.message.reply_text(f"❌ {ticker}: {error}")
    else:
        await update.message.reply_text(msg)

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open('data/signals.json', 'r', encoding='utf-8') as f:
            signals = json.load(f)
        if not signals:
            await update.message.reply_text("📭 Hôm nay không có tín hiệu nào.")
            return
        msg = "📊 TÍN HIỆU HÔM NAY\n" + "="*30 + "\n"
        for s in signals:
            emoji = "🟢" if s['signal_type'] == 'BUY' else "🔴"
            msg  += f"{emoji} {s['ticker']} — {s['signal_type']} — {s['price'] * 1000:,.0f} đ\n"
        await update.message.reply_text(msg)
    except:
        await update.message.reply_text("❌ Chưa có dữ liệu hôm nay.")

async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history     = load_trade_history()
    open_trades = [t for t in history if t['status'] == 'OPEN']

    if not open_trades:
        await update.message.reply_text("📭 Chưa có vị thế nào đang mở.")
        return

    msg = "💼 DANH MỤC ĐANG NẮM GIỮ\n" + "="*30 + "\n"
    for t in open_trades:
        try:
            conn = sqlite3.connect('data/market_data.db')
            df   = pd.read_sql_query(f"""
                SELECT close FROM historical_ohlcv
                WHERE symbol='{t['ticker']}'
                ORDER BY date DESC LIMIT 1
            """, conn)
            conn.close()
            current_price = float(df['close'].iloc[0])
        except:
            current_price = t['entry_price']

        t_plus, pnl = calc_trade_stats(t, current_price)
        emoji = "🟢" if pnl >= 0 else "🔴"
        msg += (
            f"\n{emoji} {t['ticker']}\n"
            f"- Ngày mua: {t['entry_date']}\n"
            f"- Giá vào: {t['entry_price'] * 1000:,.0f} đ\n"
            f"- Giá hiện tại: {current_price * 1000:,.0f} đ\n"
            f"- Lãi/Lỗ: {pnl:+.1f}% {emoji}\n"
            f"- Số phiên: T+{t_plus}\n"
            f"- Cắt lỗ: {t['stop_loss'] * 1000:,.0f} đ\n"
            f"- Chốt lời: {t['take_profit'] * 1000:,.0f} đ\n"
        )
    await update.message.reply_text(msg)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 HƯỚNG DẪN SỬ DỤNG\n\n"
        "/stock <mã> — Tra cứu tín hiệu\n"
        "  Ví dụ: /stock KLB\n\n"
        "/today — Tín hiệu hôm nay\n"
        "/portfolio — Danh mục đang nắm giữ\n"
        "/start — Giới thiệu bot\n"
    )

async def run_bot():
    with open('data/signals.json', 'r', encoding='utf-8') as f:
        signals = json.load(f)
    print(f"Gửi {len(signals)} tín hiệu lên Telegram...")
    await send_signals(signals)
    print("Gửi xong!")

def start_bot_polling():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("stock",     cmd_stock))
    app.add_handler(CommandHandler("today",     cmd_today))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("help",      cmd_help))
    print("🤖 Bot đang lắng nghe lệnh...")
    app.run_polling()