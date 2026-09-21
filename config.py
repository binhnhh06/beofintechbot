# ── Telegram ──────────────────────────────────────────
TELEGRAM_TOKEN   = "8707908079:AAGiGD3I4Rvj0xO1MIK685DWZrEqP2aIGDU"
TELEGRAM_CHAT_ID = "8813239803"

# ── SSI API ───────────────────────────────────────────
SSI_BASE_URL = "https://iboard-api.ssi.com.vn/statistics/company/ssmi"
SSI_HEADERS  = {
    "Accept":     "application/json",
    "User-Agent": "Mozilla/5.0"
}

# ── FA Filter ─────────────────────────────────────────
FA_ROE_MIN               = 15
FA_DE_MAX                = 1.2
FA_NET_PROFIT_GROWTH_MIN = 15
FA_REVENUE_GROWTH_MIN    = 15

# ── Liquidity Filter ──────────────────────────────────
LIQUIDITY_TURNOVER_MIN    = 5_000_000_000
LIQUIDITY_VOLUME_MA20_MIN = 100_000
LIQUIDITY_FREE_FLOAT_MIN  = 10

# ── TA Filter ─────────────────────────────────────────
TA_RSI_BUY          = 50
TA_RSI_SELL         = 70
TA_VOLUME_RATIO_MIN = 1.5
TA_STOP_LOSS_PCT    = 0.94
TA_TAKE_PROFIT_PCT  = 1.12

# ── Danh sách mã ──────────────────────────────────────
TICKER_LIST = [
    "FPT", "CMG", "VGI",
    "GAS", "PVS", "PLX",
    "VCB", "TCB", "MBB", "ACB",
]

SECTOR_MAP = {
    "FPT": "Cong nghe", "CMG": "Cong nghe", "VGI": "Cong nghe",
    "GAS": "Dau khi",   "PVS": "Dau khi",   "PLX": "Dau khi",
    "VCB": "Ngan hang", "TCB": "Ngan hang",
    "MBB": "Ngan hang", "ACB": "Ngan hang",
}