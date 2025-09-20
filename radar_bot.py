import argparse
import time
import datetime as dt
import asyncio
from typing import List, Dict, Any

import requests
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from utils import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    POLL_INTERVAL_MINUTES, MAX_ALERTS_PER_CYCLE,
    MCAP_MIN, MCAP_MAX, MIN_VOL_24H,
    MIN_CHANGE_7D, MIN_CHANGE_24H,
    COINS_MARKETS_ENDPOINT, REQUIRED_FIELDS,
)

CHAT_ID_FILE = "chat_id.txt"

# ---------------------------------------------------------------
# Fetch & filter
# ---------------------------------------------------------------

def fetch_markets_page(page: int):
    url = COINS_MARKETS_ENDPOINT.format(page=page)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def fetch_all_candidates(max_pages: int = 8):
    out = []
    for page in range(1, max_pages + 1):
        try:
            items = fetch_markets_page(page)
        except Exception:
            break
        if not items:
            break
        out.extend(items)
        last_mc = items[-1].get("market_cap") or 0
        if last_mc and last_mc > (MCAP_MAX * 3):
            break
    return out


def valid_coin(obj: dict) -> bool:
    for f in REQUIRED_FIELDS:
        if f not in obj or obj[f] is None:
            return False
    mc = obj.get("market_cap") or 0
    vol = obj.get("total_volume") or 0
    ch24 = obj.get("price_change_percentage_24h_in_currency") or 0
    ch7d = obj.get("price_change_percentage_7d_in_currency") or 0
    return (
        (MCAP_MIN <= mc <= MCAP_MAX) and
        (vol >= MIN_VOL_24H) and
        (ch7d >= MIN_CHANGE_7D) and
        (ch24 >= MIN_CHANGE_24H)
    )


def format_alert(c: dict) -> str:
    name = c.get("name")
    symbol = (c.get("symbol") or "").upper()
    price = c.get("current_price")
    mc = c.get("market_cap")
    vol = c.get("total_volume")
    ch24 = c.get("price_change_percentage_24h_in_currency")
    ch7d = c.get("price_change_percentage_7d_in_currency")
    cg_link = f"https://www.coingecko.com/en/coins/{c.get('id','')}"
    return (
        "🔥 *Radar LowCap*

"
        f"*{name}* ({symbol})
"
        f"💲 *Preço*: ${price:,.6f}
"
        f"🏦 *MCap*: ${mc:,.0f}
"
        f"📊 *Volume 24h*: ${vol:,.0f}
"
        f"⏫ *7d*: {ch7d:.2f}%  |  ⏩ *24h*: {ch24:.2f}%
"
        f"🔗 [CoinGecko]({cg_link})
"
        "
⚠️ *Atenção:* Low-caps são altamente voláteis. *Não é recomendação.*"
    )


def find_candidates():
    all_items = fetch_all_candidates()
    valids = [c for c in all_items if valid_coin(c)]
    valids.sort(
        key=lambda x: (
            x.get("price_change_percentage_7d_in_currency") or 0,
            x.get("price_change_percentage_24h_in_currency") or 0,
            x.get("total_volume") or 0,
        ),
        reverse=True,
    )
    return valids[:MAX_ALERTS_PER_CYCLE]


def send_alerts(bot: Bot, coins: list):
    # tenta carregar TELEGRAM_CHAT_ID do arquivo se houver
    dest = TELEGRAM_CHAT_ID
    try:
        with open("chat_id.txt") as f:
            cid = f.read().strip()
            if cid:
                dest = cid
    except Exception:
        pass
    if not dest:
        return
    if not coins:
        bot.send_message(
            chat_id=dest,
            text=("🔎 *Radar LowCap*: Nenhum ativo bateu os filtros neste ciclo.

"
                  "Dica: ajuste thresholds no .env ou rode /radar mais tarde."),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        return
    header = (
        "🚨 *Radar LowCap — Candidatos do ciclo*
"
        f"🕒 {dt.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"
        f"🎯 Filtros: MCAP ${MCAP_MIN:,}–${MCAP_MAX:,}; Vol≥${int(MIN_VOL_24H):,}; "
        f"7d≥{MIN_CHANGE_7D}% ; 24h≥{MIN_CHANGE_24H}%

"
    )
    bot.send_message(chat_id=dest, text=header, parse_mode="Markdown", disable_web_page_preview=True)
    for c in coins:
        try:
            bot.send_message(
                chat_id=dest,
                text=format_alert(c),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            time.sleep(0.7)
        except Exception:
            continue

# ---------------------------------------------------------------
# Comandos do Bot
# ---------------------------------------------------------------

async def cmd_radar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text="🔎 *Radar LowCap*: buscando...", parse_mode="Markdown")
    try:
        coins = await asyncio.to_thread(find_candidates)
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❗Erro ao buscar: {e}")
        return
    if not coins:
        await context.bot.send_message(chat_id=chat_id, text="Sem resultados agora.")
        return
    for c in coins:
        await context.bot.send_message(chat_id=chat_id, text=format_alert(c), parse_mode="Markdown", disable_web_page_preview=True)

async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cfg = (
        f"⚙️ *Config atual*\n"
        f"MCap: ${MCAP_MIN:,} – ${MCAP_MAX:,}\n"
        f"Vol 24h ≥ ${MIN_VOL_24H:,}\n"
        f"Δ7d ≥ {MIN_CHANGE_7D}%\n"
        f"Δ24h ≥ {MIN_CHANGE_24H}%\n"
        f"Máx alertas/ciclo: {MAX_ALERTS_PER_CYCLE}\n"
        f"Intervalo: {POLL_INTERVAL_MINUTES} min"
    )
    await context.bot.send_message(chat_id=chat_id, text=cfg, parse_mode="Markdown")

async def cmd_setchat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        with open(CHAT_ID_FILE, "w") as f:
            f.write(str(chat_id))
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Chat {chat_id} salvo como destino.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❗Erro ao salvar: {e}")

# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def main(loop: bool = False, poll: bool = False):
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN no .env")

    if poll:
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("radar", cmd_radar))
        app.add_handler(CommandHandler("config", cmd_config))
        app.add_handler(CommandHandler("setchat", cmd_setchat))

        import os
        global TELEGRAM_CHAT_ID
        if os.path.exists(CHAT_ID_FILE):
            with open(CHAT_ID_FILE) as f:
                TELEGRAM_CHAT_ID = f.read().strip()

        if TELEGRAM_CHAT_ID:
            async def periodic_alerts(context):
                try:
                    coins = await context.application.loop.run_in_executor(None, find_candidates)
                    bot = context.bot
                    send_alerts(bot, coins)
                except Exception:
                    pass
            app.job_queue.run_repeating(periodic_alerts, interval=POLL_INTERVAL_MINUTES*60, first=10)
        app.run_polling(close_loop=False)
        return

    if loop:
        if not TELEGRAM_CHAT_ID:
            raise SystemExit("Falta TELEGRAM_CHAT_ID para o modo --loop")
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        while True:
            try:
                coins = find_candidates()
                send_alerts(bot, coins)
            except Exception as e:
                try:
                    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"❗Erro no radar: {e}")
                except Exception:
                    pass
            time.sleep(POLL_INTERVAL_MINUTES * 60)
    else:
        coins = find_candidates()
        for c in coins:
            print(c.get("id"), c.get("symbol"), c.get("market_cap"))
        if TELEGRAM_CHAT_ID:
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            send_alerts(bot, coins)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll", action="store_true")
    args = parser.parse_args()

    if not any([args.loop, args.once, args.poll]):
        args.once = True

    main(loop=args.loop, poll=args.poll)