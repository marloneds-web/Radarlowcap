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
    TOKEN_OK,
)
from scanner import escanear_lowcaps, formatar_ranking
from analysis import gerar_relatorio_completo

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Estado global do chat destino ─────────────────────────────
chat_destino = {"id": TELEGRAM_CHAT_ID}


# ══════════════════════════════════════════════════════════════
# HANDLERS DE COMANDO
# ══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👁️ *RADAR LOWCAP BOT*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Monitor de lowcaps cripto que detecta moedas\n"
        "próximas a grandes movimentos usando:\n\n"
        "• 🔒 AMD \\(Acumulação → Manipulação → Distribuição\\)\n"
        "• 🚨 Squeeze Momentum \\(BB \\+ Keltner\\)\n"
        "• 📊 Volume Spike \\+ OBV\n"
        "• 🕯️ CRT \\+ Price Action \\(Al Brooks\\)\n"
        "• 📐 Fibonacci Dinâmico\n"
        "• 🕐 Multi\\-Timeframe \\(1D \\+ 4H \\+ 1H\\)\n\n"
        "Exchanges: *Bitget* \\| *MEXC* \\| *BingX*\n\n"
        "Use /ajuda para ver os comandos disponíveis\\."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_ajuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📋 *COMANDOS DISPONÍVEIS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• /start → Apresentação\n"
        "• /radar → Scan manual agora\n"
        "• /analise `BTCUSDT` → Análise de um par\n"
        "• /analise `BTCUSDT 1h` → Par \\+ timeframe\n"
        "• /config → Configuração atual\n"
        "• /setchat → Definir este chat para alertas\n"
        "• /ajuda → Esta mensagem\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_setchat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    chat_destino["id"] = chat_id
    await update.message.reply_text(
        f"✅ *Chat configurado com sucesso\\!*\n\n"
        f"ID: `{chat_id}`\n"
        f"Alertas automáticos serão enviados aqui\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
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
        f"📡 Chat destino: `{chat_destino['id'] or 'não configurado'}`\n\n"
        "Exchanges ativas:\n"
        "  • Bitget \\(API pública\\)\n"
        "  • MEXC  \\(API pública\\)\n"
        "  • BingX \\(API pública\\)\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_radar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *Iniciando scan manual\\.\\.\\.*\n"
        "Aguarde, isso pode levar alguns minutos\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    try:
        resultados = escanear_lowcaps(
            top_n=TOP_N_MOEDAS,
            timeframe=TIMEFRAME_PADRAO,
            score_minimo=SCORE_MINIMO,
        )
        msg = formatar_ranking(resultados, TIMEFRAME_PADRAO)
        # Divide mensagem se for muito longa (limite Telegram: 4096 chars)
        for i in range(0, len(msg), 4000):
            await update.message.reply_text(
                msg[i:i+4000],
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    except Exception as e:
        log.error(f"Erro cmd_radar: {e}")
        await update.message.reply_text(f"❌ Erro ao escanear: `{e}`",
                                        parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_analise(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "⚠️ Uso: `/analise BTCUSDT` ou `/analise BTCUSDT 1h`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    par       = args[0].upper()
    timeframe = args[1].lower() if len(args) > 1 else TIMEFRAME_PADRAO

    await update.message.reply_text(
        f"📊 Analisando *{par}* no `{timeframe}`\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    try:
        relatorio = gerar_relatorio_completo(par, timeframe)
        # Divide mensagem se for muito longa
        for i in range(0, len(relatorio), 4000):
            await update.message.reply_text(
                relatorio[i:i+4000],
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    except Exception as e:
        log.error(f"Erro cmd_analise {par}: {e}")
        await update.message.reply_text(
            f"❌ Erro ao analisar `{par}`:\n`{e}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


# ══════════════════════════════════════════════════════════════
# SCAN AUTOMÁTICO (POLLING)
# ══════════════════════════════════════════════════════════════

async def enviar_alerta_automatico(app: Application):
    """Roda o scan e envia para o chat destino."""
    cid = chat_destino.get("id", "")
    if not cid:
        log.warning("⚠️ Chat destino não configurado. Use /setchat.")
        return

    log.info("⏰ Iniciando scan automático...")
    try:
        resultados = escanear_lowcaps(
            top_n=TOP_N_MOEDAS,
            timeframe=TIMEFRAME_PADRAO,
            score_minimo=SCORE_MINIMO,
        )
        msg = formatar_ranking(resultados, TIMEFRAME_PADRAO)

        # Divide se necessário
        for i in range(0, len(msg), 4000):
            await app.bot.send_message(
                chat_id=cid,
                text=msg[i:i+4000],
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        log.info(f"✅ Alerta enviado para {cid} ({len(resultados)} moedas)")

    except Exception as e:
        log.error(f"Erro no alerta automático: {e}")
        try:
            await app.bot.send_message(
                chat_id=cid,
                text=f"⚠️ Erro no scan automático: `{e}`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            pass


def iniciar_scheduler(app: Application):
    """Inicia o scheduler em thread separada."""
    loop = asyncio.new_event_loop()

    def job():
        loop.run_until_complete(enviar_alerta_automatico(app))

    schedule.every(POLL_INTERVAL_MINUTES).minutes.do(job)
    log.info(f"⏰ Scheduler ativo — scan a cada {POLL_INTERVAL_MINUTES} min")

    def run():
        while True:
            schedule.run_pending()
            time.sleep(30)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    # ── Valida token ANTES de qualquer coisa ──────────────────
    if not TOKEN_OK:
        print("=" * 55)
        print("❌  TELEGRAM_BOT_TOKEN não configurado!")
        print("=" * 55)
        print("→ No DISCLOUD:")
        print("  Dashboard → sua app → Envs → adicionar:")
        print("  TELEGRAM_BOT_TOKEN = seu_token_aqui")
        print("  TELEGRAM_CHAT_ID   = seu_chat_id_aqui")
        print("=" * 55)
        raise SystemExit(1)

    log.info("🚀 Iniciando Radar Lowcap Bot...")
    log.info(f"⏰ Intervalo: {POLL_INTERVAL_MINUTES} min")
    log.info(f"📊 Score mínimo: {SCORE_MINIMO}")
    log.info(f"🏆 Top moedas: {TOP_N_MOEDAS}")
    log.info(f"⏱️ Timeframe: {TIMEFRAME_PADRAO}")

    # ── Cria aplicação ────────────────────────────────────────
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # ── Registra handlers ─────────────────────────────────────
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("ajuda",   cmd_ajuda))
    app.add_handler(CommandHandler("setchat", cmd_setchat))
    app.add_handler(CommandHandler("config",  cmd_config))
    app.add_handler(CommandHandler("radar",   cmd_radar))
    app.add_handler(CommandHandler("analise", cmd_analise))

    # ── Post-init: menu + scheduler ───────────────────────────
    async def post_init(application: Application):
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

    # ── Inicia polling ────────────────────────────────────────
    log.info("🤖 Bot em polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
