"""Tests des cas d'usage introduits par la refonte."""

from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from stock_cuisine import Batch, Product, Repository, StockApplication, connect_database
from stock_cuisine.backup import backup_database
from stock_cuisine.export import csv_text, write_csv


class OperationsTests(unittest.TestCase):
    """Vérifie les sorties partagées par les interfaces."""

    def setUp(self) -> None:
        self.connection = connect_database(":memory:")
        self.repository = Repository(self.connection)
        self.addCleanup(self.connection.close)

    def test_dashboard_and_stock_export_share_the_same_total(self) -> None:
        product = self.repository.create_product(
            Product("Lait", "L", "Frais", 2.0, shelf_life_after_opening_days=0)
        )
        self.repository.create_batch(
            Batch(
                product_id=product.id,
                quantity=3.0,
                unit_price_cents=125,
                purchase_date=date(2026, 9, 29),
            )
        )

        dashboard = StockApplication(self.repository).dashboard(
            date(2026, 9, 29)
        )
        self.assertEqual(dashboard.products[0].quantity, 3.0)
        self.assertEqual(dashboard.products[0].value_cents, 375)
        self.assertEqual(dashboard.total_value_cents, 375)
        self.assertIn("3,L,2,ok,375", csv_text(self.repository, "stock"))
        self.assertIn("valeur_stock_centimes", csv_text(self.repository, "stock"))
        self.assertIn("valeur_stock_centimes", csv_text(self.repository, "batches"))
        self.assertIn(",0\r\n", csv_text(self.repository, "products"))

    def test_products_are_sorted_by_category_then_name(self) -> None:
        self.repository.create_product(Product("Zeste", "kg", "Frais", 1.0))
        self.repository.create_product(Product("Abricot", "kg", "Frais", 1.0))
        self.repository.create_product(Product("Riz", "kg", "Épicerie", 1.0))

        products = StockApplication(self.repository).product_stock()

        self.assertEqual(
            [line.product.name for line in products],
            ["Riz", "Abricot", "Zeste"],
        )

    def test_write_csv_creates_parent_directory(self) -> None:
        self.repository.create_product(Product("Riz", "kg", "Épicerie", 1.0))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "exports" / "products.csv"
            returned = write_csv(self.repository, "products", target)
            self.assertEqual(returned, target)
            self.assertTrue(target.exists())
            self.assertIn("Riz", target.read_text(encoding="utf-8-sig"))

    def test_backup_contains_an_initialized_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.db"
            target = Path(directory) / "backups" / "copy.db"
            source_connection = connect_database(str(source))
            Repository(source_connection).create_product(
                Product("Farine", "kg", "Épicerie", 1.0)
            )
            source_connection.close()

            backup_database(source, target)
            copied = connect_database(str(target))
            self.addCleanup(copied.close)
            self.assertEqual(copied.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
