import ta
from exchanges import obter_candles, listar_lowcaps
from strategy import calcular_score_final, classificar_setup, calcular_squeeze_pro
from analysis import avaliar_tendencia, analise_multi_timeframe
from utils import SCORE_MINIMO, TOP_N_MOEDAS, TIMEFRAME_PADRAO


def _esc(text: str) -> str:
    """Escapa todos os caracteres especiais do MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


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

            mtf, confluencia = analise_multi_timeframe(par)
            score, breakdown, fase_amd = calcular_score_final(df, par, confluencia)
            direcao, _, _ = avaliar_tendencia(df)
            sq        = calcular_squeeze_pro(df)
            rsi       = ta.momentum.RSIIndicator(df["close"], 14).rsi().iloc[-1]
            vol_ma21  = df["volume"].rolling(21).mean().iloc[-1]
            vol_ratio = df["volume"].iloc[-1] / vol_ma21 if vol_ma21 > 0 else 0
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

        except Exception:
            continue

    resultados.sort(key=lambda x: x["score"], reverse=True)
    print(f"✅ Scan completo. {len(resultados)} moedas com score ≥ {score_minimo}.")
    return resultados[:top_n]


def formatar_ranking(resultados: list, timeframe: str) -> str:
    if not resultados:
        return "❄️ Nenhuma lowcap com score suficiente neste ciclo\\."

    linhas = [
        f"🏆 *RADAR LOWCAP — TOP {len(resultados)}*",
        f"📅 Timeframe: `{timeframe.upper()}` \\| Ciclo atual",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    medals = ["🥇", "🥈", "🥉"]

    for i, r in enumerate(resultados):
        medal = medals[i] if i < 3 else f"{i + 1}\\."

        # Tags de destaque
        tags = []
        if r["squeeze"] == "LIBERADO":
            tags.append("🚨 SQUEEZE")
        if r["fase_amd"] == "acumulacao":
            tags.append("🔒 ACUM")
        tags_str = "  ".join(tags)

        # Direção (já vem formatada, escapa tudo)
        direcao_esc = _esc(r["direcao"])

        # Classe (escapa)
        classe_esc = _esc(r["classe"])

        # MTF — escapa cada valor individualmente
        mtf_1d = _esc(str(r["mtf"].get("1d", "?"))[:10])
        mtf_4h = _esc(str(r["mtf"].get("4h", "?"))[:10])
        mtf_1h = _esc(str(r["mtf"].get("1h", "?"))[:10])

        # Preço formatado
        price_esc = _esc(f"{r['price']:.8f}".rstrip("0").rstrip("."))

        # Change 24h com sinal
        change = r["change24h"]
        change_emoji = "📈" if change >= 0 else "📉"
        change_esc = _esc(f"{change:+.2f}%")

        bloco = (
            f"{medal} *{_esc(r['symbol'])}* "
            f"\\({_esc(r['exchange'].upper())}\\) {tags_str}\n"
            f"  💰 Preço: `{price_esc}` {change_emoji} `{change_esc}`\n"
            f"  🎯 Score: `{r['score']}/10` — {classe_esc}\n"
            f"  {direcao_esc}\n"
            f"  📊 RSI: `{r['rsi']}` \\| Vol: `{r['vol_ratio']}x`\n"
            f"  🕐 MTF: `1D` {mtf_1d} \\| `4H` {mtf_4h} \\| `1H` {mtf_1h}\n"
        )
        linhas.append(bloco)

    linhas.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    linhas.append("⚠️ _Apenas para estudo\\. Não é recomendação\\._")
    return "\n".join(linhas)
