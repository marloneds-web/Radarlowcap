import requests
import pandas as pd
import numpy as np
from utils import MIN_VOL_24H

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


# ══════════════════════════════════════════
# LIQUIDAÇÕES (CoinGlass público)
# ══════════════════════════════════════════
def obter_liquidacoes(symbol: str) -> str:
    try:
        coin = symbol.replace("USDT","").replace("-","")
        url  = "https://open-api.coinglass.com/public/v2/liquidation_history"
        r    = requests.get(url, params={"symbol":coin,"interval":"h4","limit":3}, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not data.get("success") or not data.get("data"):
            return "Sem dados de liquidação."
        linhas = []
        for item in data["data"][:3]:
            ts = pd.to_datetime(item.get("createTime",0), unit="ms")
            linhas.append(f"  {ts.strftime('%d/%m %H:%M')} | "
                          f"Longs: ${item.get('longLiquidationUsd',0):,.0f} | "
                          f"Shorts: ${item.get('shortLiquidationUsd',0):,.0f}")
        return "\n".join(linhas) or "Sem liquidações recentes."
    except Exception as e:
        return f"Erro liquidações: {e}"
