"""Connexion SQLite, schéma initial et migrations simples."""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
import sqlite3


CURRENT_SCHEMA_VERSION = 2

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        unit TEXT NOT NULL,
        category TEXT NOT NULL,
        category_id INTEGER NOT NULL,
        min_stock_threshold REAL NOT NULL
            CHECK (min_stock_threshold >= 0),
        shelf_life_after_opening_days INTEGER
            CHECK (
                shelf_life_after_opening_days IS NULL
                OR shelf_life_after_opening_days >= 0
            ),
        FOREIGN KEY (category_id)
            REFERENCES categories(id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS batches (
        id INTEGER PRIMARY KEY,
        product_id INTEGER NOT NULL,
        quantity REAL NOT NULL
            CHECK (quantity >= 0),
        unit_price_cents INTEGER NOT NULL
            CHECK (unit_price_cents >= 0),
        purchase_date TEXT NOT NULL,
        expiry_date TEXT,
        opened_date TEXT,
        supplier TEXT,
        notes TEXT,
        CHECK (expiry_date IS NULL OR expiry_date >= purchase_date),
        FOREIGN KEY (product_id)
            REFERENCES products(id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_movements (
        id INTEGER PRIMARY KEY,
        batch_id INTEGER NOT NULL,
        type TEXT NOT NULL
            CHECK (type IN ('in', 'out', 'loss')),
        quantity REAL NOT NULL
            CHECK (quantity > 0),
        date TEXT NOT NULL,
        reason TEXT NOT NULL,
        FOREIGN KEY (batch_id)
            REFERENCES batches(id)
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_batches_product_id
        ON batches(product_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_products_category_id
        ON products(category_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_stock_movements_batch_id
        ON stock_movements(batch_id)
    """,
)


# Ces index sont ajoutés séparément afin que les bases déjà en version 2 en
# bénéficient aussi, sans modifier la structure des tables ni forcer une
# migration de données.
ADDITIONAL_INDEX_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS idx_stock_movements_date_id
        ON stock_movements(date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_stock_movements_batch_date_id
        ON stock_movements(batch_id, date DESC, id DESC)
    """,
)


def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
    """Ajoute les catégories sans perdre les produits existants."""

    with transaction(connection):
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE
            )
            """
        )
        connection.execute(
            """
            ALTER TABLE products
            ADD COLUMN category_id INTEGER
                REFERENCES categories(id) ON DELETE RESTRICT
            """
        )

        category_ids: dict[str, int] = {}
        for existing in connection.execute(
            "SELECT id, name FROM categories ORDER BY id"
        ).fetchall():
            category_ids.setdefault(
                str(existing["name"]).strip().casefold(),
                int(existing["id"]),
            )
        products = connection.execute(
            "SELECT id, category FROM products ORDER BY id"
        ).fetchall()
        for product in products:
            category_name = str(product["category"]).strip() or "Sans catégorie"
            category_key = category_name.casefold()
            category_id = category_ids.get(category_key)
            if category_id is None:
                cursor = connection.execute(
                    "INSERT INTO categories (name) VALUES (?)",
                    (category_name,),
                )
                category_id = int(cursor.lastrowid)
            category_ids[category_key] = category_id
            connection.execute(
                """
                UPDATE products
                SET category = ?, category_id = ?
                WHERE id = ?
                """,
                (category_name, category_id, int(product["id"])),
            )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_products_category_id
                ON products(category_id)
            """
        )
        connection.execute("PRAGMA user_version = 2")


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Exécute un bloc dans une transaction d'écriture atomique."""

    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def initialize_database(connection: sqlite3.Connection) -> None:
    """Active les clés étrangères et applique les migrations connues."""

    connection.row_factory = sqlite3.Row
    connection.isolation_level = None
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    version_row = connection.execute("PRAGMA user_version").fetchone()
    version = int(version_row[0])

    if version > CURRENT_SCHEMA_VERSION:
        raise RuntimeError("Version de base de données non prise en charge.")

    if version == 0:
        with transaction(connection):
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(
                "PRAGMA user_version = {}".format(CURRENT_SCHEMA_VERSION)
            )
    elif version == 1:
        _migrate_v1_to_v2(connection)

    for statement in ADDITIONAL_INDEX_STATEMENTS:
        connection.execute(statement)


def connect_database(database: str = ":memory:") -> sqlite3.Connection:
    """Ouvre une base SQLite et initialise son schéma."""

    if database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, timeout=5)
    initialize_database(connection)
    return connection
