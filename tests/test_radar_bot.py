import asyncio
import json

import pytest

import radar_bot
import utils


def test_split_msg_corta_em_quebra_de_linha():
    texto = "\n".join(["x" * 30] * 10)
    partes = radar_bot._split_msg(texto, limit=100)
    assert all(len(p) <= 100 for p in partes)
    assert "\n".join(partes) == texto


def test_estado_persiste_e_recarrega(tmp_path, monkeypatch):
    monkeypatch.setattr(radar_bot, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(utils, "SCORE_MINIMO", 8)
    monkeypatch.setitem(radar_bot.chat_destino, "id", "-100")
    radar_bot._salvar_estado()
    assert json.loads((tmp_path / "state.json").read_text())["SCORE_MINIMO"] == 8

    monkeypatch.setattr(utils, "SCORE_MINIMO", 5)
    monkeypatch.setitem(radar_bot.chat_destino, "id", "")
    radar_bot._carregar_estado()
    assert utils.SCORE_MINIMO == 8
    assert radar_bot.chat_destino["id"] == "-100"


class _Msg:
    def __init__(self):
        self.enviadas = []

    async def reply_text(self, texto, **kwargs):
        self.enviadas.append(texto)


class _Update:
    def __init__(self, user_id):
        self.effective_user = type("U", (), {"id": user_id})()
        self.message = _Msg()


@pytest.mark.parametrize("user_id,permitido", [(1, True), (2, False)])
def test_admin_only(monkeypatch, user_id, permitido):
    monkeypatch.setattr(radar_bot, "ADMIN_IDS", {1})
    chamado = []

    @radar_bot.admin_only
    async def cmd_teste(update, ctx):
        chamado.append(True)

    update = _Update(user_id)
    asyncio.run(cmd_teste(update, None))
    assert bool(chamado) == permitido
    assert bool(update.message.enviadas) == (not permitido)
