import sqlite3
import pandas as pd
import ta

conn = sqlite3.connect('data/market_data.db')
df = pd.read_sql_query("""
    SELECT date, high, low, close, volume
    FROM historical_ohlcv
    WHERE symbol = 'KLB'
    ORDER BY date ASC
""", conn)
conn.close()

df['price']        = df['close']
df['EMA20']        = ta.trend.ema_indicator(df['price'], window=20)
df['EMA50']        = ta.trend.ema_indicator(df['price'], window=50)
df['MA50']         = df['price'].rolling(50).mean()
df['RSI_14']       = ta.momentum.rsi(df['price'], window=14)
df['volume_MA20']  = df['volume'].rolling(20).mean()
df['volume_ratio'] = df['volume'] / df['volume_MA20']
df = df.dropna()

latest = df.iloc[-1]
print(f"Ngày         : {df['date'].iloc[-1]}")
print(f"Giá          : {latest['price']}")
print(f"EMA20 > EMA50: {latest['EMA20'] > latest['EMA50']}")
print(f"RSI          : {latest['RSI_14']:.2f} (cần > 50)")
print(f"Price>=MA50  : {latest['price'] >= latest['MA50']}")
print(f"Volume ratio : {latest['volume_ratio']:.2f} (cần >= 1.5)")