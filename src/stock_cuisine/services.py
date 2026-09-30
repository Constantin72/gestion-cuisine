"""Règles métier indépendantes du stockage SQLite."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from .models import Batch, Product
from .repository import Repository


def calculate_effective_expiry(
    product: Product, batch: Batch
) -> Optional[date]:
    """Calcule la première date limite applicable à un lot."""

    expiry_dates = []
    if batch.expiry_date is not None:
        expiry_dates.append(batch.expiry_date)

    if (
        batch.opened_date is not None
        and product.shelf_life_after_opening_days is not None
    ):
        expiry_dates.append(
            batch.opened_date
            + timedelta(days=product.shelf_life_after_opening_days)
        )

    return None if not expiry_dates else min(expiry_dates)


def is_batch_expired(
    product: Product, batch: Batch, today: date
) -> bool:
    """Indique si la date limite est antérieure à la date donnée."""

    if isinstance(today, datetime) or not isinstance(today, date):
        raise TypeError("La date de référence doit être une date Python.")
    effective_expiry = calculate_effective_expiry(product, batch)
    return effective_expiry is not None and effective_expiry < today


def _reference_date(today: Optional[date]) -> date:
    """Valide ou crée la date de référence métier."""

    reference = date.today() if today is None else today
    if isinstance(reference, datetime) or not isinstance(reference, date):
        raise TypeError("La date de référence doit être une date Python.")
    return reference


def _validate_days(days: int) -> int:
    """Valide un nombre de jours non négatif."""

    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("Le nombre de jours doit être un entier positif ou nul.")
    return days


def _round_stock(value: Decimal) -> float:
    """Convertit un total Decimal en quantité REAL stable."""

    return float(value.quantize(Decimal("0.001")))


@dataclass(frozen=True)
class StockSnapshot:
    """Jeu de données cohérent utilisé pour construire les vues de stock."""

    products: Tuple[Product, ...]
    batches: Tuple[Batch, ...]
    totals: Dict[int, float]


class StockService:
    """Expose les règles métier liées aux stocks et aux dates limites."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def stock_snapshot(self) -> StockSnapshot:
        """Charge une seule fois les produits, les lots actifs et leurs totaux."""

        products = tuple(self.repository.list_products())
        batches = tuple(self.repository.list_batches_in_stock())
        totals = {
            product.id: Decimal("0")
            for product in products
            if product.id is not None
        }
        for batch in batches:
            current = totals.get(batch.product_id, Decimal("0"))
            totals[batch.product_id] = current + Decimal(str(batch.quantity))
        return StockSnapshot(
            products=products,
            batches=batches,
            totals={
                product_id: _round_stock(total)
                for product_id, total in totals.items()
            },
        )

    def total_stock_by_product(self) -> Dict[int, float]:
        """Retourne la quantité totale de chaque produit."""

        return self.stock_snapshot().totals

    def products_below_minimum(self) -> List[Product]:
        """Retourne les produits sous leur seuil minimal."""

        snapshot = self.stock_snapshot()
        products = []
        for product in snapshot.products:
            if product.id is None:
                continue
            total = Decimal(str(snapshot.totals.get(product.id, 0.0)))
            threshold = Decimal(str(product.min_stock_threshold))
            if total < threshold:
                products.append(product)
        return products

    def expired_batches(self, today: Optional[date] = None) -> List[Batch]:
        """Retourne les lots en stock dont la date limite est dépassée."""

        reference = _reference_date(today)
        snapshot = self.stock_snapshot()
        products = {
            product.id: product
            for product in snapshot.products
            if product.id is not None
        }
        expired = []
        for batch in snapshot.batches:
            product = products.get(batch.product_id)
            if product is not None and is_batch_expired(product, batch, reference):
                expired.append(batch)
        return expired

    def batches_expiring_within(
        self, days: int = 7, today: Optional[date] = None
    ) -> List[Batch]:
        """Retourne les lots en stock arrivant à échéance prochainement."""

        number_of_days = _validate_days(days)
        reference = _reference_date(today)
        deadline = reference + timedelta(days=number_of_days)
        snapshot = self.stock_snapshot()
        products = {
            product.id: product
            for product in snapshot.products
            if product.id is not None
        }
        expiring = []
        for batch in snapshot.batches:
            product = products.get(batch.product_id)
            if product is None:
                continue
            effective_expiry = calculate_effective_expiry(product, batch)
            if (
                effective_expiry is not None
                and reference <= effective_expiry <= deadline
            ):
                expiring.append(batch)
        return expiring
