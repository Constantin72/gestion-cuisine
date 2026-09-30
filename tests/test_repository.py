"""Tests du repository SQLite."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
import sqlite3
import sys
import unittest


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from stock_cuisine.db import connect_database
from stock_cuisine.models import (
    Batch,
    Category,
    Product,
    StockMovement,
    cents_to_euros,
    euros_to_cents,
)
from stock_cuisine.repository import Repository


PURCHASE_DATE = date(2026, 9, 29)


class RepositoryTestCase(unittest.TestCase):
    """Initialise une base SQLite en mémoire pour chaque test."""

    def setUp(self) -> None:
        self.connection = connect_database(":memory:")
        self.repository = Repository(self.connection)
        self.addCleanup(self.connection.close)

    def product(self, name: str = "Lait") -> Product:
        """Construit un produit de test."""

        return Product(
            name=name,
            unit="L",
            category="Frais",
            min_stock_threshold=1.0,
            shelf_life_after_opening_days=3,
        )

    def batch(self, product_id: int, quantity: float = 1.0) -> Batch:
        """Construit un lot de test."""

        return Batch(
            product_id=product_id,
            quantity=quantity,
            unit_price_cents=125,
            purchase_date=PURCHASE_DATE,
        )

    def movement(
        self,
        batch_id: int,
        movement_type: str,
        quantity: float,
    ) -> StockMovement:
        """Construit un mouvement de test."""

        return StockMovement(
            batch_id=batch_id,
            type=movement_type,
            quantity=quantity,
            date=PURCHASE_DATE,
            reason="Test",
        )

    def movement_count(self, batch_id: int) -> int:
        """Compte les mouvements d'un lot."""

        row = self.connection.execute(
            "SELECT COUNT(*) FROM stock_movements WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        return int(row[0])


class RepositoryTests(RepositoryTestCase):
    """Vérifie les opérations du repository."""

    def test_create_product_and_batch_creates_initial_movement(self) -> None:
        product = self.repository.create_product(self.product())
        batch = self.repository.create_batch(self.batch(product.id))

        self.assertEqual(batch.unit_price_cents, 125)
        self.assertAlmostEqual(batch.quantity, 1.0)
        row = self.connection.execute(
            """
            SELECT type, quantity, date, reason
            FROM stock_movements
            WHERE batch_id = ?
            """,
            (batch.id,),
        ).fetchone()
        self.assertEqual(tuple(row), ("in", 1.0, "2026-09-29", "Stock initial"))

    def test_movement_history_is_sorted_and_filterable_by_batch(self) -> None:
        product = self.repository.create_product(self.product())
        first_batch = self.repository.create_batch(self.batch(product.id, 2.0))
        second_batch = self.repository.create_batch(self.batch(product.id, 3.0))

        self.repository.record_movement(
            StockMovement(
                batch_id=first_batch.id,
                type="out",
                quantity=0.5,
                date=date(2026, 10, 1),
                reason="Déjeuner",
            )
        )
        self.repository.record_movement(
            StockMovement(
                batch_id=second_batch.id,
                type="loss",
                quantity=0.25,
                date=date(2026, 10, 2),
                reason="Casse",
            )
        )

        history = self.repository.list_movements()
        self.assertEqual(
            [(movement.batch_id, movement.type) for movement in history],
            [
                (second_batch.id, "loss"),
                (first_batch.id, "out"),
                (second_batch.id, "in"),
                (first_batch.id, "in"),
            ],
        )
        filtered = self.repository.list_movements(batch_id=first_batch.id)
        self.assertEqual(
            [movement.type for movement in filtered],
            ["out", "in"],
        )
        self.assertEqual(len(self.repository.list_movements(limit=2)), 2)

    def test_product_name_is_stripped_and_casefolded_for_duplicates(self) -> None:
        product = self.repository.create_product(self.product("  Épice  "))

        self.assertEqual(product.name, "Épice")
        with self.assertRaises(ValueError):
            self.repository.create_product(self.product("épice"))

    def test_product_and_batch_crud_and_queries(self) -> None:
        product = self.repository.create_product(self.product())
        updated_product = self.repository.update_product(
            Product(
                id=product.id,
                name="  Lait entier ",
                unit="L",
                category="Épicerie",
                min_stock_threshold=2.0,
                shelf_life_after_opening_days=None,
            )
        )
        self.assertEqual(updated_product.name, "Lait entier")
        self.assertEqual(len(self.repository.list_products()), 1)

        batch = self.repository.create_batch(self.batch(product.id, 2.0))
        self.assertEqual(self.repository.get_batch(batch.id).id, batch.id)
        self.assertEqual(len(self.repository.list_batches_for_product(product.id)), 1)
        self.assertEqual(len(self.repository.list_batches_in_stock()), 1)

        updated_batch = self.repository.update_batch(
            Batch(
                id=batch.id,
                product_id=product.id,
                quantity=2.0,
                unit_price_cents=200,
                purchase_date=PURCHASE_DATE,
                supplier="Association",
                notes="Modifié",
            )
        )
        self.assertAlmostEqual(updated_batch.quantity, 2.0)
        self.assertEqual(updated_batch.unit_price_cents, 200)
        self.assertEqual(self.movement_count(batch.id), 1)

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.delete_batch(batch.id)

    def test_batch_edit_cannot_bypass_stock_history(self) -> None:
        product = self.repository.create_product(self.product())
        other_product = self.repository.create_product(self.product("Crème"))
        batch = self.repository.create_batch(self.batch(product.id, 2.0))
        for changes in (
            {"quantity": 1.5},
            {"product_id": other_product.id},
            {"opened_date": PURCHASE_DATE},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.repository.update_batch(replace(batch, **changes))
        self.assertEqual(self.repository.get_batch(batch.id), batch)
        self.assertEqual(self.movement_count(batch.id), 1)

    def test_stale_batch_edit_preserves_a_concurrent_movement(self) -> None:
        product = self.repository.create_product(self.product())
        stale_batch = self.repository.create_batch(self.batch(product.id, 2.0))
        self.repository.record_movement(self.movement(stale_batch.id, "out", 0.5))

        with self.assertRaises(ValueError):
            self.repository.update_batch(replace(stale_batch, unit_price_cents=200))

        self.assertEqual(self.repository.get_batch(stale_batch.id).quantity, 1.5)
        self.assertEqual(self.movement_count(stale_batch.id), 2)

    def test_duplicate_product_name_is_rejected(self) -> None:
        self.repository.create_product(self.product("Lait"))

        with self.assertRaises(ValueError):
            self.repository.create_product(self.product("lait"))

    def test_categories_can_be_created_and_reused_by_products(self) -> None:
        category = self.repository.create_category(Category("Frais"))
        product = self.repository.create_product(self.product())

        self.assertEqual(product.category, "Frais")
        self.assertEqual(self.repository.list_categories(), [category])
        self.assertEqual(
            self.repository.count_products_by_category(),
            {category.id: 1},
        )
        with self.assertRaises(ValueError):
            self.repository.create_category(Category("frais"))

    def test_product_without_batches_can_be_deleted(self) -> None:
        product = self.repository.create_product(self.product())

        self.repository.delete_product(product.id)

        self.assertIsNone(self.repository.get_product(product.id))

    def test_negative_quantity_is_rejected(self) -> None:
        product = self.repository.create_product(self.product())

        with self.assertRaises(ValueError):
            self.repository.create_batch(self.batch(product.id, -0.1))

        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0],
            0,
        )

    def test_output_larger_than_available_stock_is_rejected(self) -> None:
        product = self.repository.create_product(self.product())
        batch = self.repository.create_batch(self.batch(product.id, 0.5))

        with self.assertRaises(ValueError):
            self.repository.record_movement(self.movement(batch.id, "out", 0.6))

        current_batch = self.repository.get_batch(batch.id)
        self.assertAlmostEqual(current_batch.quantity, 0.5)
        self.assertEqual(self.movement_count(batch.id), 1)

    def test_successive_point_one_outputs_from_point_three_are_exact(self) -> None:
        product = self.repository.create_product(self.product())
        batch = self.repository.create_batch(self.batch(product.id, 0.3))

        expected_quantities = (0.2, 0.1, 0.0)
        for expected_quantity in expected_quantities:
            self.repository.record_movement(self.movement(batch.id, "out", 0.1))
            current_batch = self.repository.get_batch(batch.id)
            self.assertAlmostEqual(current_batch.quantity, expected_quantity)

        with self.assertRaises(ValueError):
            self.repository.record_movement(self.movement(batch.id, "out", 0.1))
        self.assertEqual(self.movement_count(batch.id), 4)
        self.assertEqual(self.repository.list_batches_in_stock(), [])

    def test_create_batch_rolls_back_if_initial_movement_fails(self) -> None:
        product = self.repository.create_product(self.product())
        self.connection.execute(
            """
            CREATE TRIGGER reject_initial_movement
            BEFORE INSERT ON stock_movements
            WHEN NEW.type = 'in'
            BEGIN
                SELECT RAISE(ABORT, 'forced initial movement failure');
            END
            """
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.create_batch(self.batch(product.id, 1.0))

        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM batches").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0],
            0,
        )

    def test_record_movement_rolls_back_quantity_if_insert_fails(self) -> None:
        product = self.repository.create_product(self.product())
        batch = self.repository.create_batch(self.batch(product.id, 1.0))
        self.connection.execute(
            """
            CREATE TRIGGER reject_output_movement
            BEFORE INSERT ON stock_movements
            WHEN NEW.type = 'out'
            BEGIN
                SELECT RAISE(ABORT, 'forced output movement failure');
            END
            """
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.record_movement(self.movement(batch.id, "out", 0.2))

        current_batch = self.repository.get_batch(batch.id)
        self.assertAlmostEqual(current_batch.quantity, 1.0)
        self.assertEqual(self.movement_count(batch.id), 1)

    def test_inventory_records_only_the_difference(self) -> None:
        product = self.repository.create_product(self.product())
        batch = self.repository.create_batch(self.batch(product.id, 3.0))

        loss = self.repository.record_inventory(
            batch.id, 2.25, PURCHASE_DATE, "Comptage"
        )
        self.assertEqual((loss.type, loss.quantity, loss.reason), ("loss", 0.75, "Comptage"))
        self.assertAlmostEqual(self.repository.get_batch(batch.id).quantity, 2.25)

        addition = self.repository.record_inventory(
            batch.id, 3.0, PURCHASE_DATE, "Second comptage"
        )
        self.assertEqual((addition.type, addition.quantity), ("in", 0.75))
        self.assertAlmostEqual(self.repository.get_batch(batch.id).quantity, 3.0)

        with self.assertRaises(ValueError):
            self.repository.record_inventory(
                batch.id, 3.0, PURCHASE_DATE, "Comptage identique"
            )

    def test_product_with_batches_cannot_be_deleted(self) -> None:
        product = self.repository.create_product(self.product())
        self.repository.create_batch(self.batch(product.id))

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.delete_product(product.id)

        self.assertIsNotNone(self.repository.get_product(product.id))

    def test_date_constraints_are_validated_in_python(self) -> None:
        product = self.repository.create_product(self.product())

        with self.assertRaises(ValueError):
            self.repository.create_batch(
                Batch(
                    product_id=product.id,
                    quantity=1.0,
                    unit_price_cents=100,
                    purchase_date=PURCHASE_DATE,
                    expiry_date=date(2026, 9, 28),
                )
            )

        batch = self.repository.create_batch(self.batch(product.id))
        with self.assertRaises(ValueError):
            self.repository.mark_batch_open(batch.id, date(2026, 9, 28))

    def test_mark_batch_open_sets_date_once(self) -> None:
        product = self.repository.create_product(self.product())
        batch = self.repository.create_batch(self.batch(product.id))

        opened = self.repository.mark_batch_open(batch.id, date(2026, 9, 30))
        self.assertEqual(opened.opened_date, date(2026, 9, 30))
        unchanged = self.repository.mark_batch_open(batch.id, date(2026, 10, 1))
        self.assertEqual(unchanged.opened_date, date(2026, 9, 30))

    def test_money_conversions_use_decimal(self) -> None:
        self.assertEqual(euros_to_cents("12.34"), 1234)
        self.assertEqual(euros_to_cents(Decimal("0.005")), 1)
        self.assertEqual(cents_to_euros(1234), Decimal("12.34"))

    def test_zero_after_rounding_is_not_a_valid_movement(self) -> None:
        product = self.repository.create_product(self.product())
        batch = self.repository.create_batch(self.batch(product.id))

        with self.assertRaises(ValueError):
            self.repository.record_movement(self.movement(batch.id, "out", 0.0004))


if __name__ == "__main__":
    unittest.main()
