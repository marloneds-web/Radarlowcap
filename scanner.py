import ta
import numpy as np
from exchanges import obter_candles, listar_lowcaps
from strategy import calcular_score_final, classificar_setup, calcular_squeeze_pro
from analysis import avaliar_tendencia, analise_multi_timeframe, calcular_setup_trade
from utils import SCORE_MINIMO, TOP_N_MOEDAS, TIMEFRAME_PADRAO


def _esc(text: str) -> str:
    """Escapa todos os caracteres especiais do MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _formatar_mtf(valor: str) -> str:
    """Converte a string de direção MTF em label curto e limpo."""
    v = str(valor).strip()
    if "ALTA" in v:
        return "📈 ALTA"
    if "BAIXA" in v:
        return "📉 BAIXA"
    if "Erro" in v or not v or v == "?":
        return "❓ N/A"
    return _esc(v[:12])


def _fmt_price(price: float) -> str:
    """Formata preço de acordo com a magnitude."""
    if price < 0.0001:
        return f"{price:.8f}"
    elif price < 1:
        return f"{price:.6f}"
    elif price < 1000:
        return f"{price:.4f}"
    else:
        return f"{price:,.2f}"


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

            mtf, confluencia    = analise_multi_timeframe(par)
            score, breakdown, fase_amd = calcular_score_final(df, par, confluencia)
            direcao, _, _       = avaliar_tendencia(df)
            sq                  = calcular_squeeze_pro(df)
            rsi                 = ta.momentum.RSIIndicator(df["close"], 14).rsi().iloc[-1]
            vol_ma21            = df["volume"].rolling(21).mean().iloc[-1]
            vol_ratio           = df["volume"].iloc[-1] / vol_ma21 if vol_ma21 > 0 else 0
            classe, classe_desc = classificar_setup(score, fase_amd, sq["estado"], vol_ratio)

            # ── Cálculo profissional de entrada/SL/TP ──────────
            setup_trade = calcular_setup_trade(df, direcao)

            if score >= score_minimo:
                resultados.append({
                    "symbol":       par,
                    "exchange":     m["exchange"],
                    "score":        score,
                    "classe":       classe,
                    "classe_desc":  classe_desc,
                    "direcao":      direcao,
                    "fase_amd":     fase_amd,
                    "squeeze":      sq["estado"],
                    "rsi":          round(rsi, 2),
                    "vol_ratio":    round(vol_ratio, 2),
                    "change24h":    m["change24h"],
                    "price":        m["price"],
                    "breakdown":    breakdown,
                    "mtf":          mtf,
                    "setup_trade":  setup_trade,
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
        medal  = medals[i] if i < 3 else f"{i + 1}\\."
        st     = r.get("setup_trade", {})

        # ── Tags ──────────────────────────────────────────────
        tags = []
        if r["squeeze"] == "LIBERADO":
            tags.append("🚨 SQUEEZE")
        if r["fase_amd"] == "acumulacao":
            tags.append("🔒 ACUM")
        tags_str = "  ".join(tags)

        # ── Preço e variação ──────────────────────────────────
        price_esc  = _esc(_fmt_price(r["price"]))
        change     = r["change24h"]
        change_esc = _esc(f"{change:+.2f}%")
        c_emoji    = "📈" if change >= 0 else "📉"

        # ── MTF ───────────────────────────────────────────────
        mtf_1d = _formatar_mtf(r["mtf"].get("1d", "?"))
        mtf_4h = _formatar_mtf(r["mtf"].get("4h", "?"))
        mtf_1h = _formatar_mtf(r["mtf"].get("1h", "?"))

        # ── Setup de trade (SL / TPs / RR) ────────────────────
        if st and st.get("valido"):
            lado      = "🟢 LONG" if st["lado"] == "long" else "🔴 SHORT"
            entrada   = _esc(_fmt_price(st["entrada"]))
            sl        = _esc(_fmt_price(st["sl"]))
            tp1       = _esc(_fmt_price(st["tp1"]))
            tp2       = _esc(_fmt_price(st["tp2"]))
            tp3       = _esc(_fmt_price(st["tp3"]))
            rr        = _esc(f"{st['rr']:.1f}")
            risco_pct = _esc(f"{st['risco_pct']:.2f}%")
            sl_tipo   = _esc(st.get("sl_tipo", "estrutural"))

            trade_bloco = (
                f"\n  ┌─ {lado} ─ R:R `1:{rr}`\n"
                f"  │ 🎯 Entrada:  `{entrada}`\n"
                f"  │ 🛑 SL:       `{sl}` \\({risco_pct}\\) — _{sl_tipo}_\n"
                f"  │ 🥇 TP1 \\(30%\\): `{tp1}`\n"
                f"  │ 🥈 TP2 \\(40%\\): `{tp2}`\n"
                f"  │ 🥉 TP3 \\(30%\\): `{tp3}` _\\+ trailing_\n"
                f"  └─ _SL → breakeven após TP1_\n"
            )
        else:
            motivo      = _esc(st.get("motivo", "setup inválido"))
            trade_bloco = f"\n  ⚠️ _Sem setup: {motivo}_\n"

        # ── Monta bloco completo ───────────────────────────────
        bloco = (
            f"{medal} *{_esc(r['symbol'])}* "
            f"\\({_esc(r['exchange'].upper())}\\)"
            + (f" {tags_str}" if tags_str else "") + "\n"
            f"  💰 `{price_esc}` {c_emoji} `{change_esc}`\n"
            f"  🎯 Score: `{r['score']}/10` — {_esc(r['classe'])}\n"
            f"  {_esc(r['direcao'])}\n"
            f"  📊 RSI: `{r['rsi']}` \\| Vol: `{r['vol_ratio']}x`\n"
            f"  🕐 1D: {mtf_1d} \\| 4H: {mtf_4h} \\| 1H: {mtf_1h}"
            f"{trade_bloco}"
        )
        linhas.append(bloco)

    linhas.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    linhas.append("⚠️ _Apenas para estudo\\. Não é recomendação\\._")
    return "\n".join(linhas)
