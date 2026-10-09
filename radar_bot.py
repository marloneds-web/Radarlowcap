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
import json
import logging
import os
from functools import wraps

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
    ADMIN_IDS,
)
from formatacao import esc
from scanner import escanear_lowcaps, formatar_ranking
from analysis import gerar_relatorio_completo

# ── SUPORTE A TÓPICOS ──────────────────────────────────────
_thread_id_raw = os.getenv("TELEGRAM_THREAD_ID", "")
MESSAGE_THREAD_ID = int(_thread_id_raw) if _thread_id_raw.isdigit() else None

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Estado global ─────────────────────────────────────────────
chat_destino = {"id": TELEGRAM_CHAT_ID}

# Configurações alteradas por /set e /setchat sobrevivem a reinícios
STATE_FILE = os.getenv("STATE_FILE", "state.json")
_CHAVES_ESTADO = ("SCORE_MINIMO", "TOP_N_MOEDAS", "POLL_INTERVAL_MINUTES", "TIMEFRAME_PADRAO")

# Impede dois scans simultâneos (manual + automático)
_scan_lock = asyncio.Lock()


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _split_msg(text: str, limit: int = 4000) -> list[str]:
    """
    Divide em chunks seguros — corta sempre em \\n
    para nunca partir entidades abertas.
    """
    chunks = []
    while len(text) > limit:
        corte = text.rfind("\n", 0, limit)
        if corte == -1:
            corte = limit
        chunks.append(text[:corte])
        text = text[corte:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def admin_only(handler):
    """Restringe o comando aos usuários listados em ADMIN_IDS."""
    @wraps(handler)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not ADMIN_IDS:
            # Sem ADMIN_IDS configurado: mantém compatibilidade, mas avisa no log
            return await handler(update, ctx)
        user = update.effective_user
        if user is None or user.id not in ADMIN_IDS:
            log.warning(f"Acesso negado a /{handler.__name__[4:]} para user {user.id if user else '?'}")
            await update.message.reply_text("⛔ Comando restrito ao administrador do bot.")
            return
        return await handler(update, ctx)
    return wrapper


def _carregar_estado():
    """Aplica o estado salvo (se houver) sobre os valores do .env."""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            estado = json.load(f)
    except FileNotFoundError:
        return
    except Exception as e:
        log.warning(f"⚠️ Não foi possível ler {STATE_FILE}: {e}")
        return
    for chave in _CHAVES_ESTADO:
        if chave in estado:
            setattr(utils, chave, estado[chave])
    if estado.get("chat_id"):
        chat_destino["id"] = estado["chat_id"]
    log.info(f"💾 Estado carregado de {STATE_FILE}")


def _salvar_estado():
    estado = {chave: getattr(utils, chave) for chave in _CHAVES_ESTADO}
    estado["chat_id"] = chat_destino["id"]
    try:
        tmp = f"{STATE_FILE}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log.warning(f"⚠️ Não foi possível salvar {STATE_FILE}: {e}")


async def _executar_scan() -> tuple[str, int]:
    """Roda o scan numa thread (não bloqueia o bot) e devolve o ranking formatado."""
    resultados = await asyncio.to_thread(
        escanear_lowcaps,
        top_n=utils.TOP_N_MOEDAS,
        timeframe=utils.TIMEFRAME_PADRAO,
        score_minimo=utils.SCORE_MINIMO,
    )
    return formatar_ranking(resultados, utils.TIMEFRAME_PADRAO), len(resultados)


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


@admin_only
async def cmd_setchat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    chat_destino["id"] = chat_id
    _salvar_estado()
    await update.message.reply_text(
        f"✅ *Chat configurado com sucesso\\!*\n\n"
        f"ID: `{chat_id}`\n"
        f"Alertas automáticos serão enviados aqui\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    log.info(f"Chat destino atualizado: {chat_id}")


async def cmd_config(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    thread_info = f" ✅ \\(Tópico: `{MESSAGE_THREAD_ID}`\\)" if MESSAGE_THREAD_ID else ""
    msg = (
        "⚙️ *CONFIGURAÇÃO ATUAL*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🕐 Intervalo de scan:  `{utils.POLL_INTERVAL_MINUTES} min`\n"
        f"📊 Score mínimo:       `{utils.SCORE_MINIMO}/10`\n"
        f"🏆 Top moedas:         `{utils.TOP_N_MOEDAS}`\n"
        f"⏱️ Timeframe padrão:   `{utils.TIMEFRAME_PADRAO}`\n\n"
        f"📡 Chat destino: `{chat_destino['id'] or 'não configurado'}`{thread_info}\n\n"
        "Exchanges ativas:\n"
        "  • Bitget \\(API pública\\)\n"
        "  • MEXC  \\(API pública\\)\n"
        "  • BingX \\(API pública\\)\n\n"
        "💡 Use /set para ajustar os valores acima\\."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


# ══════════════════════════════════════════════════════════════
# COMANDO /set
# ══════════════════════════════════════════════════════════════

@admin_only
async def cmd_set(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args

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
            _salvar_estado()
            log.info(f"SCORE_MINIMO: {antigo} → {novo}")
            dica = (
                "⚠️ Score baixo → mais alertas, menor qualidade" if novo <= 3
                else "🎯 Boa escolha\\!" if novo <= 6
                else "🔬 Score alto → apenas os melhores setups"
            )
            await update.message.reply_text(
                f"✅ *Score mínimo atualizado\\!*\n\n"
                f"  Antes: `{antigo}/10`\n"
                f"  Agora: `{novo}/10`\n\n{dica}",
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
            _salvar_estado()
            log.info(f"TOP_N_MOEDAS: {antigo} → {novo}")
            dica = (
                "📋 Lista longa → use score alto para filtrar" if novo >= 20
                else "🎯 Lista focada\\!" if novo <= 10
                else "📊 Quantidade moderada"
            )
            await update.message.reply_text(
                f"✅ *Top moedas atualizado\\!*\n\n"
                f"  Antes: `{antigo} moedas`\n"
                f"  Agora: `{novo} moedas`\n\n{dica}",
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
            _salvar_estado()
            agendar_radar(ctx.application)
            log.info(f"POLL_INTERVAL_MINUTES: {antigo} → {novo}")
            horas, minutos = divmod(novo, 60)
            if horas > 0 and minutos > 0:
                tempo_fmt = f"{horas}h {minutos}min"
            elif horas > 0:
                tempo_fmt = f"{horas}h"
            else:
                tempo_fmt = f"{minutos}min"
            await update.message.reply_text(
                f"✅ *Intervalo de scan atualizado\\!*\n\n"
                f"  Antes: `{antigo} min`\n"
                f"  Agora: `{novo} min` \\({esc(tempo_fmt)}\\)\n\n"
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
                f"❌ Timeframe inválido\\.\n\nOpções válidas: {tfs_str}\n\n"
                f"Exemplo: `/set timeframe 4h`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        antigo = utils.TIMEFRAME_PADRAO
        utils.TIMEFRAME_PADRAO = valor_raw
        _salvar_estado()
        log.info(f"TIMEFRAME_PADRAO: {antigo} → {valor_raw}")
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
            f"{esc(dicas.get(valor_raw, ''))}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    # ── desconhecido ──────────────────────────────────────────
    else:
        await update.message.reply_text(
            f"❌ Parâmetro `{esc(parametro)}` desconhecido\\.\n\n"
            "Parâmetros válidos: `score`, `moedas`, `intervalo`, `timeframe`\n\n"
            "Digite /set para ver o menu completo\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


# ══════════════════════════════════════════════════════════════
# COMANDO /radar
# ══════════════════════════════════════════════════════════════

@admin_only
async def cmd_radar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if _scan_lock.locked():
        await update.message.reply_text("⏳ Já existe um scan em andamento. Aguarde o resultado.")
        return
    await update.message.reply_text(
        f"🔍 *Iniciando scan manual\\.\\.\\.*\n"
        f"Score ≥ `{utils.SCORE_MINIMO}` \\| Top `{utils.TOP_N_MOEDAS}` \\| `{utils.TIMEFRAME_PADRAO.upper()}`\n\n"
        f"Aguarde, isso pode levar alguns minutos\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    try:
        async with _scan_lock:
            msg, _ = await _executar_scan()
        for chunk in _split_msg(msg):
            await update.message.reply_text(
                chunk,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    except Exception as e:
        log.error(f"Erro cmd_radar: {e}")
        await update.message.reply_text(
            f"❌ Erro ao escanear: `{esc(str(e))}`",
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
        f"📊 Analisando *{esc(par)}* no `{timeframe}`\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    try:
        relatorio = await asyncio.to_thread(gerar_relatorio_completo, par, timeframe)
        for chunk in _split_msg(relatorio):
            await update.message.reply_text(
                chunk,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    except Exception as e:
        log.error(f"Erro cmd_analise {par}: {e}")
        await update.message.reply_text(
            f"❌ Erro ao analisar `{esc(par)}`:\n`{esc(str(e))}`",
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
    if _scan_lock.locked():
        log.info("⏭️ Scan automático pulado: outro scan em andamento.")
        return
    try:
        async with _scan_lock:
            msg, qtd = await _executar_scan()

        for chunk in _split_msg(msg):
            kwargs = {
                "chat_id": cid,
                "text": chunk,
                "parse_mode": ParseMode.MARKDOWN_V2,
            }
            if MESSAGE_THREAD_ID:
                kwargs["message_thread_id"] = MESSAGE_THREAD_ID

            await app.bot.send_message(**kwargs)

        log.info(f"✅ Alerta enviado para {cid} ({qtd} moedas)")

    except Exception as e:
        log.error(f"Erro no alerta automático: {e}")
        try:
            kwargs = {
                "chat_id": cid,
                "text": f"⚠️ Erro no scan automático: `{esc(str(e))}`",
                "parse_mode": ParseMode.MARKDOWN_V2,
            }
            if MESSAGE_THREAD_ID:
                kwargs["message_thread_id"] = MESSAGE_THREAD_ID

            await app.bot.send_message(**kwargs)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# SCHEDULER — JobQueue do python-telegram-bot
# ══════════════════════════════════════════════════════════════

async def _job_radar(ctx: ContextTypes.DEFAULT_TYPE):
    await enviar_alerta_automatico(ctx.application)


def agendar_radar(app: Application):
    """(Re)cria o job de scan automático com o intervalo atual."""
    for job in app.job_queue.get_jobs_by_name("radar"):
        job.schedule_removal()
    intervalo = utils.POLL_INTERVAL_MINUTES * 60
    app.job_queue.run_repeating(_job_radar, interval=intervalo, first=intervalo, name="radar")
    log.info(f"⏰ Scan automático a cada {utils.POLL_INTERVAL_MINUTES} min")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    if not TOKEN_OK:
        print("=" * 55)
        print("❌  TELEGRAM_BOT_TOKEN não configurado!")
        print("=" * 55)
        raise SystemExit(1)

    thread_info = f" | Tópico: {MESSAGE_THREAD_ID}" if MESSAGE_THREAD_ID else " | Grupo geral"
    log.info(f"🚀 Iniciando Radar Lowcap Bot...{thread_info}")
    if not ADMIN_IDS:
        log.warning("⚠️ ADMIN_IDS não configurado — qualquer usuário pode usar /radar, /set e /setchat.")
    _carregar_estado()

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
    app.add_handler(CommandHandler("set",     cmd_set))
    app.add_handler(CommandHandler("radar",   cmd_radar))
    app.add_handler(CommandHandler("analise", cmd_analise))

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

        agendar_radar(application)
        log.info("✅ Bot iniciado com sucesso!")

    app.post_init = post_init

    log.info("🤖 Bot em polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
