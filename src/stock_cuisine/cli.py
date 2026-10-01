"""Interface en ligne de commande pour la gestion du stock."""

import argparse
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation
import sqlite3
import sys
from typing import Callable, Iterable, Optional, Sequence

from . import __version__
from .application import AlertBatch, StockApplication
from .backup import backup_database
from .db import connect_database
from .export import EXPORT_KINDS, write_csv
from .formatting import (
    format_date as _format_date,
    format_price as _format_price,
    format_quantity as _format_quantity,
    movement_label,
)
from .models import Batch, Product, StockMovement, euros_to_cents
from .repository import Repository


CommandHandler = Callable[[Repository, argparse.Namespace], None]


def _date_argument(value: str) -> date:
    """Convertit un argument en date ISO."""

    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "la date doit être au format AAAA-MM-JJ"
        ) from None


def _decimal_argument(value: str) -> Decimal:
    """Convertit une quantité décimale fournie en argument."""

    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError("la quantité doit être numérique") from None
    if not parsed.is_finite():
        raise argparse.ArgumentTypeError("la quantité doit être finie")
    return parsed


def _print_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    """Affiche un tableau texte sans dépendance externe."""

    rendered_rows = [[str(value) for value in row] for row in rows]
    if not rendered_rows:
        print("Aucun résultat.")
        return

    widths = [len(header) for header in headers]
    for row in rendered_rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def render(row: Sequence[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    print(render(headers))
    print("  ".join("-" * width for width in widths))
    for row in rendered_rows:
        print(render(row))


def _product_name_by_id(repository: Repository) -> dict[int, str]:
    return {
        product.id: product.name
        for product in repository.list_products()
        if product.id is not None
    }


def _handle_product_add(repository: Repository, args: argparse.Namespace) -> None:
    product = StockApplication(repository).create_product(
        Product(
            name=args.name,
            unit=args.unit,
            category=args.category,
            min_stock_threshold=args.minimum,
            shelf_life_after_opening_days=args.shelf_life,
        )
    )
    print(f"Produit créé : #{product.id} {product.name}")


def _handle_product_list(repository: Repository, args: argparse.Namespace) -> None:
    products = repository.list_products()
    _print_table(
        ("ID", "Nom", "Unité", "Catégorie", "Seuil", "Après ouverture"),
        (
            (
                product.id,
                product.name,
                product.unit,
                product.category,
                _format_quantity(product.min_stock_threshold),
                "-"
                if product.shelf_life_after_opening_days is None
                else f"{product.shelf_life_after_opening_days} j",
            )
            for product in products
        ),
    )


def _handle_product_delete(repository: Repository, args: argparse.Namespace) -> None:
    product = repository.get_product(args.product_id)
    if product is None:
        raise KeyError("Produit introuvable.")
    StockApplication(repository).delete_product(product.id)
    print(f"Produit supprimé : #{product.id} {product.name}")


def _handle_batch_add(repository: Repository, args: argparse.Namespace) -> None:
    batch = StockApplication(repository).create_batch(
        Batch(
            product_id=args.product_id,
            quantity=args.quantity,
            unit_price_cents=euros_to_cents(args.unit_price),
            purchase_date=args.purchase_date or date.today(),
            expiry_date=args.expiry_date,
            supplier=args.supplier,
            notes=args.notes,
        )
    )
    print(f"Lot créé : #{batch.id} (produit #{batch.product_id})")


def _handle_batch_list(repository: Repository, args: argparse.Namespace) -> None:
    batches = (
        repository.list_batches()
        if args.product_id is None
        else repository.list_batches_for_product(args.product_id)
    )
    product_names = _product_name_by_id(repository)
    _print_table(
        ("ID", "Produit", "Quantité", "Prix unitaire", "Achat", "Expiration", "Ouvert"),
        (
            (
                batch.id,
                f"#{batch.product_id} {product_names.get(batch.product_id, '?')}",
                _format_quantity(batch.quantity),
                _format_price(batch.unit_price_cents),
                batch.purchase_date.isoformat(),
                _format_date(batch.expiry_date),
                _format_date(batch.opened_date),
            )
            for batch in batches
        ),
    )


def _handle_batch_open(repository: Repository, args: argparse.Namespace) -> None:
    batch = StockApplication(repository).open_batch(args.batch_id, args.opened_date)
    print(f"Lot #{batch.id} ouvert le {batch.opened_date.isoformat()}")


def _handle_movement_add(repository: Repository, args: argparse.Namespace) -> None:
    movement = StockApplication(repository).record_movement(
        StockMovement(
            batch_id=args.batch_id,
            type=args.movement_type,
            quantity=args.quantity,
            date=args.date or date.today(),
            reason=args.reason,
        )
    )
    batch = repository.get_batch(movement.batch_id)
    assert batch is not None
    print(
        f"Mouvement #{movement.id} enregistré ; "
        f"stock du lot #{batch.id} : {_format_quantity(batch.quantity)}"
    )


def _handle_movement_list(repository: Repository, args: argparse.Namespace) -> None:
    """Affiche l'historique des mouvements."""

    movements = repository.list_movements(
        batch_id=args.batch_id,
        limit=args.limit,
    )
    batches = {batch.id: batch for batch in repository.list_batches()}
    product_names = _product_name_by_id(repository)
    _print_table(
        ("ID", "Date", "Lot", "Produit", "Type", "Quantité", "Motif"),
        (
            (
                movement.id,
                movement.date.isoformat(),
                f"#{movement.batch_id}",
                product_names.get(
                    batches[movement.batch_id].product_id,
                    "?",
                ),
                movement_label(movement.type),
                _format_quantity(movement.quantity),
                movement.reason,
            )
            for movement in movements
        ),
    )


def _handle_stock_list(repository: Repository, args: argparse.Namespace) -> None:
    stock = StockApplication(repository).product_stock(only_in_stock=True)
    _print_table(
        ("ID", "Produit", "Stock", "Unité", "Valeur", "Seuil", "État"),
        (
            (
                line.product.id,
                line.product.name,
                _format_quantity(line.quantity),
                line.product.unit,
                _format_price(line.value_cents),
                _format_quantity(line.product.min_stock_threshold),
                "SOUS SEUIL" if line.below_minimum else "OK",
            )
            for line in stock
        ),
    )


def _handle_alerts(repository: Repository, args: argparse.Namespace) -> None:
    reference_date = args.date or date.today()
    report = StockApplication(repository).alerts(args.days, reference_date)

    print(f"Alertes au {reference_date.isoformat()}")
    print("\nProduits sous le seuil minimal :")
    if report.below_minimum:
        for product in report.below_minimum:
            print(f"- #{product.id} {product.name}")
    else:
        print("- aucune")

    def print_batches(title: str, batches: Iterable[AlertBatch]) -> None:
        print(f"\n{title} :")
        if not batches:
            print("- aucun")
            return
        for alert in batches:
            batch = alert.batch
            print(
                f"- lot #{batch.id} ({alert.product.name}), "
                f"stock {_format_quantity(batch.quantity)}, "
                f"date limite {_format_date(alert.effective_expiry)}"
            )

    print_batches("Lots périmés", report.expired)
    print_batches(
        f"Lots arrivant à échéance sous {report.days} jours", report.expiring
    )


def _handle_web(repository: Repository, args: argparse.Namespace) -> None:
    """Démarre l’interface web locale."""

    from .web import serve

    serve(args.database, args.host, args.port)


def _handle_export(repository: Repository, args: argparse.Namespace) -> None:
    """Exporte un jeu de données dans un fichier CSV."""

    path = write_csv(repository, args.kind, args.output)
    assert path is not None
    print(f"Export {args.kind} écrit dans {path}")


def _add_product_commands(subparsers: argparse._SubParsersAction) -> None:
    product_parser = subparsers.add_parser("product", help="gérer les produits")
    product_commands = product_parser.add_subparsers(dest="product_command", required=True)

    add_parser = product_commands.add_parser("add", help="ajouter un produit")
    add_parser.add_argument("--name", required=True, help="nom du produit")
    add_parser.add_argument("--unit", required=True, help="unité, par exemple kg ou L")
    add_parser.add_argument("--category", required=True, help="catégorie")
    add_parser.add_argument("--minimum", required=True, type=_decimal_argument, help="seuil minimal")
    add_parser.add_argument("--shelf-life", type=int, help="durée après ouverture, en jours")
    add_parser.set_defaults(handler=_handle_product_add)

    list_parser = product_commands.add_parser("list", help="lister les produits")
    list_parser.set_defaults(handler=_handle_product_list)

    delete_parser = product_commands.add_parser(
        "delete", help="supprimer un produit sans lot associé"
    )
    delete_parser.add_argument("--product-id", required=True, type=int)
    delete_parser.set_defaults(handler=_handle_product_delete)


def _add_batch_commands(subparsers: argparse._SubParsersAction) -> None:
    batch_parser = subparsers.add_parser("batch", help="gérer les lots")
    batch_commands = batch_parser.add_subparsers(dest="batch_command", required=True)

    add_parser = batch_commands.add_parser("add", help="ajouter un lot")
    add_parser.add_argument("--product-id", required=True, type=int)
    add_parser.add_argument("--quantity", required=True, type=_decimal_argument)
    add_parser.add_argument("--unit-price", required=True, help="prix unitaire en euros")
    add_parser.add_argument("--purchase-date", type=_date_argument)
    add_parser.add_argument("--expiry-date", type=_date_argument)
    add_parser.add_argument("--supplier")
    add_parser.add_argument("--notes")
    add_parser.set_defaults(handler=_handle_batch_add)

    list_parser = batch_commands.add_parser("list", help="lister les lots")
    list_parser.add_argument("--product-id", type=int)
    list_parser.set_defaults(handler=_handle_batch_list)

    open_parser = batch_commands.add_parser("open", help="marquer un lot comme ouvert")
    open_parser.add_argument("--batch-id", required=True, type=int)
    open_parser.add_argument("--date", dest="opened_date", type=_date_argument)
    open_parser.set_defaults(handler=_handle_batch_open)


def _add_movement_commands(subparsers: argparse._SubParsersAction) -> None:
    movement_parser = subparsers.add_parser("movement", help="enregistrer un mouvement")
    movement_commands = movement_parser.add_subparsers(
        dest="movement_command", required=True
    )

    add_parser = movement_commands.add_parser("add", help="ajouter un mouvement")
    add_parser.add_argument("--batch-id", required=True, type=int)
    add_parser.add_argument("--type", dest="movement_type", choices=("in", "out", "loss"), required=True)
    add_parser.add_argument("--quantity", required=True, type=_decimal_argument)
    add_parser.add_argument("--date", type=_date_argument)
    add_parser.add_argument("--reason", required=True)
    add_parser.set_defaults(handler=_handle_movement_add)

    list_parser = movement_commands.add_parser(
        "list", help="afficher l’historique des mouvements"
    )
    list_parser.add_argument("--batch-id", type=int)
    list_parser.add_argument("--limit", type=int, default=50)
    list_parser.set_defaults(handler=_handle_movement_list)


def build_parser() -> argparse.ArgumentParser:
    """Construit le parseur de commandes."""

    parser = argparse.ArgumentParser(
        prog="stock-cuisine",
        description="Gestion simple du stock de cuisine.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--database",
        default="stock.db",
        help="fichier SQLite à utiliser (défaut : stock.db)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_product_commands(subparsers)
    _add_batch_commands(subparsers)
    _add_movement_commands(subparsers)

    stock_parser = subparsers.add_parser("stock", help="consulter le stock")
    stock_commands = stock_parser.add_subparsers(dest="stock_command", required=True)
    list_parser = stock_commands.add_parser("list", help="afficher le stock total")
    list_parser.set_defaults(handler=_handle_stock_list)

    alerts_parser = subparsers.add_parser("alerts", help="afficher les alertes")
    alerts_parser.add_argument("--days", type=int, default=7)
    alerts_parser.add_argument("--date", type=_date_argument)
    alerts_parser.set_defaults(handler=_handle_alerts)

    web_parser = subparsers.add_parser("web", help="démarrer l’interface web locale")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8000)
    web_parser.set_defaults(handler=_handle_web)

    export_parser = subparsers.add_parser(
        "export", help="exporter les données au format CSV"
    )
    export_parser.add_argument("kind", choices=EXPORT_KINDS)
    export_parser.add_argument("--output", required=True, help="fichier CSV de sortie")
    export_parser.set_defaults(handler=_handle_export)

    backup_parser = subparsers.add_parser(
        "backup", help="sauvegarder la base SQLite"
    )
    backup_parser.add_argument("--output", required=True, help="fichier SQLite de sortie")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Exécute la CLI et retourne un code de sortie."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            path = backup_database(args.database, args.output)
            print(f"Sauvegarde écrite dans {path}")
            return 0
        handler: CommandHandler = args.handler
        with closing(connect_database(args.database)) as connection:
            handler(Repository(connection), args)
    except (KeyError, TypeError, ValueError, RuntimeError, OSError, sqlite3.Error) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
