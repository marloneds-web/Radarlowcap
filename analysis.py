import pandas as pd
import numpy as np
import ta
from exchanges import obter_candles


# ══════════════════════════════════════════════════════════════
# FIBONACCI
# ══════════════════════════════════════════════════════════════

def calcular_fibonacci(df: pd.DataFrame, janela: int = 50):
    df_j  = df.tail(janela)
    topo  = df_j["high"].max()
    fundo = df_j["low"].min()
    diff  = topo - fundo
    if diff == 0:
        return {}, {}
    ret = {
        "0%":    round(topo, 8),
        "23.6%": round(topo - 0.236 * diff, 8),
        "38.2%": round(topo - 0.382 * diff, 8),
        "50%":   round(topo - 0.500 * diff, 8),
        "61.8%": round(topo - 0.618 * diff, 8),
        "78.6%": round(topo - 0.786 * diff, 8),
        "100%":  round(fundo, 8),
    }
    exp = {
        "127.2%": round(topo + 0.272 * diff, 8),
        "161.8%": round(topo + 0.618 * diff, 8),
        "261.8%": round(topo + 1.618 * diff, 8),
    }
    return ret, exp


# ══════════════════════════════════════════════════════════════
# SWING POINTS
# ══════════════════════════════════════════════════════════════

def _swing_points(df: pd.DataFrame, janela: int = 5):
    """Detecta topos e fundos de swing."""
    highs = df["high"].values
    lows  = df["low"].values
    n     = len(highs)

    swing_highs = []
    swing_lows  = []

    for idx in range(janela, n - janela):
        if all(highs[idx] >= highs[idx - j] for j in range(1, janela + 1)) and \
           all(highs[idx] >= highs[idx + j] for j in range(1, janela + 1)):
            swing_highs.append((idx, highs[idx]))

        if all(lows[idx] <= lows[idx - j] for j in range(1, janela + 1)) and \
           all(lows[idx] <= lows[idx + j] for j in range(1, janela + 1)):
            swing_lows.append((idx, lows[idx]))

    return swing_highs, swing_lows


# ══════════════════════════════════════════════════════════════
# FAIR VALUE GAP
# ══════════════════════════════════════════════════════════════

def _detectar_fvg(df: pd.DataFrame, lado: str = "long") -> list:
    """
    Detecta Fair Value Gaps recentes.
    Long  FVG: low[i] > high[i-2]
    Short FVG: high[i] < low[i-2]
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


# ══════════════════════════════════════════════════════════════
# TENDÊNCIA
# ══════════════════════════════════════════════════════════════

def avaliar_tendencia(df: pd.DataFrame):
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
    score   = sum(1 for _, ok in criterios if ok)
    direcao = (f"📈 ALTA ({score}/5)" if score >= 3
               else f"📉 BAIXA ({5 - score}/5)")
    detalhes = "\n".join(
        f"  {'✅' if ok else '❌'} {nome}" for nome, ok in criterios
    )
    return direcao, detalhes, score


# ══════════════════════════════════════════════════════════════
# MULTI-TIMEFRAME
# ══════════════════════════════════════════════════════════════

def analise_multi_timeframe(par: str, timeframes: tuple = ("1d", "4h", "1h")):
    resultados = {}
    for tf in timeframes:
        try:
            df = obter_candles(par, tf, limit=200)
            direcao, _, _ = avaliar_tendencia(df)
            resultados[tf] = direcao
        except Exception as e:
            resultados[tf] = f"Erro: {str(e)[:20]}"
    confluencia = sum(1 for v in resultados.values() if "ALTA" in v)
    return resultados, confluencia


# ══════════════════════════════════════════════════════════════
# SETUP DE TRADE: ENTRADA / SL / TP
# ══════════════════════════════════════════════════════════════

def calcular_setup_trade(df: pd.DataFrame, direcao: str, mtf: dict = None) -> dict:
    """
    Calcula entrada, SL e TPs baseado em estrutura de mercado.

    Filosofia do SL:
    ─────────────────────────────────────────────────────────
    • SL fica ABAIXO do swing low (long) ou ACIMA do swing high (short)
    • Buffer = 0.3x ATR  — só pra não pegar o pavio exato
    • Mínimo = 0.5x ATR  — só se o swing estiver colado no preço
    • Quem define o SL é o SWING, não o ATR
    """
    try:
        preco = df["close"].iloc[-1]
        atr   = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], 14
        ).average_true_range().iloc[-1]
        rsi   = ta.momentum.RSIIndicator(df["close"], 14).rsi().iloc[-1]

        swing_highs, swing_lows = _swing_points(df, janela=5)
        lado = "long" if "ALTA" in direcao else "short"

        # ── Filtro 1: RSI extremo ──────────────────────────────
        if lado == "long" and rsi > 70:
            return {
                "valido": False,
                "motivo": f"RSI sobrecomprado ({rsi:.1f}) — risco de topo",
            }
        if lado == "short" and rsi < 30:
            return {
                "valido": False,
                "motivo": f"RSI sobrevendido ({rsi:.1f}) — risco de fundo",
            }

        # ── Filtro 2: Preço próximo ao topo/fundo estrutural ──
        if swing_highs and lado == "long":
            ultimo_topo   = swing_highs[-1][1]
            dist_topo_pct = ((ultimo_topo - preco) / preco) * 100
            if dist_topo_pct < 1.5:
                return {
                    "valido": False,
                    "motivo": f"Preço próximo ao topo ({dist_topo_pct:.1f}% de distância)",
                }

        if swing_lows and lado == "short":
            ultimo_fundo   = swing_lows[-1][1]
            dist_fundo_pct = ((preco - ultimo_fundo) / preco) * 100
            if dist_fundo_pct < 1.5:
                return {
                    "valido": False,
                    "motivo": f"Preço próximo ao fundo ({dist_fundo_pct:.1f}% de distância)",
                }

        # ── Filtro 3: Confluência MTF ──────────────────────────
        aviso_mtf = ""
        if mtf:
            tf_1h = str(mtf.get("1h", ""))
            tf_4h = str(mtf.get("4h", ""))
            if lado == "long":
                if "BAIXA" in tf_1h and "BAIXA" in tf_4h:
                    return {
                        "valido": False,
                        "motivo": "1H e 4H em BAIXA — sem confluência",
                    }
                if "BAIXA" in tf_1h:
                    aviso_mtf = "⚠️ 1H em baixa — aguardar pullback"
            else:
                if "ALTA" in tf_1h and "ALTA" in tf_4h:
                    return {
                        "valido": False,
                        "motivo": "1H e 4H em ALTA — sem confluência",
                    }
                if "ALTA" in tf_1h:
                    aviso_mtf = "⚠️ 1H em alta — aguardar pullback"

        if lado == "long":
            # ── LONG ──────────────────────────────────────────
            if len(swing_lows) < 2:
                return {"valido": False, "motivo": "swings insuficientes"}

            ultimo_fundo = swing_lows[-1][1]

            # SL: swing low - buffer 0.3x ATR
            sl_raw    = ultimo_fundo - (atr * 0.3)
            risco_abs = preco - sl_raw

            # Mínimo de 0.5x ATR (evita stop colado)
            if risco_abs < atr * 0.5:
                sl_raw    = preco - (atr * 0.5)
                risco_abs = preco - sl_raw

            risco_pct = (risco_abs / preco) * 100

            if risco_pct > 8:
                return {"valido": False, "motivo": f"SL muito distante ({risco_pct:.1f}%)"}
            if risco_abs <= 0:
                return {"valido": False, "motivo": "SL inválido"}

            entrada = preco

            # TP1 → topo de swing mais próximo acima
            topos_acima = sorted([h for _, h in swing_highs if h > preco])
            tp1 = round(topos_acima[0], 8) if topos_acima \
                  else round(preco + risco_abs * 2.0, 8)

            # TP2 → FVG bullish ou Fibonacci 127.2%
            fvgs      = _detectar_fvg(df, lado="long")
            fvg_acima = sorted([f for f in fvgs if f > tp1])
            if fvg_acima:
                tp2 = round(fvg_acima[0], 8)
            else:
                _, fib_exp = calcular_fibonacci(df, janela=50)
                tp2_fib    = fib_exp.get("127.2%", 0)
                tp2 = round(tp2_fib, 8) if tp2_fib > tp1 \
                      else round(tp1 + risco_abs * 1.5, 8)

            # TP3 → maior topo estrutural acima do TP2
            topos_grandes = sorted([h for _, h in swing_highs if h > tp2])
            tp3 = round(topos_grandes[-1], 8) if topos_grandes \
                  else round(tp2 + risco_abs * 2.0, 8)

            rr = round((tp2 - entrada) / risco_abs, 2)

        else:
            # ── SHORT ─────────────────────────────────────────
            if len(swing_highs) < 2:
                return {"valido": False, "motivo": "swings insuficientes"}

            ultimo_topo = swing_highs[-1][1]

            # SL: swing high + buffer 0.3x ATR
            sl_raw    = ultimo_topo + (atr * 0.3)
            risco_abs = sl_raw - preco

            # Mínimo de 0.5x ATR
            if risco_abs < atr * 0.5:
                sl_raw    = preco + (atr * 0.5)
                risco_abs = sl_raw - preco

            risco_pct = (risco_abs / preco) * 100

            if risco_pct > 8:
                return {"valido": False, "motivo": f"SL muito distante ({risco_pct:.1f}%)"}
            if risco_abs <= 0:
                return {"valido": False, "motivo": "SL inválido"}

            entrada = preco

            # TP1 → fundo de swing mais próximo abaixo
            fundos_abaixo = sorted([l for _, l in swing_lows if l < preco], reverse=True)
            tp1 = round(fundos_abaixo[0], 8) if fundos_abaixo \
                  else round(preco - risco_abs * 2.0, 8)

            # TP2 → FVG bearish ou Fibonacci 61.8%
            fvgs       = _detectar_fvg(df, lado="short")
            fvg_abaixo = sorted([f for f in fvgs if f < tp1], reverse=True)
            if fvg_abaixo:
                tp2 = round(fvg_abaixo[0], 8)
            else:
                fib_ret, _ = calcular_fibonacci(df, janela=50)
                tp2_fib    = fib_ret.get("61.8%", 0)
                tp2 = round(tp2_fib, 8) if 0 < tp2_fib < tp1 \
                      else round(tp1 - risco_abs * 1.5, 8)

            # TP3 → menor fundo estrutural abaixo do TP2
            fundos_grandes = sorted([l for _, l in swing_lows if l < tp2])
            tp3 = round(fundos_grandes[0], 8) if fundos_grandes \
                  else round(tp2 - risco_abs * 2.0, 8)

            rr = round((entrada - tp2) / risco_abs, 2)

        # ── Filtro final: R:R mínimo 2:1 ──────────────────────
        if rr < 2.0:
            return {
                "valido": False,
                "motivo": f"R:R insuficiente (1:{rr})",
            }

        # ── Avisos (não invalidam, só alertam) ────────────────
        avisos = []
        if lado == "long"  and rsi > 60:
            avisos.append(f"⚠️ RSI elevado ({rsi:.1f}) — entrada em força")
        if lado == "short" and rsi < 40:
            avisos.append(f"⚠️ RSI baixo ({rsi:.1f}) — entrada em fraqueza")
        if aviso_mtf:
            avisos.append(aviso_mtf)

        sl_tipo = "abaixo do swing low" if lado == "long" else "acima do swing high"

        return {
            "valido":    True,
            "lado":      lado,
            "entrada":   round(entrada, 8),
            "sl":        round(sl_raw, 8),
            "sl_tipo":   sl_tipo,
            "tp1":       tp1,
            "tp2":       tp2,
            "tp3":       tp3,
            "rr":        rr,
            "risco_pct": round(risco_pct, 2),
            "atr":       round(atr, 8),
            "avisos":    avisos,
        }

    except Exception as e:
        return {"valido": False, "motivo": str(e)[:40]}


# ══════════════════════════════════════════════════════════════
# RELATÓRIO COMPLETO (comando /analisar)
# ══════════════════════════════════════════════════════════════

def gerar_relatorio_completo(par: str = "BTCUSDT", timeframe: str = "1h") -> str:
    from strategy import calcular_score_final, classificar_setup, calcular_squeeze_pro
    from exchanges import obter_liquidacoes

    df = obter_candles(par, timeframe, limit=300)

    df["EMA_9"]   = ta.trend.EMAIndicator(df["close"],   9).ema_indicator()
    df["EMA_21"]  = ta.trend.EMAIndicator(df["close"],  21).ema_indicator()
    df["EMA_80"]  = ta.trend.EMAIndicator(df["close"],  80).ema_indicator()
    df["EMA_200"] = ta.trend.EMAIndicator(df["close"], 200).ema_indicator()

    rsi_s     = ta.momentum.RSIIndicator(df["close"], 14).rsi()
    macd_obj  = ta.trend.MACD(df["close"], 6, 13, 4)
    stoch_rsi = ta.momentum.StochRSIIndicator(df["close"], 8, 5, 5, 3).stochrsi()
    sar       = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar()
    atr_s     = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], 14
    ).average_true_range()

    df["vol_ma21"] = df["volume"].rolling(21).mean()
    vol_ratio      = df["volume"].iloc[-1] / df["vol_ma21"].iloc[-1]
    vol_forca      = "Alta 🔥" if vol_ratio > 1 else "Baixa"

    fib_ret, fib_exp           = calcular_fibonacci(df)
    direcao, crit_det, _       = avaliar_tendencia(df)
    mtf, confluencia           = analise_multi_timeframe(par)

    sq                         = calcular_squeeze_pro(df)
    score, breakdown, fase_amd = calcular_score_final(df, par, confluencia)
    classe, classe_desc        = classificar_setup(score, fase_amd, sq["estado"], vol_ratio)
    liquidacoes                = obter_liquidacoes(par)

    st = calcular_setup_trade(df, direcao, mtf=mtf)

    if st.get("valido"):
        lado_label = "🟢 LONG" if st["lado"] == "long" else "🔴 SHORT"
        avisos_txt = "\n".join(f"  {a}" for a in st.get("avisos", []))
        setup_txt  = (
            f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📐 *SETUP:* {lado_label} | R:R `1:{st['rr']}`\n\n"
            f"  🎯 Entrada:     `{st['entrada']}`\n"
            f"  🛑 SL:          `{st['sl']}` ({st['risco_pct']}%) — {st['sl_tipo']}\n"
            f"  🥇 TP1 (30%):   `{st['tp1']}`\n"
            f"  🥈 TP2 (40%):   `{st['tp2']}`\n"
            f"  🥉 TP3 (30%):   `{st['tp3']}` + trailing\n"
            f"  📏 ATR(14):     `{st['atr']}`\n"
            + (f"\n{avisos_txt}\n" if avisos_txt else "")
            + f"  💡 _Após TP1: mover SL para entrada (breakeven)_"
        )
    else:
        setup_txt = (
            f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *SETUP:* _{st.get('motivo', 'não identificado')}_"
        )

    score_emoji = "🔥" if score >= 8 else "⚡" if score >= 6 else "📊" if score >= 4 else "❄️"

    relatorio = (
        f"╔══════════════════════════════════════════╗\n"
        f"   📊 *{par}* | {timeframe.upper()}\n"
        f"╚══════════════════════════════════════════╝\n\n"
        f"{score_emoji} *SCORE: {score}/10* — {classe}\n"
        f"_{classe_desc}_\n\n"
        + "\n".join(breakdown) +
        f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📐 *TENDÊNCIA:* {direcao}\n"
        f"{crit_det}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 *MULTI-TIMEFRAME:*\n"
        f"  1D → {mtf.get('1d', 'N/A')}\n"
        f"  4H → {mtf.get('4h', 'N/A')}\n"
        f"  1H → {mtf.get('1h', 'N/A')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *SQUEEZE:* {sq['emoji']} {sq['msg']}\n"
        f"  Momentum: {sq['momentum']} {'↑' if sq['crescendo'] else '↓'}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *MÉDIAS MÓVEIS:*\n"
        f"  EMA 9   → {df['EMA_9'].iloc[-1]:.6f}\n"
        f"  EMA 21  → {df['EMA_21'].iloc[-1]:.6f}\n"
        f"  EMA 80  → {df['EMA_80'].iloc[-1]:.6f}\n"
        f"  EMA 200 → {df['EMA_200'].iloc[-1]:.6f}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *INDICADORES:*\n"
        f"  RSI(14):   {rsi_s.iloc[-1]:.2f}\n"
        f"  MACD:      {macd_obj.macd().iloc[-1]:.6f}\n"
        f"  Sinal:     {macd_obj.macd_signal().iloc[-1]:.6f}\n"
        f"  Stoch RSI: {stoch_rsi.iloc[-1]:.4f}\n"
        f"  SAR:       {sar.iloc[-1]:.6f}\n"
        f"  ATR(14):   {atr_s.iloc[-1]:.6f}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *VOLUME:*\n"
        f"  Atual: {df['volume'].iloc[-1]:.2f}\n"
        f"  MM21:  {df['vol_ma21'].iloc[-1]:.2f}\n"
        f"  Ratio: {vol_ratio:.2f}x — {vol_forca}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📐 *FIBONACCI (50 candles):*\n"
        + "\n".join(f"  {k}: {v}" for k, v in fib_ret.items())
        + setup_txt +
        f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💥 *LIQUIDAÇÕES:*\n"
        f"{liquidacoes}\n\n"
        f"⚠️ _Apenas para estudo. Não é recomendação._"
    )
    return relatorio
