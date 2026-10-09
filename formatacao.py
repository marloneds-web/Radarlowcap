"""Helpers de formatação para mensagens MarkdownV2 do Telegram."""

from telegram.helpers import escape_markdown


def esc(text) -> str:
    """Escapa todos os caracteres reservados do MarkdownV2."""
    return escape_markdown(str(text), version=2)


def italic(text) -> str:
    """Itálico seguro: escapa o conteúdo (inclusive _) antes de envolver."""
    return f"_{esc(text)}_"


def fmt_price(price) -> str:
    """Formata preço de acordo com a magnitude (sem escape)."""
    price = float(price)
    if price < 0.0001: return f"{price:.8f}"
    if price < 1:      return f"{price:.6f}"
    if price < 1000:   return f"{price:.4f}"
    return f"{price:,.2f}"
