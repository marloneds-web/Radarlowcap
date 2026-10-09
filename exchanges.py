import requests
import pandas as pd
import numpy as np
import threading
import time
import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from utils import MIN_VOL_24H, MCAP_MIN, MCAP_MAX, COINGECKO_BASE, COINGECKO_API_KEY

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

# Sessão HTTP compartilhada: reaproveita conexões TCP/TLS entre requisições
# (o scan faz centenas de chamadas às mesmas exchanges).
_http = requests.Session()
_http.mount("https://", requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=32))

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
    r   = _http.get(url, params={"symbol":symbol,"granularity":tf,"limit":min(limit,1000)}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "00000" or not data.get("data"):
        raise ValueError(f"Bitget: {data.get('msg','sem dados')}")
    rows = [{"timestamp":int(i[0]),"open":i[1],"high":i[2],"low":i[3],"close":i[4],"volume":i[5]}
            for i in data["data"]]
    return _normalizar_df(pd.DataFrame(rows, columns=COLUNAS))


def bitget_tickers() -> list:
    r = _http.get(f"{BITGET_BASE}/api/v2/spot/market/tickers", timeout=TIMEOUT)
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
    r   = _http.get(url, params={"symbol":sym,"interval":tf,"limit":min(limit,1000)}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0 or not data.get("data"):
        raise ValueError(f"BingX: {data.get('msg','sem dados')}")
    rows = [{"timestamp":int(i["time"]),"open":i["open"],"high":i["high"],
             "low":i["low"],"close":i["close"],"volume":i["volume"]}
            for i in data["data"]]
    return _normalizar_df(pd.DataFrame(rows, columns=COLUNAS))


def bingx_tickers() -> list:
    r = _http.get(f"{BINGX_BASE}/openApi/spot/v1/ticker/24hr", timeout=TIMEOUT)
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
    r   = _http.get(url, params={"symbol":symbol,"interval":tf,"limit":min(limit,1000)}, timeout=TIMEOUT)
    r.raise_for_status()
    raw = r.json()
    if not isinstance(raw, list) or len(raw) == 0:
        raise ValueError(f"MEXC: sem dados para {symbol}")
    rows = [{"timestamp":int(i[0]),"open":i[1],"high":i[2],
             "low":i[3],"close":i[4],"volume":i[5]} for i in raw]
    return _normalizar_df(pd.DataFrame(rows, columns=COLUNAS))


def mexc_tickers() -> list:
    r = _http.get(f"{MEXC_BASE}/api/v3/ticker/24hr", timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if not isinstance(d, list):
        raise ValueError("MEXC tickers: resposta inesperada")
    return d


# ══════════════════════════════════════════
# INTERFACE UNIFICADA
# ══════════════════════════════════════════
def obter_candles(symbol: str, timeframe="1h", limit=300, exchange="auto",
                  fechados=True, preferida=None) -> pd.DataFrame:
    """
    fechados=True descarta o último candle, que ainda está em formação
    (volume parcial e corpo/sombras que ainda vão mudar).
    preferida: exchange tentada primeiro no modo "auto" (ex.: onde o par foi listado).
    """
    def _limpar(df):
        return df.iloc[:-1].reset_index(drop=True) if fechados else df

    mapa = {"bitget":bitget_candles,"mexc":mexc_candles,"bingx":bingx_candles}
    if exchange != "auto":
        return _limpar(mapa[exchange](symbol, timeframe, limit))
    ordem = sorted(mapa, key=lambda nome: nome != preferida)
    erros = {}
    for nome in ordem:
        func = mapa[nome]
        try:
            df = func(symbol, timeframe, limit)
            if df is not None and len(df) >= 51:
                return _limpar(df)
        except Exception as e:
            erros[nome] = str(e)
    raise ConnectionError(f"Todas exchanges falharam para {symbol}:\n"+"\n".join(f"  {k}: {v}" for k,v in erros.items()))


# ══════════════════════════════════════════
# MARKET CAP (CoinGecko)
# ══════════════════════════════════════════
_MCAP_CACHE_TTL = 6 * 3600
_mcap_cache = {"ts": 0.0, "simbolos": None}
_mcap_lock  = threading.Lock()


def _simbolos_por_mcap(mcap_min=MCAP_MIN, mcap_max=MCAP_MAX, max_paginas=12):
    """
    Retorna o set de símbolos (ex.: {"PEPE", "WIF"}) com market cap entre
    mcap_min e mcap_max, ou None se a CoinGecko estiver indisponível.
    Resultado fica em cache por 6h (market cap muda devagar).
    """
    with _mcap_lock:
        if _mcap_cache["simbolos"] is not None and time.time() - _mcap_cache["ts"] < _MCAP_CACHE_TTL:
            return _mcap_cache["simbolos"]

        headers  = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}
        simbolos = set()
        try:
            for pagina in range(1, max_paginas + 1):
                params = {"vs_currency": "usd", "order": "market_cap_desc",
                          "per_page": 250, "page": pagina}
                r = _http.get(f"{COINGECKO_BASE}/coins/markets", params=params,
                                 headers=headers, timeout=TIMEOUT)
                if r.status_code == 429:  # rate limit do plano gratuito
                    time.sleep(30)
                    r = _http.get(f"{COINGECKO_BASE}/coins/markets", params=params,
                                     headers=headers, timeout=TIMEOUT)
                r.raise_for_status()
                moedas = r.json()
                if not moedas:
                    break
                for c in moedas:
                    mcap = c.get("market_cap") or 0
                    if mcap_min <= mcap <= mcap_max:
                        simbolos.add(str(c.get("symbol", "")).upper())
                # Ordenado por mcap desc: ao passar do mínimo, acabou
                if (moedas[-1].get("market_cap") or 0) < mcap_min:
                    break
                time.sleep(2.5)
        except Exception as e:
            log.warning(f"⚠️ CoinGecko indisponível ({e}) — filtro de market cap desativado neste ciclo.")
            return None

        _mcap_cache.update(ts=time.time(), simbolos=simbolos)
        log.info(f"✅ CoinGecko: {len(simbolos)} moedas entre ${mcap_min:,.0f} e ${mcap_max:,.0f}")
        return simbolos


# ══════════════════════════════════════════
# LISTAR LOWCAPS
# ══════════════════════════════════════════
def listar_lowcaps(vol_min=MIN_VOL_24H, exchanges=None, apenas_usdt=True,
                   filtrar_mcap=True) -> list:
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
            log.warning(f"⚠️ Bitget tickers: {e}")

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
            log.warning(f"⚠️ MEXC tickers: {e}")

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
            log.warning(f"⚠️ BingX tickers: {e}")

    seen = {}
    for r in sorted(resultados, key=lambda x: x["volume"], reverse=True):
        if r["symbol"] not in seen:
            seen[r["symbol"]] = r

    if filtrar_mcap:
        permitidos = _simbolos_por_mcap()
        if permitidos is not None:
            seen = {s: r for s, r in seen.items()
                    if s.removesuffix("USDT") in permitidos}
    log.info(f"✅ {len(seen)} lowcaps encontradas.")
    return list(seen.values())


# ══════════════════════════════════════════════════════════════
# LIQUIDAÇÕES
# ══════════════════════════════════════════════════════════════

_liq_cache: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
_liq_lock  = threading.Lock()
_okx_ativo = False


def _norm_okx(symbol: str) -> str:
    sym = symbol.upper().replace("-", "")
    if sym.endswith("USDT"):
        return f"{sym[:-4]}-USDT-SWAP"
    if sym.endswith("USD"):
        return f"{sym[:-3]}-USD-SWAP"
    return sym


# ── OKX WebSocket ──────────────────────────────────────────────
def iniciar_ws_okx():
    """Inicia (uma vez) a thread do WebSocket de liquidações da OKX."""
    global _okx_ativo

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


# ── Bitfinex REST ──────────────────────────────────────────────
def _base_bitfinex(sym_bfx: str) -> str:
    """'tBTCF0:USTF0' → 'BTC' | 'tETHUSD' → 'ETH'."""
    s = sym_bfx[1:] if sym_bfx.startswith("t") else sym_bfx
    s = s.upper().split(":")[0]
    s = s.removesuffix("F0")
    for quote in ("UST", "USD"):
        if s.endswith(quote) and len(s) > len(quote):
            s = s[:-len(quote)]
            break
    return s


def _liquidacoes_bitfinex(symbol: str, limit: int = 100) -> list[dict]:
    """
    Formato da API (cada item vem embrulhado numa lista):
    [[ "pos", POS_ID, MTS, _, SYMBOL, AMOUNT, BASE_PRICE, _, IS_MATCH,
       IS_MARKET_SOLD, _, PRICE_ACQUIRED ], ...]
    AMOUNT > 0 → posição LONG liquidada.
    """
    try:
        url = "https://api-pub.bitfinex.com/v2/liquidations/hist"
        r   = _http.get(url, params={"limit": limit, "sort": -1}, timeout=6)
        r.raise_for_status()
        base_req = symbol.upper().removesuffix("USDT").removesuffix("USD")
        eventos = []
        for item in r.json():
            if isinstance(item, list) and item and isinstance(item[0], list):
                item = item[0]
            if not isinstance(item, list) or len(item) < 7 or item[0] != "pos":
                continue
            if _base_bitfinex(str(item[4])) != base_req:
                continue
            amount_raw = float(item[5] or 0)
            amount     = abs(amount_raw)
            price      = float(item[11]) if len(item) > 11 and item[11] else float(item[6] or 0)
            usd        = amount * price
            if usd < 500:
                continue
            eventos.append({
                "lado":  "LONG" if amount_raw > 0 else "SHORT",
                "qty":   amount,
                "price": price,
                "usd":   usd,
                "ts":    datetime.fromtimestamp(int(item[2]) / 1000, tz=timezone.utc),
                "fonte": "Bitfinex",
            })
        return eventos
    except Exception as e:
        log.debug(f"Bitfinex liquidações erro: {e}")
        return []


# ── Função principal ───────────────────────────────────────────
def obter_liquidacoes(symbol: str, janela_minutos: int = 60) -> str:
    sym   = symbol.upper().replace("-", "")
    agora = datetime.now(timezone.utc)

    def na_janela(eventos):
        return [e for e in eventos
                if (agora - e["ts"]).total_seconds() <= janela_minutos * 60]

    with _liq_lock:
        cache = list(_liq_cache.get(sym, []))
    recentes    = na_janela(cache)
    fonte_usada = "OKX" if recentes else None

    if not recentes:
        recentes = na_janela(_liquidacoes_bitfinex(sym))
        if recentes:
            fonte_usada = "Bitfinex"

    if not recentes:
        return f"Sem liquidacoes significativas nos ultimos {janela_minutos}min."

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
