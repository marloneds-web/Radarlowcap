import pandas as pd
import numpy as np
import ta
from exchanges import obter_candles


def calcular_fibonacci(df, janela=50):
    df_j = df.tail(janela)
    topo  = df_j["high"].max()
    fundo = df_j["low"].min()
    diff  = topo - fundo
    if diff == 0:
        return {}, {}
    ret = {
        "0%":    round(topo, 6),
        "23.6%": round(topo - 0.236*diff, 6),
        "38.2%": round(topo - 0.382*diff, 6),
        "50%":   round(topo - 0.500*diff, 6),
        "61.8%": round(topo - 0.618*diff, 6),
        "78.6%": round(topo - 0.786*diff, 6),
        "100%":  round(fundo, 6),
    }
    exp = {
        "127.2%": round(fundo - 0.272*diff, 6),
        "161.8%": round(fundo - 0.618*diff, 6),
        "261.8%": round(fundo - 1.618*diff, 6),
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
    score = sum(1 for _, ok in criterios if ok)
    direcao = (f"📈 ALTA ({score}/5)" if score >= 3
               else f"📉 BAIXA ({5-score}/5)")
    detalhes = "\n".join(
        f"  {'✅' if ok else '❌'} {nome}" for nome, ok in criterios)
    return direcao, detalhes, score


def analise_multi_timeframe(par, timeframes=("1d","4h","1h")):
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


def gerar_relatorio_completo(par="BTCUSDT", timeframe="1h"):
    """Relatório técnico completo para um par."""
    from strategy import calcular_score_final, classificar_setup, calcular_squeeze_pro
    from exchanges import obter_liquidacoes

    df = obter_candles(par, timeframe, limit=300)

    df["EMA_9"]   = ta.trend.EMAIndicator(df["close"],  9).ema_indicator()
    df["EMA_21"]  = ta.trend.EMAIndicator(df["close"], 21).ema_indicator()
    df["EMA_80"]  = ta.trend.EMAIndicator(df["close"], 80).ema_indicator()
    df["EMA_200"] = ta.trend.EMAIndicator(df["close"],200).ema_indicator()

    rsi       = ta.momentum.RSIIndicator(df["close"], 14).rsi()
    macd_obj  = ta.trend.MACD(df["close"], 6, 13, 4)
    stoch_rsi = ta.momentum.StochRSIIndicator(df["close"], 8, 5, 5, 3).stochrsi()
    sar       = ta.trend.PSARIndicator(df["high"], df["low"], df["close"]).psar()
    atr       = ta.volatility.AverageTrueRange(df["high"],df["low"],df["close"],14).average_true_range()

    df["vol_ma21"] = df["volume"].rolling(21).mean()
    vol_ratio      = df["volume"].iloc[-1] / df["vol_ma21"].iloc[-1]
    vol_forca      = "Alta 🔥" if vol_ratio > 1 else "Baixa"

    fib_ret, fib_exp  = calcular_fibonacci(df)
    direcao, crit_det, _ = avaliar_tendencia(df)
    mtf, confluencia  = analise_multi_timeframe(par)
    sq                = calcular_squeeze_pro(df)
    score, breakdown, fase_amd = calcular_score_final(df, par, confluencia)
    classe, classe_desc = classificar_setup(score, fase_amd, sq["estado"], vol_ratio)
    liquidacoes       = obter_liquidacoes(par)

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
  {chr(10).join(f'  {k}: {v}' for k,v in fib_ret.items())}

━━━━━━━━━━━━━━━━━━━━━━━━
💥 *LIQUIDAÇÕES:*
{liquidacoes}

⚠️ _Apenas para estudo. Não é recomendação._
"""
    return relatorio
