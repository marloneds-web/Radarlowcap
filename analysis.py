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
                "motivo": f"RSI sobrecomprado \\({rsi:.1f}\\) — risco de topo",
            }
        if lado == "short" and rsi < 30:
            return {
                "valido": False,
                "motivo": f"RSI sobrevendido \\({rsi:.1f}\\) — risco de fundo",
            }

        # ── Filtro 2: Preço próximo ao topo/fundo estrutural ──
        if swing_highs and lado == "long":
            ultimo_topo      = swing_highs[-1][1]
            dist_topo_pct    = ((ultimo_topo - preco) / preco) * 100
            if dist_topo_pct < 1.5:
                return {
                    "valido": False,
                    "motivo": f"Preço próximo ao topo \\({dist_topo_pct:.1f}% de distância\\)",
                }

        if swing_lows and lado == "short":
            ultimo_fundo     = swing_lows[-1][1]
            dist_fundo_pct   = ((preco - ultimo_fundo) / preco) * 100
            if dist_fundo_pct < 1.5:
                return {
                    "valido": False,
                    "motivo": f"Preço próximo ao fundo \\({dist_fundo_pct:.1f}% de distância\\)",
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
                return {"valido": False, "motivo": f"SL muito distante \\({risco_pct:.1f}%\\)"}
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
                tp2_fib   = fib_exp.get("127.2%", 0)
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
                return {"valido": False, "motivo": f"SL muito distante \\({risco_pct:.1f}%\\)"}
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
                "motivo": f"R:R insuficiente \\(1:{rr}\\)",
            }

        # ── Avisos (não invalidam, só alertam) ────────────────
        avisos = []
        if lado == "long"  and rsi > 60:
            avisos.append(f"⚠️ RSI elevado \\({rsi:.1f}\\) — entrada em força")
        if lado == "short" and rsi < 40:
            avisos.append(f"⚠️ RSI baixo \\({rsi:.1f}\\) — entrada em fraqueza")
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
