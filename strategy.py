import pandas as pd
import numpy as np
import ta


# ══════════════════════════════════════════════════════════════
# SQUEEZE MOMENTUM (Bollinger Bands + Keltner Channel)
# ══════════════════════════════════════════════════════════════

def calcular_squeeze_pro(df: pd.DataFrame) -> dict:
    """
    Detecta Squeeze: quando BB fica dentro do Keltner Channel.
    Squeeze = volatilidade comprimida → explosão iminente.
    """
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]

    # Bollinger Bands (20, 2)
    bb     = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_up  = bb.bollinger_hband()
    bb_low = bb.bollinger_lband()

    # Keltner Channel (20, 1.5)
    kc     = ta.volatility.KeltnerChannel(high, low, close, window=20, window_atr=10)
    kc_up  = kc.keltner_channel_hband()
    kc_low = kc.keltner_channel_lband()

    # Squeeze ON = BB dentro do KC
    squeeze_on  = (bb_up.iloc[-1] < kc_up.iloc[-1]) and (bb_low.iloc[-1] > kc_low.iloc[-1])
    squeeze_ant = (bb_up.iloc[-2] < kc_up.iloc[-2]) and (bb_low.iloc[-2] > kc_low.iloc[-2])

    # Momentum (Linear Regression do delta de preço)
    delta     = close - ((high + low + close) / 3)
    momentum  = delta.rolling(20).mean()
    mom_atual = round(float(momentum.iloc[-1]), 6)
    mom_ant   = round(float(momentum.iloc[-2]), 6)
    crescendo = mom_atual > mom_ant

    # Estado
    if not squeeze_on and squeeze_ant:
        estado = "LIBERADO"
        emoji  = "🚀"
        msg    = "Squeeze LIBERADO — explosão iniciando!"
    elif squeeze_on:
        estado = "COMPRIMIDO"
        emoji  = "🔒"
        msg    = "Squeeze ATIVO — compressão de volatilidade"
    else:
        estado = "NEUTRO"
        emoji  = "😐"
        msg    = "Sem squeeze no momento"

    return {
        "estado":    estado,
        "emoji":     emoji,
        "msg":       msg,
        "momentum":  mom_atual,
        "crescendo": crescendo,
    }


# ══════════════════════════════════════════════════════════════
# DETECTAR FASE AMD
# (Acumulação / Manipulação / Distribuição)
# ══════════════════════════════════════════════════════════════

def detectar_fase_amd(df: pd.DataFrame) -> str:
    """
    Detecta em qual fase AMD o ativo está.
    Baseado em estrutura de preço + volume + volatilidade.
    """
    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    # Últimos 50 candles
    c50 = close.tail(50)
    v50 = volume.tail(50)

    # Range de preço normalizado
    preco_range = (c50.max() - c50.min()) / c50.mean() if c50.mean() > 0 else 0

    # Volume médio das metades
    v_primeira = v50.iloc[:25].mean()
    v_segunda  = v50.iloc[25:].mean()
    vol_crescente = v_segunda > v_primeira * 1.1

    # Volatilidade recente (ATR normalizado)
    atr = ta.volatility.AverageTrueRange(high, low, close, 14).average_true_range()
    atr_norm = atr.iloc[-1] / close.iloc[-1] if close.iloc[-1] > 0 else 0

    # Tendência de curto prazo
    ema9  = ta.trend.EMAIndicator(close,  9).ema_indicator()
    ema21 = ta.trend.EMAIndicator(close, 21).ema_indicator()
    tendencia_alta = ema9.iloc[-1] > ema21.iloc[-1]

    # ── Classificação ─────────────────────────────────────────
    # ACUMULAÇÃO: range lateral, volume crescendo, baixa volatilidade
    if preco_range < 0.15 and vol_crescente and atr_norm < 0.03:
        return "acumulacao"

    # MANIPULAÇÃO: spike de volume, volatilidade alta, movimento brusco
    if atr_norm > 0.05 and v_segunda > v_primeira * 1.5:
        return "manipulacao"

    # DISTRIBUIÇÃO: tendência de alta com volume caindo
    if tendencia_alta and not vol_crescente and preco_range > 0.10:
        return "distribuicao"

    return "indefinido"


# ══════════════════════════════════════════════════════════════
# DETECTAR PADRÕES DE CANDLE (CRT + Brooks)
# ══════════════════════════════════════════════════════════════

def detectar_padroes_candle(df: pd.DataFrame) -> list:
    """
    Detecta padrões relevantes nos últimos candles.
    """
    padroes = []
    if len(df) < 5:
        return padroes

    o  = df["open"].values
    h  = df["high"].values
    l  = df["low"].values
    c  = df["close"].values

    i = -1  # último candle

    corpo_atual = abs(c[i] - o[i])
    sombra_sup  = h[i] - max(c[i], o[i])
    sombra_inf  = min(c[i], o[i]) - l[i]
    range_atual = h[i] - l[i]

    if range_atual == 0:
        return padroes

    # ── Engolfo de alta ───────────────────────────────────────
    if (c[i] > o[i] and c[i-1] < o[i-1]
            and c[i] > o[i-1] and o[i] < c[i-1]):
        padroes.append("🕯️ Engolfo de Alta")

    # ── Engolfo de baixa ──────────────────────────────────────
    if (c[i] < o[i] and c[i-1] > o[i-1]
            and c[i] < o[i-1] and o[i] > c[i-1]):
        padroes.append("🕯️ Engolfo de Baixa")

    # ── Martelo (hammer) ──────────────────────────────────────
    if (sombra_inf > corpo_atual * 2
            and sombra_sup < corpo_atual * 0.5
            and corpo_atual / range_atual > 0.1):
        padroes.append("🔨 Martelo (reversão alta)")

    # ── Estrela cadente ───────────────────────────────────────
    if (sombra_sup > corpo_atual * 2
            and sombra_inf < corpo_atual * 0.5
            and corpo_atual / range_atual > 0.1):
        padroes.append("⭐ Estrela Cadente (reversão baixa)")

    # ── Doji ──────────────────────────────────────────────────
    if corpo_atual < range_atual * 0.1:
        padroes.append("✚ Doji (indecisão)")

    # ── CRT Thick (candle de range expandido) ─────────────────
    ranges_anteriores = [h[j] - l[j] for j in range(-6, -1)]
    media_range = np.mean(ranges_anteriores) if ranges_anteriores else 0
    if range_atual > media_range * 1.8 and corpo_atual > range_atual * 0.6:
        padroes.append("📊 CRT Thick (range expandido)")

    # ── Breakout de alta (Brooks) ──────────────────────────────
    max_anterior = max(h[-6:-1])
    if c[i] > max_anterior and corpo_atual > range_atual * 0.5:
        padroes.append("🚀 Breakout de Alta (Brooks)")

    # ── Breakout de baixa (Brooks) ─────────────────────────────
    min_anterior = min(l[-6:-1])
    if c[i] < min_anterior and corpo_atual > range_atual * 0.5:
        padroes.append("📉 Breakout de Baixa (Brooks)")

    return padroes


# ══════════════════════════════════════════════════════════════
# DETECTAR DIVERGÊNCIAS RSI
# ══════════════════════════════════════════════════════════════

def detectar_divergencia_rsi(df: pd.DataFrame) -> str:
    """
    Alta: preço faz fundo mais baixo, RSI faz fundo mais alto → compra
    Baixa: preço faz topo mais alto, RSI faz topo mais baixo → venda
    """
    try:
        rsi   = ta.momentum.RSIIndicator(df["close"], 14).rsi()
        close = df["close"]

        # Compara últimos 2 fundos / topos (janela de 20 candles)
        janela = 20
        c20   = close.tail(janela).values
        r20   = rsi.tail(janela).values

        # Divergência de alta
        if c20[-1] < c20[0] and r20[-1] > r20[0]:
            return "📈 Divergência de ALTA no RSI"

        # Divergência de baixa
        if c20[-1] > c20[0] and r20[-1] < r20[0]:
            return "📉 Divergência de BAIXA no RSI"

        return "Sem divergência"
    except Exception:
        return "Sem divergência"


# ══════════════════════════════════════════════════════════════
# DETECTAR ZONAS DE FIBONACCI
# ══════════════════════════════════════════════════════════════

def verificar_zona_fibonacci(df: pd.DataFrame, janela=50) -> str:
    """
    Verifica se o preço atual está próximo de uma zona de Fibonacci.
    """
    try:
        df_j  = df.tail(janela)
        topo  = df_j["high"].max()
        fundo = df_j["low"].min()
        preco = df["close"].iloc[-1]
        diff  = topo - fundo

        if diff == 0:
            return "Sem zona relevante"

        zonas = {
            "23.6%": topo - 0.236 * diff,
            "38.2%": topo - 0.382 * diff,
            "50.0%": topo - 0.500 * diff,
            "61.8%": topo - 0.618 * diff,
            "78.6%": topo - 0.786 * diff,
        }

        tolerancia = diff * 0.02  # 2% de tolerância

        for nivel, valor in zonas.items():
            if abs(preco - valor) <= tolerancia:
                return f"📐 Preço na zona Fibonacci {nivel} ({valor:.6f})"

        return "Fora das zonas de Fibonacci"
    except Exception:
        return "Erro ao calcular Fibonacci"


# ══════════════════════════════════════════════════════════════
# SCORE FINAL
# ══════════════════════════════════════════════════════════════

def calcular_score_final(
    df: pd.DataFrame,
    symbol: str = "",
    confluencia_mtf: int = 0,
) -> tuple:
    """
    Calcula score de 0 a 10 para o setup.
    Retorna: (score, breakdown[], fase_amd)
    """
    score     = 0
    breakdown = []

    close  = df["close"]
    high   = df["high"]
    low    = df["low"]
    volume = df["volume"]

    # ── 1. TENDÊNCIA (EMA) ────────────────────────────────── (0-2 pts)
    ema9  = ta.trend.EMAIndicator(close,  9).ema_indicator()
    ema21 = ta.trend.EMAIndicator(close, 21).ema_indicator()
    ema50 = ta.trend.EMAIndicator(close, 50).ema_indicator()
    preco = close.iloc[-1]

    pts_tend = 0
    if preco > ema21.iloc[-1]:
        pts_tend += 1
    if ema9.iloc[-1] > ema21.iloc[-1] and ema21.iloc[-1] > ema50.iloc[-1]:
        pts_tend += 1
    score += pts_tend
    breakdown.append(f"  {'✅' if pts_tend == 2 else '⚡' if pts_tend == 1 else '❌'} "
                     f"Tendência EMA: {pts_tend}/2 pts")

    # ── 2. RSI ────────────────────────────────────────────── (0-1 pt)
    rsi_val = ta.momentum.RSIIndicator(close, 14).rsi().iloc[-1]
    pts_rsi = 1 if 40 <= rsi_val <= 70 else 0
    score  += pts_rsi
    breakdown.append(f"  {'✅' if pts_rsi else '❌'} "
                     f"RSI ({rsi_val:.1f}): {pts_rsi}/1 pt")

    # ── 3. MACD ───────────────────────────────────────────── (0-1 pt)
    macd_obj   = ta.trend.MACD(close, 6, 13, 4)
    macd_val   = macd_obj.macd().iloc[-1]
    macd_sig   = macd_obj.macd_signal().iloc[-1]
    macd_hist  = macd_obj.macd_diff().iloc[-1]
    macd_ant   = macd_obj.macd_diff().iloc[-2]
    pts_macd   = 1 if (macd_val > macd_sig and macd_hist > macd_ant) else 0
    score     += pts_macd
    breakdown.append(f"  {'✅' if pts_macd else '❌'} "
                     f"MACD cruzando: {pts_macd}/1 pt")

    # ── 4. VOLUME ─────────────────────────────────────────── (0-1 pt)
    vol_ma21  = volume.rolling(21).mean()
    vol_ratio = volume.iloc[-1] / vol_ma21.iloc[-1] if vol_ma21.iloc[-1] > 0 else 0
    pts_vol   = 1 if vol_ratio >= 1.5 else 0
    score    += pts_vol
    breakdown.append(f"  {'✅' if pts_vol else '❌'} "
                     f"Volume spike ({vol_ratio:.2f}x): {pts_vol}/1 pt")

    # ── 5. SQUEEZE ────────────────────────────────────────── (0-2 pts)
    sq       = calcular_squeeze_pro(df)
    pts_sq   = 0
    if sq["estado"] == "LIBERADO":
        pts_sq = 2
    elif sq["estado"] == "COMPRIMIDO":
        pts_sq = 1
    score += pts_sq
    breakdown.append(f"  {'✅' if pts_sq == 2 else '⚡' if pts_sq == 1 else '❌'} "
                     f"Squeeze ({sq['estado']}): {pts_sq}/2 pts")

    # ── 6. MULTI-TIMEFRAME ────────────────────────────────── (0-1 pt)
    pts_mtf = 1 if confluencia_mtf >= 2 else 0
    score  += pts_mtf
    breakdown.append(f"  {'✅' if pts_mtf else '❌'} "
                     f"Confluência MTF ({confluencia_mtf}/3): {pts_mtf}/1 pt")

    # ── 7. PADRÕES DE CANDLE ──────────────────────────────── (0-1 pt)
    padroes  = detectar_padroes_candle(df)
    pts_cand = 1 if len(padroes) > 0 else 0
    score   += pts_cand
    breakdown.append(f"  {'✅' if pts_cand else '❌'} "
                     f"Padrão candle ({len(padroes)}): {pts_cand}/1 pt")
    if padroes:
        for p in padroes[:2]:
            breakdown.append(f"    → {p}")

    # ── 8. FIBONACCI ──────────────────────────────────────── (0-1 pt)
    fib_zona = verificar_zona_fibonacci(df)
    pts_fib  = 1 if "Preço na zona" in fib_zona else 0
    score   += pts_fib
    breakdown.append(f"  {'✅' if pts_fib else '❌'} "
                     f"Fibonacci: {pts_fib}/1 pt")
    if pts_fib:
        breakdown.append(f"    → {fib_zona}")

    # ── Fase AMD ──────────────────────────────────────────────
    fase_amd = detectar_fase_amd(df)

    # ── Garante range 0-10 ────────────────────────────────────
    score = max(0, min(10, score))

    return score, breakdown, fase_amd


# ══════════════════════════════════════════════════════════════
# CLASSIFICAR SETUP
# ══════════════════════════════════════════════════════════════

def classificar_setup(
    score: int,
    fase_amd: str,
    squeeze_estado: str,
    vol_ratio: float,
) -> tuple:
    """
    Classifica o setup em categorias com descrição.
    Retorna: (classe, descricao)
    """
    # Bônus por contexto
    bonus = 0
    if fase_amd == "acumulacao":
        bonus += 1
    if squeeze_estado == "LIBERADO":
        bonus += 1
    if vol_ratio >= 2.0:
        bonus += 1

    score_efetivo = score + bonus

    if score_efetivo >= 9:
        return (
            "🔥 SETUP A+ — ALTÍSSIMA PROBABILIDADE",
            "Squeeze liberado + acumulação + volume confirmando"
        )
    elif score_efetivo >= 7:
        return (
            "⚡ SETUP A — ALTA PROBABILIDADE",
            "Múltiplas confluências alinhadas"
        )
    elif score_efetivo >= 5:
        return (
            "📊 SETUP B — PROBABILIDADE MODERADA",
            "Alguns indicadores alinhados, aguardar confirmação"
        )
    elif score_efetivo >= 3:
        return (
            "🌀 SETUP C — BAIXA PROBABILIDADE",
            "Poucos indicadores favoráveis"
        )
    else:
        return (
            "❄️ SEM SETUP",
            "Condições desfavoráveis no momento"
        )
