import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import ta
from exchanges import obter_candles, listar_lowcaps
from strategy import calcular_score_final, classificar_setup, calcular_squeeze_pro
from analysis import (
    avaliar_tendencia,
    analise_multi_timeframe,
    confluencia_mtf,
    lado_da_direcao,
    calcular_setup_trade,
)
from formatacao import esc, italic, fmt_price
from utils import SCORE_MINIMO, TOP_N_MOEDAS, TIMEFRAME_PADRAO, SCAN_WORKERS

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# HELPERS DE FORMATAÇÃO
# ══════════════════════════════════════════════════════════════

def _formatar_mtf(valor: str) -> str:
    """Converte a string de direção MTF em label curto e limpo."""
    v = str(valor).strip()
    if "ALTA"  in v: return "📈 ALTA"
    if "BAIXA" in v: return "📉 BAIXA"
    if "Erro"  in v or not v or v == "?": return "❓ N/A"
    return esc(v[:12])


# ══════════════════════════════════════════════════════════════
# SCAN PRINCIPAL
# ══════════════════════════════════════════════════════════════

def _analisar_moeda(m: dict, timeframe: str, score_minimo: int):
    """Analisa uma moeda; retorna o dict do resultado ou None se não passar no score."""
    par = m["symbol"]
    df  = obter_candles(par, timeframe, limit=300, preferida=m["exchange"])
    if df is None or len(df) < 100:
        return None

    direcao, _, _ = avaliar_tendencia(df)
    lado          = lado_da_direcao(direcao)

    # A confluência MTF vale no máximo 1 ponto: se nem com ela a moeda chega
    # ao score mínimo, poupa as 3 requisições extras do multi-timeframe.
    score, _, _ = calcular_score_final(df, par, 3, lado)
    if score < score_minimo:
        return None

    mtf, _ = analise_multi_timeframe(par, preferida=m["exchange"])
    score, breakdown, fase_amd = calcular_score_final(
        df, par, confluencia_mtf(mtf, lado), lado
    )
    if score < score_minimo:
        return None

    sq        = calcular_squeeze_pro(df)
    rsi       = ta.momentum.RSIIndicator(df["close"], 14).rsi().iloc[-1]
    vol_ma21  = df["volume"].rolling(21).mean().iloc[-1]
    vol_ratio = df["volume"].iloc[-1] / vol_ma21 if vol_ma21 > 0 else 0
    classe, classe_desc = classificar_setup(score, fase_amd, lado)

    return {
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
        "setup_trade": calcular_setup_trade(df, direcao, mtf=mtf),
    }


def escanear_lowcaps(
    top_n=TOP_N_MOEDAS,
    timeframe=TIMEFRAME_PADRAO,
    score_minimo=SCORE_MINIMO,
    workers=SCAN_WORKERS,
) -> list:
    moedas     = listar_lowcaps()
    total      = len(moedas)
    resultados = []
    falhas     = 0
    log.info(f"🔍 Escaneando {total} lowcaps no timeframe {timeframe} ({workers} workers)...")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futuros = {
            pool.submit(_analisar_moeda, m, timeframe, score_minimo): m["symbol"]
            for m in moedas
        }
        for i, fut in enumerate(as_completed(futuros), 1):
            try:
                r = fut.result()
                if r:
                    resultados.append(r)
            except Exception as e:
                falhas += 1
                log.debug(f"Falha ao analisar {futuros[fut]}: {e}")
            if i % 50 == 0:
                log.info(f"  ⏳ {i}/{total} processados...")

    resultados.sort(key=lambda x: x["score"], reverse=True)
    log.info(
        f"✅ Scan completo. {len(resultados)} moedas com score ≥ {score_minimo} "
        f"({falhas} falhas de dados)."
    )
    return resultados[:top_n]


# ══════════════════════════════════════════════════════════════
# FORMATAÇÃO DO RANKING
# ══════════════════════════════════════════════════════════════

def formatar_ranking(resultados: list, timeframe: str) -> str:
    if not resultados:
        return "❄️ Nenhuma lowcap com score suficiente neste ciclo\\."

    linhas = [
        f"🏆 *RADAR LOWCAP — TOP {len(resultados)}*",
        f"📅 Timeframe\\: `{esc(timeframe.upper())}` \\| Ciclo atual",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    medals = ["🥇", "🥈", "🥉"]

    for i, r in enumerate(resultados):
        medal = medals[i] if i < 3 else f"{i + 1}\\."
        st    = r.get("setup_trade", {})

        # ── Tags ──────────────────────────────────────────────
        tags = []
        if r["squeeze"] == "LIBERADO":   tags.append("🚨 SQUEEZE")
        if r["fase_amd"] == "acumulacao": tags.append("🔒 ACUM")
        tags_str = "  ".join(tags)

        # ── Preço e variação ──────────────────────────────────
        price_esc  = esc(fmt_price(r["price"]))
        change     = r["change24h"]
        change_esc = esc(f"{change:+.2f}%")
        c_emoji    = "📈" if change >= 0 else "📉"

        # ── MTF ───────────────────────────────────────────────
        mtf_1d = _formatar_mtf(r["mtf"].get("1d", "?"))
        mtf_4h = _formatar_mtf(r["mtf"].get("4h", "?"))
        mtf_1h = _formatar_mtf(r["mtf"].get("1h", "?"))

        # ── Score e classe ────────────────────────────────────
        score_esc   = esc(str(r["score"]))
        classe_esc  = esc(r["classe"])
        direcao_esc = esc(r["direcao"])
        rsi_esc     = esc(str(r["rsi"]))
        vol_esc     = esc(f"{r['vol_ratio']}x")

        # ── Bloco do setup de trade ───────────────────────────
        if st and st.get("valido"):
            lado      = "🟢 LONG" if st["lado"] == "long" else "🔴 SHORT"
            entrada   = esc(fmt_price(st["entrada"]))
            sl        = esc(fmt_price(st["sl"]))
            tp1       = esc(fmt_price(st["tp1"]))
            tp2       = esc(fmt_price(st["tp2"]))
            tp3       = esc(fmt_price(st["tp3"]))
            rr        = esc(f"{st['rr']:.1f}")
            risco_pct = esc(f"{st['risco_pct']:.2f}%")

            # ✅ sl_tipo isolado na função italic() — seguro para qualquer conteúdo
            sl_tipo_fmt = italic(st.get("sl_tipo", "estrutural"))

            avisos_txt = ""
            for aviso in st.get("avisos", []):
                avisos_txt += f"  ├ {esc(str(aviso))}\n"

            trade_bloco = (
                f"\n  ┌─ {lado} ─ R\\:R `1:{rr}`\n"
                f"  ├ 🎯 Entrada\\:      `{entrada}`\n"
                f"  ├ 🛑 SL\\:           `{sl}` \\({risco_pct}\\) — {sl_tipo_fmt}\n"
                f"  ├ 🥇 TP1 \\(30%\\)\\: `{tp1}`\n"
                f"  ├ 🥈 TP2 \\(40%\\)\\: `{tp2}`\n"
                f"  ├ 🥉 TP3 \\(30%\\)\\: `{tp3}` _\\+trailing_\n"
                + (avisos_txt if avisos_txt else "")
                + f"  └ _Após TP1\\: SL → breakeven_\n"
            )
        else:
            motivo      = st.get("motivo", "setup inválido") if st else "não calculado"
            # ✅ motivo dinâmico isolado dentro do italic() — nunca quebra o itálico
            trade_bloco = f"\n  ⚠️ {italic('Sem setup: ' + motivo)}\n"

        # ── Bloco completo da moeda ───────────────────────────
        symbol_esc   = esc(r["symbol"])
        exchange_esc = esc(r["exchange"].upper())

        bloco = (
            f"{medal} *{symbol_esc}* \\({exchange_esc}\\)"
            + (f" {tags_str}" if tags_str else "") + "\n"
            f"  💰 `{price_esc}` {c_emoji} `{change_esc}`\n"
            f"  🎯 Score\\: `{score_esc}/10` — {classe_esc}\n"
            f"  {direcao_esc}\n"
            f"  📊 RSI\\: `{rsi_esc}` \\| Vol\\: `{vol_esc}`\n"
            f"  🕐 1D\\: {mtf_1d} \\| 4H\\: {mtf_4h} \\| 1H\\: {mtf_1h}"
            f"{trade_bloco}"
        )
        linhas.append(bloco)

    linhas.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    linhas.append("⚠️ _Apenas para estudo\\. Não é recomendação\\._")
    return "\n".join(linhas)
