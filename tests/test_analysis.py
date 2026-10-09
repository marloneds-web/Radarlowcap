import pytest

from analysis import (
    _golden_pocket, _nivel_fib_mais_proximo, _detectar_fvg,
    calcular_fibonacci, calcular_setup_trade, avaliar_tendencia, confluencia_mtf,
)


def test_golden_pocket_ordenado():
    ret = {"61.8%": 10.0, "65%": 9.5}
    assert _golden_pocket(ret) == (9.5, 10.0)


def test_golden_pocket_do_fibonacci_real(candles):
    ret, _, meta = calcular_fibonacci(candles(seed=3))
    low, high = _golden_pocket(ret)
    assert meta["fundo"] <= low < high <= meta["topo"]


def test_nivel_fib_retorna_o_mais_proximo():
    ret = {"38.2%": 100.0, "50%": 101.0}
    # 100.9 está dentro da tolerância dos dois níveis, mas é mais perto do 50%
    assert _nivel_fib_mais_proximo(100.9, ret) == ("50%", 101.0)
    assert _nivel_fib_mais_proximo(200.0, ret) == (None, None)


def test_fvg_long_detecta_gap(candles):
    df = candles(n=5)
    df.loc[:, "high"] = [10, 10, 10, 10, 10]
    df.loc[:, "low"]  = [9, 9, 9, 9, 12]  # low[4]=12 > high[2]=10
    assert _detectar_fvg(df, "long") == [11.0]
    assert _detectar_fvg(df, "short") == []


def test_confluencia_mtf_por_lado():
    mtf = {"1d": "📈 ALTA (4/5)", "4h": "📉 BAIXA (3/5)", "1h": "Erro: timeout"}
    assert confluencia_mtf(mtf, "long") == 1
    assert confluencia_mtf(mtf, "short") == 1


CASOS = [(seed, drift) for seed in range(60) for drift in (0.001, -0.001)]


def _setup(candles, seed, drift):
    df = candles(seed=seed, drift=drift, vol=0.01)
    direcao, _, _ = avaliar_tendencia(df)
    return calcular_setup_trade(df, direcao)


def test_setups_validos_existem_nos_dois_lados(candles):
    lados = {st["lado"] for st in (_setup(candles, *c) for c in CASOS) if st["valido"]}
    assert lados == {"long", "short"}


@pytest.mark.parametrize("seed,drift", CASOS)
def test_setup_trade_valido_e_coerente(candles, seed, drift):
    st = _setup(candles, seed, drift)
    if not st["valido"]:
        assert st["motivo"]
        return
    assert st["rr"] >= 2.0
    assert 0 < st["risco_pct"] <= 8
    if st["lado"] == "long":
        assert st["sl"] < st["entrada"] < st["tp1"] < st["tp2"] < st["tp3"]
    else:
        assert st["sl"] > st["entrada"] > st["tp1"] > st["tp2"] > st["tp3"]
