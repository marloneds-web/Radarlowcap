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
git clone https://github.com/marloneds-web/Radarlowcap
cd Radarlowcap
pip install -r requirements.txt
cp .env.example .env
# Edite o .env: TELEGRAM_BOT_TOKEN e ADMIN_IDS (seu ID de usuário no Telegram)
python radar_bot.py
```

## ☁️ Deploy Discloud

1. Copie `.env.example` para `.env` e preencha (o `.env` **não** vai para o Git,
   mas é enviado ao Discloud junto com o projeto)
2. Compacte o projeto em `.zip` (ou use a CLI/extensão do Discloud, que respeita o `.discloudignore`)
3. Acesse [discloud.com/dashboard](https://discloud.com/dashboard) e faça upload do `.zip`
4. Use `/setchat` no Telegram para definir o chat dos alertas

As alterações feitas com `/set` e `/setchat` ficam salvas em `state.json`
e sobrevivem a reinícios do bot.

## 🔐 Permissões

Defina `ADMIN_IDS` no `.env` (IDs separados por vírgula). Só esses usuários
podem usar `/radar`, `/set` e `/setchat`. Sem `ADMIN_IDS`, qualquer pessoa
que encontrar o bot consegue usar esses comandos.

## 💬 Comandos

| Comando | Descrição |
|---|---|
| `/start` | Apresentação |
| `/radar` | Scan manual (admin) |
| `/analise BTCUSDT` | Análise de par |
| `/analise BTCUSDT 1h` | Par + timeframe |
| `/config` | Configuração atual |
| `/set score 7` | Ajusta score mínimo, `moedas`, `intervalo` ou `timeframe` (admin) |
| `/setchat` | Define chat para alertas (admin) |
| `/ajuda` | Lista de comandos |

## 🧪 Testes

```bash
pip install -r requirements-dev.txt
pytest
```

## ⚠️ Aviso

Este bot é apenas para fins educacionais.
Não é recomendação de investimento.
