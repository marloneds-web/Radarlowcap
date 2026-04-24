"""
╔══════════════════════════════════════════════════════════╗
║          RADAR LOWCAP BOT — ARQUIVO PRINCIPAL            ║
║                                                          ║
║  Comandos:                                               ║
║  /start    → Apresentação do bot                         ║
║  /radar    → Dispara scan manual agora                   ║
║  /analise  → Análise detalhada de um par específico      ║
║  /config   → Exibe configuração atual                    ║
║  /set      → Ajusta configurações em tempo real          ║
║  /setchat  → Define este chat como destino dos alertas   ║
║  /ajuda    → Lista de comandos                           ║
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

import utils
from utils import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
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

# ── Referência global do scheduler (para reagendar) ───────────
_scheduler_app: Application = None


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _escape(text: str) -> str:
    """Escapa caracteres especiais do MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _reagendar(app: Application):
    """Limpa e recria o job do scheduler com o intervalo atual."""
    schedule.clear("radar")

    def job():
        loop = asyncio.new_event_loop()
        loop.run_until_complete(enviar_alerta_automatico(app))
        loop.close()

    schedule.every(utils.POLL_INTERVAL_MINUTES).minutes.do(job).tag("radar")
    log.info(f"⏰ Scheduler reagendado → a cada {utils.POLL_INTERVAL_MINUTES} min")


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
        "• /set `score 7` → Ajustar score mínimo\n"
        "• /set `moedas 20` → Ajustar top N moedas\n"
        "• /set `intervalo 60` → Intervalo em minutos\n"
        "• /set `timeframe 1h` → Timeframe do scan\n"
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
        f"🕐 Intervalo de scan:  `{utils.POLL_INTERVAL_MINUTES} min`\n"
        f"📊 Score mínimo:       `{utils.SCORE_MINIMO}/10`\n"
        f"🏆 Top moedas:         `{utils.TOP_N_MOEDAS}`\n"
        f"⏱️ Timeframe padrão:   `{utils.TIMEFRAME_PADRAO}`\n\n"
        f"📡 Chat destino: `{chat_destino['id'] or 'não configurado'}`\n\n"
        "Exchanges ativas:\n"
        "  • Bitget \\(API pública\\)\n"
        "  • MEXC  \\(API pública\\)\n"
        "  • BingX \\(API pública\\)\n\n"
        "💡 Use /set para ajustar os valores acima\\."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


# ══════════════════════════════════════════════════════════════
# COMANDO /set — AJUSTE EM TEMPO REAL
# ══════════════════════════════════════════════════════════════

async def cmd_set(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Ajusta configurações em tempo real via Telegram.

    Uso:
      /set score 7
      /set moedas 20
      /set intervalo 60
      /set timeframe 1h
    """
    args = ctx.args

    # Sem argumentos → mostra menu de ajuda
    if not args:
        msg = (
            "⚙️ *AJUSTAR CONFIGURAÇÃO*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "*Parâmetros disponíveis:*\n\n"
            "📊 `/set score <1\\-10>`\n"
            "  → Score mínimo para alertar\n"
            "  → Atual: `" + str(utils.SCORE_MINIMO) + "`\n\n"
            "🏆 `/set moedas <1\\-50>`\n"
            "  → Quantas moedas retornar no scan\n"
            "  → Atual: `" + str(utils.TOP_N_MOEDAS) + "`\n\n"
            "🕐 `/set intervalo <5\\-1440>`\n"
            "  → Minutos entre scans automáticos\n"
            "  → Atual: `" + str(utils.POLL_INTERVAL_MINUTES) + " min`\n\n"
            "⏱️ `/set timeframe <valor>`\n"
            "  → Timeframe da análise\n"
            "  → Opções: `1m 5m 15m 1h 4h 1d`\n"
            "  → Atual: `" + utils.TIMEFRAME_PADRAO + "`\n\n"
            "💡 Exemplo: `/set score 7`"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
        return

    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ Uso correto: `/set <parâmetro> <valor>`\n\n"
            "Exemplo: `/set score 7`\n\n"
            "Digite /set para ver todos os parâmetros\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    parametro = args[0].lower().strip()
    valor_raw = args[1].lower().strip()

    # ── score ─────────────────────────────────────────────────
    if parametro == "score":
        try:
            novo = int(valor_raw)
            if not 1 <= novo <= 10:
                raise ValueError
            antigo = utils.SCORE_MINIMO
            utils.SCORE_MINIMO = novo
            log.info(f"SCORE_MINIMO alterado: {antigo} → {novo}")

            if novo <= 3:
                dica = "⚠️ Score baixo → mais alertas, menor qualidade"
            elif novo <= 6:
                dica = "🎯 Boa escolha\\!"
            else:
                dica = "🔬 Score alto → apenas os melhores setups"

            await update.message.reply_text(
                f"✅ *Score mínimo atualizado\\!*\n\n"
                f"  Antes: `{antigo}/10`\n"
                f"  Agora: `{novo}/10`\n\n"
                f"{dica}",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Valor inválido\\. Use um número inteiro entre `1` e `10`\\.\n"
                "Exemplo: `/set score 7`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    # ── moedas ────────────────────────────────────────────────
    elif parametro == "moedas":
        try:
            novo = int(valor_raw)
            if not 1 <= novo <= 50:
                raise ValueError
            antigo = utils.TOP_N_MOEDAS
            utils.TOP_N_MOEDAS = novo
            log.info(f"TOP_N_MOEDAS alterado: {antigo} → {novo}")

            if novo >= 20:
                dica = "📋 Lista longa → use score alto para filtrar"
            elif novo <= 10:
                dica = "🎯 Lista focada\\!"
            else:
                dica = "📊 Quantidade moderada"

            await update.message.reply_text(
                f"✅ *Top moedas atualizado\\!*\n\n"
                f"  Antes: `{antigo} moedas`\n"
                f"  Agora: `{novo} moedas`\n\n"
                f"{dica}",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Valor inválido\\. Use um número inteiro entre `1` e `50`\\.\n"
                "Exemplo: `/set moedas 15`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    # ── intervalo ─────────────────────────────────────────────
    elif parametro == "intervalo":
        try:
            novo = int(valor_raw)
            if not 5 <= novo <= 1440:
                raise ValueError
            antigo = utils.POLL_INTERVAL_MINUTES
            utils.POLL_INTERVAL_MINUTES = novo
            _reagendar(ctx.application)
            log.info(f"POLL_INTERVAL_MINUTES alterado: {antigo} → {novo}")

            horas = novo // 60
            minutos = novo % 60
            if horas > 0 and minutos > 0:
                tempo_fmt = f"{horas}h {minutos}min"
            elif horas > 0:
                tempo_fmt = f"{horas}h"
            else:
                tempo_fmt = f"{minutos}min"

            await update.message.reply_text(
                f"✅ *Intervalo de scan atualizado\\!*\n\n"
                f"  Antes: `{antigo} min`\n"
                f"  Agora: `{novo} min` \\({_escape(tempo_fmt)}\\)\n\n"
                f"⏰ Próximo scan automático em `{novo} min`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Valor inválido\\. Use um número entre `5` e `1440` minutos\\.\n"
                "Exemplo: `/set intervalo 60`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    # ── timeframe ─────────────────────────────────────────────
    elif parametro == "timeframe":
        tfs_validos = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
        if valor_raw not in tfs_validos:
            tfs_str = " \\| ".join(f"`{t}`" for t in tfs_validos)
            await update.message.reply_text(
                f"❌ Timeframe inválido\\.\n\n"
                f"Opções válidas: {tfs_str}\n\n"
                f"Exemplo: `/set timeframe 4h`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        antigo = utils.TIMEFRAME_PADRAO
        utils.TIMEFRAME_PADRAO = valor_raw
        log.info(f"TIMEFRAME_PADRAO alterado: {antigo} → {valor_raw}")

        dicas = {
            "1m":  "⚡ Scalping — muito ruído, use com cuidado",
            "5m":  "⚡ Scalping curto",
            "15m": "📊 Operações rápidas intraday",
            "30m": "📊 Intraday moderado",
            "1h":  "🎯 Day trade — boa relação sinal/ruído",
            "4h":  "🎯 Swing trade — recomendado para lowcaps",
            "1d":  "📈 Position trade — longo prazo",
        }
        await update.message.reply_text(
            f"✅ *Timeframe atualizado\\!*\n\n"
            f"  Antes: `{antigo}`\n"
            f"  Agora: `{valor_raw}`\n\n"
            f"{_escape(dicas.get(valor_raw, ''))}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    # ── parâmetro desconhecido ─────────────────────────────────
    else:
        await update.message.reply_text(
            f"❌ Parâmetro `{_escape(parametro)}` desconhecido\\.\n\n"
            "Parâmetros válidos: `score`, `moedas`, `intervalo`, `timeframe`\n\n"
            "Digite /set para ver o menu completo\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


# ══════════════════════════════════════════════════════════════
# COMANDO /radar
# ══════════════════════════════════════════════════════════════

async def cmd_radar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🔍 *Iniciando scan manual\\.\\.\\.*\n"
        f"Score ≥ `{utils.SCORE_MINIMO}` \\| Top `{utils.TOP_N_MOEDAS}` \\| `{utils.TIMEFRAME_PADRAO.upper()}`\n\n"
        f"Aguarde, isso pode levar alguns minutos\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    try:
        resultados = escanear_lowcaps(
            top_n=utils.TOP_N_MOEDAS,
            timeframe=utils.TIMEFRAME_PADRAO,
            score_minimo=utils.SCORE_MINIMO,
        )
        msg = formatar_ranking(resultados, utils.TIMEFRAME_PADRAO)
        for i in range(0, len(msg), 4000):
            await update.message.reply_text(
                msg[i:i+4000],
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    except Exception as e:
        log.error(f"Erro cmd_radar: {e}")
        await update.message.reply_text(
            f"❌ Erro ao escanear: `{_escape(str(e))}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


# ══════════════════════════════════════════════════════════════
# COMANDO /analise
# ══════════════════════════════════════════════════════════════

async def cmd_analise(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "⚠️ Uso: `/analise BTCUSDT` ou `/analise BTCUSDT 1h`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    par       = args[0].upper()
    timeframe = args[1].lower() if len(args) > 1 else utils.TIMEFRAME_PADRAO

    await update.message.reply_text(
        f"📊 Analisando *{_escape(par)}* no `{timeframe}`\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    try:
        relatorio = gerar_relatorio_completo(par, timeframe)
        for i in range(0, len(relatorio), 4000):
            await update.message.reply_text(
                relatorio[i:i+4000],
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    except Exception as e:
        log.error(f"Erro cmd_analise {par}: {e}")
        await update.message.reply_text(
            f"❌ Erro ao analisar `{_escape(par)}`:\n`{_escape(str(e))}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


# ══════════════════════════════════════════════════════════════
# SCAN AUTOMÁTICO
# ══════════════════════════════════════════════════════════════

async def enviar_alerta_automatico(app: Application):
    """Roda o scan e envia para o chat destino."""
    cid = chat_destino.get("id", "")
    if not cid:
        log.warning("⚠️ Chat destino não configurado. Use /setchat.")
        return

    log.info(
        f"⏰ Scan automático | score≥{utils.SCORE_MINIMO} "
        f"| top{utils.TOP_N_MOEDAS} | {utils.TIMEFRAME_PADRAO}"
    )
    try:
        resultados = escanear_lowcaps(
            top_n=utils.TOP_N_MOEDAS,
            timeframe=utils.TIMEFRAME_PADRAO,
            score_minimo=utils.SCORE_MINIMO,
        )
        msg = formatar_ranking(resultados, utils.TIMEFRAME_PADRAO)
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
                text=f"⚠️ Erro no scan automático: `{_escape(str(e))}`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            pass


def iniciar_scheduler(app: Application):
    """Inicia o scheduler em thread separada."""
    global _scheduler_app
    _scheduler_app = app

    def job():
        loop = asyncio.new_event_loop()
        loop.run_until_complete(enviar_alerta_automatico(app))
        loop.close()

    schedule.every(utils.POLL_INTERVAL_MINUTES).minutes.do(job).tag("radar")
    log.info(f"⏰ Scheduler ativo — scan a cada {utils.POLL_INTERVAL_MINUTES} min")

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
    log.info(f"⏰ Intervalo:    {utils.POLL_INTERVAL_MINUTES} min")
    log.info(f"📊 Score mínimo: {utils.SCORE_MINIMO}")
    log.info(f"🏆 Top moedas:   {utils.TOP_N_MOEDAS}")
    log.info(f"⏱️ Timeframe:    {utils.TIMEFRAME_PADRAO}")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    # ── Registra handlers ─────────────────────────────────────
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("ajuda",    cmd_ajuda))
    app.add_handler(CommandHandler("setchat",  cmd_setchat))
    app.add_handler(CommandHandler("config",   cmd_config))
    app.add_handler(CommandHandler("set",      cmd_set))
    app.add_handler(CommandHandler("radar",    cmd_radar))
    app.add_handler(CommandHandler("analise",  cmd_analise))

    # ── Post-init ─────────────────────────────────────────────
    async def post_init(application: Application):
        await application.bot.set_my_commands([
            BotCommand("start",   "Apresentação do bot"),
            BotCommand("radar",   "Scan manual agora"),
            BotCommand("analise", "Análise de um par"),
            BotCommand("config",  "Configuração atual"),
            BotCommand("set",     "Ajustar configurações"),
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
