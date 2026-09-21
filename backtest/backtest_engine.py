import sqlite3
import pandas as pd
import ta
import json
from config import *

def get_price_data(ticker):
    try:
        conn = sqlite3.connect('data/market_data.db')
        query = f"""
            SELECT date, high, low, close, volume
            FROM historical_ohlcv
            WHERE symbol = '{ticker}'
            ORDER BY date ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        if len(df) < 50:
            return None
        df['date']  = pd.to_datetime(df['date'])
        df['price'] = df['close']
        return df
    except:
        return None

def calc_indicators(df):
    df['EMA20']        = ta.trend.ema_indicator(df['price'], window=20)
    df['EMA50']        = ta.trend.ema_indicator(df['price'], window=50)
    df['MA50']         = df['price'].rolling(50).mean()
    df['RSI_14']       = ta.momentum.rsi(df['price'], window=14)
    df['ATR_14']       = ta.volatility.average_true_range(df['high'], df['low'], df['price'], window=14)
    df['volume_MA20']  = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_MA20']
    df['resist_20']    = df['high'].rolling(20).max().shift(1)
    return df.dropna()

def backtest_ticker(ticker, df):
    """Backtest 1 mã với ATR Stop-loss và R/R >= 1.5"""
    trades      = []
    position    = 0
    entry_price = 0
    entry_date  = None
    stop_loss   = 0
    take_profit = 0

    for i in range(1, len(df)):
        row   = df.iloc[i]
        price = row['price']
        atr   = row['ATR_14']

        if position == 0:
            buy_ok = (
                price >= row['MA50'] and
                row['EMA20'] > row['EMA50'] and
                row['RSI_14'] > TA_RSI_BUY and
                row['volume_ratio'] >= TA_VOLUME_RATIO_MIN
            )

            if buy_ok:
                sl     = price - 2 * atr
                risk   = price - sl
                resist = row['resist_20']
                reward = resist - price
                if reward < 2 * risk:
                    reward = 2 * risk
                    resist = price + reward
                rr = reward / risk if risk > 0 else 0

                if rr >= 1.5:
                    position    = 1
                    entry_price = price
                    entry_date  = row['date']
                    stop_loss   = sl
                    take_profit = resist

        elif position == 1:
            rsi_sell = row['RSI_14'] > TA_RSI_SELL

            if price <= stop_loss or price >= take_profit or rsi_sell:
                pnl = (price - entry_price) / entry_price * 100

                if price <= stop_loss:
                    exit_reason = 'Stop-loss'
                elif price >= take_profit:
                    exit_reason = 'Take-profit'
                else:
                    exit_reason = 'RSI overbought'

                trades.append({
                    'ticker':      ticker,
                    'entry_date':  str(entry_date.date()),
                    'exit_date':   str(row['date'].date()),
                    'entry_price': round(entry_price * 1000, 0),
                    'exit_price':  round(price * 1000, 0),
                    'pnl_%':       round(pnl, 2),
                    'result':      'WIN' if pnl > 0 else 'LOSS',
                    'exit_reason': exit_reason,
                })
                position    = 0
                entry_price = 0

    return trades

def run_backtest():
    print("=" * 50)
    print("BẮT ĐẦU BACKTEST — Chiến lược CANSLIM + ATR")
    print("=" * 50)

    with open('data/watch_list.json', 'r', encoding='utf-8') as f:
        watch_list = json.load(f)
    tickers = [item['ticker'] for item in watch_list]
    print(f"Backtest {len(tickers)} mã từ watch_list.json\n")

    all_trades = []
    for ticker in tickers:
        df = get_price_data(ticker)
        if df is None:
            print(f"  {ticker}: Bỏ qua (không đủ dữ liệu)")
            continue

        df     = calc_indicators(df)
        trades = backtest_ticker(ticker, df)
        all_trades.extend(trades)

        if trades:
            wins     = sum(1 for t in trades if t['result'] == 'WIN')
            avg_pnl  = sum(t['pnl_%'] for t in trades) / len(trades)
            print(f"  {ticker}: {len(trades)} GD | Win: {wins/len(trades)*100:.0f}% | Avg: {avg_pnl:+.1f}%")
        else:
            print(f"  {ticker}: Không có giao dịch")

    if not all_trades:
        print("\n⚠️ Không có giao dịch nào!")
        return

    total   = len(all_trades)
    wins    = sum(1 for t in all_trades if t['result'] == 'WIN')
    losses  = total - wins
    returns = [t['pnl_%'] for t in all_trades]

    # Phan tich ly do thoat lenh
    reasons = {}
    for t in all_trades:
        r = t['exit_reason']
        reasons[r] = reasons.get(r, 0) + 1

    print("\n" + "=" * 50)
    print("KẾT QUẢ BACKTEST TỔNG HỢP")
    print("=" * 50)
    print(f"Tổng giao dịch     : {total}")
    print(f"Thắng              : {wins} ({wins/total*100:.1f}%)")
    print(f"Thua               : {losses} ({losses/total*100:.1f}%)")
    print(f"Tổng lợi nhuận     : {sum(returns):.1f}%")
    print(f"TB mỗi giao dịch   : {sum(returns)/total:.1f}%")
    print(f"Tốt nhất           : +{max(returns):.1f}%")
    print(f"Tệ nhất            : {min(returns):.1f}%")
    print(f"\nLý do thoát lệnh:")
    for r, count in reasons.items():
        print(f"  {r}: {count} lần ({count/total*100:.0f}%)")
    print("=" * 50)

    result = {
        'summary': {
            'total_trades':  total,
            'win_rate':      round(wins/total*100, 1),
            'loss_rate':     round(losses/total*100, 1),
            'total_return':  round(sum(returns), 1),
            'avg_return':    round(sum(returns)/total, 1),
            'best_trade':    round(max(returns), 1),
            'worst_trade':   round(min(returns), 1),
            'exit_reasons':  reasons,
        },
        'trades': all_trades
    }

    with open('data/backtest_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("Lưu xong -> data/backtest_result.json")
    return result

if __name__ == '__main__':
    run_backtest()