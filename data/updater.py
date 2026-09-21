import requests
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}

def get_last_date(ticker, conn):
    """Lấy ngày dữ liệu mới nhất trong DB"""
    try:
        df = pd.read_sql_query(f"""
            SELECT MAX(date) as last_date FROM historical_ohlcv
            WHERE symbol = '{ticker}'
        """, conn)
        return df['last_date'].iloc[0]
    except:
        return None

def fetch_price_ssi(ticker, from_date, to_date):
    """Lấy giá từ SSI API"""
    try:
        url = (
            f"https://iboard-api.ssi.com.vn/statistics/company/ssmi/stock-info"
            f"?symbol={ticker}&fromDate={from_date}&toDate={to_date}&page=1&pageSize=100"
        )
        r    = requests.get(url, headers=headers, timeout=10)
        data = r.json().get('data', [])
        if not data:
            return None

        rows = []
        for item in data:
                    rows.append({
                'symbol': ticker,
                'date':   datetime.strptime(item['tradingDate'], '%d/%m/%Y').strftime('%Y-%m-%d'),
                'open':   float(item.get('open', 0)) / 1000,
                'high':   float(item.get('high', 0)) / 1000,
                'low':    float(item.get('low', 0)) / 1000,
                'close':  float(item.get('close', 0)) / 1000,
                'volume': float(item.get('volume', 0)),
            })
        return rows
    except:
        return None

def update_prices():
    """Cập nhật giá cho tất cả mã trong DB"""
    print("=" * 50)
    print("BẮT ĐẦU CẬP NHẬT GIÁ")
    print("=" * 50)

    conn = sqlite3.connect('data/market_data.db')

    # Lay danh sach ma can cap nhat
    df_symbols = pd.read_sql_query("""
        SELECT DISTINCT symbol FROM historical_ohlcv
    """, conn)
    tickers = df_symbols['symbol'].tolist()
    print(f"Cập nhật {len(tickers)} mã...")

    today    = datetime.now().strftime('%d/%m/%Y')
    updated  = 0
    skipped  = 0

    for ticker in tickers:
        last_date = get_last_date(ticker, conn)

        if last_date:
            # Lay tu ngay tiep theo sau ngay cuoi cung
            last_dt   = datetime.strptime(last_date, '%Y-%m-%d')
            from_date = (last_dt + timedelta(days=1)).strftime('%d/%m/%Y')
        else:
            from_date = '01/01/2026'

        # Neu da cap nhat roi thi bo qua
        if from_date == datetime.now().strftime('%d/%m/%Y') and datetime.now().hour < 15:
            skipped += 1
            continue

        rows = fetch_price_ssi(ticker, from_date, today)
        if not rows:
            skipped += 1
            continue

        # Them vao DB
        for row in rows:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO historical_ohlcv
                    (symbol, date, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    row['symbol'], row['date'],
                    row['open'], row['high'],
                    row['low'], row['close'],
                    row['volume']
                ))
            except:
                pass

        conn.commit()
        updated += 1

    conn.close()
    print(f"Cập nhật xong: {updated} mã mới | {skipped} mã bỏ qua")
    print("=" * 50)

if __name__ == '__main__':
    update_prices()