# 🤖 FinTech Stock Bot — Telegram Bot Tín Hiệu Đầu Tư Chứng Khoán Việt Nam

> Chiến lược: **Hybrid CANSLIM + Momentum & ATR Risk Management**  
> Môn: Tài chính — UEL | Nhóm FinTech Bot

---

## 📋 Giới thiệu

FinTech Stock Bot là hệ thống tự động phân tích và phát tín hiệu Mua/Bán cổ phiếu trên thị trường chứng khoán Việt Nam qua Telegram. Hệ thống sử dụng chiến lược 3 lớp lọc kết hợp Phân tích Cơ bản (FA) và Phân tích Kỹ thuật (TA).

---

## 🏗️ Kiến trúc hệ thống

```
[ TOÀN BỘ CỔ PHIẾU SÀN (~1500 mã) ]
            │
            ▼
[ LỚP 1: FA FILTER — fa_strategy.py ]
  - ROE > 15%
  - D/E < 1.2
  - EPS tăng trưởng > 15% & tăng tốc
  - 3 năm liên tiếp lợi nhuận dương
            │
            ▼  watch_list.json (~10-20 mã)
            │
            ▼
[ LỚP 2: LIQUIDITY FILTER ]
  - Turnover >= 5 tỷ VNĐ/phiên
  - Volume MA20 >= 100,000 CP/phiên
            │
            ▼
[ LỚP 3: TA & ATR RISK — ta_strategy.py ]
  - Market Regime: VN-Index >= MA50
  - EMA20 > EMA50 & RSI(14) > 50
  - Volume >= 1.5x MA20
  - Stop-loss = Price - 2xATR(14)
  - R/R Ratio >= 1.5
            │
            ▼
[ TELEGRAM BOT — telegram_bot.py ]
```

---

## 📁 Cấu trúc thư mục

```
fintech_bot/
├── data/
│   ├── financial_data.json     # Dữ liệu BCTC 1500+ mã
│   ├── market_data.db          # Dữ liệu giá lịch sử
│   ├── watch_list.json         # Output Lớp 1+2
│   ├── signals.json            # Tín hiệu hôm nay
│   ├── trade_history.json      # Lịch sử lệnh
│   └── backtest_result.json    # Kết quả backtest
├── strategies/
│   ├── fa_strategy.py          # Bộ lọc FA + Liquidity
│   └── ta_strategy.py          # Bộ lọc TA + ATR
├── backtest/
│   └── backtest_engine.py      # Backtest engine
├── bot/
│   └── telegram_bot.py         # Telegram Bot
├── config.py                   # Cấu hình & thông số
├── main.py                     # Entry point
└── README.md
```

---

## ⚙️ Cài đặt

### Yêu cầu
- Python 3.11+
- Windows/Mac/Linux

### Bước 1 — Clone hoặc tải về

```bash
git clone https://github.com/thaitran3936-hub/fintech-stock-signal-bot
cd fintech-stock-signal-bot
```

### Bước 2 — Tạo môi trường ảo

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### Bước 3 — Cài thư viện

```bash
pip install requests pandas ta python-telegram-bot schedule vnstock
```

### Bước 4 — Cấu hình

Mở file `config.py`, điền token và chat ID Telegram:

```python
TELEGRAM_TOKEN   = "your_bot_token_here"
TELEGRAM_CHAT_ID = "your_chat_id_here"
```

> Lấy token từ @BotFather, lấy Chat ID từ @getmyid_bot

### Bước 5 — Chạy bot

```bash
python main.py
```

---

## 🤖 Các lệnh Telegram

| Lệnh | Chức năng |
|---|---|
| `/start` | Giới thiệu bot |
| `/stock FPT` | Tra cứu tín hiệu mã FPT |
| `/today` | Xem tín hiệu hôm nay |
| `/portfolio` | Danh mục đang nắm giữ |
| `/help` | Hướng dẫn sử dụng |

---

## 📊 Kết quả Backtest

Chiến lược CANSLIM + ATR trên 14 mã đã qua lọc FA:

| Chỉ số | Kết quả |
|---|---|
| Tổng giao dịch | 118 |
| Win Rate | **61.9%** |
| Tổng lợi nhuận | **+165.6%** |
| TB mỗi giao dịch | +1.4% |
| Giao dịch tốt nhất | +25.3% |
| Giao dịch tệ nhất | -21.0% |

---

## 📐 Công thức tính toán

### ATR Dynamic Stop-loss
```
Stop-loss = Giá mua - 2 x ATR(14)
```

### R/R Ratio
```
R/R = (Resistance_20 - Giá mua) / (Giá mua - Stop-loss) >= 1.5
```

### SMARTSCORE
```
Điểm Động lượng  = RSI x 0.4 + EMA_score x 0.4 + Volume_score x 0.2
Điểm Chất lượng  = ROE x 0.4 + DE_score x 0.3 + EPS_growth x 0.3
Điểm Định giá    = PE_score x 0.5 + PB_score x 0.5
Tổng             = Định giá x 0.3 + Chất lượng x 0.35 + Động lượng x 0.35
```

---

## 📦 Thư viện sử dụng

| Thư viện | Mục đích |
|---|---|
| `pandas` | Xử lý dữ liệu |
| `ta` | Tính chỉ báo kỹ thuật |
| `python-telegram-bot` | Kết nối Telegram |
| `requests` | Gọi SSI API |
| `vnstock` | Lấy thông tin ngành |
| `schedule` | Lên lịch tự động |
| `sqlite3` | Đọc market_data.db |

---

## 👥 Nhóm thực hiện

| Thành viên | Vai trò |
|---|---|
| Thành viên 3 | TA Strategy, Backtest, Market Data |
| Thành viên 4 | FA Strategy, Data Pipeline, Telegram Bot |

---

## 📌 Lưu ý

- Bot tự động chạy lúc **09:00 mỗi ngày** (thứ 2 - thứ 6)
- Dữ liệu BCTC cập nhật theo quý từ file `financial_data.json`
- Dữ liệu giá từ `market_data.db` do TV3 cập nhật hàng ngày
- Thông tin chỉ mang tính **tham khảo**, không phải lời khuyên đầu tư
