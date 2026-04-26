import pandas as pd
import numpy as np
import ta
from exchanges import obter_candles


# ══════════════════════════════════════════════════════════════
# HELPERS DE ESCAPE — MarkdownV2
# ══════════════════════════════════════════════════════════════

def _e(text) -> str:
    """Escapa TODOS os caracteres reservados do MarkdownV2."""
    text = str(text)
    for ch in r"\_*[]()~`>#+-=|{}.!:":
        text = text.replace(ch, f"\\{ch}")
    return text


def _c(text) -> str:
    """Envolve em bloco de código inline (não precisa escapar dentro)."""
    return f"`{text}`"


def _b(text) -> str:
    """Negrito seguro."""
    return f"*{_e(str(text))}*"


def _i(text) -> str:
    """
    Itálico seguro — escapa tudo EXCETO underscore,
    que é o delimitador do itálico no MarkdownV2.
    """
    inner = str(text)
    for ch in r"\*[]()~`>#+-=|{}.!:":
        inner = inner.replace(ch, f"\\{ch}")
    return f"_{inner}_"


def _safe(text) -> str:
    """
    Remove delimitadores de entidade para textos dinâmicos curtos.
    Substitui _ por espaço, remove * ` ~ [ ].
    """
    return (
        str(text)
        .replace("_", " ")
        .replace("*", "")
        .replace("`", "")
        .replace("~", "")
        .replace("[", "")
        .replace("]", "")
    )


# ══════════════════════════════════════════════════════════════
# FIBONACCI — versão melhorada (Boroden + Golden Pocket)
# ══════════════════════════════════════════════════════════════

def calcular_fibonacci(df: pd.DataFrame, janela: int = 50):
    """
    Calcula níveis de retração e extensão a partir dos swing points
    reais dentro da janela, não apenas max/min bruto.

    Retorna:
        ret  — dict com níveis de retração
        exp  — dict com extensões + Golden Pocket
        meta — dict com topo, fundo e diff usados
    """
    df_j = df.tail(janela).copy()

    # ── Swing points dentro da janela (lookback = 3) ───────────
    swing_h, swing_l = _swing_points(df_j.reset_index(drop=True), janela=3)

    # Fallback: usa max/min se não houver swings suficientes
    topo  = swing_h[-1][1] if swing_h else df_j["high"].max()
    fundo = swing_l[-1][1] if swing_l else df_j["low"].min()

    # Garante ordem correta
    if fundo > topo:
        topo, fundo = fundo, topo

    diff = topo - fundo
    if diff == 0:
        return {}, {}, {}

    # ── Retrações (do topo para baixo) ────────────────────────
    ret = {
        "0%":    round(topo,              8),
        "23.6%": round(topo - 0.236*diff, 8),
        "38.2%": round(topo - 0.382*diff, 8),
        "50%":   round(topo - 0.500*diff, 8),
        "61.8%": round(topo - 0.618*diff, 8),  # Golden Ratio
        "65%":   round(topo - 0.650*diff, 8),  # Golden Pocket (par com 61.8%)
        "78.6%": round(topo - 0.786*diff, 8),
        "88.6%": round(topo - 0.886*diff, 8),  # Nível profundo
        "100%":  round(fundo,             8),
    }

    # ── Extensões ──────────────────────────────────────────────
    exp = {
        "127.2%":     round(topo  + 0.272*diff, 8),
        "161.8%":     round(topo  + 0.618*diff, 8),
        "200%":       round(topo  + 1.000*diff, 8),
        "261.8%":     round(topo  + 1.618*diff, 8),
        "ext_127.2%": round(fundo - 0.272*diff, 8),  # abaixo do fundo (short)
        "ext_161.8%": round(fundo - 0.618*diff, 8),  # abaixo do fundo (short)
    }

    meta = {"topo": topo, "fundo": fundo, "diff": diff}
    return ret, exp, meta


def _golden_pocket(fib_ret: dict) -> tuple:
    """Retorna a zona Golden Pocket (61.8% ~ 65%)."""
    return fib_ret.get("61.8%", 0), fib_ret.get("65%", 0)


def _nivel_fib_mais_proximo(preco: float, fib_ret: dict, tolerancia_pct: float = 1.5):
    """
    Verifica se o preço está próximo de algum nível Fib.
    Retorna (nivel_nome, nivel_valor) ou (None, None).
    Boroden: 3-4 ticks de tolerância → usamos % do preço.
    """
    for nome, valor in fib_ret.items():
        if valor == 0:
            continue
        dist_pct = abs(preco - valor) / preco * 100
        if dist_pct <= tolerancia_pct:
            return nome, valor
    return None, None


def _projecao_alternada(swing_a: float, swing_b: float,
                        ponto_c: float, razao: float = 1.0) -> float:
    """
    Alternate Price Projection (Boroden Cap. 5):
    Compara swings na mesma direção.
    APP = C ± (|A-B| × razão)
    """
    diff = abs(swing_b - swing_a)
    if swing_b > swing_a:
        return round(ponto_c + diff * razao, 8)
    return round(ponto_c - diff * razao, 8)


# ══════════════════════════════════════════════════════════════
# SWING POINTS
# ══════════════════════════════════════════════════════════════

def _swing_points(df: pd.DataFrame, janela: int = 5):
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
        ("Preco acima da EMA21",  preco > ema21.iloc[-1]),
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
# SETUP DE TRADE — melhorado com Boroden + Golden Pocket
# ══════════════════════════════════════════════════════════════

def calcular_setup_trade(df: pd.DataFrame, direcao: str, mtf: dict = None) -> dict:
    """
    Setup melhorado com:
    - Golden Pocket como zona de entrada preferencial
    - Confluência Fib + swing points para TPs
    - Alternate Price Projection (Boroden) para TP3
    - Validação de proximidade do preço ao nível Fib
    """
    try:
        preco = df["close"].iloc[-1]
        atr   = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], 14
        ).average_true_range().iloc[-1]
        rsi   = ta.momentum.RSIIndicator(df["close"], 14).rsi().iloc[-1]

        swing_highs, swing_lows = _swing_points(df, janela=5)
        lado = "long" if "ALTA" in direcao else "short"

        # ── Filtros RSI ──────────────────────────────────────────
        if lado == "long"  and rsi > 70:
            return {"valido": False, "motivo": f"RSI sobrecomprado ({rsi:.1f})"}
        if lado == "short" and rsi < 30:
            return {"valido": False, "motivo": f"RSI sobrevendido ({rsi:.1f})"}

        # ── Fibonacci completo ───────────────────────────────────
        fib_ret, fib_exp, fib_meta = calcular_fibonacci(df, janela=50)
        golden_low, golden_high    = _golden_pocket(fib_ret)

        # Verifica se preço está no Golden Pocket
        em_golden_pocket = (
            golden_low and golden_high
            and golden_low <= preco <= golden_high * 1.005
        )

        # Nível Fib mais próximo
        nivel_nome, nivel_valor = _nivel_fib_mais_proximo(preco, fib_ret)

        # ── Validação distância de swing ─────────────────────────
        if swing_highs and lado == "long":
            ultimo_topo   = swing_highs[-1][1]
            dist_topo_pct = ((ultimo_topo - preco) / preco) * 100
            if dist_topo_pct < 1.5:
                return {"valido": False,
                        "motivo": f"Preco proximo ao topo ({dist_topo_pct:.1f}%)"}

        if swing_lows and lado == "short":
            ultimo_fundo   = swing_lows[-1][1]
            dist_fundo_pct = ((preco - ultimo_fundo) / preco) * 100
            if dist_fundo_pct < 1.5:
                return {"valido": False,
                        "motivo": f"Preco proximo ao fundo ({dist_fundo_pct:.1f}%)"}

        # ── Aviso MTF ────────────────────────────────────────────
        aviso_mtf = ""
        if mtf:
            tf_1h = str(mtf.get("1h", ""))
            tf_4h = str(mtf.get("4h", ""))
            if lado == "long":
                if "BAIXA" in tf_1h and "BAIXA" in tf_4h:
                    return {"valido": False, "motivo": "1H e 4H em BAIXA sem confluencia"}
                if "BAIXA" in tf_1h:
                    aviso_mtf = "1H em baixa — aguardar pullback ao Golden Pocket"
            else:
                if "ALTA" in tf_1h and "ALTA" in tf_4h:
                    return {"valido": False, "motivo": "1H e 4H em ALTA sem confluencia"}
                if "ALTA" in tf_1h:
                    aviso_mtf = "1H em alta — aguardar pullback ao 61.8%"

        # ════════════════════════════════════════════════════════
        # LONG
        # ════════════════════════════════════════════════════════
        if lado == "long":
            if len(swing_lows) < 2:
                return {"valido": False, "motivo": "swings insuficientes"}

            ultimo_fundo = swing_lows[-1][1]
            penult_fundo = swing_lows[-2][1]

            sl_raw    = ultimo_fundo - (atr * 0.3)
            risco_abs = preco - sl_raw

            if risco_abs < atr * 0.5:
                sl_raw    = preco - (atr * 0.5)
                risco_abs = preco - sl_raw

            risco_pct = (risco_abs / preco) * 100

            if risco_pct > 8:
                return {"valido": False, "motivo": f"SL muito distante ({risco_pct:.1f}%)"}
            if risco_abs <= 0:
                return {"valido": False, "motivo": "SL invalido"}

            entrada = preco

            # TP1 — primeiro swing high acima
            topos_acima = sorted([h for _, h in swing_highs if h > preco])
            tp1 = round(topos_acima[0], 8) if topos_acima \
                  else round(preco + risco_abs * 2.0, 8)

            # TP2 — FVG > extensão 127.2% > fallback
            fvgs      = _detectar_fvg(df, lado="long")
            fvg_acima = sorted([f for f in fvgs if f > tp1])
            ext_1272  = fib_exp.get("127.2%", 0)

            if fvg_acima:
                tp2 = round(fvg_acima[0], 8)
            elif ext_1272 and ext_1272 > tp1:
                tp2 = round(ext_1272, 8)
            else:
                tp2 = round(tp1 + risco_abs * 1.5, 8)

            # TP3 — Alternate Price Projection (Boroden Cap. 5)
            if len(swing_highs) >= 2:
                penult_topo = swing_highs[-2][1]
                app_100 = _projecao_alternada(penult_fundo, penult_topo, ultimo_fundo, 1.0)
                app_162 = _projecao_alternada(penult_fundo, penult_topo, ultimo_fundo, 1.618)
                if app_100 > tp2:
                    tp3 = round(app_100, 8)
                elif app_162 > tp2:
                    tp3 = round(app_162, 8)
                else:
                    ext_1618 = fib_exp.get("161.8%", 0)
                    tp3 = round(ext_1618, 8) if ext_1618 > tp2 \
                          else round(tp2 + risco_abs * 2.0, 8)
            else:
                ext_1618 = fib_exp.get("161.8%", 0)
                tp3 = round(ext_1618, 8) if ext_1618 > tp2 \
                      else round(tp2 + risco_abs * 2.0, 8)

            rr = round((tp2 - entrada) / risco_abs, 2)

        # ════════════════════════════════════════════════════════
        # SHORT
        # ════════════════════════════════════════════════════════
        else:
            if len(swing_highs) < 2:
                return {"valido": False, "motivo": "swings insuficientes"}

            ultimo_topo = swing_highs[-1][1]
            penult_topo = swing_highs[-2][1]

            sl_raw    = ultimo_topo + (atr * 0.3)
            risco_abs = sl_raw - preco

            if risco_abs < atr * 0.5:
                sl_raw    = preco + (atr * 0.5)
                risco_abs = sl_raw - preco

            risco_pct = (risco_abs / preco) * 100

            if risco_pct > 8:
                return {"valido": False, "motivo": f"SL muito distante ({risco_pct:.1f}%)"}
            if risco_abs <= 0:
                return {"valido": False, "motivo": "SL invalido"}

            entrada = preco

            # TP1 — primeiro swing low abaixo
            fundos_abaixo = sorted([l for _, l in swing_lows if l < preco], reverse=True)
            tp1 = round(fundos_abaixo[0], 8) if fundos_abaixo \
                  else round(preco - risco_abs * 2.0, 8)

            # TP2 — FVG > 61.8% retração > ext_127.2% > fallback
            fvgs       = _detectar_fvg(df, lado="short")
            fvg_abaixo = sorted([f for f in fvgs if f < tp1], reverse=True)
            fib_618    = fib_ret.get("61.8%", 0)
            ext_1272b  = fib_exp.get("ext_127.2%", 0)

            if fvg_abaixo:
                tp2 = round(fvg_abaixo[0], 8)
            elif fib_618 and 0 < fib_618 < tp1:
                tp2 = round(fib_618, 8)
            elif ext_1272b and 0 < ext_1272b < tp1:
                tp2 = round(ext_1272b, 8)
            else:
                tp2 = round(tp1 - risco_abs * 1.5, 8)

            # TP3 — APP para short
            if len(swing_lows) >= 2:
                penult_fundo = swing_lows[-2][1]
                ultimo_fundo = swing_lows[-1][1]
                app_100 = _projecao_alternada(penult_topo, penult_fundo, ultimo_topo, 1.0)
                app_162 = _projecao_alternada(penult_topo, penult_fundo, ultimo_topo, 1.618)
                if app_100 < tp2:
                    tp3 = round(app_100, 8)
                elif app_162 < tp2:
                    tp3 = round(app_162, 8)
                else:
                    ext_1618b = fib_exp.get("ext_161.8%", 0)
                    tp3 = round(ext_1618b, 8) if 0 < ext_1618b < tp2 \
                          else round(tp2 - risco_abs * 2.0, 8)
            else:
                ext_1618b = fib_exp.get("ext_161.8%", 0)
                tp3 = round(ext_1618b, 8) if 0 < ext_1618b < tp2 \
                      else round(tp2 - risco_abs * 2.0, 8)

            rr = round((entrada - tp2) / risco_abs, 2)

        # ── Validação RR ─────────────────────────────────────────
        if rr < 2.0:
            return {"valido": False, "motivo": f"RR insuficiente (1:{rr})"}

        # ── Avisos ───────────────────────────────────────────────
        avisos = []
        if lado == "long"  and rsi > 60:
            avisos.append(f"RSI elevado ({rsi:.1f}) — entrada em forca")
        if lado == "short" and rsi < 40:
            avisos.append(f"RSI baixo ({rsi:.1f}) — entrada em fraqueza")
        if aviso_mtf:
            avisos.append(aviso_mtf)
        if em_golden_pocket:
            avisos.append("Preco no Golden Pocket (61.8-65%) — zona ideal Boroden")
        if nivel_nome:
            avisos.append(f"Preco proximo ao nivel Fib {nivel_nome} — zona de decisao")

        sl_tipo = "abaixo do swing low" if lado == "long" else "acima do swing high"

        return {
            "valido":           True,
            "lado":             lado,
            "entrada":          round(entrada, 8),
            "sl":               round(sl_raw, 8),
            "sl_tipo":          sl_tipo,
            "tp1":              tp1,
            "tp2":              tp2,
            "tp3":              tp3,
            "rr":               rr,
            "risco_pct":        round(risco_pct, 2),
            "atr":              round(atr, 8),
            "avisos":           avisos,
            "em_golden_pocket": em_golden_pocket,
            "nivel_fib":        nivel_nome or "—",
        }

    except Exception as ex:
        return {"valido": False, "motivo": str(ex)[:40]}


# ══════════════════════════════════════════════════════════════
# RELATÓRIO COMPLETO — 100% MarkdownV2 seguro
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

    fib_ret, fib_exp, fib_meta     = calcular_fibonacci(df)
    direcao, crit_det, _           = avaliar_tendencia(df)
    mtf, confluencia               = analise_multi_timeframe(par)

    sq                             = calcular_squeeze_pro(df)
    score, breakdown, fase_amd     = calcular_score_final(df, par, confluencia)
    classe, classe_desc            = classificar_setup(score, fase_amd, sq["estado"], vol_ratio)
    liquidacoes                    = obter_liquidacoes(par)

    st = calcular_setup_trade(df, direcao, mtf=mtf)

    # ── Helpers locais de formatação numérica ─────────────────
    def _fp(v) -> str:
        f = float(v)
        if f < 0.0001:   s = f"{f:.8f}"
        elif f < 1:      s = f"{f:.6f}"
        elif f < 1000:   s = f"{f:.4f}"
        else:            s = f"{f:,.2f}"
        return f"`{s}`"

    def _fn(v, decimais=2) -> str:
        return _e(f"{float(v):.{decimais}f}")

    # ── Bloco de setup ────────────────────────────────────────
    if st.get("valido"):
        lado_label = "🟢 LONG" if st["lado"] == "long" else "🔴 SHORT"
        rr_esc     = _e(str(st["rr"]))
        risco_esc  = _e(f"{st['risco_pct']}%")
        sl_tipo_e  = _e(_safe(st["sl_tipo"]))
        gp_badge   = " ⭐ _Golden Pocket_" if st.get("em_golden_pocket") else ""
        fib_badge  = f" \\({_e(st['nivel_fib'])}\\)" if st.get("nivel_fib") and st["nivel_fib"] != "—" else ""

        avisos_linhas = ""
        for av in st.get("avisos", []):
            avisos_linhas += f"  ⚠️ {_e(_safe(str(av)))}\n"

        setup_txt = (
            f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📐 *SETUP:* {lado_label} \\| R\\:R `1:{rr_esc}`{gp_badge}\n\n"
            f"  🎯 Entrada\\:{fib_badge}   {_fp(st['entrada'])}\n"
            f"  🛑 SL\\:        {_fp(st['sl'])} \\({risco_esc}\\) \\— {sl_tipo_e}\n"
            f"  🥇 TP1 \\(30%\\)\\: {_fp(st['tp1'])}\n"
            f"  🥈 TP2 \\(40%\\)\\: {_fp(st['tp2'])}\n"
            f"  🥉 TP3 \\(30%\\)\\: {_fp(st['tp3'])} \\+trailing\n"
            f"  📏 ATR\\(14\\)\\:  {_fp(st['atr'])}\n"
            + (f"\n{avisos_linhas}" if avisos_linhas else "")
            + f"  💡 Apos TP1\\: mover SL para entrada \\(breakeven\\)\n"
        )
    else:
        motivo_e  = _e(_safe(st.get("motivo", "nao identificado")))
        setup_txt = (
            f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *SETUP:* {motivo_e}\n"
        )

    score_emoji = (
        "🔥" if score >= 8 else
        "⚡" if score >= 6 else
        "📊" if score >= 4 else
        "❄️"
    )

    # ── MTF ───────────────────────────────────────────────────
    mtf_1d = _e(_safe(mtf.get("1d", "N/A")))
    mtf_4h = _e(_safe(mtf.get("4h", "N/A")))
    mtf_1h = _e(_safe(mtf.get("1h", "N/A")))

    # ── Squeeze ────────────────────────────────────────────────
    sq_emoji = sq.get("emoji", "")
    sq_msg   = _e(_safe(sq.get("msg", "")))
    sq_mom   = _e(_safe(str(sq.get("momentum", ""))))
    sq_seta  = "↑" if sq.get("crescendo") else "↓"

    # ── Breakdown ─────────────────────────────────────────────
    breakdown_txt = "\n".join(_e(_safe(str(b))) for b in breakdown)

    # ── Critérios tendência ────────────────────────────────────
    crit_det_esc = _e(_safe(crit_det))

    # ── Fibonacci — retrações + Golden Pocket ─────────────────
    fib_linhas = "\n".join(
        f"  {_e(k)}\\: {_fp(v)}" for k, v in fib_ret.items()
    )

    gp_low  = fib_ret.get("61.8%", 0)
    gp_high = fib_ret.get("65%",   0)
    gp_txt  = (
        f"  🎯 Golden Pocket\\: {_fp(gp_low)} \\— {_fp(gp_high)}\n"
        if gp_low and gp_high else ""
    )

    # ── Extensões Fib ──────────────────────────────────────────
    ext_linhas = "\n".join(
        f"  {_e(k)}\\: {_fp(v)}"
        for k, v in fib_exp.items()
        if not k.startswith("ext_")   # mostra só as de cima
    )

    # ── Liquidações ────────────────────────────────────────────
    liq_esc = _e(_safe(str(liquidacoes)))

    # ── Classe / descrição ─────────────────────────────────────
    classe_e      = _e(_safe(classe))
    classe_desc_e = _e(_safe(classe_desc))
    direcao_e     = _e(_safe(direcao))
    vol_forca_e   = _e(_safe(vol_forca))

    relatorio = (
        f"📊 *{_e(par)}* \\| `{_e(timeframe.upper())}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        f"{score_emoji} *SCORE\\: {_e(str(score))}/10* \\— {classe_e}\n"
        f"{classe_desc_e}\n\n"
        f"{breakdown_txt}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📐 *TENDENCIA\\:* {direcao_e}\n"
        f"{crit_det_esc}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 *MULTI\\-TIMEFRAME\\:*\n"
        f"  1D \\→ {mtf_1d}\n"
        f"  4H \\→ {mtf_4h}\n"
        f"  1H \\→ {mtf_1h}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 *SQUEEZE\\:* {sq_emoji} {sq_msg}\n"
        f"  Momentum\\: {sq_mom} {_e(sq_seta)}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *MEDIAS MOVEIS\\:*\n"
        f"  EMA 9   \\→ {_fp(df['EMA_9'].iloc[-1])}\n"
        f"  EMA 21  \\→ {_fp(df['EMA_21'].iloc[-1])}\n"
        f"  EMA 80  \\→ {_fp(df['EMA_80'].iloc[-1])}\n"
        f"  EMA 200 \\→ {_fp(df['EMA_200'].iloc[-1])}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *INDICADORES\\:*\n"
        f"  RSI\\(14\\)\\:   {_fn(rsi_s.iloc[-1])}\n"
        f"  MACD\\:      {_fn(macd_obj.macd().iloc[-1], 6)}\n"
        f"  Sinal\\:     {_fn(macd_obj.macd_signal().iloc[-1], 6)}\n"
        f"  Stoch RSI\\: {_fn(stoch_rsi.iloc[-1], 4)}\n"
        f"  SAR\\:       {_fn(sar.iloc[-1], 6)}\n"
        f"  ATR\\(14\\)\\:  {_fn(atr_s.iloc[-1], 6)}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *VOLUME\\:*\n"
        f"  Atual\\: {_fn(df['volume'].iloc[-1])}\n"
        f"  MM21\\:  {_fn(df['vol_ma21'].iloc[-1])}\n"
        f"  Ratio\\: {_fn(vol_ratio)}x \\— {vol_forca_e}\n\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📐 *FIBONACCI \\(50 candles\\)\\:*\n"
        f"{fib_linhas}\n"
        f"{gp_txt}"
        f"\n  📈 *Extensoes\\:*\n"
        f"{ext_linhas}"
        f"{setup_txt}\n"

        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💥 *LIQUIDACOES\\:*\n"
        f"{liq_esc}\n\n"

        f"⚠️ Apenas para estudo\\. Nao e recomendacao\\."
    )
    return relatorio
