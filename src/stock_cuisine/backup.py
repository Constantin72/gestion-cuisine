"""Sauvegarde cohérente d'une base SQLite."""

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Union


PathLike = Union[str, Path]


def backup_database(database: PathLike, destination: PathLike) -> Path:
    """Copie une base SQLite avec l'API ``backup`` prévue à cet effet."""

    source_path = Path(database)
    destination_path = Path(destination)
    if str(source_path) == ":memory:":
        raise ValueError("Une base en mémoire ne peut pas être sauvegardée par chemin.")
    if not source_path.is_file():
        raise FileNotFoundError(f"Base source introuvable : {source_path}")
    if source_path.resolve() == destination_path.resolve():
        raise ValueError("La destination de sauvegarde doit être différente de la base.")
    if destination_path.exists() and source_path.samefile(destination_path):
        raise ValueError("La destination de sauvegarde doit être différente de la base.")

    source_uri = source_path.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source:
        # Valide la source avant d'ouvrir une destination éventuellement existante.
        source.execute("PRAGMA schema_version").fetchone()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(destination_path))) as destination:
            source.backup(destination)
    return destination_path
