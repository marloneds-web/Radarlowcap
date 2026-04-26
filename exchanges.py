import requests
import pandas as pd
import numpy as np
import threading
import time
import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from utils import MIN_VOL_24H

log = logging.getLogger(__name__)

# ── Importação segura do websocket-client ─────────────────────
try:
    import websocket
    _WEBSOCKET_DISPONIVEL = True
except ImportError:
    _WEBSOCKET_DISPONIVEL = False
    log.warning(
        "⚠️ websocket-client não instalado. "
        "Liquidações OKX desativadas. Execute: pip install websocket-client"
    )

TIMEOUT = 10

TIMEFRAME_MAP = {
    "bitget": {
        "1m":"1min","5m":"5min","15m":"15min","30m":"30min",
        "1h":"1H","4h":"4H","1d":"1day","1w":"1week",
    },
    "bingx": {
        "1m":"1m","5m":"5m","15m":"15m","30m":"30m",
        "1h":"1h","4h":"4h","1d":"1d","1w":"1w",
    },
    "mexc": {
        "1m":"1m","5m":"5m","15m":"15m","30m":"30m",
        "1h":"60m","4h":"4h","1d":"1d","1w":"1W",
    },
}

COLUNAS = ["timestamp","open","high","low","close","volume"]

BITGET_BASE = "https://api.bitget.com"
BINGX_BASE  = "https://open-api.bingx.com"
MEXC_BASE   = "https://api.mexc.com"


def _normalizar_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["open","high","low","close","volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df.dropna()


# ══════════════════════════════════════════
# BITGET
# ══════════════════════════════════════════
def bitget_candles(symbol: str, timeframe="1h", limit=300) -> pd.DataFrame:
    tf  = TIMEFRAME_MAP["bitget"].get(timeframe, "1H")
    url = f"{BITGET_BASE}/api/v2/spot/market/candles"
    r   = requests.get(url, params={"symbol":symbol,"granularity":tf,"limit":min(limit,1000)}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "00000" or not data.get("data"):
        raise ValueError(f"Bitget: {data.get('msg','sem dados')}")
    rows = [{"timestamp":int(i[0]),"open":i[1],"high":i[2],"low":i[3],"close":i[4],"volume":i[5]}
            for i in data["data"]]
    return _normalizar_df(pd.DataFrame(rows, columns=COLUNAS))


def bitget_tickers() -> list:
    r = requests.get(f"{BITGET_BASE}/api/v2/spot/market/tickers", timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if d.get("code") != "00000":
        raise ValueError(f"Bitget tickers: {d.get('msg')}")
    return d.get("data", [])


# ══════════════════════════════════════════
# BINGX
# ══════════════════════════════════════════
def bingx_candles(symbol: str, timeframe="1h", limit=300) -> pd.DataFrame:
    sym = symbol.replace("USDT","-USDT").replace("--","-")
    tf  = TIMEFRAME_MAP["bingx"].get(timeframe, "1h")
    url = f"{BINGX_BASE}/openApi/spot/v2/market/kline"
    r   = requests.get(url, params={"symbol":sym,"interval":tf,"limit":min(limit,1000)}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0 or not data.get("data"):
        raise ValueError(f"BingX: {data.get('msg','sem dados')}")
    rows = [{"timestamp":int(i["time"]),"open":i["open"],"high":i["high"],
             "low":i["low"],"close":i["close"],"volume":i["volume"]}
            for i in data["data"]]
    return _normalizar_df(pd.DataFrame(rows, columns=COLUNAS))


def bingx_tickers() -> list:
    r = requests.get(f"{BINGX_BASE}/openApi/spot/v1/ticker/24hr", timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if d.get("code") != 0:
        raise ValueError(f"BingX tickers: {d.get('msg')}")
    return d.get("data", [])


# ══════════════════════════════════════════
# MEXC
# ══════════════════════════════════════════
def mexc_candles(symbol: str, timeframe="1h", limit=300) -> pd.DataFrame:
    tf  = TIMEFRAME_MAP["mexc"].get(timeframe, "60m")
    url = f"{MEXC_BASE}/api/v3/klines"
    r   = requests.get(url, params={"symbol":symbol,"interval":tf,"limit":min(limit,1000)}, timeout=TIMEOUT)
    r.raise_for_status()
    raw = r.json()
    if not isinstance(raw, list) or len(raw) == 0:
        raise ValueError(f"MEXC: sem dados para {symbol}")
    rows = [{"timestamp":int(i[0]),"open":i[1],"high":i[2],
             "low":i[3],"close":i[4],"volume":i[5]} for i in raw]
    return _normalizar_df(pd.DataFrame(rows, columns=COLUNAS))


def mexc_tickers() -> list:
    r = requests.get(f"{MEXC_BASE}/api/v3/ticker/24hr", timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if not isinstance(d, list):
        raise ValueError("MEXC tickers: resposta inesperada")
    return d


# ══════════════════════════════════════════
# INTERFACE UNIFICADA
# ══════════════════════════════════════════
def obter_candles(symbol: str, timeframe="1h", limit=300, exchange="auto") -> pd.DataFrame:
    mapa = {"bitget":bitget_candles,"mexc":mexc_candles,"bingx":bingx_candles}
    if exchange != "auto":
        return mapa[exchange](symbol, timeframe, limit)
    erros = {}
    for nome, func in [("bitget",bitget_candles),("mexc",mexc_candles),("bingx",bingx_candles)]:
        try:
            df = func(symbol, timeframe, limit)
            if df is not None and len(df) >= 50:
                return df
        except Exception as e:
            erros[nome] = str(e)
    raise ConnectionError(f"Todas exchanges falharam para {symbol}:\n"+"\n".join(f"  {k}: {v}" for k,v in erros.items()))


# ══════════════════════════════════════════
# LISTAR LOWCAPS
# ══════════════════════════════════════════
def listar_lowcaps(vol_min=MIN_VOL_24H, exchanges=None, apenas_usdt=True) -> list:
    if exchanges is None:
        exchanges = ["bitget","mexc","bingx"]
    resultados = []

    if "bitget" in exchanges:
        try:
            for t in bitget_tickers():
                sym = t.get("symbol","")
                if apenas_usdt and not sym.endswith("USDT"): continue
                vol = float(t.get("quoteVolume",0) or 0)
                if vol >= vol_min:
                    resultados.append({"symbol":sym,"exchange":"bitget","volume":vol,
                        "price":float(t.get("lastPr",0) or 0),
                        "change24h":round(float(t.get("change24h",0) or 0)*100,2)})
        except Exception as e:
            print(f"⚠️ Bitget: {e}")

    if "mexc" in exchanges:
        try:
            for t in mexc_tickers():
                sym = t.get("symbol","")
                if apenas_usdt and not sym.endswith("USDT"): continue
                vol = float(t.get("quoteVolume",0) or 0)
                if vol >= vol_min:
                    resultados.append({"symbol":sym,"exchange":"mexc","volume":vol,
                        "price":float(t.get("lastPrice",0) or 0),
                        "change24h":round(float(t.get("priceChangePercent",0) or 0),2)})
        except Exception as e:
            print(f"⚠️ MEXC: {e}")

    if "bingx" in exchanges:
        try:
            for t in bingx_tickers():
                sym = t.get("symbol","").replace("-","")
                if apenas_usdt and not sym.endswith("USDT"): continue
                vol = float(t.get("quoteVolume",0) or 0)
                if vol >= vol_min:
                    resultados.append({"symbol":sym,"exchange":"bingx","volume":vol,
                        "price":float(t.get("lastPrice",0) or 0),
                        "change24h":round(float(t.get("priceChangePercent",0) or 0),2)})
        except Exception as e:
            print(f"⚠️ BingX: {e}")

    seen = {}
    for r in sorted(resultados, key=lambda x: x["volume"], reverse=True):
        if r["symbol"] not in seen:
            seen[r["symbol"]] = r
    print(f"✅ {len(seen)} lowcaps encontradas.")
    return list(seen.values())


# ══════════════════════════════════════════════════════════════
# LIQUIDAÇÕES — SEM RESTRIÇÃO GEOGRÁFICA
# Primário:  OKX WebSocket (global, sem auth, sem geo-block)
# Fallback1: Bitfinex REST  (global, sem auth)
# Fallback2: Bitget REST    (global, sem auth)
# ══════════════════════════════════════════════════════════════

# ── Cache global ───────────────────────────────────────────────
_liq_cache: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
_liq_lock  = threading.Lock()
_okx_ativo = False


# ── Normalização de símbolos ───────────────────────────────────
def _norm_okx(symbol: str) -> str:
    """BTCUSDT → BTC-USDT-SWAP"""
    sym = symbol.upper().replace("-", "")
    if sym.endswith("USDT"):
        return f"{sym[:-4]}-USDT-SWAP"
    if sym.endswith("USD"):
        return f"{sym[:-3]}-USD-SWAP"
    return sym


def _norm_bitget(symbol: str) -> str:
    return symbol.upper().replace("-", "")


# ── OKX WebSocket (primário) ───────────────────────────────────
def _iniciar_ws_okx():
    global _okx_ativo

    # Aborta silenciosamente se websocket-client não estiver instalado
    if not _WEBSOCKET_DISPONIVEL:
        log.warning("OKX WS ignorado: websocket-client ausente. Usando apenas REST fallbacks.")
        return

    if _okx_ativo:
        return
    _okx_ativo = True

    def on_open(ws):
        ws.send(json.dumps({
            "op": "subscribe",
            "args": [{"channel": "liquidation-orders", "instType": "SWAP"}]
        }))
        log.info("✅ OKX WS: inscrito em liquidation-orders SWAP")

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "data" not in data:
                return
            for item in data.get("data", []):
                inst_id = item.get("instId", "")
                sym = inst_id.replace("-SWAP","").replace("-PERP","").replace("-","")
                for detail in item.get("details", []):
                    side  = detail.get("posSide", "").upper()
                    price = float(detail.get("bkPx", 0))
                    qty   = float(detail.get("sz",   0))
                    usd   = price * qty
                    if usd < 500:
                        continue
                    with _liq_lock:
                        _liq_cache[sym].appendleft({
                            "lado":  "LONG" if side == "LONG" else "SHORT",
                            "qty":   qty,
                            "price": price,
                            "usd":   usd,
                            "ts":    datetime.now(timezone.utc),
                            "fonte": "OKX",
                        })
        except Exception as e:
            log.debug(f"OKX WS parse error: {e}")

    def on_error(ws, error):
        log.warning(f"OKX WS erro: {error}")

    def on_close(ws, *args):
        global _okx_ativo
        _okx_ativo = False

    def run():
        global _okx_ativo
        while True:
            try:
                ws = websocket.WebSocketApp(
                    "wss://ws.okx.com:8443/ws/v5/public",
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                )
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                log.warning(f"OKX WS exception: {e}")
            _okx_ativo = False
            time.sleep(5)
            _okx_ativo = True

    threading.Thread(target=run, daemon=True, name="ws-okx-liq").start()
    log.info("🚀 OKX WebSocket de liquidações iniciado")


# Inicia na importação do módulo
_iniciar_ws_okx()


# ── Bitfinex REST (fallback 1) ─────────────────────────────────
def _liquidacoes_bitfinex(symbol: str, limit: int = 20) -> list[dict]:
    try:
        url = "https://api-pub.bitfinex.com/v2/liquidations/hist"
        r   = requests.get(url, params={"limit": limit, "sort": -1}, timeout=6)
        r.raise_for_status()
        eventos = []
        for item in r.json():
            if not isinstance(item, list) or len(item) < 6:
                continue
            sym_bfx = str(item[3]).upper()
            amount  = abs(float(item[4]))
            price   = float(item[11]) if len(item) > 11 and item[11] else float(item[5])
            lado    = "LONG" if float(item[4]) > 0 else "SHORT"
            usd     = amount * price
            ts_ms   = int(item[1])
            if usd < 500:
                continue
            base_req = symbol.upper().replace("USDT","").replace("USD","")
            if base_req not in sym_bfx:
                continue
            eventos.append({
                "lado":  lado,
                "qty":   amount,
                "price": price,
                "usd":   usd,
                "ts":    datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                "fonte": "Bitfinex",
            })
        return eventos
    except Exception as e:
        log.debug(f"Bitfinex liquidações erro: {e}")
        return []


# ── Bitget REST (fallback 2) ───────────────────────────────────
def _liquidacoes_bitget(symbol: str, limit: int = 20) -> list[dict]:
    try:
        sym = _norm_bitget(symbol)
        url = "https://api.bitget.com/api/v2/mix/market/fills-history"
        r   = requests.get(
            url,
            params={"symbol": sym, "productType": "USDT-FUTURES", "limit": limit},
            timeout=6,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "00000":
            return []
        eventos = []
        for t in data.get("data", []):
            price = float(t.get("price", 0))
            size  = float(t.get("size",  0))
            usd   = price * size
            side  = t.get("side", "").upper()
            if usd < 5000:
                continue
            eventos.append({
                "lado":  "LONG" if "BUY" in side else "SHORT",
                "qty":   size,
                "price": price,
                "usd":   usd,
                "ts":    datetime.fromtimestamp(int(t.get("ts", 0)) / 1000, tz=timezone.utc),
                "fonte": "Bitget",
            })
        return eventos
    except Exception as e:
        log.debug(f"Bitget fills erro: {e}")
        return []


# ── Função principal ───────────────────────────────────────────
def obter_liquidacoes(symbol: str, janela_minutos: int = 60) -> str:
    """
    Retorna texto puro com resumo de liquidações.
    Cascade: OKX WS → Bitfinex REST → Bitget REST.
    O escape MDv2 é feito em analysis.py via _e().
    """
    sym   = symbol.upper().replace("-", "")
    agora = datetime.now(timezone.utc)

    # Fonte 1: cache OKX WebSocket
    with _liq_lock:
        cache = list(_liq_cache.get(sym, []))
    recentes = [
        e for e in cache
        if (agora - e["ts"]).total_seconds() <= janela_minutos * 60
    ]
    fonte_usada = "OKX" if recentes else None

    # Fonte 2: Bitfinex REST
    if not recentes:
        recentes = _liquidacoes_bitfinex(sym)
        if recentes:
            fonte_usada = "Bitfinex"

    # Fonte 3: Bitget REST
    if not recentes:
        recentes = _liquidacoes_bitget(sym)
        if recentes:
            fonte_usada = "Bitget (proxy fills)"

    if not recentes:
        return "Sem liquidacoes significativas na ultima hora."

    longs  = [e for e in recentes if e["lado"] == "LONG"]
    shorts = [e for e in recentes if e["lado"] == "SHORT"]

    total_long  = sum(e["usd"] for e in longs)
    total_short = sum(e["usd"] for e in shorts)
    total_geral = total_long + total_short

    def fmt_usd(v: float) -> str:
        if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
        if v >= 1_000:     return f"${v/1_000:.1f}K"
        return f"${v:.0f}"

    maior = max(recentes, key=lambda e: e["usd"])

    if total_long > total_short * 2:
        sinal = "Pressao vendedora (longs forcados) — possivel continuidade de baixa"
    elif total_short > total_long * 2:
        sinal = "Pressao compradora (shorts forcados) — possivel short squeeze"
    elif total_geral > 1_000_000:
        sinal = "Volume alto de liquidacoes — volatilidade elevada"
    else:
        sinal = "Liquidacoes equilibradas — sem pressao dominante"

    return (
        f"Fonte: {fonte_usada} | Janela: {janela_minutos}min\n"
        f"  Total:      {fmt_usd(total_geral)} ({len(recentes)} eventos)\n"
        f"  Longs liq:  {fmt_usd(total_long)} ({len(longs)} ordens)\n"
        f"  Shorts liq: {fmt_usd(total_short)} ({len(shorts)} ordens)\n"
        f"  Maior:      {fmt_usd(maior['usd'])} @ {maior['price']:.4f} ({maior['lado']})\n"
        f"  Sinal:      {sinal}"
    )
