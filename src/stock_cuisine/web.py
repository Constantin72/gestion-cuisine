"""Serveur HTTP de Stock Cuisine, utilisable derrière un proxy HTTPS.

Le module est un adaptateur très léger : il ouvre une connexion par requête,
traduit les formulaires en objets métier et délègue le rendu à ``web_views``.
"""

from datetime import date
import base64
import binascii
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import hmac
import os
import re
import secrets
import socket
import sqlite3
from http.cookies import CookieError, SimpleCookie
from typing import Mapping, Optional, Sequence
from urllib.parse import parse_qs, urlencode, urlparse

from .application import StockApplication
from .db import connect_database
from .export import EXPORT_KINDS, csv_text
from .models import Batch, Category, Product, StockMovement, euros_to_cents
from .repository import Repository
from .web_views import (
    _page,
    alerts_page,
    batch_edit_page,
    batches_page,
    categories_page,
    dashboard,
    inventory_page,
    movements_page,
    product_edit_page,
    products_page,
)


MAX_FORM_BYTES = 64 * 1024


def _escape(value: object) -> str:
    """Compatibilité pour les intégrations qui importaient ce helper."""

    return html.escape(str(value), quote=True)


def _form_value(form: Mapping[str, Sequence[str]], name: str) -> str:
    value = form.get(name, ("",))[0].strip()
    if not value:
        raise ValueError(f"Le champ « {name} » est obligatoire.")
    return value


def _optional_form_value(
    form: Mapping[str, Sequence[str]], name: str
) -> Optional[str]:
    value = form.get(name, ("",))[0].strip()
    return value or None


def _decimal_form_value(form: Mapping[str, Sequence[str]], name: str) -> Decimal:
    value = _form_value(form, name)
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"Le champ « {name} » doit être numérique.") from None
    if not parsed.is_finite():
        raise ValueError(f"Le champ « {name} » doit être fini.")
    return parsed


def _integer_form_value(form: Mapping[str, Sequence[str]], name: str) -> int:
    value = _form_value(form, name)
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Le champ « {name} » doit être un entier.") from None


def _date_form_value(
    form: Mapping[str, Sequence[str]], name: str, optional: bool = False
) -> Optional[date]:
    value = _optional_form_value(form, name) if optional else _form_value(form, name)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Le champ « {name} » doit utiliser AAAA-MM-JJ.") from None


def _query_integer(
    query: str, name: str, default: Optional[int] = None
) -> Optional[int]:
    values = parse_qs(query).get(name, [])
    if not values or not values[0].strip():
        return default
    try:
        return int(values[0])
    except ValueError:
        raise ValueError(f"Le filtre « {name} » doit être un entier.") from None


def _query_date(query: str, name: str) -> Optional[date]:
    values = parse_qs(query).get(name, [])
    if not values or not values[0].strip():
        return None
    try:
        return date.fromisoformat(values[0])
    except ValueError:
        raise ValueError(f"Le filtre « {name} » doit utiliser AAAA-MM-JJ.") from None


class StockRequestHandler(BaseHTTPRequestHandler):
    """Traite les pages et formulaires de l'interface locale."""

    database_path = "stock.db"
    auth_user: Optional[str] = None
    auth_password: Optional[str] = None
    _csrf_form_pattern = re.compile(
        r'(<form\b[^>]*\bmethod="post"[^>]*>)'
    )

    def _send_unauthorized(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Stock Cuisine"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _is_authorized(self) -> bool:
        """Vérifie l'authentification HTTP Basic si elle est configurée."""

        if self.auth_user is None:
            return True

        header = self.headers.get("Authorization", "")
        scheme, separator, encoded = header.partition(" ")
        if scheme.lower() != "basic" or not separator:
            self._send_unauthorized()
            return False

        try:
            credentials = base64.b64decode(
                encoded.encode("ascii"), validate=True
            ).decode("utf-8")
        except (binascii.Error, UnicodeError, ValueError):
            self._send_unauthorized()
            return False

        username, separator, password = credentials.partition(":")
        configured_password = self.auth_password
        if (
            not separator
            or configured_password is None
            or not hmac.compare_digest(
                username.encode("utf-8"), self.auth_user.encode("utf-8")
            )
            or not hmac.compare_digest(
                password.encode("utf-8"), configured_password.encode("utf-8")
            )
        ):
            self._send_unauthorized()
            return False
        return True

    def _csrf_cookie(self) -> Optional[str]:
        if self.auth_user is None:
            return None
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return None
        morsel = cookies.get("stock_cuisine_csrf")
        return None if morsel is None else morsel.value

    def _csrf_token(self) -> Optional[str]:
        if self.auth_user is None:
            return None
        return self._csrf_cookie() or secrets.token_urlsafe(32)

    def _is_valid_csrf(self, form: Mapping[str, Sequence[str]]) -> bool:
        cookie_token = self._csrf_cookie()
        form_values = form.get("_csrf", ("",))
        form_token = form_values[0] if form_values else ""
        return bool(
            cookie_token
            and form_token
            and hmac.compare_digest(
                form_token.encode("utf-8"), cookie_token.encode("utf-8")
            )
        )

    def _send_html(self, content: str, status: int = 200) -> None:
        csrf_token = self._csrf_token()
        if csrf_token is not None:
            hidden_input = (
                f'<input type="hidden" name="_csrf" '
                f'value="{_escape(csrf_token)}">'
            )
            content = self._csrf_form_pattern.sub(
                rf"\1{hidden_input}", content
            )
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        if csrf_token is not None:
            cookie_attributes = "Path=/; HttpOnly; SameSite=Strict"
            if self.headers.get("X-Forwarded-Proto", "").lower() == "https":
                cookie_attributes += "; Secure"
            self.send_header(
                "Set-Cookie",
                "stock_cuisine_csrf={}; {}".format(
                    csrf_token, cookie_attributes
                ),
            )
        self.end_headers()
        self.wfile.write(data)

    def _send_csv(self, kind: str, repository: Repository) -> None:
        data = ("\ufeff" + csv_text(repository, kind)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header(
            "Content-Disposition", f'attachment; filename="stock-cuisine-{kind}.csv"'
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, message: str, target: str = "/") -> None:
        location = target + ("&" if "?" in target else "?") + urlencode({"message": message})
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _error(self, message: str, status: int = 400) -> None:
        content = _page(
            "Erreur",
            '<div class="page-heading"><div><h2>Impossible de traiter la demande</h2></div></div>'
            f'<p class="error">{_escape(message)}</p>'
            '<p><a class="button secondary" href="/">Retour au tableau de bord</a></p>',
        )
        self._send_html(content, status)

    def _open_repository(self) -> Repository:
        connection = connect_database(self.database_path)
        self._request_connection = connection
        return Repository(connection)

    def _close_repository(self) -> None:
        connection = getattr(self, "_request_connection", None)
        if connection is not None:
            connection.close()
            self._request_connection = None

    def do_GET(self) -> None:  # noqa: N802 - nom imposé par BaseHTTPRequestHandler
        if not self._is_authorized():
            return
        parsed = urlparse(self.path)
        message_values = parse_qs(parsed.query).get("message", [])
        message = message_values[0] if message_values else None
        try:
            repository = self._open_repository()
            if parsed.path.startswith("/export/") and parsed.path.endswith(".csv"):
                kind = parsed.path[len("/export/") : -len(".csv")]
                if kind not in EXPORT_KINDS:
                    self._error("Export introuvable.", 404)
                    return
                self._send_csv(kind, repository)
                return
            if parsed.path == "/":
                content = dashboard(repository)
                title = "Tableau de bord"
            elif parsed.path == "/products":
                search = parse_qs(parsed.query).get("q", [""])[0]
                content = products_page(repository, search)
                title = "Produits"
            elif parsed.path == "/products/edit":
                product_id = _query_integer(parsed.query, "product_id")
                if product_id is None:
                    raise ValueError("Le filtre « product_id » est obligatoire.")
                content = product_edit_page(repository, product_id)
                title = "Modifier un produit"
            elif parsed.path == "/categories":
                content = categories_page(repository)
                title = "Catégories"
            elif parsed.path == "/batches":
                search = parse_qs(parsed.query).get("q", [""])[0]
                content = batches_page(repository, search)
                title = "Lots"
            elif parsed.path == "/batches/edit":
                batch_id = _query_integer(parsed.query, "batch_id")
                if batch_id is None:
                    raise ValueError("Le filtre « batch_id » est obligatoire.")
                content = batch_edit_page(repository, batch_id)
                title = "Modifier un lot"
            elif parsed.path == "/batches/inventory":
                batch_id = _query_integer(parsed.query, "batch_id")
                if batch_id is None:
                    raise ValueError("Le filtre « batch_id » est obligatoire.")
                content = inventory_page(repository, batch_id)
                title = "Inventaire"
            elif parsed.path == "/movements":
                batch_id = _query_integer(parsed.query, "batch_id")
                limit = _query_integer(parsed.query, "limit", 100)
                assert limit is not None
                content = movements_page(repository, batch_id, limit)
                title = "Historique"
            elif parsed.path == "/alerts":
                days = _query_integer(parsed.query, "days", 7)
                assert days is not None
                content = alerts_page(repository, days, _query_date(parsed.query, "date"))
                title = "Alertes"
            else:
                self._error("Page introuvable.", 404)
                return
            self._send_html(_page(title, content, message, parsed.path))
        except (KeyError, TypeError, ValueError, sqlite3.Error) as error:
            self._error(str(error))
        finally:
            self._close_repository()

    def do_POST(self) -> None:  # noqa: N802 - nom imposé par BaseHTTPRequestHandler
        if not self._is_authorized():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._error("La requête est invalide.")
            return
        if length < 0:
            self._error("La taille de la requête est invalide.")
            return
        if length > MAX_FORM_BYTES:
            self._error("Le formulaire est trop volumineux (64 Kio maximum).", 413)
            return
        try:
            form = parse_qs(
                self.rfile.read(length).decode("utf-8"),
                keep_blank_values=True,
                max_num_fields=50,
            )
        except (UnicodeError, ValueError):
            self._error("Le formulaire est mal encodé ou contient trop de champs.")
            return
        path = urlparse(self.path).path
        try:
            if self.auth_user is not None and not self._is_valid_csrf(form):
                self._error("La requête de formulaire n'est pas valide.", 403)
                return
            application = StockApplication(self._open_repository())
            if path == "/products":
                shelf_life_value = _optional_form_value(form, "shelf_life")
                application.create_product(
                    Product(
                        name=_form_value(form, "name"),
                        unit=_form_value(form, "unit"),
                        category=_form_value(form, "category"),
                        min_stock_threshold=_decimal_form_value(form, "minimum"),
                        shelf_life_after_opening_days=(
                            None if shelf_life_value is None else int(shelf_life_value)
                        ),
                    )
                )
                self._redirect("Produit créé.")
            elif path == "/products/edit":
                shelf_life_value = _optional_form_value(form, "shelf_life")
                application.update_product(
                    Product(
                        id=_integer_form_value(form, "product_id"),
                        name=_form_value(form, "name"),
                        unit=_form_value(form, "unit"),
                        category=_form_value(form, "category"),
                        min_stock_threshold=_decimal_form_value(form, "minimum"),
                        shelf_life_after_opening_days=(
                            None if shelf_life_value is None else int(shelf_life_value)
                        ),
                    )
                )
                self._redirect("Produit modifié.", "/products")
            elif path == "/products/delete":
                application.delete_product(_integer_form_value(form, "product_id"))
                self._redirect("Produit supprimé.", "/products")
            elif path == "/categories":
                application.create_category(
                    Category(name=_form_value(form, "name"))
                )
                self._redirect("Catégorie créée.", "/categories")
            elif path == "/batches":
                purchase_date = _date_form_value(form, "purchase_date")
                if purchase_date is None:
                    raise ValueError("La date d'achat est obligatoire.")
                application.create_batch(
                    Batch(
                        product_id=_integer_form_value(form, "product_id"),
                        quantity=_decimal_form_value(form, "quantity"),
                        unit_price_cents=euros_to_cents(_form_value(form, "unit_price")),
                        purchase_date=purchase_date,
                        expiry_date=_date_form_value(form, "expiry_date", optional=True),
                        supplier=_optional_form_value(form, "supplier"),
                        notes=_optional_form_value(form, "notes"),
                    )
                )
                self._redirect("Lot créé.")
            elif path == "/batches/edit":
                batch_id = _integer_form_value(form, "batch_id")
                current_batch = application.repository.get_batch(batch_id)
                if current_batch is None:
                    raise KeyError("Lot introuvable.")
                purchase_date = _date_form_value(form, "purchase_date")
                if purchase_date is None:
                    raise ValueError("La date d'achat est obligatoire.")
                application.update_batch(
                    Batch(
                        id=current_batch.id,
                        product_id=current_batch.product_id,
                        quantity=current_batch.quantity,
                        unit_price_cents=euros_to_cents(_form_value(form, "unit_price")),
                        purchase_date=purchase_date,
                        expiry_date=_date_form_value(form, "expiry_date", optional=True),
                        opened_date=current_batch.opened_date,
                        supplier=_optional_form_value(form, "supplier"),
                        notes=_optional_form_value(form, "notes"),
                    )
                )
                self._redirect("Lot modifié.", "/batches")
            elif path == "/batches/inventory":
                inventory_date = _date_form_value(form, "inventory_date")
                if inventory_date is None:
                    raise ValueError("La date de l'inventaire est obligatoire.")
                application.record_inventory(
                    batch_id=_integer_form_value(form, "batch_id"),
                    actual_quantity=_decimal_form_value(form, "actual_quantity"),
                    inventory_date=inventory_date,
                    reason=_form_value(form, "reason"),
                )
                self._redirect("Inventaire enregistré.", "/batches")
            elif path == "/movements":
                movement_type = _form_value(form, "movement_type")
                movement_date = _date_form_value(form, "movement_date")
                if movement_date is None:
                    raise ValueError("La date du mouvement est obligatoire.")
                application.record_movement(
                    StockMovement(
                        batch_id=_integer_form_value(form, "batch_id"),
                        type=movement_type,
                        quantity=_decimal_form_value(form, "quantity"),
                        date=movement_date,
                        reason=_form_value(form, "reason"),
                    )
                )
                self._redirect("Mouvement enregistré.")
            elif path == "/batches/open":
                application.open_batch(_integer_form_value(form, "batch_id"))
                self._redirect("Lot ouvert.")
            else:
                self._error("Action introuvable.", 404)
        except (KeyError, TypeError, ValueError, sqlite3.Error) as error:
            self._error(str(error))
        finally:
            self._close_repository()


class StockHTTPServer(ThreadingHTTPServer):
    """Serveur réutilisable et adapté aux arrêts propres en local."""

    allow_reuse_address = True
    daemon_threads = True


class StockIPv6HTTPServer(StockHTTPServer):
    """Variante IPv6 utilisée par les hébergeurs comme Alwaysdata."""

    address_family = socket.AF_INET6


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    database: str = "stock.db",
    auth_user: Optional[str] = None,
    auth_password: Optional[str] = None,
) -> ThreadingHTTPServer:
    """Construit un serveur configuré pour une base donnée."""

    configured_user = (
        os.environ.get("STOCK_CUISINE_AUTH_USER")
        if auth_user is None
        else auth_user
    )
    configured_password = (
        os.environ.get("STOCK_CUISINE_AUTH_PASSWORD")
        if auth_password is None
        else auth_password
    )
    if (configured_user is None) != (configured_password is None):
        raise RuntimeError(
            "STOCK_CUISINE_AUTH_USER et STOCK_CUISINE_AUTH_PASSWORD "
            "doivent être définis ensemble."
        )
    if configured_user == "" or configured_password == "":
        raise RuntimeError("Les identifiants d'accès ne peuvent pas être vides.")
    if host not in {"127.0.0.1", "localhost", "::1"} and configured_user is None:
        raise RuntimeError(
            "Une authentification est obligatoire lorsque le serveur écoute "
            "sur une adresse publique."
        )

    class ConfiguredStockRequestHandler(StockRequestHandler):
        database_path = database
        auth_user = configured_user
        auth_password = configured_password

    server_class = StockIPv6HTTPServer if ":" in host else StockHTTPServer
    return server_class((host, port), ConfiguredStockRequestHandler)


def serve(
    database: str = "stock.db",
    host: str = "127.0.0.1",
    port: int = 8000,
    auth_user: Optional[str] = None,
    auth_password: Optional[str] = None,
) -> None:
    """Démarre le serveur web jusqu'à interruption clavier."""

    server = create_server(host, port, database, auth_user, auth_password)
    print(f"Interface web disponible sur http://{host}:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
    finally:
        server.server_close()
