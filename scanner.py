import ta
from exchanges import obter_candles, listar_lowcaps
from strategy import calcular_score_final, classificar_setup, calcular_squeeze_pro
from analysis import avaliar_tendencia, analise_multi_timeframe
from utils import SCORE_MINIMO, TOP_N_MOEDAS, TIMEFRAME_PADRAO


def escanear_lowcaps(
    top_n=TOP_N_MOEDAS,
    timeframe=TIMEFRAME_PADRAO,
    score_minimo=SCORE_MINIMO
) -> list:
    moedas = listar_lowcaps()
    resultados = []
    total = len(moedas)
    print(f"🔍 Escaneando {total} lowcaps no timeframe {timeframe}...")

    for i, m in enumerate(moedas, 1):
        par = m["symbol"]
        try:
            df = obter_candles(par, timeframe, limit=300)
            if df is None or len(df) < 100:
                continue

            _, _, mtf_conf = analise_multi_timeframe.__wrapped__(par) \
                if hasattr(analise_multi_timeframe,'__wrapped__') \
                else (None, None, 0)

            mtf, confluencia = analise_multi_timeframe(par)
            score, breakdown, fase_amd = calcular_score_final(df, par, confluencia)
            direcao, _, _ = avaliar_tendencia(df)
            sq  = calcular_squeeze_pro(df)
            rsi = ta.momentum.RSIIndicator(df["close"], 14).rsi().iloc[-1]
            vol_ratio = df["volume"].iloc[-1] / df["volume"].rolling(21).mean().iloc[-1]
            classe, classe_desc = classificar_setup(score, fase_amd, sq["estado"], vol_ratio)

            if score >= score_minimo:
                resultados.append({
                    "symbol":      par,
                    "exchange":    m["exchange"],
                    "score":       score,
                    "classe":      classe,
                    "classe_desc": classe_desc,
                    "direcao":     direcao,
                    "fase_amd":    fase_amd,
                    "squeeze":     sq["estado"],
                    "rsi":         round(rsi, 2),
                    "vol_ratio":   round(vol_ratio, 2),
                    "change24h":   m["change24h"],
                    "price":       m["price"],
                    "breakdown":   breakdown,
                    "mtf":         mtf,
                })
            if i % 20 == 0:
                print(f"  ⏳ {i}/{total} processados...")

        except Exception as e:
            continue

    resultados.sort(key=lambda x: x["score"], reverse=True)
    print(f"✅ Scan completo. {len(resultados)} moedas com score ≥ {score_minimo}.")
    return resultados[:top_n]


def formatar_ranking(resultados: list, timeframe: str) -> str:
    if not resultados:
        return "❄️ Nenhuma lowcap com score suficiente neste ciclo."

    linhas = [
        f"🏆 *RADAR LOWCAP — TOP {len(resultados)}*",
        f"📅 Timeframe: `{timeframe.upper()}` | Ciclo atual",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    medals = ["🥇","🥈","🥉"]
    for i, r in enumerate(resultados):
        emoji = medals[i] if i < 3 else f"{i+1}\\."
        squeeze_tag = "🚨 SQUEEZE!" if r["squeeze"] == "LIBERADO" else ""
        amd_tag     = "🔒 ACUM"    if r["fase_amd"] == "acumulacao" else ""
        tags = " ".join(filter(None, [squeeze_tag, amd_tag]))

        linhas.append(
            f"{emoji} *{r['symbol']}* ({r['exchange'].upper()}) {tags}\n"
            f"  Score: `{r['score']}/10` — {r['classe']}\n"
            f"  {r['direcao']}\n"
            f"  RSI: `{r['rsi']}` | Vol: `{r['vol_ratio']}x` | 24h: `{r['change24h']}%`\n"
            f"  MTF: 1D={r['mtf'].get('1d','?')[:8]} | "
            f"4H={r['mtf'].get('4h','?')[:8]} | "
            f"1H={r['mtf'].get('1h','?')[:8]}\n"
        )

    linhas.append("⚠️ _Apenas para estudo. Não é recomendação._")
    return "\n".join(linhas)
