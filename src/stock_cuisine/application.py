"""Cas d'usage de l'application.

Cette couche assemble le repository et les règles métier. Les interfaces CLI et
web peuvent ainsi partager les mêmes vues de stock sans connaître les détails
de SQLite.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from .models import Batch, Category, Product, StockMovement
from .repository import Repository
from .services import StockService, StockSnapshot, calculate_effective_expiry


@dataclass(frozen=True)
class ProductStock:
    """Ligne de stock agrégée pour un produit."""

    product: Product
    quantity: float
    below_minimum: bool


@dataclass(frozen=True)
class AlertBatch:
    """Lot accompagné des informations utiles à l'affichage d'une alerte."""

    batch: Batch
    product: Product
    effective_expiry: Optional[date]


@dataclass(frozen=True)
class AlertReport:
    """État complet des alertes à une date donnée."""

    reference_date: date
    days: int
    below_minimum: Tuple[Product, ...]
    expired: Tuple[AlertBatch, ...]
    expiring: Tuple[AlertBatch, ...]


@dataclass(frozen=True)
class Dashboard:
    """Données nécessaires au tableau de bord."""

    reference_date: date
    products: Tuple[ProductStock, ...]
    active_batches: int
    below_minimum: int
    expired: int
    latest_movements: Tuple[StockMovement, ...]


def _validated_date(value: Optional[date]) -> date:
    reference = date.today() if value is None else value
    if isinstance(reference, datetime) or not isinstance(reference, date):
        raise TypeError("La date de référence doit être une date Python.")
    return reference


class StockApplication:
    """Façade applicative utilisée par les interfaces du projet."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.service = StockService(repository)

    @staticmethod
    def _validated_days(days: int) -> int:
        if isinstance(days, bool) or not isinstance(days, int) or days < 0:
            raise ValueError("Le nombre de jours doit être un entier positif ou nul.")
        return days

    @staticmethod
    def _product_stock_from_snapshot(
        snapshot: StockSnapshot, search: Optional[str] = None
    ) -> List[ProductStock]:
        products = snapshot.products
        if search:
            needle = search.strip().casefold()
            if needle:
                products = tuple(
                    product
                    for product in products
                    if needle in product.name.casefold()
                    or needle in product.category.casefold()
                )

        result = []
        for product in products:
            product_id = product.id
            quantity = 0.0 if product_id is None else snapshot.totals.get(product_id, 0.0)
            result.append(
                ProductStock(
                    product=product,
                    quantity=quantity,
                    below_minimum=quantity < product.min_stock_threshold,
                )
            )
        return result

    @staticmethod
    def _classify_expiry(
        snapshot: StockSnapshot,
        reference_date: date,
        days: Optional[int] = None,
    ) -> Tuple[List[Batch], List[Batch]]:
        deadline = None
        if days is not None:
            deadline = reference_date + timedelta(days=days)
        products = {
            product.id: product
            for product in snapshot.products
            if product.id is not None
        }
        expired = []
        expiring = []
        for batch in snapshot.batches:
            product = products.get(batch.product_id)
            if product is None:
                continue
            effective_expiry = calculate_effective_expiry(product, batch)
            if effective_expiry is None:
                continue
            if effective_expiry < reference_date:
                expired.append(batch)
            elif deadline is not None and effective_expiry <= deadline:
                expiring.append(batch)
        return expired, expiring

    def product_stock(self, search: Optional[str] = None) -> List[ProductStock]:
        """Retourne le stock de chaque produit, avec recherche facultative."""

        return self._product_stock_from_snapshot(
            self.service.stock_snapshot(), search
        )

    def dashboard(self, reference_date: Optional[date] = None) -> Dashboard:
        """Construit un tableau de bord cohérent en une seule opération."""

        today = _validated_date(reference_date)
        snapshot = self.service.stock_snapshot()
        stock = self._product_stock_from_snapshot(snapshot)
        expired, _ = self._classify_expiry(snapshot, today)
        return Dashboard(
            reference_date=today,
            products=tuple(stock),
            active_batches=len(snapshot.batches),
            below_minimum=sum(1 for line in stock if line.below_minimum),
            expired=len(expired),
            latest_movements=tuple(self.repository.list_movements(limit=10)),
        )

    def alerts(self, days: int = 7, reference_date: Optional[date] = None) -> AlertReport:
        """Construit le rapport des alertes et calcule les dates limites effectives."""

        today = _validated_date(reference_date)
        number_of_days = self._validated_days(days)
        snapshot = self.service.stock_snapshot()
        below_minimum = tuple(
            product
            for product in snapshot.products
            if product.id is not None
            and Decimal(str(snapshot.totals.get(product.id, 0.0)))
            < Decimal(str(product.min_stock_threshold))
        )
        expired_batches, expiring_batches = self._classify_expiry(
            snapshot, today, number_of_days
        )
        products: Dict[Optional[int], Product] = {
            product.id: product for product in snapshot.products
        }

        def enrich(batches: List[Batch]) -> Tuple[AlertBatch, ...]:
            result = []
            for batch in batches:
                product = products.get(batch.product_id)
                if product is None:
                    continue
                result.append(
                    AlertBatch(
                        batch=batch,
                        product=product,
                        effective_expiry=calculate_effective_expiry(product, batch),
                    )
                )
            return tuple(result)

        return AlertReport(
            reference_date=today,
            days=number_of_days,
            below_minimum=below_minimum,
            expired=enrich(expired_batches),
            expiring=enrich(expiring_batches),
        )

    # Les méthodes ci-dessous rendent explicites les actions mutantes utilisées
    # par les adaptateurs. Elles gardent les règles dans le repository métier.
    def create_product(self, product: Product) -> Product:
        return self.repository.create_product(product)

    def update_product(self, product: Product) -> Product:
        return self.repository.update_product(product)

    def create_category(self, category: Category) -> Category:
        return self.repository.create_category(category)

    def delete_product(self, product_id: int) -> None:
        """Supprime un produit qui n'a encore aucun lot associé."""

        if self.repository.get_product(product_id) is None:
            raise KeyError("Produit introuvable.")
        if self.repository.list_batches_for_product(product_id):
            raise ValueError(
                "Impossible de supprimer ce produit : des lots lui sont associés."
            )
        self.repository.delete_product(product_id)

    def create_batch(self, batch: Batch) -> Batch:
        return self.repository.create_batch(batch)

    def update_batch(self, batch: Batch) -> Batch:
        return self.repository.update_batch(batch)

    def record_movement(self, movement: StockMovement) -> StockMovement:
        return self.repository.record_movement(movement)

    def record_inventory(
        self,
        batch_id: int,
        actual_quantity: object,
        inventory_date: date,
        reason: str,
    ) -> StockMovement:
        return self.repository.record_inventory(
            batch_id, actual_quantity, inventory_date, reason
        )

    def open_batch(self, batch_id: int, opened_date: Optional[date] = None) -> Batch:
        return self.repository.mark_batch_open(batch_id, opened_date)
