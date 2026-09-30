"""Sauvegarde cohérente d'une base SQLite."""

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
    if source_path.resolve() == destination_path.resolve():
        raise ValueError("La destination de sauvegarde doit être différente de la base.")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(source_path))
    destination = sqlite3.connect(str(destination_path))
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()
    return destination_path
