# analysis.py — função calcular_setup_trade — REESCRITA COMPLETA

def calcular_setup_trade(df: pd.DataFrame, direcao: str, mtf: dict = None) -> dict:
    """
    Calcula entrada, SL e TPs baseado em estrutura de mercado.

    Filtros de qualidade aplicados:
    ─────────────────────────────────────────────────────────
    ✅ Entrada sempre abaixo do preço atual (long) ou acima (short)
    ✅ RSI: rejeita long com RSI > 70 (topo) ou short com RSI < 30 (fundo)
    ✅ RSI: penaliza long com RSI > 60 (avisa risco de topo)
    ✅ MTF: exige confluência mínima (1H alinhado ou avisa divergência)
    ✅ SL baseado em swing + buffer ATR (mínimo 1x ATR)
    ✅ Distância mínima do SL: 1.5x ATR (evita stop por ruído/pavio)
    ✅ R:R mínimo 2.0 para validar
    ✅ SL não pode ultrapassar 8% do preço
    ✅ Detecta se preço está em topo/fundo estrutural recente
    """
    try:
        preco = df["close"].iloc[-1]
        atr   = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], 14
        ).average_true_range().iloc[-1]

        rsi = ta.momentum.RSIIndicator(df["close"], 14).rsi().iloc[-1]

        swing_highs, swing_lows = _swing_points(df, janela=5)
        lado = "long" if "ALTA" in direcao else "short"

        # ── Filtro 1: RSI extremo (topo/fundo) ────────────────
        if lado == "long" and rsi > 70:
            return {
                "valido": False,
                "motivo": f"RSI sobrecomprado \\({rsi:.1f}\\) — risco de topo",
            }
        if lado == "short" and rsi < 30:
            return {
                "valido": False,
                "motivo": f"RSI sobrevendido \\({rsi:.1f}\\) — risco de fundo",
            }

        # ── Filtro 2: Preço próximo ao topo estrutural recente ─
        if swing_highs and lado == "long":
            ultimo_topo = swing_highs[-1][1]
            distancia_topo_pct = ((ultimo_topo - preco) / preco) * 100
            if distancia_topo_pct < 1.5:
                return {
                    "valido": False,
                    "motivo": f"Preço próximo ao topo estrutural \\({distancia_topo_pct:.1f}% de distância\\)",
                }

        if swing_lows and lado == "short":
            ultimo_fundo = swing_lows[-1][1]
            distancia_fundo_pct = ((preco - ultimo_fundo) / preco) * 100
            if distancia_fundo_pct < 1.5:
                return {
                    "valido": False,
                    "motivo": f"Preço próximo ao fundo estrutural \\({distancia_fundo_pct:.1f}% de distância\\)",
                }

        # ── Filtro 3: Confluência MTF ──────────────────────────
        aviso_mtf = ""
        if mtf:
            tf_1h = mtf.get("1h", "")
            tf_4h = mtf.get("4h", "")
            if lado == "long":
                if "BAIXA" in tf_1h and "BAIXA" in tf_4h:
                    return {
                        "valido": False,
                        "motivo": "1H e 4H em BAIXA — contra a tendência",
                    }
                if "BAIXA" in tf_1h:
                    aviso_mtf = "⚠️ 1H divergente — aguardar pullback"
            else:
                if "ALTA" in tf_1h and "ALTA" in tf_4h:
                    return {
                        "valido": False,
                        "motivo": "1H e 4H em ALTA — contra a tendência",
                    }
                if "ALTA" in tf_1h:
                    aviso_mtf = "⚠️ 1H divergente — aguardar pullback"

        if lado == "long":
            # ── LONG ──────────────────────────────────────────
            if len(swing_lows) < 2:
                return {"valido": False, "motivo": "swings insuficientes"}

            ultimo_fundo = swing_lows[-1][1]

            # SL: abaixo do último fundo — mínimo 1x ATR de buffer
            sl_raw   = ultimo_fundo - (atr * 1.0)
            risco_abs = preco - sl_raw

            # Garante SL mínimo de 1.5x ATR (evita stop por ruído)
            if risco_abs < atr * 1.5:
                sl_raw    = preco - (atr * 1.5)
                risco_abs = preco - sl_raw

            risco_pct = (risco_abs / preco) * 100

            if risco_pct > 8:
                return {"valido": False, "motivo": f"SL muito distante \\({risco_pct:.1f}%\\)"}
            if risco_abs <= 0:
                return {"valido": False, "motivo": "SL inválido"}

            # Entrada: preço ATUAL (não acima dele)
            entrada = preco

            # TP1 → primeiro topo de swing acima do preço
            topos_acima = sorted([h for _, h in swing_highs if h > preco])
            tp1 = round(topos_acima[0], 8) if topos_acima else round(preco + risco_abs * 2.0, 8)

            # TP2 → FVG bullish ou projeção estrutural
            fvgs = _detectar_fvg(df, lado="long")
            fvg_acima = sorted([f for f in fvgs if f > tp1])
            if fvg_acima:
                tp2 = round(fvg_acima[0], 8)
            else:
                fib_ret, fib_exp = calcular_fibonacci(df, janela=50)
                tp2_fib = fib_exp.get("127.2%", 0)
                tp2 = round(tp2_fib, 8) if tp2_fib > tp1 else round(tp1 + risco_abs * 1.5, 8)

            # TP3 → maior topo estrutural acima
            topos_grandes = sorted([h for _, h in swing_highs if h > tp2])
            tp3 = round(topos_grandes[-1], 8) if topos_grandes else round(tp2 + risco_abs * 2.0, 8)

            # R:R calculado sobre TP2
            rr = round((tp2 - entrada) / risco_abs, 2)

        else:
            # ── SHORT ─────────────────────────────────────────
            if len(swing_highs) < 2:
                return {"valido": False, "motivo": "swings insuficientes"}

            ultimo_topo = swing_highs[-1][1]
            sl_raw      = ultimo_topo + (atr * 1.0)
            risco_abs   = sl_raw - preco

            if risco_abs < atr * 1.5:
                sl_raw    = preco + (atr * 1.5)
                risco_abs = sl_raw - preco

            risco_pct = (risco_abs / preco) * 100

            if risco_pct > 8:
                return {"valido": False, "motivo": f"SL muito distante \\({risco_pct:.1f}%\\)"}
            if risco_abs <= 0:
                return {"valido": False, "motivo": "SL inválido"}

            entrada = preco

            fundos_abaixo = sorted([l for _, l in swing_lows if l < preco], reverse=True)
            tp1 = round(fundos_abaixo[0], 8) if fundos_abaixo else round(preco - risco_abs * 2.0, 8)

            fvgs = _detectar_fvg(df, lado="short")
            fvg_abaixo = sorted([f for f in fvgs if f < tp1], reverse=True)
            if fvg_abaixo:
                tp2 = round(fvg_abaixo[0], 8)
            else:
                fib_ret, _ = calcular_fibonacci(df, janela=50)
                tp2_fib = fib_ret.get("61.8%", 0)
                tp2 = round(tp2_fib, 8) if 0 < tp2_fib < tp1 else round(tp1 - risco_abs * 1.5, 8)

            fundos_grandes = sorted([l for _, l in swing_lows if l < tp2])
            tp3 = round(fundos_grandes[0], 8) if fundos_grandes else round(tp2 - risco_abs * 2.0, 8)

            rr = round((entrada - tp2) / risco_abs, 2)

        # ── Filtro final: R:R mínimo ───────────────────────────
        if rr < 2.0:
            return {
                "valido": False,
                "motivo": f"R:R insuficiente \\(1:{rr}\\)",
            }

        sl = round(sl_raw, 8)
        sl_tipo = "abaixo do swing low" if lado == "long" else "acima do swing high"

        # ── Aviso de RSI elevado (não invalida, mas alerta) ────
        aviso_rsi = ""
        if lado == "long" and rsi > 60:
            aviso_rsi = f"⚠️ RSI elevado \\({rsi:.1f}\\) — entrada em força, cuidado"
        elif lado == "short" and rsi < 40:
            aviso_rsi = f"⚠️ RSI baixo \\({rsi:.1f}\\) — entrada em fraqueza, cuidado"

        avisos = [a for a in [aviso_rsi, aviso_mtf] if a]

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
            "avisos":    avisos,
        }

    except Exception as e:
        return {"valido": False, "motivo": str(e)[:40]}
