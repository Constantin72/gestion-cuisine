"""Modèles de données et conversions monétaires."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Union


EuroInput = Union[str, int, float, Decimal]


def euros_to_cents(euros: EuroInput) -> int:
    """Convertit un montant en euros en centimes avec ``Decimal``."""

    if isinstance(euros, bool):
        raise TypeError("Le montant en euros doit être numérique.")

    try:
        amount = Decimal(str(euros))
    except (InvalidOperation, ValueError):
        raise ValueError("Le montant en euros est invalide.") from None

    if not amount.is_finite():
        raise ValueError("Le montant en euros est invalide.")

    try:
        rounded_amount = amount.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except InvalidOperation:
        raise ValueError("Le montant en euros est trop grand.") from None

    return int(rounded_amount * Decimal("100"))


def cents_to_euros(cents: int) -> Decimal:
    """Convertit un nombre entier de centimes en ``Decimal`` euros."""

    if isinstance(cents, bool) or not isinstance(cents, int):
        raise TypeError("Les centimes doivent être un entier.")

    return (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"))


@dataclass
class Category:
    """Catégorie disponible pour classer les produits."""

    name: str
    id: Optional[int] = None


@dataclass
class Product:
    """Produit suivi dans le stock."""

    name: str
    unit: str
    category: str
    min_stock_threshold: float
    shelf_life_after_opening_days: Optional[int] = None
    id: Optional[int] = None


@dataclass
class Batch:
    """Lot d'un produit."""

    product_id: int
    quantity: float
    unit_price_cents: int
    purchase_date: date
    expiry_date: Optional[date] = None
    opened_date: Optional[date] = None
    supplier: Optional[str] = None
    notes: Optional[str] = None
    id: Optional[int] = None


@dataclass
class StockMovement:
    """Mouvement appliqué à un lot."""

    batch_id: int
    type: str
    quantity: float
    date: date
    reason: str
    id: Optional[int] = None
