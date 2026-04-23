import pandas as pd
import numpy as np
import ta
from exchanges import obter_candles


def calcular_fibonacci(df, janela=50):
    df_j  = df.tail(janela)
    topo  = df_j["high"].max()
    fundo = df_j["low"].min()
    diff  = topo - fundo
    if diff == 0:
        return {}, {}
    ret = {
        "0%":    round(topo, 6),
        "23.6%": round(topo - 0.236 * diff, 6),
        "38.2%": round(topo - 0.382 * diff, 6),
        "50%":   round(topo - 0.500 * diff, 6),
        "61.8%": round(topo - 0.618 * diff, 6),
        "78.6%": round(topo - 0.786 * diff, 6),
        "100%":  round(fundo, 6),
    }
    exp = {
        "127.2%": round(fundo - 0.272 * diff, 6),
        "161.8%": round(fundo - 0.618 * diff, 6),
        "261.8%": round(fundo - 1.618 * diff, 6),
    }
    return ret, exp


def avaliar_tendencia(df):
    ema9  = ta.trend.EMAIndicator(df["close"],  9).ema_indicator()
    ema21 = ta.trend.EMAIndicator(df["close"], 21).ema_indicator()
    ema50 = ta.trend.EMAIndicator(df["close"], 50).ema_indicator()
    preco = df["close"].iloc[-1]

    criterios = [
        ("Topos e fundos ascendentes",
         df["high"].tail(20).iloc[-1] > df["high"].tail(20).iloc[0]
         and df["low"].tail(20).iloc[-1] > df["low"].tail(20).iloc[0]),
        ("Preço acima da EMA21",  preco > ema21.iloc[-1]),
        ("EMA21 ascendente",      ema21.iloc[-1] > ema21.iloc[-5]),
        ("EMA9 acima da EMA21",   ema9.iloc[-1]  > ema21.iloc[-1]),
        ("EMA21 acima da EMA50",  ema21.iloc[-1] > ema50.iloc[-1]),
    ]
    score    = sum(1 for _, ok in criterios if ok)
    direcao  = (f"📈 ALTA ({score}/5)" if score >= 3
                else f"📉 BAIXA ({5 - score}/5)")
    detalhes = "\n".join(
        f"  {'✅' if ok else '❌'} {nome}" for nome, ok in criterios)
    return direcao, detalhes, score


def analise_multi_timeframe(par, timeframes=("1d", "4h", "1h")):
    resultados = {}
    for tf in timeframes:
        try:
            df = obter_candles(par, tf, limit=200)
            direcao, _, _ = avaliar_tendencia(df)
            resultados[tf] = direcao
        except Exception as e:
            resultados[tf] = f"Erro: {e}"
    confluencia = sum(1 for v in resultados.values() if "ALTA" in v)
    return resultados, confluencia


# ══════════════════════════════════════════════════════════════
# CÁLCULO PROFISSIONAL DE SETUP: ENTRADA / SL / TP
# ══════════════════════════════════════════════════════════════

def _swing_points(df, janela=5):
    """Detecta topos e fundos de swing nos últimos candles."""
    highs = df["high"].values
    lows  = df["low"].values
    n     = len(highs)

    swing_highs = []
    swing_lows  = []

    for idx in range(janela, n - janela):
        # Topo: maior que todos os vizinhos
        if all(highs[idx] >= highs[idx - j] for j in range(1, janela + 1)) and \
           all(highs[idx] >= highs[idx + j] for j in range(1, janela + 1)):
            swing_highs.append((idx, highs[idx]))

        # Fundo: menor que todos os vizinhos
        if all(lows[idx] <= lows[idx - j] for j in range(1, janela + 1)) and \
           all(lows[idx] <= lows[idx + j] for j in range(1, janela + 1)):
            swing_lows.append((idx, lows[idx]))

    return swing_highs, swing_lows


def _detectar_fvg(df, lado="long"):
    """
    Detecta Fair Value Gaps (FVG) recentes.
    Long FVG: low[i] > high[i-2]  → gap de alta
    Short FVG: high[i] < low[i-2] → gap de baixa
    """
    fvgs = []
    for i in range(2, len(df)):
        if lado == "long":
            gap_low  = df["low"].iloc[i]
            gap_high = df["high"].iloc[i - 2]
            if gap_low > gap_high:
                fvgs.append((gap_high + gap_low) / 2)
        else:
            gap_high = df["high"].iloc[i]
            gap_low  = df["low"].iloc[i - 2]
            if gap_high < gap_low:
                fvgs.append((gap_high + gap_low) / 2)
    return fvgs[-3:] if fvgs else []


def calcular_setup_trade(df: pd.DataFrame, direcao: str) -> dict:
    """
    Calcula entrada, SL e TPs baseado em estrutura de mercado.

    Lógica:
    ─────────────────────────────────────────────
    SL  → abaixo/acima do último swing + buffer ATR
    TP1 → swing anterior oposto (primeira liquidez)
    TP2 → FVG ou Fibonacci 61.8%
    TP3 → máxima/mínima estrutural (maior swing)
    R:R → mínimo 2.0 para validar o setup
    """
    try:
        preco  = df["close"].iloc[-1]
        atr    = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], 14
        ).average_true_range().iloc[-1]

        swing_highs, swing_lows = _swing_points(df, janela=5)

        lado = "long" if "ALTA" in direcao else "short"

        if lado == "long":
            # ── LONG ──────────────────────────────────────────
            if len(swing_lows) < 2:
                return {"valido": False, "motivo": "swings insuficientes"}

            # SL: abaixo do último fundo de swing + buffer 0.5x ATR
            ultimo_fundo = swing_lows[-1][1]
            sl = round(ultimo_fundo - (atr * 0.5), 8)

            # Valida: SL não pode estar muito longe (> 8% do preço)
            risco_abs = preco - sl
            risco_pct = (risco_abs / preco) * 100
            if risco_pct > 8:
                return {"valido": False, "motivo": f"SL muito distante \\({risco_pct:.1f}%\\)"}
            if risco_abs <= 0:
                return {"valido": False, "motivo": "SL acima do preço atual"}

            # Entrada: preço atual (ou levemente acima do último swing high)
            entrada = preco

            # TPs baseados em estrutura
            # TP1 → topo de swing mais próximo acima
            topos_acima = [h for _, h in swing_highs if h > preco]
            tp1 = round(min(topos_acima), 8) if topos_acima else round(preco + risco_abs * 2, 8)

            # TP2 → FVG bullish ou Fibonacci 61.8% projetado
            fvgs = _detectar_fvg(df, lado="long")
            fvg_acima = [f for f in fvgs if f > tp1]
            if fvg_acima:
                tp2 = round(min(fvg_acima), 8)
            else:
                # Fibonacci extensão 161.8% da última perna de baixa
                fib_ret, fib_exp = calcular_fibonacci(df, janela=50)
                tp2 = round(fib_exp.get("161.8%", preco + risco_abs * 3), 8)
                if tp2 <= tp1:
                    tp2 = round(tp1 + risco_abs * 1.5, 8)

            # TP3 → maior topo estrutural (maior swing high)
            if swing_highs:
                tp3 = round(max(h for _, h in swing_highs), 8)
                if tp3 <= tp2:
                    tp3 = round(tp2 + risco_abs * 2, 8)
            else:
                tp3 = round(tp2 + risco_abs * 2, 8)

            # R:R baseado no TP2 (alvo principal)
            rr = round((tp2 - entrada) / risco_abs, 2)

        else:
            # ── SHORT ─────────────────────────────────────────
            if len(swing_highs) < 2:
                return {"valido": False, "motivo": "swings insuficientes"}

            # SL: acima do último topo de swing + buffer 0.5x ATR
            ultimo_topo = swing_highs[-1][1]
            sl = round(ultimo_topo + (atr * 0.5), 8)

            risco_abs = sl - preco
            risco_pct = (risco_abs / preco) * 100
            if risco_pct > 8:
                return {"valido": False, "motivo": f"SL muito distante \\({risco_pct:.1f}%\\)"}
            if risco_abs <= 0:
                return {"valido": False, "motivo": "SL abaixo do preço atual"}

            entrada = preco

            # TP1 → fundo de swing mais próximo abaixo
            fundos_abaixo = [l for _, l in swing_lows if l < preco]
            tp1 = round(max(fundos_abaixo), 8) if fundos_abaixo else round(preco - risco_abs * 2, 8)

            # TP2 → FVG bearish ou Fibonacci
            fvgs = _detectar_fvg(df, lado="short")
            fvg_abaixo = [f for f in fvgs if f < tp1]
            if fvg_abaixo:
                tp2 = round(max(fvg_abaixo), 8)
            else:
                fib_ret, fib_exp = calcular_fibonacci(df, janela=50)
                tp2 = round(fib_ret.get("61.8%", preco - risco_abs * 3), 8)
                if tp2 >= tp1:
                    tp2 = round(tp1 - risco_abs * 1.5, 8)

            # TP3 → menor fundo estrutural
            if swing_lows:
                tp3 = round(min(l for _, l in swing_lows), 8)
                if tp3 >= tp2:
                    tp3 = round(tp2 - risco_abs * 2, 8)
            else:
                tp3 = round(tp2 - risco_abs * 2, 8)

            rr = round((entrada - tp2) / risco_abs, 2)

        # ── Valida R:R mínimo ──────────────────────────────────
        if rr < 2.0:
            return {
                "valido": False,
                "motivo": f"R:R insuficiente \\(1:{rr}\\)",
            }

        # ── Tipo do SL (descritivo) ────────────────────────────
        sl_tipo = "abaixo do swing low" if lado == "long" else "acima do swing high"

        return {
            "valido":    True,
            "lado":      lado,
            "entrada":   round(entrada, 8),
            "sl":        sl,
            "sl_tipo":   sl_tipo,
            "tp1":       tp1,
            "tp2":       tp2,
            "tp3":       tp3,
            "rr":        rr,
            "risco_pct": round(risco_pct, 2),
            "atr":       round(atr, 8),
        }

    except Exception as e:
        return {"valido": False, "motivo": str(e)[:40]}


# ══════════════════════════════════════════════════════════════
# RELATÓRIO COMPLETO
# ══════════════════════════════════════════════════════════════

def gerar_relatorio_completo(par="BTCUSDT", timeframe="1h"):
    """Relatório técnico completo para um par."""
    from strategy import calcular_score_final, classificar_setup, calcular_squeeze_pro
    from exchanges import obter_liquidacoes

    df = obter_candles(par, timeframe, limit=300)

    df["EMA_9"]   = ta.trend.EMAIndicator(df["close"],   9).ema_indicator()
    df["EMA_21"]  = ta.trend.EMAIndicator(df["close"],  21).ema_indicator()
    df["EMA_80"]  = ta.trend.EMAIndicator(df["close"],  80).ema_indicator()
    df["EMA_200"] = ta.trend.EMAIndicator(df["close"], 200).ema_indicator()

    rsi       = ta.momentum.RSIIndicator(df["close"], 14).rsi()
    macd_obj  = ta.trend.MACD(df["close"], 6, 13, 4)
    stoch_rsi = ta.momentum.StochRSIIndicator(df["close"], 8, 5, 5, 3).stochrsi()
    sar       = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar()
    atr       = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], 14
    ).average_true_range()

    df["vol_ma21"] = df["volume"].rolling(21).mean()
    vol_ratio      = df["volume"].iloc[-1] / df["vol_ma21"].iloc[-1]
    vol_forca      = "Alta 🔥" if vol_ratio > 1 else "Baixa"

    fib_ret, fib_exp        = calcular_fibonacci(df)
    direcao, crit_det, _    = avaliar_tendencia(df)
    mtf, confluencia        = analise_multi_timeframe(par)

    from strategy import calcular_score_final, classificar_setup, calcular_squeeze_pro
    sq                      = calcular_squeeze_pro(df)
    score, breakdown, fase_amd = calcular_score_final(df, par, confluencia)
    classe, classe_desc     = classificar_setup(score, fase_amd, sq["estado"], vol_ratio)
    liquidacoes             = obter_liquidacoes(par)

    # ── Setup profissional ─────────────────────────────────────
    st = calcular_setup_trade(df, direcao)

    if st.get("valido"):
        lado_label = "🟢 LONG" if st["lado"] == "long" else "🔴 SHORT"
        setup_txt = f"""
━━━━━━━━━━━━━━━━━━━━━━━━
📐 *SETUP DE TRADE:* {lado_label} | R:R `1:{st['rr']}`

  🎯 Entrada:        `{st['entrada']}`
  🛑 Stop Loss:      `{st['sl']}` ({st['risco_pct']}%) — _{st['sl_tipo']}_
  ✅ TP1 (30%):      `{st['tp1']}`
  ✅ TP2 (40%):      `{st['tp2']}`
  ✅ TP3 (30%):      `{st['tp3']}` + trailing

  💡 _Após TP1: mover SL para entrada \\(breakeven\\)_
  📏 ATR\\(14\\): `{st['atr']}`"""
    else:
        setup_txt = f"""
━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *SETUP:* _{st.get('motivo', 'não identificado')}_"""

    score_emoji = "🔥" if score >= 8 else "⚡" if score >= 6 else "📊" if score >= 4 else "❄️"

    relatorio = f"""
╔══════════════════════════════════════════╗
   📊 *{par}* | {timeframe.upper()}
╚══════════════════════════════════════════╝

{score_emoji} *SCORE: {score}/10* — {classe}
_{classe_desc}_

{chr(10).join(breakdown)}

━━━━━━━━━━━━━━━━━━━━━━━━
📐 *TENDÊNCIA:* {direcao}
{crit_det}

━━━━━━━━━━━━━━━━━━━━━━━━
🕐 *MULTI-TIMEFRAME:*
  1D → {mtf.get('1d','N/A')}
  4H → {mtf.get('4h','N/A')}
  1H → {mtf.get('1h','N/A')}

━━━━━━━━━━━━━━━━━━━━━━━━
🎯 *SQUEEZE:* {sq['emoji']} {sq['msg']}
  Momentum: {sq['momentum']} {'↑' if sq['crescendo'] else '↓'}

━━━━━━━━━━━━━━━━━━━━━━━━
📌 *MÉDIAS MÓVEIS:*
  EMA 9   → {df['EMA_9'].iloc[-1]:.6f}
  EMA 21  → {df['EMA_21'].iloc[-1]:.6f}
  EMA 80  → {df['EMA_80'].iloc[-1]:.6f}
  EMA 200 → {df['EMA_200'].iloc[-1]:.6f}

━━━━━━━━━━━━━━━━━━━━━━━━
📊 *INDICADORES:*
  RSI(14):    {rsi.iloc[-1]:.2f}
  MACD:       {macd_obj.macd().iloc[-1]:.6f}
  Sinal:      {macd_obj.macd_signal().iloc[-1]:.6f}
  Stoch RSI:  {stoch_rsi.iloc[-1]:.4f}
  SAR:        {sar.iloc[-1]:.6f}
  ATR(14):    {atr.iloc[-1]:.6f}

━━━━━━━━━━━━━━━━━━━━━━━━
📊 *VOLUME:*
  Atual: {df['volume'].iloc[-1]:.2f}
  MM21:  {df['vol_ma21'].iloc[-1]:.2f}
  Ratio: {vol_ratio:.2f}x — {vol_forca}

━━━━━━━━━━━━━━━━━━━━━━━━
📐 *FIBONACCI (50 candles):*
  {chr(10).join(f'  {k}: {v}' for k, v in fib_ret.items())}
{setup_txt}

━━━━━━━━━━━━━━━━━━━━━━━━
💥 *LIQUIDAÇÕES:*
{liquidacoes}

⚠️ _Apenas para estudo. Não é recomendação._
"""
    return relatorio
