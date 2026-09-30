"""Exports CSV reproductibles pour les sauvegardes et les usages associatifs."""

import csv
from io import StringIO
from pathlib import Path
from typing import IO, Optional, Union

from .application import StockApplication
from .formatting import format_date, format_quantity
from .repository import Repository


ExportTarget = Union[str, Path, IO[str]]
EXPORT_KINDS = ("products", "stock", "batches", "movements")


def _csv_rows(repository: Repository, kind: str):
    if kind not in EXPORT_KINDS:
        raise ValueError("Le type d'export est invalide.")

    if kind == "products":
        yield (
            "id",
            "nom",
            "unite",
            "categorie",
            "seuil_minimal",
            "duree_apres_ouverture_jours",
        )
        for product in repository.list_products():
            yield (
                product.id,
                product.name,
                product.unit,
                product.category,
                format_quantity(product.min_stock_threshold),
                ""
                if product.shelf_life_after_opening_days is None
                else product.shelf_life_after_opening_days,
            )
        return

    if kind == "stock":
        yield ("produit_id", "produit", "categorie", "stock", "unite", "seuil", "etat")
        for line in StockApplication(repository).product_stock():
            yield (
                line.product.id,
                line.product.name,
                line.product.category,
                format_quantity(line.quantity),
                line.product.unit,
                format_quantity(line.product.min_stock_threshold),
                "sous_seuil" if line.below_minimum else "ok",
            )
        return

    if kind == "batches":
        product_names = {
            product.id: product.name for product in repository.list_products()
        }
        yield (
            "id",
            "produit_id",
            "produit",
            "quantite",
            "prix_unitaire_centimes",
            "date_achat",
            "date_expiration",
            "date_ouverture",
            "fournisseur",
            "notes",
        )
        for batch in repository.list_batches():
            yield (
                batch.id,
                batch.product_id,
                product_names.get(batch.product_id, ""),
                format_quantity(batch.quantity),
                batch.unit_price_cents,
                format_date(batch.purchase_date),
                format_date(batch.expiry_date),
                format_date(batch.opened_date),
                batch.supplier or "",
                batch.notes or "",
            )
        return

    batches = {batch.id: batch for batch in repository.list_batches()}
    product_names = {product.id: product.name for product in repository.list_products()}
    yield (
        "id",
        "date",
        "lot_id",
        "produit_id",
        "produit",
        "type",
        "quantite",
        "motif",
    )
    for movement in repository.list_movements():
        batch = batches.get(movement.batch_id)
        product_id = "" if batch is None else batch.product_id
        yield (
            movement.id,
            format_date(movement.date),
            movement.batch_id,
            product_id,
            "" if batch is None else product_names.get(product_id, ""),
            movement.type,
            format_quantity(movement.quantity),
            movement.reason,
        )


def write_csv(repository: Repository, kind: str, target: ExportTarget) -> Optional[Path]:
    """Écrit un export CSV et retourne son chemin si la cible est un fichier."""

    close_target = isinstance(target, (str, Path))
    if close_target:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("w", encoding="utf-8-sig", newline="")
    else:
        path = None
        stream = target

    try:
        writer = csv.writer(stream)
        writer.writerows(_csv_rows(repository, kind))
    finally:
        if close_target:
            stream.close()
    return path


def csv_text(repository: Repository, kind: str) -> str:
    """Retourne le CSV en mémoire, pratique pour l'interface HTTP."""

    stream = StringIO(newline="")
    write_csv(repository, kind, stream)
    return stream.getvalue()
