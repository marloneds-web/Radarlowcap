# Radar Low-Cap (<US$100M) — Bot de Alertas para Telegram

Monitor de low-caps que dispara alertas no Telegram quando os filtros são atendidos.
Comandos interativos quando rodando em modo polling: `/radar`, `/config`, `/setchat`.

## Instalação local
```bash
pip install -r requirements.txt
cp .env.example .env
# Edite TELEGRAM_BOT_TOKEN (e TELEGRAM_CHAT_ID se quiser fixo)
python radar_bot.py --once     # roda 1x e envia alertas se houver
python radar_bot.py --poll     # modo comandos: /radar /config /setchat
```

## GitHub Actions (cron) — grátis
Crie `.github/workflows/radar.yml` (já incluso neste pacote), adicione os *Secrets*:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

O workflow executa `python radar_bot.py --once` a cada 10 minutos.

## Render (opcional)
Como Worker: `python radar_bot.py --poll` (tem custos no Worker).

## Aviso
Conteúdo educativo. Não é recomendação. Low-caps são altamente voláteis.
