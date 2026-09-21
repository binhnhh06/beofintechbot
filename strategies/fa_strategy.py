import json
import pandas as pd
from vnstock import Vnstock
import time
from config import *

def map_sector_from_vnstock(sector_raw):
    s = str(sector_raw).lower()
    if any(x in s for x in ['technology', 'software', 'telecom']):
        return 'Cong nghe'
    if any(x in s for x in ['energy', 'oil', 'gas']):
        return 'Dau khi'
    if any(x in s for x in ['bank', 'financial', 'insurance']):
        return 'Ngan hang'
    if any(x in s for x in ['real estate']):
        return 'Bat dong san'
    if any(x in s for x in ['construction', 'materials']):
        return 'Xay dung'
    if any(x in s for x in ['food', 'beverage']):
        return 'Thuc pham'
    if any(x in s for x in ['retail']):
        return 'Ban le'
    if any(x in s for x in ['chemicals']):
        return 'Hoa chat'
    if any(x in s for x in ['industrial', 'goods']):
        return 'Cong nghiep'
    return sector_raw

def get_sector_from_vnstock(ticker):
    try:
        stock  = Vnstock().stock(symbol=ticker, source='VCI')
        info   = stock.company.overview()
        sector = info['sector'].iloc[0] if 'sector' in info.columns else 'Khac'
        return map_sector_from_vnstock(sector)
    except:
        return 'Khac'

def check_3_year_positive(history):
    """Kiểm tra 3 năm liên tiếp dương lợi nhuận"""
    try:
        recent = [h for h in history if h.get('eps') and float(h['eps'] or 0) > 0]
        return len(recent) >= 3
    except:
        return False

def check_eps_acceleration(history):
    """Kiểm tra tăng tốc EPS"""
    try:
        growth_list = [h.get('eps_growth_yoy') for h in history
                       if h.get('eps_growth_yoy') is not None]
        if len(growth_list) >= 2:
            return float(growth_list[-1]) > float(growth_list[-2])
        return False
    except:
        return False

def load_financial_data():
    """Đọc file financial_data.json mới có lịch sử"""
    with open('data/financial_data.json', 'r', encoding='utf-8') as f:
        raw = json.load(f)

    records = []
    for ticker, info in raw.items():
        history = info.get('history', [])

        # Lay du lieu moi nhat
        latest = history[-1] if history else {}

        records.append({
            'ticker':              ticker,
            'sector_tag':          SECTOR_MAP.get(ticker, 'Khac'),
            'ROE':                 float(latest.get('roe') or 0),
            'DE_ratio':            float(latest.get('debt_equity') or 0),
            'EPS_growth_yoy':      float(latest.get('eps_growth_yoy') or 0),
            'pe':                  float(latest.get('pe') or 0),
            'pb':                  float(latest.get('pb') or 0),
            'net_margin':          float(latest.get('net_margin') or 0),
            'three_year_positive': check_3_year_positive(history),
            'eps_accelerating':    check_eps_acceleration(history),
            'updated_at':          info.get('updated_at', ''),
        })

    df = pd.DataFrame(records)
    print(f"Đọc xong {len(df)} mã từ financial_data.json")
    return df

def filter_fa(df):
    """Lọc FA theo tiêu chí CANSLIM đầy đủ"""
    mask = (
        (df['ROE'] > FA_ROE_MIN) &
        (df['DE_ratio'] < FA_DE_MAX) &
        (df['EPS_growth_yoy'] > FA_NET_PROFIT_GROWTH_MIN) &
        (df['three_year_positive'] == True) &
        (df['eps_accelerating'] == True)
    )
    result = df[mask].copy()
    print(f"Qua FA Filter: {len(result)} mã")
    return result

def enrich_sector(df):
    """Lấy ngành từ vnstock cho mã chưa có"""
    print("\nĐang lấy thông tin ngành...")
    for i, row in df.iterrows():
        if row['sector_tag'] == 'Khac':
            sector = get_sector_from_vnstock(row['ticker'])
            df.at[i, 'sector_tag'] = sector
            print(f"  {row['ticker']}: {sector}")
            time.sleep(2)
    return df

def export_watch_list(df):
    """Xuất watch_list.json"""
    cols = ['ticker', 'sector_tag', 'ROE', 'DE_ratio',
            'EPS_growth_yoy', 'pe', 'pb', 'net_margin',
            'three_year_positive', 'eps_accelerating', 'updated_at']

    watch = df[cols].to_dict(orient='records')

    with open('data/watch_list.json', 'w', encoding='utf-8') as f:
        json.dump(watch, f, ensure_ascii=False, indent=2)

    print(f"\nDanh sách mã qua lọc:")
    for item in watch:
        acc = "✅" if item['eps_accelerating'] else "⚠️"
        print(f"  {item['ticker']} | Ngành: {item['sector_tag']} | ROE: {item['ROE']:.1f}% | EPS: {item['EPS_growth_yoy']:.1f}% {acc}")

    return watch

def run_fa_filter():
    print("=" * 50)
    print("BẮT ĐẦU FA FILTER")
    print("=" * 50)

    df    = load_financial_data()
    df    = filter_fa(df)
    df    = enrich_sector(df)
    watch = export_watch_list(df)

    print("=" * 50)
    print(f"XONG! {len(watch)} mã vào watch_list.json")
    print("=" * 50)
    return watch

if __name__ == '__main__':
    run_fa_filter()