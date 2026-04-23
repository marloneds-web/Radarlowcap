"""
╔══════════════════════════════════════════════════════════╗
║          RADAR LOWCAP BOT — ARQUIVO PRINCIPAL            ║
║                                                          ║
║  Comandos:                                               ║
║  /start   → Apresentação do bot                          ║
║  /radar   → Dispara scan manual agora                    ║
║  /analise → Análise detalhada de um par específico       ║
║  /config  → Exibe configuração atual                     ║
║  /setchat → Define este chat como destino dos alertas    ║
║  /ajuda   → Lista de comandos                            ║
╚══════════════════════════════════════════════════════════╝
"""

import asyncio
import logging
import schedule
import time
import threading

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from utils import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    POLL_INTERVAL_MINUTES,
    SCORE_MINIMO,
    TOP_N_MOEDAS,
    TIMEFRAME_PADRAO,
)
from scanner import escanear_lowcaps, formatar_ranking
from analysis import gerar_relatorio_completo

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Estado global do chat destino ─────────────────────────
chat_destino = {"id": TELEGRAM_CHAT_ID}


# ══════════════════════════════════════════════════════════
# HANDLERS DE COMANDO
# ══════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👁️ *RADAR LOWCAP BOT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Monitor de lowcaps cripto que detecta moedas\n"
        "próximas a grandes movimentos usando:\n\n"
        "• 🔒 AMD (Acumulação → Manipulação → Distribuição)\n"
        "• 🚨 Squeeze Momentum (BB + Keltner)\n"
        "• 📊 Volume Spike + OBV\n"
        "• 🕯️ CRT + Price Action (Al Brooks)\n"
        "• 📐 Fibonacci Dinâmico\n"
        "• 🕐 Multi-Timeframe (1D + 4H + 1H)\n\n"
        "Exchanges: *Bitget* | *MEXC* | *BingX*\n\n"
        "Use /ajuda para ver os comandos disponíveis."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_ajuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📋 *COMANDOS DISPONÍVEIS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• /start → Apresentação\n"
        "• /radar → Scan manual agora\n"
        "• /analise `BTCUSDT` → Análise de um par\n"
        "• /analise `BTCUSDT 1h` → Par + timeframe\n"
        "• /config → Configuração atual\n"
        "• /setchat → Definir este chat para alertas\n"
        "• /ajuda → Esta mensagem\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_setchat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    chat_destino["id"] = chat_id
    await update.message.reply_text(
        f"✅ Chat configurado!\n"
        f"ID: `{chat_id}`\n"
        f"Alertas automáticos serão enviados aqui.",
        parse_mode=ParseMode.MARKDOWN
    )
    log.info(f"Chat destino atualizado: {chat_id}")


async def cmd_config(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "⚙️ *CONFIGURAÇÃO ATUAL*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🕐 Intervalo de scan:  `{POLL_INTERVAL_MINUTES} min`\n"
        f"📊 Score mínimo:       `{SCORE_MINIMO}/10`\n"
        f"🏆 Top moedas:         `{TOP_N_MOEDAS}`\n"
        f"⏱️ Timeframe padrão:   `{TIMEFRAME_PADRAO}`\n\n"
        f"📡 Chat destino: `{chat_destino['id']}`\n\n"
        f"Exchanges ativas:\n"
        f"  • Bitget (API pública)\n"
        f"  • MEXC  (API pública)\n"
        f"  • BingX (API pública)\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_radar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *Iniciando scan manual...*\n"
        "Aguarde, isso pode levar alguns minutos.",
        parse_mode=ParseMode.MARKDOWN
    )
    try:
        resultados = escanear_lowcaps(
            top_n=TOP_N_MOEDAS,
            timeframe=TIMEFRAME_PADRAO,
            score_minimo=SCORE_MINIMO,
        )
        msg = formatar_ranking(resultados, TIMEFRAME_PADRAO)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error(f"Erro cmd_radar: {e}")
        await update.message.reply_text(f"❌ Erro ao escanear: {e}")


async def cmd_analise(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "⚠️ Uso: /analise `BTCUSDT` ou /analise `BTCUSDT 1h`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    par       = args[0].upper()
    timeframe = args[1].lower() if len(args) > 1 else TIMEFRAME_PADRAO

    await update.message.reply_text(
        f"📊 Analisando *{par}* no `{timeframe}`...",
        parse_mode=ParseMode.MARKDOWN
    )
    try:
        relatorio = gerar_relatorio_completo(par, timeframe)
        await update.message.reply_text(relatorio, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error(f"Erro cmd_analise {par}: {e}")
        await update.message.reply_text(f"❌ Erro ao analisar {par}: {e}")


# ══════════════════════════════════════════════════════════
# SCAN AUTOMÁTICO (POLLING)
# ══════════════════════════════════════════════════════════

async def enviar_alerta_automatico(app: Application):
    """Roda o scan e envia para o chat destino."""
    cid = chat_destino.get("id", "")
    if not cid:
        log.warning("Chat destino não configurado. Use /setchat.")
        return

    log.info("⏰ Iniciando scan automático...")
    try:
        resultados = escanear_lowcaps(
            top_n=TOP_N_MOEDAS,
            timeframe=TIMEFRAME_PADRAO,
            score_minimo=SCORE_MINIMO,
        )
        msg = formatar_ranking(resultados, TIMEFRAME_PADRAO)
        await app.bot.send_message(
            chat_id=cid,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
        )
        log.info(f"✅ Alerta enviado para {cid} ({len(resultados)} moedas)")
    except Exception as e:
        log.error(f"Erro no alerta automático: {e}")
        try:
            await app.bot.send_message(
                chat_id=cid,
                text=f"⚠️ Erro no scan automático: {e}"
            )
        except Exception:
            pass


def iniciar_scheduler(app: Application):
    """Inicia o scheduler em uma thread separada."""
    loop = asyncio.new_event_loop()

    def job():
        loop.run_until_complete(enviar_alerta_automatico(app))

    schedule.every(POLL_INTERVAL_MINUTES).minutes.do(job)
    log.info(f"⏰ Scheduler ativo — scan a cada {POLL_INTERVAL_MINUTES} minutos")

    def run():
        while True:
            schedule.run_pending()
            time.sleep(30)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    log.info("🚀 Iniciando Radar Lowcap Bot...")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Registra comandos
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("ajuda",   cmd_ajuda))
    app.add_handler(CommandHandler("setchat", cmd_setchat))
    app.add_handler(CommandHandler("config",  cmd_config))
    app.add_handler(CommandHandler("radar",   cmd_radar))
    app.add_handler(CommandHandler("analise", cmd_analise))

    # Define comandos no menu do Telegram
    async def post_init(application):
        await application.bot.set_my_commands([
            BotCommand("start",   "Apresentação do bot"),
            BotCommand("radar",   "Scan manual agora"),
            BotCommand("analise", "Análise de um par"),
            BotCommand("config",  "Configuração atual"),
            BotCommand("setchat", "Definir chat para alertas"),
            BotCommand("ajuda",   "Lista de comandos"),
        ])
        iniciar_scheduler(application)
        log.info("✅ Bot iniciado com sucesso!")

    app.post_init = post_init

    log.info("🤖 Bot em polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
