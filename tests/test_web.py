"""Tests HTTP de l’interface web locale."""

from base64 import b64encode
from pathlib import Path
import sys
import tempfile
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unittest


SOURCE_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from stock_cuisine.web import create_server


class WebTests(unittest.TestCase):
    """Vérifie le parcours principal depuis un navigateur HTTP."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.database = str(Path(self.temp_directory.name) / "stock.db")
        self.server = create_server("127.0.0.1", 0, self.database)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def get(self, path: str) -> str:
        with urlopen(self.base_url + path) as response:
            self.assertEqual(response.status, 200)
            return response.read().decode("utf-8")

    def post(self, path: str, values: dict[str, str]) -> str:
        request = Request(
            self.base_url + path,
            data=urlencode(values).encode("utf-8"),
            method="POST",
        )
        with urlopen(request) as response:
            self.assertEqual(response.status, 200)
            return response.read().decode("utf-8")

    def test_browser_workflow_creates_and_updates_stock(self) -> None:
        page = self.get("/")
        self.assertIn("Tableau de bord", page)
        self.assertIn("Cuisine 4H", page)
        self.assertIn('href="/" aria-current="page"', page)
        self.assertIn("Aucun produit enregistré", page)

        page = self.post(
            "/products",
            {
                "name": "Lait",
                "unit": "L",
                "category": "Frais",
                "minimum": "2",
                "shelf_life": "3",
            },
        )
        self.assertIn("Produit créé.", page)
        self.assertIn("Lait", page)

        page = self.post(
            "/batches",
            {
                "product_id": "1",
                "quantity": "3",
                "unit_price": "1.25",
                "purchase_date": "2026-09-29",
                "expiry_date": "2026-10-10",
            },
        )
        self.assertIn("Lot créé.", page)
        self.assertIn("3.75 €", page)

        page = self.post(
            "/movements",
            {
                "batch_id": "1",
                "movement_type": "out",
                "quantity": "1",
                "movement_date": "2026-09-29",
                "reason": "Déjeuner",
            },
        )
        self.assertIn("Mouvement enregistré.", page)
        self.assertIn("2 L", page)
        self.assertIn("2.50 €", page)

        page = self.post("/batches/open", {"batch_id": "1"})
        self.assertIn("Lot ouvert.", page)
        self.assertIn("2026-", page)

        page = self.get("/movements")
        self.assertIn("Historique des mouvements", page)
        self.assertIn("Stock initial", page)
        self.assertIn("Déjeuner", page)
        self.assertIn("Sortie", page)

        page = self.get("/batches")
        self.assertIn("Lait", page)
        self.assertNotIn(">Ouvrir</button>", page)

        page = self.get("/products")
        self.assertIn('href="/products" aria-current="page"', page)
        self.assertIn("Lots associés", page)
        self.assertNotIn('action="/products/delete"', page)

    def test_product_without_batch_can_be_deleted_from_products_page(self) -> None:
        self.post(
            "/products",
            {
                "name": "Riz",
                "unit": "kg",
                "category": "Épicerie",
                "minimum": "1",
            },
        )

        page = self.get("/products")
        self.assertIn("Supprimer", page)

        page = self.post("/products/delete", {"product_id": "1"})
        self.assertIn("Produit supprimé.", page)
        self.assertIn("Aucun produit enregistré", page)

    def test_categories_can_be_added_and_used_for_products(self) -> None:
        page = self.get("/categories")
        self.assertIn("Aucune catégorie enregistrée", page)

        page = self.post("/categories", {"name": "Frais"})
        self.assertIn("Catégorie créée.", page)
        self.assertIn("Frais", page)

        page = self.get("/products")
        self.assertIn('name="category"', page)
        self.assertIn('value="Frais"', page)

        self.post(
            "/products",
            {
                "name": "Lait",
                "unit": "L",
                "category": "Frais",
                "minimum": "2",
            },
        )
        page = self.get("/categories")
        self.assertIn("1 produit(s)", page)

    def test_products_and_batches_can_be_edited_from_the_web(self) -> None:
        self.post(
            "/products",
            {
                "name": "Lait",
                "unit": "L",
                "category": "Frais",
                "minimum": "2",
                "shelf_life": "3",
            },
        )

        page = self.get("/products/edit?product_id=1")
        self.assertIn("Modifier le produit", page)
        self.assertIn('value="Lait"', page)

        page = self.post(
            "/products/edit",
            {
                "product_id": "1",
                "name": "Lait entier",
                "unit": "L",
                "category": "Frais",
                "minimum": "3",
                "shelf_life": "5",
            },
        )
        self.assertIn("Produit modifié.", page)
        self.assertIn("Lait entier", page)

        self.post(
            "/batches",
            {
                "product_id": "1",
                "quantity": "3",
                "unit_price": "1.25",
                "purchase_date": "2026-09-29",
                "expiry_date": "2026-10-10",
                "supplier": "Fournisseur",
                "notes": "Avant modification",
            },
        )
        page = self.get("/batches/edit?batch_id=1")
        self.assertIn("Modifier le lot", page)
        self.assertIn("Avant modification", page)

        page = self.post(
            "/batches/edit",
            {
                "batch_id": "1",
                "product_id": "1",
                "quantity": "3",
                "opened_date": "",
                "unit_price": "1.50",
                "purchase_date": "2026-09-29",
                "expiry_date": "2026-10-20",
                "supplier": "Nouveau fournisseur",
                "notes": "Après modification",
            },
        )
        self.assertIn("Lot modifié.", page)
        self.assertIn("2026-10-20", page)
        page = self.get("/batches/edit?batch_id=1")
        self.assertIn("Nouveau fournisseur", page)
        self.assertIn("Après modification", page)

    def test_batches_are_grouped_by_category_and_product(self) -> None:
        self.post("/categories", {"name": "Frais"})
        self.post("/categories", {"name": "Épicerie"})
        for name, category in (
            ("Zeste", "Frais"),
            ("Abricot", "Frais"),
            ("Riz", "Épicerie"),
        ):
            self.post(
                "/products",
                {
                    "name": name,
                    "unit": "kg",
                    "category": category,
                    "minimum": "1",
                },
            )
        for product_id in (1, 2, 3):
            self.post(
                "/batches",
                {
                    "product_id": str(product_id),
                    "quantity": "1",
                    "unit_price": "2",
                    "purchase_date": "2026-09-30",
                },
            )

        page = self.get("/batches")

        self.assertLess(page.index("Épicerie"), page.index("Frais"))
        self.assertLess(page.index("<strong>Abricot</strong>"), page.index("<strong>Zeste</strong>"))
        self.assertLess(page.index("<strong>Riz</strong>"), page.index("<strong>Abricot</strong>"))

    def test_inventory_adjusts_batch_stock_and_keeps_history(self) -> None:
        self.post(
            "/products",
            {
                "name": "Riz",
                "unit": "kg",
                "category": "Épicerie",
                "minimum": "1",
            },
        )
        self.post(
            "/batches",
            {
                "product_id": "1",
                "quantity": "5",
                "unit_price": "2",
                "purchase_date": "2026-09-29",
            },
        )

        page = self.get("/batches/inventory?batch_id=1")
        self.assertIn("Quantité réellement comptée", page)

        page = self.post(
            "/batches/inventory",
            {
                "batch_id": "1",
                "actual_quantity": "3.5",
                "inventory_date": "2026-09-30",
                "reason": "Comptage du matin",
            },
        )
        self.assertIn("Inventaire enregistré.", page)
        self.assertIn("3.5", page)

        page = self.get("/movements?batch_id=1")
        self.assertIn("Comptage du matin", page)
        self.assertIn("Perte", page)

    def test_public_server_requires_basic_authentication(self) -> None:
        server = create_server(
            "0.0.0.0",
            0,
            self.database,
            auth_user="equipe",
            auth_password="secret",
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            with self.assertRaises(HTTPError) as context:
                urlopen(url)
            self.assertEqual(context.exception.code, 401)

            credentials = b64encode(b"equipe:secret").decode("ascii")
            request = Request(
                url,
                headers={"Authorization": f"Basic {credentials}"},
            )
            with urlopen(request) as response:
                self.assertEqual(response.status, 200)
                page = response.read().decode("utf-8")
                self.assertIn('name="_csrf"', page)

            request = Request(
                url,
                data=urlencode({"name": "Frais"}).encode("utf-8"),
                headers={"Authorization": f"Basic {credentials}"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as context:
                urlopen(request)
            self.assertEqual(context.exception.code, 403)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
