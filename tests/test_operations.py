"""Tests des cas d'usage introduits par la refonte."""

from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


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

    def test_missing_backup_source_does_not_create_any_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "missing.db"
            target = Path(directory) / "copy.db"
            with self.assertRaises(FileNotFoundError):
                backup_database(source, target)
            self.assertFalse(source.exists())
            self.assertFalse(target.exists())

    def test_invalid_backup_source_preserves_an_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.db"
            target = Path(directory) / "previous.db"
            source.write_text("Ce fichier n'est pas une base SQLite.", encoding="utf-8")
            target.write_bytes(b"sauvegarde precedente")
            with self.assertRaises(sqlite3.DatabaseError):
                backup_database(source, target)
            self.assertEqual(target.read_bytes(), b"sauvegarde precedente")

    def test_application_and_service_agree_on_expiry_boundaries(self) -> None:
        reference = date(2026, 9, 29)
        product = self.repository.create_product(
            Product("Lait", "L", "Frais", 10.0, shelf_life_after_opening_days=2)
        )
        batches = [
            self.repository.create_batch(
                Batch(product.id, 1.0, 125, date(2026, 9, 1), expiry, opened)
            )
            for expiry, opened in (
                (date(2026, 9, 28), None),
                (reference, None),
                (date(2026, 10, 6), None),
                (date(2026, 10, 7), None),
                (None, None),
                (date(2026, 12, 1), date(2026, 9, 25)),
            )
        ]
        application = StockApplication(self.repository)
        report = application.alerts(7, reference)
        expired = [item.batch for item in report.expired]
        expiring = [item.batch for item in report.expiring]
        self.assertEqual(expired, [batches[0], batches[5]])
        self.assertEqual(expiring, [batches[1], batches[2]])
        self.assertEqual(expired, application.service.expired_batches(reference))
        self.assertEqual(expiring, application.service.batches_expiring_within(7, reference))
        self.assertEqual(report.below_minimum, (product,))
        self.assertEqual(application.dashboard(reference).expired, 2)

    def test_invalid_export_does_not_truncate_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "export.csv"
            target.write_text("export précédent", encoding="utf-8")
            with self.assertRaises(ValueError):
                write_csv(self.repository, "invalid", target)
            self.assertEqual(target.read_text(encoding="utf-8"), "export précédent")

    def test_stock_snapshot_is_consistent_during_another_connection_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "stock.db")
            with closing(connect_database(path)) as reader_connection:
                with closing(connect_database(path)) as writer_connection:
                    reader = Repository(reader_connection)
                    writer = Repository(writer_connection)
                    writer.create_product(Product("Riz", "kg", "Épicerie", 1.0))
                    list_products = reader.list_products

                    def read_then_write():
                        products = list_products()
                        added = writer.create_product(
                            Product("Farine", "kg", "Épicerie", 1.0)
                        )
                        writer.create_batch(
                            Batch(added.id, 2.0, 100, date(2026, 9, 29))
                        )
                        return products

                    application = StockApplication(reader)
                    with patch.object(reader, "list_products", side_effect=read_then_write):
                        snapshot = application.service.stock_snapshot()
                    self.assertEqual([p.name for p in snapshot.products], ["Riz"])
                    self.assertEqual(snapshot.batches, ())
                    self.assertEqual(len(application.product_stock()), 2)
                    self.assertFalse(reader_connection.in_transaction)


if __name__ == "__main__":
    unittest.main()
