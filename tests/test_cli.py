"""Tests du parcours CLI principal."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from stock_cuisine.cli import main


class CliTests(unittest.TestCase):
    """Vérifie les commandes utilisables par un opérateur."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.database = str(Path(self.temp_directory.name) / "stock.db")

    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        output = StringIO()
        errors = StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = main(("--database", self.database, *arguments))
        return result, output.getvalue(), errors.getvalue()

    def test_product_batch_movement_stock_and_alerts_workflow(self) -> None:
        result, output, errors = self.run_cli(
            "product",
            "add",
            "--name",
            "Lait",
            "--unit",
            "L",
            "--category",
            "Frais",
            "--minimum",
            "2",
            "--shelf-life",
            "3",
        )
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("Produit créé : #1 Lait", output)

        result, output, errors = self.run_cli(
            "batch",
            "add",
            "--product-id",
            "1",
            "--quantity",
            "3",
            "--unit-price",
            "1.25",
            "--purchase-date",
            "2026-09-29",
            "--expiry-date",
            "2026-10-10",
        )
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("Lot créé : #1", output)

        result, output, errors = self.run_cli("movement", "add", "--batch-id", "1", "--type", "out", "--quantity", "1", "--date", "2026-09-29", "--reason", "Déjeuner")
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("stock du lot #1 : 2", output)

        result, output, errors = self.run_cli("movement", "list")
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("Stock initial", output)
        self.assertIn("Sortie", output)
        self.assertIn("Déjeuner", output)

        result, output, errors = self.run_cli("stock", "list")
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("Lait", output)
        self.assertIn("2", output)
        self.assertIn("2.50 €", output)
        self.assertIn("OK", output)

        result, output, errors = self.run_cli("alerts", "--date", "2026-09-29", "--days", "7")
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("Lots arrivant à échéance sous 7 jours", output)

    def test_invalid_movement_returns_user_friendly_error(self) -> None:
        self.run_cli(
            "product",
            "add",
            "--name",
            "Riz",
            "--unit",
            "kg",
            "--category",
            "Épicerie",
            "--minimum",
            "1",
        )
        self.run_cli(
            "batch",
            "add",
            "--product-id",
            "1",
            "--quantity",
            "1",
            "--unit-price",
            "2",
            "--purchase-date",
            "2026-09-29",
        )

        result, output, errors = self.run_cli(
            "movement",
            "add",
            "--batch-id",
            "1",
            "--type",
            "out",
            "--quantity",
            "2",
            "--reason",
            "Test",
        )
        self.assertEqual(result, 2)
        self.assertEqual(output, "")
        self.assertIn("Stock insuffisant", errors)

    def test_product_delete_requires_no_associated_batch(self) -> None:
        result, output, errors = self.run_cli(
            "product",
            "add",
            "--name",
            "Riz",
            "--unit",
            "kg",
            "--category",
            "Épicerie",
            "--minimum",
            "1",
        )
        self.assertEqual((result, errors), (0, ""))

        result, output, errors = self.run_cli(
            "product", "delete", "--product-id", "1"
        )
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("Produit supprimé : #1 Riz", output)

        result, output, errors = self.run_cli("product", "list")
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("Aucun résultat.", output)

    def test_product_delete_with_batch_returns_user_friendly_error(self) -> None:
        self.run_cli(
            "product",
            "add",
            "--name",
            "Riz",
            "--unit",
            "kg",
            "--category",
            "Épicerie",
            "--minimum",
            "1",
        )
        self.run_cli(
            "batch",
            "add",
            "--product-id",
            "1",
            "--quantity",
            "1",
            "--unit-price",
            "2",
            "--purchase-date",
            "2026-09-29",
        )

        result, output, errors = self.run_cli(
            "product", "delete", "--product-id", "1"
        )
        self.assertEqual(result, 2)
        self.assertEqual(output, "")
        self.assertIn("des lots lui sont associés", errors)


if __name__ == "__main__":
    unittest.main()
