"""Tests de la couche métier des stocks."""

from datetime import date
from pathlib import Path
import sys
import unittest
from typing import Optional


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from stock_cuisine.db import connect_database
from stock_cuisine.models import Batch, Product, StockMovement
from stock_cuisine.repository import Repository
from stock_cuisine.services import (
    StockService,
    calculate_effective_expiry,
)


REFERENCE_DATE = date(2026, 9, 29)


class ServiceTests(unittest.TestCase):
    """Vérifie les règles métier sans accès SQL direct."""

    def setUp(self) -> None:
        self.connection = connect_database(":memory:")
        self.repository = Repository(self.connection)
        self.service = StockService(self.repository)
        self.addCleanup(self.connection.close)

    def product(
        self,
        name: str,
        threshold: float = 1.0,
        shelf_life: int = 3,
    ) -> Product:
        """Construit un produit de test."""

        return Product(
            name=name,
            unit="kg",
            category="Alimentaire",
            min_stock_threshold=threshold,
            shelf_life_after_opening_days=shelf_life,
        )

    def batch(
        self,
        product_id: int,
        quantity: float,
        expiry_date: date = date(2026, 10, 10),
        opened_date: Optional[date] = None,
    ) -> Batch:
        """Construit un lot de test."""

        return Batch(
            product_id=product_id,
            quantity=quantity,
            unit_price_cents=100,
            purchase_date=date(2026, 9, 1),
            expiry_date=expiry_date,
            opened_date=opened_date,
        )

    def test_effective_expiry_uses_the_earliest_applicable_date(self) -> None:
        product = self.product("Yaourt", shelf_life=3)
        batch = self.batch(
            product_id=1,
            quantity=1.0,
            expiry_date=date(2026, 9, 20),
            opened_date=date(2026, 9, 10),
        )

        self.assertEqual(
            calculate_effective_expiry(product, batch),
            date(2026, 9, 13),
        )

    def test_effective_expiry_without_opening_uses_product_expiry(self) -> None:
        product = self.product("Conserve", shelf_life=3)
        batch = self.batch(
            product_id=1,
            quantity=1.0,
            expiry_date=date(2026, 10, 10),
            opened_date=None,
        )

        self.assertEqual(
            calculate_effective_expiry(product, batch),
            date(2026, 10, 10),
        )

    def test_effective_expiry_can_come_only_from_opening_shelf_life(self) -> None:
        product = self.product("Sauce", shelf_life=5)
        batch = self.batch(
            product_id=1,
            quantity=1.0,
            expiry_date=None,
            opened_date=date(2026, 9, 10),
        )

        self.assertEqual(
            calculate_effective_expiry(product, batch),
            date(2026, 9, 15),
        )

    def test_total_stock_by_product_includes_zero_stock_products(self) -> None:
        first_product = self.repository.create_product(self.product("Farine"))
        second_product = self.repository.create_product(self.product("Riz"))
        first_batch = self.repository.create_batch(
            self.batch(first_product.id, 0.3)
        )
        self.repository.create_batch(self.batch(first_product.id, 0.2))
        second_batch = self.repository.create_batch(
            self.batch(second_product.id, 0.4)
        )
        self.repository.record_movement(
            self._movement(second_batch.id, "out", 0.4)
        )

        totals = self.service.total_stock_by_product()

        self.assertAlmostEqual(totals[first_product.id], 0.5)
        self.assertAlmostEqual(totals[second_product.id], 0.0)
        self.assertEqual(first_batch.quantity, 0.3)

    def test_stock_value_uses_remaining_quantity_and_each_lot_price(self) -> None:
        product = self.repository.create_product(self.product("Farine"))
        first_batch = self.repository.create_batch(
            Batch(
                product_id=product.id,
                quantity=3.0,
                unit_price_cents=125,
                purchase_date=REFERENCE_DATE,
            )
        )
        self.repository.create_batch(
            Batch(
                product_id=product.id,
                quantity=2.0,
                unit_price_cents=200,
                purchase_date=REFERENCE_DATE,
            )
        )
        self.repository.record_movement(
            self._movement(first_batch.id, "out", 1.0)
        )

        snapshot = self.service.stock_snapshot()

        self.assertAlmostEqual(snapshot.totals[product.id], 4.0)
        self.assertEqual(snapshot.values_cents[product.id], 650)

    def test_products_below_minimum_include_products_without_lots(self) -> None:
        low_product = self.repository.create_product(
            self.product("Lentilles", threshold=2.0)
        )
        sufficient_product = self.repository.create_product(
            self.product("Pâtes", threshold=0.5)
        )
        no_stock_product = self.repository.create_product(
            self.product("Sel", threshold=1.0)
        )
        self.repository.create_batch(self.batch(low_product.id, 1.0))
        self.repository.create_batch(self.batch(sufficient_product.id, 0.5))

        low_products = self.service.products_below_minimum()

        self.assertEqual(
            [product.id for product in low_products],
            [low_product.id, no_stock_product.id],
        )

    def test_expired_batches_include_opening_shelf_life(self) -> None:
        product = self.repository.create_product(self.product("Crème", shelf_life=3))
        expired_batch = self.repository.create_batch(
            self.batch(
                product.id,
                quantity=1.0,
                expiry_date=date(2026, 12, 31),
                opened_date=date(2026, 9, 20),
            )
        )

        expired = self.service.expired_batches(REFERENCE_DATE)

        self.assertEqual([batch.id for batch in expired], [expired_batch.id])

    def test_expiring_batches_are_limited_to_the_requested_window(self) -> None:
        product = self.repository.create_product(self.product("Légumes"))
        soon_batch = self.repository.create_batch(
            self.batch(
                product.id,
                quantity=1.0,
                expiry_date=date(2026, 10, 2),
            )
        )
        later_batch = self.repository.create_batch(
            self.batch(
                product.id,
                quantity=1.0,
                expiry_date=date(2026, 10, 10),
            )
        )
        expired_batch = self.repository.create_batch(
            self.batch(
                product.id,
                quantity=1.0,
                expiry_date=date(2026, 9, 28),
            )
        )

        expiring = self.service.batches_expiring_within(
            days=7,
            today=REFERENCE_DATE,
        )

        self.assertEqual([batch.id for batch in expiring], [soon_batch.id])
        self.assertNotIn(later_batch.id, [batch.id for batch in expiring])
        self.assertNotIn(expired_batch.id, [batch.id for batch in expiring])

    def test_invalid_expiration_window_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.service.batches_expiring_within(days=-1, today=REFERENCE_DATE)

    def _movement(
        self, batch_id: int, movement_type: str, quantity: float
    ) -> StockMovement:
        """Construit un mouvement sans dupliquer le scénario métier."""

        return StockMovement(
            batch_id=batch_id,
            type=movement_type,
            quantity=quantity,
            date=REFERENCE_DATE,
            reason="Test",
        )


if __name__ == "__main__":
    unittest.main()
