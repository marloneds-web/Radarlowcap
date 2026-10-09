# 📡 Radar Lowcap Bot

Monitor de lowcaps cripto que detecta moedas próximas
a grandes movimentos e envia alertas no Telegram.

## 🚀 Estratégia

| Pilar | Método |
|---|---|
| AMD | Acumulação → Manipulação → Distribuição |
| Squeeze | Bollinger Bands + Keltner Channel |
| Volume | Spike de volume (vs. média de 21 candles) |
| Tendência / Momentum | EMAs 9/21/50 + RSI + MACD |
| Candles | CRT Thick + Engolfo + Martelo/Estrela + Brooks Breakout |
| Fibonacci | Retrações 23.6%–78.6% + Golden Pocket (61.8–65%) |
| MTF | 1D + 4H + 1H alinhados |

O score (0–10) é calculado na direção da tendência detectada (long ou short)
e usa apenas candles **fechados**.

## 📦 Instalação local

```bash
git clone https://github.com/seu-usuario/radar-lowcap-bot
cd radar-lowcap-bot
pip install -r requirements.txt
cp .env.example .env
# Edite o .env com seu token do Telegram
python radar_bot.py
```

## ☁️ Deploy Discloud

1. Edite o `.env.example` → renomeie para `.env`
2. Compacte **todos** os arquivos em `.zip`
3. Acesse [discloud.com/dashboard](https://discloud.com/dashboard)
4. Upload do `.zip`
5. Use `/setchat` no Telegram para configurar o chat

## 💬 Comandos

| Comando | Descrição |
|---|---|
| `/start` | Apresentação |
| `/radar` | Scan manual |
| `/analise BTCUSDT` | Análise de par |
| `/analise BTCUSDT 1h` | Par + timeframe |
| `/config` | Configuração atual |
| `/setchat` | Define chat para alertas |
| `/ajuda` | Lista de comandos |

## ⚠️ Aviso

Este bot é apenas para fins educacionais.
Não é recomendação de investimento.
