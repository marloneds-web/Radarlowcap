import time
from unittest import mock

import pytest

import exchanges


def test_obter_candles_descarta_candle_aberto(candles):
    df = candles(n=100)
    with mock.patch.object(exchanges, "bitget_candles", return_value=df):
        out = exchanges.obter_candles("XUSDT", "1h", exchange="bitget")
    assert len(out) == 99
    assert out["close"].iloc[-1] == df["close"].iloc[-2]


def test_obter_candles_tenta_preferida_primeiro(candles):
    chamadas = []

    def falha(*a):
        chamadas.append("outra")
        raise ValueError("x")

    def mexc(*a):
        chamadas.append("mexc")
        return candles(n=100)

    with mock.patch.object(exchanges, "bitget_candles", falha), \
         mock.patch.object(exchanges, "bingx_candles", falha), \
         mock.patch.object(exchanges, "mexc_candles", mexc):
        exchanges.obter_candles("XUSDT", "1h", preferida="mexc")
    assert chamadas == ["mexc"]


@pytest.mark.parametrize("bfx,base", [
    ("tBTCF0:USTF0", "BTC"), ("tTRXUSD", "TRX"), ("tETHUSD", "ETH"),
])
def test_base_bitfinex(bfx, base):
    assert exchanges._base_bitfinex(bfx) == base


def test_liquidacoes_bitfinex_formato_aninhado():
    agora = int(time.time() * 1000)
    resposta = [
        [["pos", 1, agora, None, "tBTCF0:USTF0", 0.5, 60000, None, 0, 1, None, 60100]],
        [["pos", 2, agora, None, "tETHF0:USTF0", -10, 3000, None, 0, 1, None, 3000]],
    ]
    r = mock.Mock(json=lambda: resposta, raise_for_status=lambda: None)
    with mock.patch.object(exchanges._http, "get", return_value=r):
        eventos = exchanges._liquidacoes_bitfinex("BTCUSDT")
    assert len(eventos) == 1
    assert eventos[0]["lado"] == "LONG"
    assert eventos[0]["usd"] == pytest.approx(0.5 * 60100)


def test_listar_lowcaps_filtra_market_cap():
    tickers = [
        {"symbol": "BTCUSDT",  "quoteVolume": "1e9", "lastPr": "1", "change24h": "0"},
        {"symbol": "PEPEUSDT", "quoteVolume": "1e7", "lastPr": "1", "change24h": "0"},
    ]
    with mock.patch.object(exchanges, "bitget_tickers", return_value=tickers), \
         mock.patch.object(exchanges, "_simbolos_por_mcap", return_value={"PEPE"}):
        out = exchanges.listar_lowcaps(exchanges=["bitget"])
    assert [m["symbol"] for m in out] == ["PEPEUSDT"]


def test_listar_lowcaps_sem_coingecko_mantem_volume():
    tickers = [{"symbol": "BTCUSDT", "quoteVolume": "1e9", "lastPr": "1", "change24h": "0"}]
    with mock.patch.object(exchanges, "bitget_tickers", return_value=tickers), \
         mock.patch.object(exchanges, "_simbolos_por_mcap", return_value=None):
        out = exchanges.listar_lowcaps(exchanges=["bitget"])
    assert len(out) == 1
