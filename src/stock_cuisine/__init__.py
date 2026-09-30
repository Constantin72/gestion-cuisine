"""Application de gestion des stocks de cuisine."""

__version__ = "2.0.0"

from .application import (
    AlertBatch,
    AlertReport,
    Dashboard,
    ProductStock,
    StockApplication,
)
from .backup import backup_database
from .db import connect_database, initialize_database
from .export import csv_text, write_csv
from .models import (
    Batch,
    Category,
    Product,
    StockMovement,
    cents_to_euros,
    euros_to_cents,
)
from .repository import Repository
from .services import (
    StockService,
    calculate_effective_expiry,
    is_batch_expired,
)

__all__ = [
    "AlertBatch",
    "AlertReport",
    "Batch",
    "Category",
    "Dashboard",
    "Product",
    "ProductStock",
    "Repository",
    "StockApplication",
    "StockService",
    "StockMovement",
    "backup_database",
    "calculate_effective_expiry",
    "cents_to_euros",
    "connect_database",
    "csv_text",
    "euros_to_cents",
    "initialize_database",
    "is_batch_expired",
    "write_csv",
    "__version__",
]
