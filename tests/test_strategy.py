from strategy import calcular_score_final, classificar_setup


def _tendencia(candles, drift):
    df = candles(seed=1, drift=drift, vol=0.002)
    return df


def test_score_entre_0_e_10(candles):
    for seed in range(10):
        df = candles(seed=seed)
        for lado in ("long", "short"):
            score, breakdown, _ = calcular_score_final(df, "X", 3, lado)
            assert 0 <= score <= 10
            assert breakdown


def test_score_respeita_direcao(candles):
    alta  = _tendencia(candles, 0.01)
    baixa = _tendencia(candles, -0.01)
    assert calcular_score_final(alta, "X", 3, "long")[0] > calcular_score_final(alta, "X", 3, "short")[0]
    assert calcular_score_final(baixa, "X", 3, "short")[0] > calcular_score_final(baixa, "X", 3, "long")[0]


def test_classificar_setup_bonus_amd_por_lado():
    # 6 + bônus de acumulação (long) = 7 → SETUP A
    assert "SETUP A " in classificar_setup(6, "acumulacao", "long")[0]
    # Acumulação não favorece short
    assert "SETUP B" in classificar_setup(6, "acumulacao", "short")[0]
    assert "SETUP A " in classificar_setup(6, "distribuicao", "short")[0]
