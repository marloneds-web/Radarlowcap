import os
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "30"))
MAX_ALERTS_PER_CYCLE = int(os.getenv("MAX_ALERTS_PER_CYCLE", "20"))
MCAP_MIN = int(os.getenv("MCAP_MIN", "10000000"))
MCAP_MAX = int(os.getenv("MCAP_MAX", "100000000"))
MIN_VOL_24H = float(os.getenv("MIN_VOL_24H", "500000"))
MIN_CHANGE_7D = float(os.getenv("MIN_CHANGE_7D", "20"))
MIN_CHANGE_24H = float(os.getenv("MIN_CHANGE_24H", "5"))

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINS_MARKETS_ENDPOINT = (
    f"{COINGECKO_BASE}/coins/markets?vs_currency=usd&order=market_cap_asc"
    "&per_page=250&page={page}&price_change_percentage=24h,7d&sparkline=false"
)

REQUIRED_FIELDS = [
    "id", "symbol", "name", "current_price", "market_cap", "total_volume",
    "price_change_percentage_24h_in_currency",
    "price_change_percentage_7d_in_currency",
]