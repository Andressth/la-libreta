from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def pesos(valor):
    """Formatea un número como pesos colombianos: 86400 -> $86.400"""
    try:
        numero = int(Decimal(valor or 0))
    except (InvalidOperation, TypeError, ValueError):
        return valor
    signo = "-" if numero < 0 else ""
    return f"{signo}${abs(numero):,}".replace(",", ".")
