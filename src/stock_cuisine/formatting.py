"""Formatage partagé par la CLI et l'interface web."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import unicodedata
from typing import Optional, Tuple

from .models import Product, cents_to_euros


QUANTITY_QUANTUM = Decimal("0.001")


def format_quantity(value: object) -> str:
    """Affiche une quantité avec au plus trois décimales."""

    try:
        quantity = Decimal(str(value)).quantize(
            QUANTITY_QUANTUM, rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError):
        return str(value)
    return format(quantity, "f").rstrip("0").rstrip(".") or "0"


def sort_text(value: str) -> str:
    """Prépare un texte pour un tri alphabétique indépendant des accents."""

    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )


def product_sort_key(product: Product) -> Tuple[str, str, int]:
    """Classe les produits par catégorie puis par nom, sans effet des accents."""

    return sort_text(product.category), sort_text(product.name), product.id or 0


def format_price(cents: int) -> str:
    """Affiche un montant stocké en centimes."""

    return f"{cents_to_euros(cents):.2f} €"


def format_date(value: Optional[date]) -> str:
    """Affiche une date facultative dans le format de l'application."""

    return "-" if value is None else value.isoformat()


def movement_label(movement_type: str) -> str:
    """Traduit le type interne d'un mouvement pour l'interface."""

    return {
        "in": "Entrée",
        "out": "Sortie",
        "loss": "Perte",
    }.get(movement_type, movement_type)
