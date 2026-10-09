import os
from dotenv import load_dotenv

# Carrega .env local (desenvolvimento)
# No Discloud as vars vêm do ambiente automaticamente
load_dotenv()

# ── TELEGRAM ──────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Usuários autorizados a usar comandos administrativos (/radar, /set, /setchat)
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",")
    if x.lstrip("-").isdigit()
}

# ── POLLING ───────────────────────────────────────────────────
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "30"))

# ── FILTROS ───────────────────────────────────────────────────
MCAP_MIN       = int(os.getenv("MCAP_MIN",        "10000000"))
MCAP_MAX       = int(os.getenv("MCAP_MAX",        "100000000"))
MIN_VOL_24H    = float(os.getenv("MIN_VOL_24H",   "500000"))

# ── SCANNER ───────────────────────────────────────────────────
SCORE_MINIMO     = int(os.getenv("SCORE_MINIMO",   "5"))
TOP_N_MOEDAS     = int(os.getenv("TOP_N_MOEDAS",   "10"))
TIMEFRAME_PADRAO = os.getenv("TIMEFRAME_PADRAO",    "4h")
SCAN_WORKERS     = int(os.getenv("SCAN_WORKERS",   "8"))  # requisições paralelas no scan

# ── COINGECKO ─────────────────────────────────────────────────
COINGECKO_BASE    = "https://api.coingecko.com/api/v3"
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")  # opcional (chave demo gratuita)

# ── FLAG de validação (sem raise aqui para não crashar o boot) ─
TOKEN_OK = bool(TELEGRAM_BOT_TOKEN)
