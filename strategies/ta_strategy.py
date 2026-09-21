import sqlite3
import pandas as pd
import ta
import json
from config import *

def get_price_data(ticker):
    """Lấy dữ liệu giá từ market_data.db"""
    try:
        conn = sqlite3.connect('data/market_data.db')
        query = f"""
            SELECT date, open, high, low, close, volume 
            FROM historical_ohlcv 
            WHERE symbol = '{ticker}'
            ORDER BY date ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if len(df) < 50:
            return None

        df['date']   = pd.to_datetime(df['date'])
        df           = df.rename(columns={'close': 'price'})
        df['ticker'] = ticker
        return df
    except:
        return None

def calc_indicators(df):
    """Tính các chỉ báo kỹ thuật"""
    df['EMA20']        = ta.trend.ema_indicator(df['price'], window=20)
    df['EMA50']        = ta.trend.ema_indicator(df['price'], window=50)
    df['RSI_14']       = ta.momentum.rsi(df['price'], window=14)
    df['volume_MA20']  = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_MA20']
    df['high_20']      = df['high'].rolling(20).max().shift(1)  # Đỉnh 20 phiên TRƯỚC
    return df.dropna()

def calc_rs_score(ticker_df, vnindex_df):
    """Tính RS Score so với VN-Index"""
    try:
        periods        = min(252, len(ticker_df) - 1, len(vnindex_df) - 1)
        ticker_return  = (ticker_df['price'].iloc[-1] / ticker_df['price'].iloc[-periods] - 1) * 100
        vnindex_return = (vnindex_df['price'].iloc[-1] / vnindex_df['price'].iloc[-periods] - 1) * 100
        return round(ticker_return - vnindex_return, 2)
    except:
        return 0

def check_market(vnindex_df):
    """Kiểm tra xu hướng VN-Index — Market Filter"""
    latest = vnindex_df.iloc[-1]
    prev   = vnindex_df.iloc[-5]

    tren_ema20 = latest['price'] > latest['EMA20']
    tren_ema50 = latest['price'] > latest['EMA50']
    rsi_ok     = latest['RSI_14'] > 45
    dang_tang  = latest['price'] > prev['price']

    diem = sum([tren_ema20, tren_ema50, rsi_ok, dang_tang])

    if diem >= 3:
        market_ok  = True
        trang_thai = "✅ TĂNG"
    elif diem == 2:
        market_ok  = True
        trang_thai = "⚠️ TRUNG TÍNH"
    else:
        market_ok  = False
        trang_thai = "🔴 GIẢM — Không phát lệnh MUA"

    print(f"\nMarket Filter — VN-Index:")
    print(f"  Trạng thái   : {trang_thai}")
    print(f"  Giá hiện tại : {latest['price']:.2f}")
    print(f"  EMA20        : {latest['EMA20']:.2f}")
    print(f"  EMA50        : {latest['EMA50']:.2f}")
    print(f"  RSI(14)      : {latest['RSI_14']:.2f}")
    print(f"  Điểm         : {diem}/4\n")

    return market_ok

def generate_signal(df, market_ok, rs_score=0):
    """Phát tín hiệu BUY/SELL"""
    latest = df.iloc[-1]

    buy_ok = (
        market_ok and
        rs_score >= 0 and
        latest['EMA20'] > latest['EMA50'] and
        latest['RSI_14'] > TA_RSI_BUY and
        latest['price'] > latest['high_20'] and
        latest['volume_ratio'] >= TA_VOLUME_RATIO_MIN
    )

    sell_ok = latest['RSI_14'] > TA_RSI_SELL

    if buy_ok:
        signal_type = 'BUY'
    elif sell_ok:
        signal_type = 'SELL'
    else:
        return None

    return {
        'ticker':        latest['ticker'],
        'signal_type':   signal_type,
        'price':         round(float(latest['price']), 2),
        'date':          str(latest['date'].date()),
        'strategy_name': 'CANSLIM + Momentum',
        'rs_score':      rs_score,
        'ta_criteria': {
            'EMA20':        round(float(latest['EMA20']), 2),
            'EMA50':        round(float(latest['EMA50']), 2),
            'RSI_14':       round(float(latest['RSI_14']), 2),
            'volume_ratio': round(float(latest['volume_ratio']), 2),
        },
        'stop_loss':   round(float(latest['price']) * TA_STOP_LOSS_PCT, 2),
        'take_profit': round(float(latest['price']) * TA_TAKE_PROFIT_PCT, 2),
    }

def run_ta_filter():
    """Chạy toàn bộ TA Filter"""
    print("=" * 50)
    print("BẮT ĐẦU TA FILTER")
    print("=" * 50)

    with open('data/watch_list.json', 'r', encoding='utf-8') as f:
        watch_list = json.load(f)
    tickers = [item['ticker'] for item in watch_list]
    print(f"Nhận {len(tickers)} mã từ watch_list.json")

    vnindex_df = get_price_data('VNINDEX')
    if vnindex_df is not None:
        vnindex_df = calc_indicators(vnindex_df)
        market_ok  = check_market(vnindex_df)
    else:
        print("⚠️ Không có dữ liệu VN-Index — mặc định thị trường OK")
        market_ok  = True
        vnindex_df = None

    signals = []
    for ticker in tickers:
        df = get_price_data(ticker)
        if df is None:
            print(f"  {ticker} -> Bỏ qua (không đủ dữ liệu)")
            continue

        df       = calc_indicators(df)
        rs_score = calc_rs_score(df, vnindex_df) if vnindex_df is not None else 0
        signal   = generate_signal(df, market_ok, rs_score)

        if signal:
            signals.append(signal)
            print(f"  {ticker} -> {signal['signal_type']} | Giá: {signal['price']} | RSI: {signal['ta_criteria']['RSI_14']} | RS: {rs_score}")
        else:
            print(f"  {ticker} -> HOLD")

    with open('data/signals.json', 'w', encoding='utf-8') as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)

    print("=" * 50)
    print(f"XONG! {len(signals)} tín hiệu -> data/signals.json")
    print("=" * 50)
    return signals

if __name__ == '__main__':
    run_ta_filter()