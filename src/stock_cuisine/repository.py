"""Accès aux données et opérations de stock."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import sqlite3
from typing import ContextManager, Dict, List, Optional, Sequence, Tuple

from .db import read_transaction, transaction
from .models import Batch, Category, Product, StockMovement


QUANTITY_QUANTUM = Decimal("0.001")
INITIAL_STOCK_REASON = "Stock initial"
MOVEMENT_TYPES = frozenset(("in", "out", "loss"))


def _quantity_decimal(value: object) -> Decimal:
    """Convertit une quantité en Decimal non négatif."""

    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise TypeError("La quantité doit être numérique.")

    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("La quantité est invalide.") from None

    if not quantity.is_finite():
        raise ValueError("La quantité est invalide.")
    if quantity < 0:
        raise ValueError("La quantité ne peut pas être négative.")
    return quantity


def _rounded_quantity_decimal(value: object) -> Decimal:
    """Arrondit une quantité à trois décimales sans calcul flottant."""

    try:
        return _quantity_decimal(value).quantize(
            QUANTITY_QUANTUM, rounding=ROUND_HALF_UP
        )
    except InvalidOperation:
        raise ValueError("La quantité est trop grande.") from None


def _rounded_quantity(value: object) -> float:
    """Retourne la représentation SQLite REAL d'une quantité arrondie."""

    return float(_rounded_quantity_decimal(value))


def _validate_id(value: object, label: str) -> int:
    """Valide un identifiant SQLite."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("{} invalide.".format(label))
    return value


def _validate_date(
    value: object, label: str, allow_none: bool = False
) -> Optional[date]:
    """Valide une date calendaire Python."""

    if value is None and allow_none:
        return None
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError("{} doit être une date Python.".format(label))
    return value


def _parse_date(value: str, label: str) -> date:
    """Convertit une date ISO stockée en base."""

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise RuntimeError(
            "La date stockée pour {} est invalide.".format(label)
        ) from None


def _date_to_iso(value: date) -> str:
    """Sérialise une date en ISO 8601."""

    return value.isoformat()


def _validate_non_negative_integer(
    value: object, label: str
) -> Optional[int]:
    """Valide un entier positif ou nul, éventuellement nul."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("{} doit être un entier.".format(label))
    if value < 0:
        raise ValueError("{} ne peut pas être négatif.".format(label))
    return value


def _normalise_product(product: Product) -> Product:
    """Prépare un produit avant écriture."""

    if not isinstance(product.name, str):
        raise TypeError("Le nom du produit doit être une chaîne.")
    name = product.name.strip()
    if not name:
        raise ValueError("Le nom du produit est obligatoire.")
    if not isinstance(product.unit, str) or not isinstance(product.category, str):
        raise TypeError("L'unité et la catégorie doivent être des chaînes.")
    unit = product.unit.strip()
    category = product.category.strip()
    if not unit:
        raise ValueError("L'unité du produit est obligatoire.")
    if not category:
        raise ValueError("La catégorie du produit est obligatoire.")

    threshold = _rounded_quantity(product.min_stock_threshold)
    shelf_life = _validate_non_negative_integer(
        product.shelf_life_after_opening_days,
        "La durée après ouverture",
    )
    return Product(
        id=product.id,
        name=name,
        unit=unit,
        category=category,
        min_stock_threshold=threshold,
        shelf_life_after_opening_days=shelf_life,
    )


def _normalise_category(category: Category) -> Category:
    """Prépare une catégorie avant écriture."""

    if not isinstance(category.name, str):
        raise TypeError("Le nom de la catégorie doit être une chaîne.")
    name = category.name.strip()
    if not name:
        raise ValueError("Le nom de la catégorie est obligatoire.")
    return Category(id=category.id, name=name)


def _normalise_batch(batch: Batch) -> Batch:
    """Prépare un lot avant écriture."""

    product_id = _validate_id(batch.product_id, "L'identifiant du produit")
    quantity = _rounded_quantity(batch.quantity)
    if isinstance(batch.unit_price_cents, bool) or not isinstance(
        batch.unit_price_cents, int
    ):
        raise TypeError("Le prix en centimes doit être un entier.")
    if batch.unit_price_cents < 0:
        raise ValueError("Le prix en centimes ne peut pas être négatif.")

    purchase_date = _validate_date(batch.purchase_date, "La date d'achat")
    expiry_date = _validate_date(
        batch.expiry_date, "La date d'expiration", allow_none=True
    )
    opened_date = _validate_date(
        batch.opened_date, "La date d'ouverture", allow_none=True
    )
    if expiry_date is not None and expiry_date < purchase_date:
        raise ValueError(
            "La date d'expiration ne peut pas précéder la date d'achat."
        )
    if opened_date is not None and opened_date < purchase_date:
        raise ValueError(
            "La date d'ouverture ne peut pas précéder la date d'achat."
        )

    return Batch(
        id=batch.id,
        product_id=product_id,
        quantity=quantity,
        unit_price_cents=batch.unit_price_cents,
        purchase_date=purchase_date,
        expiry_date=expiry_date,
        opened_date=opened_date,
        supplier=batch.supplier,
        notes=batch.notes,
    )


def _normalise_movement(movement: StockMovement) -> StockMovement:
    """Prépare un mouvement avant écriture."""

    batch_id = _validate_id(movement.batch_id, "L'identifiant du lot")
    if movement.type not in MOVEMENT_TYPES:
        raise ValueError("Le type de mouvement est invalide.")
    quantity = _rounded_quantity(movement.quantity)
    if quantity <= 0:
        raise ValueError(
            "La quantité d'un mouvement doit être supérieure à zéro."
        )
    movement_date = _validate_date(movement.date, "La date du mouvement")
    if not isinstance(movement.reason, str):
        raise TypeError("La raison du mouvement doit être une chaîne.")
    reason = movement.reason.strip()
    if not reason:
        raise ValueError("La raison du mouvement est obligatoire.")

    return StockMovement(
        id=movement.id,
        batch_id=batch_id,
        type=movement.type,
        quantity=quantity,
        date=movement_date,
        reason=reason,
    )


def _product_from_row(row: sqlite3.Row) -> Product:
    """Construit un produit depuis une ligne SQLite."""

    return Product(
        id=int(row["id"]),
        name=str(row["name"]),
        unit=str(row["unit"]),
        category=str(row["category"]),
        min_stock_threshold=float(row["min_stock_threshold"]),
        shelf_life_after_opening_days=(
            None
            if row["shelf_life_after_opening_days"] is None
            else int(row["shelf_life_after_opening_days"])
        ),
    )


def _category_from_row(row: sqlite3.Row) -> Category:
    """Construit une catégorie depuis une ligne SQLite."""

    return Category(id=int(row["id"]), name=str(row["name"]))


def _batch_from_row(row: sqlite3.Row) -> Batch:
    """Construit un lot depuis une ligne SQLite."""

    return Batch(
        id=int(row["id"]),
        product_id=int(row["product_id"]),
        quantity=float(row["quantity"]),
        unit_price_cents=int(row["unit_price_cents"]),
        purchase_date=_parse_date(row["purchase_date"], "purchase_date"),
        expiry_date=(
            None
            if row["expiry_date"] is None
            else _parse_date(row["expiry_date"], "expiry_date")
        ),
        opened_date=(
            None
            if row["opened_date"] is None
            else _parse_date(row["opened_date"], "opened_date")
        ),
        supplier=row["supplier"],
        notes=row["notes"],
    )


def _movement_from_row(row: sqlite3.Row) -> StockMovement:
    """Construit un mouvement depuis une ligne SQLite."""

    return StockMovement(
        id=int(row["id"]),
        batch_id=int(row["batch_id"]),
        type=str(row["type"]),
        quantity=float(row["quantity"]),
        date=_parse_date(row["date"], "date"),
        reason=str(row["reason"]),
    )


class Repository:
    """Repository SQLite pour les produits, lots et mouvements."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def read_snapshot(self) -> ContextManager[sqlite3.Connection]:
        """Regroupe des lectures dans une transaction cohérente, réutilisable."""

        return read_transaction(self.connection)

    def _ensure_product_name_available(
        self, name: str, excluded_id: Optional[int] = None
    ) -> None:
        """Détecte les doublons Unicode avec ``casefold``."""

        normalized_name = name.casefold()
        rows = self.connection.execute(
            "SELECT id, name FROM products"
        ).fetchall()
        for row in rows:
            if excluded_id is not None and int(row["id"]) == excluded_id:
                continue
            existing_name = str(row["name"]).strip().casefold()
            if existing_name == normalized_name:
                raise ValueError("Un produit portant ce nom existe déjà.")

    def _ensure_category_name_available(self, name: str) -> None:
        """Détecte les doublons de catégories, y compris Unicode."""

        normalized_name = name.casefold()
        rows = self.connection.execute(
            "SELECT name FROM categories"
        ).fetchall()
        for row in rows:
            existing_name = str(row["name"]).strip().casefold()
            if existing_name == normalized_name:
                raise ValueError("Une catégorie portant ce nom existe déjà.")

    def _get_or_create_category(self, name: str) -> Category:
        """Retourne une catégorie existante ou la crée dans la transaction courante."""

        normalized_name = name.casefold()
        rows = self.connection.execute(
            "SELECT id, name FROM categories ORDER BY id"
        ).fetchall()
        for row in rows:
            if str(row["name"]).strip().casefold() == normalized_name:
                return _category_from_row(row)

        cursor = self.connection.execute(
            "INSERT INTO categories (name) VALUES (?)", (name,)
        )
        return Category(id=int(cursor.lastrowid), name=name)

    def create_category(self, category: Category) -> Category:
        """Crée une catégorie."""

        prepared = _normalise_category(category)
        if prepared.id is not None:
            raise ValueError("Une nouvelle catégorie ne doit pas avoir d'identifiant.")

        with transaction(self.connection):
            self._ensure_category_name_available(prepared.name)
            cursor = self.connection.execute(
                "INSERT INTO categories (name) VALUES (?)",
                (prepared.name,),
            )
            category_id = int(cursor.lastrowid)

        created = self.get_category(category_id)
        if created is None:
            raise RuntimeError("La catégorie créée est introuvable.")
        return created

    def get_category(self, category_id: int) -> Optional[Category]:
        """Retourne une catégorie ou None."""

        validated_id = _validate_id(category_id, "L'identifiant de la catégorie")
        row = self.connection.execute(
            "SELECT id, name FROM categories WHERE id = ?", (validated_id,)
        ).fetchone()
        return None if row is None else _category_from_row(row)

    def list_categories(self) -> List[Category]:
        """Retourne les catégories dans l'ordre alphabétique."""

        rows = self.connection.execute(
            "SELECT id, name FROM categories ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [_category_from_row(row) for row in rows]

    def count_products_by_category(self) -> Dict[int, int]:
        """Retourne le nombre de produits rattachés à chaque catégorie."""

        rows = self.connection.execute(
            """
            SELECT category_id, COUNT(*) AS product_count
            FROM products
            WHERE category_id IS NOT NULL
            GROUP BY category_id
            """
        ).fetchall()
        return {
            int(row["category_id"]): int(row["product_count"]) for row in rows
        }

    def create_product(self, product: Product) -> Product:
        """Crée un produit."""

        prepared = _normalise_product(product)
        if prepared.id is not None:
            raise ValueError("Un nouveau produit ne doit pas avoir d'identifiant.")

        with transaction(self.connection):
            self._ensure_product_name_available(prepared.name)
            category = self._get_or_create_category(prepared.category)
            cursor = self.connection.execute(
                """
                INSERT INTO products (
                    name, unit, category, category_id, min_stock_threshold,
                    shelf_life_after_opening_days
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    prepared.name,
                    prepared.unit,
                    category.name,
                    category.id,
                    prepared.min_stock_threshold,
                    prepared.shelf_life_after_opening_days,
                ),
            )
            product_id = int(cursor.lastrowid)

        created = self.get_product(product_id)
        if created is None:
            raise RuntimeError("Le produit créé est introuvable.")
        return created

    def get_product(self, product_id: int) -> Optional[Product]:
        """Retourne un produit ou ``None``."""

        validated_id = _validate_id(product_id, "L'identifiant du produit")
        row = self.connection.execute(
            "SELECT * FROM products WHERE id = ?", (validated_id,)
        ).fetchone()
        return None if row is None else _product_from_row(row)

    def list_products(self) -> List[Product]:
        """Retourne tous les produits par identifiant."""

        rows = self.connection.execute(
            "SELECT * FROM products ORDER BY id"
        ).fetchall()
        return [_product_from_row(row) for row in rows]

    def update_product(self, product: Product) -> Product:
        """Met à jour un produit."""

        prepared = _normalise_product(product)
        product_id = _validate_id(prepared.id, "L'identifiant du produit")

        with transaction(self.connection):
            self._ensure_product_name_available(prepared.name, product_id)
            category = self._get_or_create_category(prepared.category)
            cursor = self.connection.execute(
                """
                UPDATE products
                SET name = ?, unit = ?, category = ?, category_id = ?,
                    min_stock_threshold = ?, shelf_life_after_opening_days = ?
                WHERE id = ?
                """,
                (
                    prepared.name,
                    prepared.unit,
                    category.name,
                    category.id,
                    prepared.min_stock_threshold,
                    prepared.shelf_life_after_opening_days,
                    product_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError("Produit introuvable.")

        updated = self.get_product(product_id)
        if updated is None:
            raise RuntimeError("Le produit mis à jour est introuvable.")
        return updated

    def delete_product(self, product_id: int) -> None:
        """Supprime un produit sans lots associés."""

        validated_id = _validate_id(product_id, "L'identifiant du produit")
        with transaction(self.connection):
            cursor = self.connection.execute(
                "DELETE FROM products WHERE id = ?", (validated_id,)
            )
            if cursor.rowcount != 1:
                raise KeyError("Produit introuvable.")

    def create_batch(self, batch: Batch) -> Batch:
        """Crée un lot et son mouvement initial dans une transaction."""

        prepared = _normalise_batch(batch)
        if prepared.id is not None:
            raise ValueError("Un nouveau lot ne doit pas avoir d'identifiant.")
        if prepared.quantity <= 0:
            raise ValueError(
                "La quantité initiale du lot doit être supérieure à zéro."
            )

        with transaction(self.connection):
            cursor = self.connection.execute(
                """
                INSERT INTO batches (
                    product_id, quantity, unit_price_cents, purchase_date,
                    expiry_date, opened_date, supplier, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prepared.product_id,
                    prepared.quantity,
                    prepared.unit_price_cents,
                    _date_to_iso(prepared.purchase_date),
                    None
                    if prepared.expiry_date is None
                    else _date_to_iso(prepared.expiry_date),
                    None
                    if prepared.opened_date is None
                    else _date_to_iso(prepared.opened_date),
                    prepared.supplier,
                    prepared.notes,
                ),
            )
            batch_id = int(cursor.lastrowid)
            self.connection.execute(
                """
                INSERT INTO stock_movements (
                    batch_id, type, quantity, date, reason
                ) VALUES (?, 'in', ?, ?, ?)
                """,
                (
                    batch_id,
                    prepared.quantity,
                    _date_to_iso(prepared.purchase_date),
                    INITIAL_STOCK_REASON,
                ),
            )

        created = self.get_batch(batch_id)
        if created is None:
            raise RuntimeError("Le lot créé est introuvable.")
        return created

    def get_batch(self, batch_id: int) -> Optional[Batch]:
        """Retourne un lot ou ``None``."""

        validated_id = _validate_id(batch_id, "L'identifiant du lot")
        row = self.connection.execute(
            "SELECT * FROM batches WHERE id = ?", (validated_id,)
        ).fetchone()
        return None if row is None else _batch_from_row(row)

    def list_batches_for_product(self, product_id: int) -> List[Batch]:
        """Retourne les lots d'un produit."""

        validated_id = _validate_id(product_id, "L'identifiant du produit")
        rows = self.connection.execute(
            """
            SELECT * FROM batches
            WHERE product_id = ?
            ORDER BY id
            """,
            (validated_id,),
        ).fetchall()
        return [_batch_from_row(row) for row in rows]

    def list_batches(self) -> List[Batch]:
        """Retourne tous les lots par identifiant."""

        rows = self.connection.execute(
            "SELECT * FROM batches ORDER BY id"
        ).fetchall()
        return [_batch_from_row(row) for row in rows]

    def list_batches_in_stock(self) -> List[Batch]:
        """Retourne les lots dont la quantité courante est positive."""

        rows = self.connection.execute(
            """
            SELECT * FROM batches
            WHERE quantity > 0
            ORDER BY id
            """
        ).fetchall()
        return [_batch_from_row(row) for row in rows]

    def update_batch(self, batch: Batch) -> Batch:
        """Corrige les informations d'un lot en préservant stock et historique.

        La quantité et l'ouverture reçues doivent encore correspondre à la
        base : une modification concurrente impose de recharger le lot.
        """

        prepared = _normalise_batch(batch)
        batch_id = _validate_id(prepared.id, "L'identifiant du lot")

        with transaction(self.connection):
            current = self.get_batch(batch_id)
            if current is None:
                raise KeyError("Lot introuvable.")
            if prepared.product_id != current.product_id:
                raise ValueError("Le produit d'un lot existant ne peut pas être changé.")
            if prepared.quantity != current.quantity:
                raise ValueError(
                    "La quantité a changé. Rechargez le lot et utilisez un mouvement "
                    "ou un inventaire pour ajuster le stock."
                )
            if prepared.opened_date != current.opened_date:
                raise ValueError(
                    "La date d'ouverture a changé. Rechargez le lot ; "
                    "utilisez l'action Ouvrir pour enregistrer son ouverture."
                )
            cursor = self.connection.execute(
                """
                UPDATE batches
                SET unit_price_cents = ?, purchase_date = ?, expiry_date = ?,
                    supplier = ?, notes = ?
                WHERE id = ?
                """,
                (
                    prepared.unit_price_cents,
                    _date_to_iso(prepared.purchase_date),
                    None
                    if prepared.expiry_date is None
                    else _date_to_iso(prepared.expiry_date),
                    prepared.supplier,
                    prepared.notes,
                    batch_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError("Lot introuvable.")

        updated = self.get_batch(batch_id)
        if updated is None:
            raise RuntimeError("Le lot mis à jour est introuvable.")
        return updated

    def delete_batch(self, batch_id: int) -> None:
        """Supprime un lot sans mouvements associés."""

        validated_id = _validate_id(batch_id, "L'identifiant du lot")
        with transaction(self.connection):
            cursor = self.connection.execute(
                "DELETE FROM batches WHERE id = ?", (validated_id,)
            )
            if cursor.rowcount != 1:
                raise KeyError("Lot introuvable.")

    def record_movement(self, movement: StockMovement) -> StockMovement:
        """Enregistre un mouvement et ajuste la quantité atomiquement."""

        prepared = _normalise_movement(movement)
        if prepared.id is not None:
            raise ValueError(
                "Un nouveau mouvement ne doit pas avoir d'identifiant."
            )
        requested = _rounded_quantity_decimal(prepared.quantity)

        with transaction(self.connection):
            row = self.connection.execute(
                "SELECT quantity FROM batches WHERE id = ?",
                (prepared.batch_id,),
            ).fetchone()
            if row is None:
                raise KeyError("Lot introuvable.")

            available = _rounded_quantity_decimal(row["quantity"])
            if prepared.type in ("out", "loss"):
                if requested > available:
                    raise ValueError("Stock insuffisant pour ce mouvement.")
                new_quantity = available - requested
            else:
                new_quantity = available + requested
            new_quantity = new_quantity.quantize(
                QUANTITY_QUANTUM, rounding=ROUND_HALF_UP
            )

            self.connection.execute(
                "UPDATE batches SET quantity = ? WHERE id = ?",
                (float(new_quantity), prepared.batch_id),
            )
            cursor = self.connection.execute(
                """
                INSERT INTO stock_movements (
                    batch_id, type, quantity, date, reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    prepared.batch_id,
                    prepared.type,
                    prepared.quantity,
                    _date_to_iso(prepared.date),
                    prepared.reason,
                ),
            )
            movement_id = int(cursor.lastrowid)

        return replace(prepared, id=movement_id)

    def record_inventory(
        self,
        batch_id: int,
        actual_quantity: object,
        movement_date: date,
        reason: str,
    ) -> StockMovement:
        """Enregistre l'écart entre le stock théorique et le stock compté."""

        movements = self.record_inventories(
            [(batch_id, actual_quantity)], movement_date, reason
        )
        if not movements:
            raise ValueError("L'inventaire ne révèle aucun écart pour ce lot.")
        return movements[0]

    def record_inventories(
        self,
        counts: Sequence[Tuple[int, object]],
        movement_date: date,
        reason: str,
    ) -> List[StockMovement]:
        """Enregistre plusieurs écarts d'inventaire dans une seule transaction.

        Les quantités comptées peuvent être identiques au stock théorique : ces
        lignes sont simplement ignorées. Toute erreur sur une ligne annule
        l'ensemble du comptage.
        """

        validated_date = _validate_date(movement_date, "La date de l'inventaire")
        assert validated_date is not None
        if not isinstance(reason, str):
            raise TypeError("La raison de l'inventaire doit être une chaîne.")
        prepared_reason = reason.strip()
        if not prepared_reason:
            raise ValueError("La raison de l'inventaire est obligatoire.")

        prepared_counts = []
        seen_batch_ids = set()
        for batch_id, actual_quantity in counts:
            validated_batch_id = _validate_id(
                batch_id, "L'identifiant du lot"
            )
            if validated_batch_id in seen_batch_ids:
                raise ValueError("Un lot ne peut être compté qu'une seule fois.")
            seen_batch_ids.add(validated_batch_id)
            prepared_counts.append(
                (validated_batch_id, _rounded_quantity_decimal(actual_quantity))
            )

        movements = []
        with transaction(self.connection):
            for validated_batch_id, target_quantity in prepared_counts:
                row = self.connection.execute(
                    "SELECT quantity FROM batches WHERE id = ?",
                    (validated_batch_id,),
                ).fetchone()
                if row is None:
                    raise KeyError("Lot introuvable.")

                current_quantity = _rounded_quantity_decimal(row["quantity"])
                difference = target_quantity - current_quantity
                if difference == 0:
                    continue

                movement_type = "in" if difference > 0 else "loss"
                prepared = _normalise_movement(
                    StockMovement(
                        batch_id=validated_batch_id,
                        type=movement_type,
                        quantity=float(abs(difference)),
                        date=validated_date,
                        reason=prepared_reason,
                    )
                )
                self.connection.execute(
                    "UPDATE batches SET quantity = ? WHERE id = ?",
                    (float(target_quantity), validated_batch_id),
                )
                cursor = self.connection.execute(
                    """
                    INSERT INTO stock_movements (
                        batch_id, type, quantity, date, reason
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        prepared.batch_id,
                        prepared.type,
                        prepared.quantity,
                        _date_to_iso(prepared.date),
                        prepared.reason,
                    ),
                )
                movements.append(replace(prepared, id=int(cursor.lastrowid)))

        return movements

    def list_movements(
        self,
        batch_id: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[StockMovement]:
        """Retourne l'historique des mouvements, du plus récent au plus ancien."""

        parameters = []
        where_clause = ""
        if batch_id is not None:
            validated_batch_id = _validate_id(batch_id, "L'identifiant du lot")
            where_clause = "WHERE batch_id = ?"
            parameters.append(validated_batch_id)

        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                raise ValueError("La limite doit être un entier supérieur à zéro.")

        query = f"""
            SELECT * FROM stock_movements
            {where_clause}
            ORDER BY date DESC, id DESC
        """
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)

        rows = self.connection.execute(query, parameters).fetchall()
        return [_movement_from_row(row) for row in rows]

    def mark_batch_open(
        self, batch_id: int, opened_date: Optional[date] = None
    ) -> Batch:
        """Renseigne la première date d'ouverture d'un lot."""

        validated_id = _validate_id(batch_id, "L'identifiant du lot")
        requested_date = _validate_date(
            date.today() if opened_date is None else opened_date,
            "La date d'ouverture",
        )
        assert requested_date is not None

        with transaction(self.connection):
            row = self.connection.execute(
                """
                SELECT purchase_date, opened_date
                FROM batches
                WHERE id = ?
                """,
                (validated_id,),
            ).fetchone()
            if row is None:
                raise KeyError("Lot introuvable.")

            purchase_date = _parse_date(row["purchase_date"], "purchase_date")
            if requested_date < purchase_date:
                raise ValueError(
                    "La date d'ouverture ne peut pas précéder la date d'achat."
                )
            if row["opened_date"] is None:
                self.connection.execute(
                    "UPDATE batches SET opened_date = ? WHERE id = ?",
                    (_date_to_iso(requested_date), validated_id),
                )

        opened_batch = self.get_batch(validated_id)
        if opened_batch is None:
            raise RuntimeError("Le lot ouvert est introuvable.")
        return opened_batch
