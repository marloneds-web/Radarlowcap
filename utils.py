import os
from dotenv import load_dotenv

load_dotenv()

# ── TELEGRAM ──────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── POLLING ───────────────────────────────────────────────────
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "30"))
MAX_ALERTS_PER_CYCLE  = int(os.getenv("MAX_ALERTS_PER_CYCLE", "10"))

# ── FILTROS ───────────────────────────────────────────────────
MCAP_MIN      = int(os.getenv("MCAP_MIN",      "10000000"))
MCAP_MAX      = int(os.getenv("MCAP_MAX",      "100000000"))
MIN_VOL_24H   = float(os.getenv("MIN_VOL_24H", "500000"))
MIN_CHANGE_7D = float(os.getenv("MIN_CHANGE_7D","20"))
MIN_CHANGE_24H= float(os.getenv("MIN_CHANGE_24H","5"))

# ── SCANNER ───────────────────────────────────────────────────
SCORE_MINIMO      = int(os.getenv("SCORE_MINIMO",   "5"))
TOP_N_MOEDAS      = int(os.getenv("TOP_N_MOEDAS",   "10"))
TIMEFRAME_PADRAO  = os.getenv("TIMEFRAME_PADRAO",   "4h")

# ── COINGECKO ─────────────────────────────────────────────────
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

REQUIRED_FIELDS = [
    "id", "symbol", "name", "current_price",
    "market_cap", "total_volume",
    "price_change_percentage_24h_in_currency",
    "price_change_percentage_7d_in_currency",
]

# ── VALIDAÇÃO ─────────────────────────────────────────────────
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN não configurado no .env")
