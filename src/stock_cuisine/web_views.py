"""Rendu HTML de l'interface web locale.

Le serveur HTTP ne contient volontairement que le routage et la lecture des
formulaires. Ce module regroupe la présentation afin qu'une évolution visuelle
ne touche pas les règles métier.
"""

from datetime import date
import html
from typing import List, Optional

from .application import AlertBatch, ProductStock, StockApplication
from .formatting import format_date, format_price, format_quantity, movement_label
from .models import Batch, Product, cents_to_euros
from .repository import Repository
from .services import batch_value_cents


STYLE = """
:root {
  color-scheme: light;
  --ink: #20302d;
  --muted: #6d7d79;
  --line: #dce8e3;
  --surface: #ffffff;
  --surface-soft: #f5faf7;
  --brand: #126b5c;
  --brand-dark: #0b4d42;
  --accent: #f2b84b;
  --danger: #a64135;
  --shadow: 0 12px 32px rgba(20, 61, 51, .08);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  color: var(--ink);
  background: #edf5f1;
}
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; }
a { color: var(--brand); }
.shell { min-height: 100vh; }
header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: linear-gradient(135deg, var(--brand-dark), var(--brand));
  color: white;
  padding: 1.25rem clamp(1rem, 4vw, 4rem) 1.1rem;
  box-shadow: 0 8px 22px rgba(11, 77, 66, .16);
}
.brand { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.brand-home { display: flex; align-items: center; gap: .8rem; color: white; text-decoration: none; }
.brand-home:hover .brand-mark { transform: rotate(-3deg) scale(1.04); }
.brand-mark { display: grid; place-items: center; width: 2.75rem; height: 2.75rem; border-radius: .85rem; background: var(--accent); color: var(--brand-dark); font-weight: 850; letter-spacing: -.08em; box-shadow: 0 5px 14px rgba(0, 0, 0, .12); }
.brand h1 { margin: 0; font-size: 1.55rem; letter-spacing: -.04em; }
.brand p { margin: .2rem 0 0; color: #d2eee5; font-size: .88rem; }
nav { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: 1.1rem; padding-top: .8rem; border-top: 1px solid rgba(255,255,255,.18); }
nav a { display: inline-flex; align-items: center; gap: .42rem; color: #e9fff7; text-decoration: none; padding: .52rem .75rem; border: 1px solid transparent; border-radius: .65rem; font-size: .92rem; font-weight: 650; white-space: nowrap; transition: background .15s ease, border-color .15s ease, transform .15s ease; }
nav a:hover, nav a:focus { background: rgba(255,255,255,.13); border-color: rgba(255,255,255,.18); transform: translateY(-1px); }
nav a.active { background: white; color: var(--brand-dark); box-shadow: 0 4px 12px rgba(0, 0, 0, .12); }
.nav-icon { width: 1.15rem; text-align: center; font-size: 1rem; }
main { max-width: 1320px; margin: 0 auto; padding: clamp(1.25rem, 4vw, 2.75rem) clamp(1rem, 4vw, 2.5rem) 3rem; }
.page-heading { display: flex; justify-content: space-between; align-items: end; gap: 1rem; margin-bottom: 1.35rem; }
.page-heading h2 { margin: 0; font-size: clamp(1.55rem, 3vw, 2.1rem); letter-spacing: -.04em; }
.page-heading p { margin: .35rem 0 0; color: var(--muted); }
.actions { display: flex; flex-wrap: wrap; gap: .5rem; }
.cards { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .9rem; margin-bottom: 1.4rem; }
.card, .panel, table { background: var(--surface); border: 1px solid var(--line); box-shadow: var(--shadow); }
.card { border-radius: .9rem; padding: 1.1rem 1.2rem; }
.card strong { display: block; color: var(--brand); font-size: 2rem; line-height: 1; }
.card span { display: block; margin-top: .55rem; color: var(--muted); font-size: .9rem; }
.columns { display: grid; grid-template-columns: minmax(260px, .8fr) minmax(0, 1.7fr); gap: 1rem; align-items: start; }
.columns.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.panel { border-radius: .9rem; padding: 1.15rem; }
.panel h3, .section-heading { margin: 0 0 .9rem; }
.section { margin-top: 1.6rem; }
.section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
.section-heading h3 { margin: 0; }
.section-heading a { font-size: .9rem; }
label { display: block; margin-top: .8rem; font-weight: 650; font-size: .92rem; }
input, select, textarea { width: 100%; padding: .68rem .72rem; margin-top: .3rem; border: 1px solid #bfd2ca; border-radius: .5rem; background: white; color: var(--ink); font: inherit; }
input:focus, select:focus, textarea:focus { outline: 3px solid rgba(18, 107, 92, .18); border-color: var(--brand); }
button, .button { display: inline-block; margin-top: 1rem; padding: .68rem .95rem; border: 0; border-radius: .5rem; background: var(--brand); color: white; cursor: pointer; font: inherit; font-weight: 650; text-decoration: none; }
button:hover, .button:hover { background: var(--brand-dark); }
button:disabled { opacity: .55; cursor: not-allowed; }
button.danger { background: var(--danger); }
button.danger:hover { background: #843128; }
.button.secondary, button.secondary { background: #e8f1ed; color: var(--brand-dark); }
.button.ghost { margin-top: 0; background: transparent; color: var(--brand); border: 1px solid var(--line); }
.table-action { padding: .42rem .65rem; font-size: .85rem; }
.filter { display: flex; flex-wrap: wrap; align-items: end; gap: .65rem; padding: .85rem; margin-bottom: 1rem; border-radius: .75rem; background: var(--surface-soft); border: 1px solid var(--line); }
.filter label { flex: 1 1 220px; margin: 0; }
.filter button { margin-top: 0; }
table { width: 100%; border-collapse: collapse; border-radius: .85rem; overflow: hidden; }
th, td { padding: .75rem .8rem; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { background: #e8f3ee; color: var(--brand-dark); font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
tr:last-child td { border-bottom: 0; }
.number { text-align: right; white-space: nowrap; }
.status { display: inline-flex; align-items: center; gap: .35rem; font-weight: 700; white-space: nowrap; }
.status::before { content: ""; width: .45rem; height: .45rem; border-radius: 50%; background: currentColor; }
.category-row th { background: #dceee7; font-size: .9rem; letter-spacing: 0; text-transform: none; }
.warning { color: var(--danger); }
.ok { color: #2a7c52; }
.muted { color: var(--muted); }
.notice, .error, .success { padding: .85rem 1rem; border-radius: .65rem; margin: 0 0 1rem; }
.notice { background: #fff8df; border: 1px solid #ead894; }
.error { background: #fff0ed; border: 1px solid #e5aaa1; color: #8d2c22; }
.success { background: #e7f7ed; border: 1px solid #abd9ba; color: #205d3d; }
.list { margin: 0; padding-left: 1.15rem; }
.list li + li { margin-top: .45rem; }
.inline { display: inline; }
.inline button { margin: 0 0 0 .4rem; padding: .42rem .65rem; font-size: .85rem; }
.empty { color: var(--muted); padding: 1.25rem; text-align: center; background: var(--surface-soft); border-radius: .7rem; }
footer { max-width: 1320px; margin: 0 auto; padding: 0 2.5rem 2rem; color: var(--muted); font-size: .85rem; }
@media (max-width: 1100px) { .cards { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 980px) { .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } .columns.three { grid-template-columns: 1fr; } }
@media (max-width: 720px) { header { padding-inline: 1rem; } .columns { grid-template-columns: 1fr; } .page-heading { align-items: start; flex-direction: column; } main { padding-inline: 1rem; } footer { padding-inline: 1rem; } table { display: block; overflow-x: auto; } nav { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: thin; } nav a { flex: 0 0 auto; } }
"""


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _page(
    title: str,
    content: str,
    message: Optional[str] = None,
    active_path: str = "/",
) -> str:
    flash = "" if message is None else f'<p class="success">{_escape(message)}</p>'
    navigation = (
        ("/", "⌂", "Tableau de bord"),
        ("/products", "🥕", "Produits"),
        ("/categories", "▦", "Catégories"),
        ("/batches", "📦", "Lots"),
        ("/movements", "↗", "Historique"),
        ("/alerts", "!", "Alertes"),
    )
    nav_links = []
    for href, icon, label in navigation:
        is_active = href == active_path or (
            href != "/" and active_path.startswith(href + "/")
        )
        class_name = "nav-link active" if is_active else "nav-link"
        current = ' aria-current="page"' if is_active else ""
        nav_links.append(
            f'<a class="{class_name}" href="{href}"{current}>'
            f'<span class="nav-icon" aria-hidden="true">{icon}</span>{label}</a>'
        )
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#126b5c">
  <title>{_escape(title)} — 4H</title>
  <style>{STYLE}</style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <a class="brand-home" href="/" aria-label="Accueil Cuisine 4H">
          <span class="brand-mark">4H</span>
          <span><h1>Cuisine 4H</h1><p>Le stock clair, même après le service.</p></span>
        </a>
        <span aria-hidden="true">🥕</span>
      </div>
      <nav aria-label="Navigation principale">
        {"".join(nav_links)}
      </nav>
    </header>
    <main>{flash}{content}</main>
    <footer>Cuisine 4H · données conservées localement dans SQLite</footer>
  </div>
</body>
</html>"""


def _heading(title: str, subtitle: str = "", actions: str = "") -> str:
    return (
        '<div class="page-heading">'
        f'<div><h2>{_escape(title)}</h2>'
        + (f'<p>{_escape(subtitle)}</p>' if subtitle else "")
        + "</div>"
        + (f'<div class="actions">{actions}</div>' if actions else "")
        + "</div>"
    )


def _products_table(
    lines: List[ProductStock],
    compact: bool = False,
    repository: Optional[Repository] = None,
) -> str:
    if not lines:
        return '<p class="empty">Aucun produit enregistré.</p>'
    product_ids_with_batches = set()
    if repository is not None:
        product_ids_with_batches = {
            batch.product_id for batch in repository.list_batches()
        }
    rows = []
    category_colspan = 4 + (0 if compact else 2)
    if repository is not None and not compact:
        category_colspan += 1
    last_category = None
    for line in lines:
        product = line.product
        if product.category != last_category:
            rows.append(
                '<tr class="category-row">'
                f'<th colspan="{category_colspan}">{_escape(product.category)}</th>'
                "</tr>"
            )
            last_category = product.category
        status = (
            '<span class="status warning">Sous seuil</span>'
            if line.below_minimum
            else '<span class="status ok">OK</span>'
        )
        action = ""
        if repository is not None and product.id is not None:
            action = (
                f'<a class="button ghost table-action" '
                f'href="/products/edit?product_id={_escape(product.id)}">Modifier</a>'
            )
            if product.id in product_ids_with_batches:
                action += ' <span class="muted">Lots associés</span>'
            else:
                action += (
                    '<form class="inline" method="post" action="/products/delete">'
                    f'<input type="hidden" name="product_id" value="{_escape(product.id)}">'
                    '<button class="danger" type="submit" '
                    'onclick="return confirm(\'Supprimer ce produit ?\')">'
                    'Supprimer</button></form>'
                )
        rows.append(
            "<tr>"
            f"<td>{_escape(product.id)}</td>"
            f"<td><strong>{_escape(product.name)}</strong><br><span class=\"muted\">{_escape(product.category)}</span></td>"
            f"<td class=\"number\">{_escape(format_quantity(line.quantity))} {_escape(product.unit)}</td>"
            f"<td class=\"number\">{_escape(format_price(line.value_cents))}</td>"
            + (f'<td class="number">{_escape(format_quantity(product.min_stock_threshold))}</td>' if not compact else "")
            + (f"<td>{status}</td>" if not compact else "")
            + (f"<td>{action}</td>" if repository is not None and not compact else "")
            + "</tr>"
        )
    headers = "<th>ID</th><th>Produit</th><th>Stock</th><th>Valeur</th>"
    if not compact:
        headers += "<th>Seuil</th><th>État</th>"
        if repository is not None:
            headers += "<th>Action</th>"
    return f'<table><thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def _product_form(repository: Repository) -> str:
    categories = repository.list_categories()
    if categories:
        options = (
            '<option value="" selected disabled>Choisir une catégorie</option>'
            + "".join(
                f'<option value="{_escape(category.name)}">'
                f'{_escape(category.name)}</option>'
                for category in categories
            )
        )
        category_field = (
            '<label>Catégorie <select name="category" required>'
            f'{options}</select></label>'
        )
        submit = '<button type="submit">Créer le produit</button>'
    else:
        category_field = (
            '<p class="notice">Ajoutez d’abord une catégorie depuis la page '
            '<a href="/categories">Catégories</a>.</p>'
            '<label>Catégorie <select name="category" required disabled>'
            '<option>Aucune catégorie disponible</option></select></label>'
        )
        submit = '<button type="submit" disabled>Créer le produit</button>'
    return f"""<form method="post" action="/products">
  <label>Nom <input name="name" autocomplete="off" required></label>
  <label>Unité <input name="unit" placeholder="kg, L, pièce" required></label>
  {category_field}
  <label>Seuil minimal <input name="minimum" type="number" min="0" step="0.001" required></label>
  <label>Durée après ouverture (jours) <input name="shelf_life" type="number" min="0" step="1"></label>
  {submit}
</form>"""


def _product_edit_form(repository: Repository, product: Product) -> str:
    """Construit le formulaire de modification d'un produit."""

    options = "".join(
        f'<option value="{_escape(category.name)}"'
        f'{" selected" if category.name.casefold() == product.category.casefold() else ""}>'
        f'{_escape(category.name)}</option>'
        for category in repository.list_categories()
    )
    shelf_life = (
        ""
        if product.shelf_life_after_opening_days is None
        else str(product.shelf_life_after_opening_days)
    )
    return f"""<form method="post" action="/products/edit">
  <input type="hidden" name="product_id" value="{_escape(product.id)}">
  <label>Nom <input name="name" value="{_escape(product.name)}" required></label>
  <label>Unité <input name="unit" value="{_escape(product.unit)}" required></label>
  <label>Catégorie <select name="category" required>{options}</select></label>
  <label>Seuil minimal <input name="minimum" type="number" min="0" step="0.001" value="{_escape(format_quantity(product.min_stock_threshold))}" required></label>
  <label>Durée après ouverture (jours) <input name="shelf_life" type="number" min="0" step="1" value="{_escape(shelf_life)}"></label>
  <div class="actions">
    <a class="button ghost" href="/products">Annuler</a>
    <button type="submit">Enregistrer les modifications</button>
  </div>
</form>"""


def product_edit_page(repository: Repository, product_id: int) -> str:
    """Affiche le formulaire de modification d'un produit."""

    product = repository.get_product(product_id)
    if product is None:
        raise KeyError("Produit introuvable.")
    content = _heading(
        "Modifier le produit",
        f"Produit #{product.id} · les mouvements et les lots sont conservés.",
        '<a class="button ghost" href="/products">Retour aux produits</a>',
    )
    content += f'<div class="panel edit-panel">{_product_edit_form(repository, product)}</div>'
    return content


def _batch_rows(
    repository: Repository,
    search: str = "",
    product_list: Optional[List[Product]] = None,
) -> str:
    products = {
        product.id: product
        for product in (
            repository.list_products() if product_list is None else product_list
        )
    }
    batches = repository.list_batches()
    needle = search.strip().casefold()
    if needle:
        batches = [
            batch
            for batch in batches
            if needle in str(batch.id)
            or needle in (products.get(batch.product_id).name.casefold() if products.get(batch.product_id) else "")
        ]
    if not batches:
        return '<p class="empty">Aucun lot correspondant.</p>'
    rows = []
    for batch in batches:
        product = products.get(batch.product_id)
        product_name = "?" if product is None else product.name
        action = (
            f'<a class="button ghost table-action" '
            f'href="/batches/edit?batch_id={_escape(batch.id)}">Modifier</a>'
            f' <a class="button secondary table-action" '
            f'href="/batches/inventory?batch_id={_escape(batch.id)}">Inventaire</a>'
        )
        if batch.opened_date is None:
            action += (
                '<form class="inline" method="post" action="/batches/open">'
                f'<input type="hidden" name="batch_id" value="{_escape(batch.id)}">'
                '<button class="secondary" type="submit">Ouvrir</button></form>'
            )
        rows.append(
            "<tr>"
            f"<td>{_escape(batch.id)}</td>"
            f"<td><strong>{_escape(product_name)}</strong><br><span class=\"muted\">Produit #{_escape(batch.product_id)}</span></td>"
            f"<td class=\"number\">{_escape(format_quantity(batch.quantity))}</td>"
            f"<td>{_escape(format_price(batch.unit_price_cents))}</td>"
            f"<td>{_escape(format_price(batch_value_cents(batch)))}</td>"
            f"<td>{_escape(format_date(batch.purchase_date))}</td>"
            f"<td>{_escape(format_date(batch.expiry_date))}</td>"
            f"<td>{_escape(format_date(batch.opened_date))} {action}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>ID</th><th>Produit</th><th>Stock</th>"
        "<th>Prix unitaire</th><th>Valeur</th><th>Achat</th><th>Expiration</th><th>Ouverture</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _batch_form(products: List[Product]) -> str:
    if not products:
        return '<p class="notice">Créez d’abord un produit avant d’ajouter un lot.</p>'
    options = "".join(
        f'<option value="{_escape(product.id)}">#{_escape(product.id)} {_escape(product.name)}</option>'
        for product in products
    )
    return f"""<form method="post" action="/batches">
  <label>Produit <select name="product_id" required>{options}</select></label>
  <label>Quantité <input name="quantity" type="number" min="0.001" step="0.001" required></label>
  <label>Prix unitaire (€) <input name="unit_price" type="number" min="0" step="0.01" required></label>
  <label>Date d’achat <input name="purchase_date" type="date" value="{date.today().isoformat()}" required></label>
  <label>Date d’expiration <input name="expiry_date" type="date"></label>
  <label>Fournisseur <input name="supplier"></label>
  <label>Notes <textarea name="notes" rows="3"></textarea></label>
  <button type="submit">Créer le lot</button>
</form>"""


def _batch_edit_form(repository: Repository, batch: Batch) -> str:
    """Construit le formulaire de modification d'un lot."""

    product = repository.get_product(batch.product_id)
    product_name = "?" if product is None else product.name
    supplier = "" if batch.supplier is None else batch.supplier
    notes = "" if batch.notes is None else batch.notes
    return f"""<form method="post" action="/batches/edit">
  <input type="hidden" name="batch_id" value="{_escape(batch.id)}">
  <p class="muted">Produit : <strong>{_escape(product_name)}</strong> · stock actuel : <strong>{_escape(format_quantity(batch.quantity))}</strong></p>
  <label>Prix unitaire (€) <input name="unit_price" type="number" min="0" step="0.01" value="{_escape(cents_to_euros(batch.unit_price_cents))}" required></label>
  <label>Date d’achat <input name="purchase_date" type="date" value="{_escape(batch.purchase_date.isoformat())}" required></label>
  <label>Date d’expiration <input name="expiry_date" type="date" value="{_escape("" if batch.expiry_date is None else batch.expiry_date.isoformat())}"></label>
  <label>Fournisseur <input name="supplier" value="{_escape(supplier)}"></label>
  <label>Notes <textarea name="notes" rows="4">{_escape(notes)}</textarea></label>
  <p class="notice">La quantité se modifie depuis l’historique des mouvements, afin de préserver les comptes.</p>
  <div class="actions">
    <a class="button ghost" href="/batches">Annuler</a>
    <button type="submit">Enregistrer les modifications</button>
  </div>
</form>"""


def batch_edit_page(repository: Repository, batch_id: int) -> str:
    """Affiche le formulaire de modification d'un lot."""

    batch = repository.get_batch(batch_id)
    if batch is None:
        raise KeyError("Lot introuvable.")
    content = _heading(
        "Modifier le lot",
        f"Lot #{batch.id} · les mouvements sont conservés.",
        '<a class="button ghost" href="/batches">Retour aux lots</a>',
    )
    content += f'<div class="panel edit-panel">{_batch_edit_form(repository, batch)}</div>'
    return content


def inventory_page(repository: Repository, batch_id: int) -> str:
    """Affiche le formulaire de comptage réel d'un lot."""

    batch = repository.get_batch(batch_id)
    if batch is None:
        raise KeyError("Lot introuvable.")
    product = repository.get_product(batch.product_id)
    product_name = "?" if product is None else product.name
    content = _heading(
        "Inventaire du lot",
        f"Lot #{batch.id} · {product_name}",
        '<a class="button ghost" href="/batches">Retour aux lots</a>',
    )
    content += f"""<div class="panel edit-panel">
  <p class="muted">Stock théorique actuel : <strong>{_escape(format_quantity(batch.quantity))}</strong>{f" {_escape(product.unit)}" if product is not None else ""}</p>
  <form method="post" action="/batches/inventory">
    <input type="hidden" name="batch_id" value="{_escape(batch.id)}">
    <label>Quantité réellement comptée <input name="actual_quantity" type="number" min="0" step="0.001" value="{_escape(format_quantity(batch.quantity))}" required></label>
    <label>Date de l'inventaire <input name="inventory_date" type="date" value="{date.today().isoformat()}" required></label>
    <label>Motif <input name="reason" value="Comptage inventaire" required></label>
    <p class="notice">L'écart sera enregistré automatiquement comme une entrée ou une perte, sans modifier l'historique existant.</p>
    <div class="actions">
      <a class="button ghost" href="/batches">Annuler</a>
      <button type="submit">Enregistrer l'inventaire</button>
    </div>
  </form>
</div>"""
    return content


def _movements_table(repository: Repository, batch_id: Optional[int] = None, limit: int = 100) -> str:
    movements = repository.list_movements(batch_id=batch_id, limit=limit)
    if not movements:
        return '<p class="empty">Aucun mouvement enregistré.</p>'
    batches = {batch.id: batch for batch in repository.list_batches()}
    products = {product.id: product for product in repository.list_products()}
    rows = []
    for movement in movements:
        batch = batches.get(movement.batch_id)
        product = None if batch is None else products.get(batch.product_id)
        rows.append(
            "<tr>"
            f"<td>{_escape(movement.id)}</td>"
            f"<td>{_escape(format_date(movement.date))}</td>"
            f"<td>#{_escape(movement.batch_id)}</td>"
            f"<td>{_escape('?' if product is None else product.name)}</td>"
            f"<td>{_escape(movement_label(movement.type))}</td>"
            f"<td class=\"number\">{_escape(format_quantity(movement.quantity))}</td>"
            f"<td>{_escape(movement.reason)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>ID</th><th>Date</th><th>Lot</th><th>Produit</th>"
        "<th>Type</th><th>Quantité</th><th>Motif</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _movement_form(repository: Repository) -> str:
    batches = repository.list_batches()
    if not batches:
        return '<p class="notice">Ajoutez d’abord un lot avant d’enregistrer un mouvement.</p>'
    products = {product.id: product for product in repository.list_products()}
    options = "".join(
        f'<option value="{_escape(batch.id)}">'
        f'#{_escape(batch.id)} — {_escape(products.get(batch.product_id).name if products.get(batch.product_id) else "?")} '
        f'({ _escape(format_quantity(batch.quantity)) } disponibles)</option>'
        for batch in batches
    )
    return f"""<form method="post" action="/movements">
  <label>Lot <select name="batch_id" required>{options}</select></label>
  <label>Type <select name="movement_type" required>
    <option value="out">Sortie</option>
    <option value="loss">Perte</option>
    <option value="in">Entrée complémentaire</option>
  </select></label>
  <label>Quantité <input name="quantity" type="number" min="0.001" step="0.001" required></label>
  <label>Date <input name="movement_date" type="date" value="{date.today().isoformat()}" required></label>
  <label>Motif <input name="reason" required></label>
  <button type="submit">Enregistrer le mouvement</button>
</form>"""


def _batch_alerts(items: List[AlertBatch], empty: str = "Aucun lot concerné.") -> str:
    if not items:
        return f'<p class="ok">{_escape(empty)}</p>'
    return "<ul class=\"list\">" + "".join(
        f"<li>Lot #{_escape(item.batch.id)} — <strong>{_escape(item.product.name)}</strong>, "
        f"stock {_escape(format_quantity(item.batch.quantity))} {_escape(item.product.unit)}, "
        f"date limite {_escape(format_date(item.effective_expiry))}</li>"
        for item in items
    ) + "</ul>"


def dashboard(repository: Repository) -> str:
    snapshot = StockApplication(repository).dashboard()
    actions = '<a class="button ghost" href="/export/stock.csv">Exporter le stock</a>'
    content = _heading(
        "Tableau de bord",
        f"Vue du {snapshot.reference_date.isoformat()} · les actions restent locales.",
        actions,
    )
    content += (
        '<div class="cards">'
        f'<div class="card"><strong>{_escape(len(snapshot.products))}</strong><span>produits suivis</span></div>'
        f'<div class="card"><strong>{_escape(snapshot.active_batches)}</strong><span>lots en stock</span></div>'
        f'<div class="card"><strong>{_escape(format_price(snapshot.total_value_cents))}</strong><span>valeur du stock</span></div>'
        f'<div class="card"><strong>{_escape(snapshot.below_minimum)}</strong><span>sous le seuil</span></div>'
        f'<div class="card"><strong>{_escape(snapshot.expired)}</strong><span>lots périmés</span></div>'
        '</div>'
    )
    content += '<section class="section"><div class="section-heading"><h3>État des produits</h3><a href="/products">Gérer les produits →</a></div>'
    content += _products_table(list(snapshot.products)) + '</section>'
    content += '<section class="section"><div class="section-heading"><h3>Derniers mouvements</h3><a href="/movements">Voir l’historique →</a></div>'
    content += _movements_table(repository, limit=10) + '</section>'
    active_batches = repository.list_batches_in_stock()
    if active_batches:
        rows = "".join(
            "<tr>"
            f"<td>#{_escape(batch.id)}</td>"
            f"<td>{_escape(format_quantity(batch.quantity))}</td>"
            f"<td>{_escape(format_date(batch.opened_date))}</td>"
            "</tr>"
            for batch in active_batches[:8]
        )
        content += '<section class="section"><div class="section-heading"><h3>Lots actifs</h3><a href="/batches">Voir tous les lots →</a></div>'
        content += f'<table><thead><tr><th>Lot</th><th>Stock</th><th>Ouvert le</th></tr></thead><tbody>{rows}</tbody></table></section>'
    content += '<section class="section columns">'
    content += f'<div class="panel"><h3>Nouveau produit</h3>{_product_form(repository)}</div>'
    content += f'<div class="panel"><h3>Enregistrer un mouvement</h3>{_movement_form(repository)}</div>'
    content += '</section>'
    return content


def products_page(repository: Repository, search: str = "") -> str:
    lines = StockApplication(repository).product_stock(search)
    form = f'<form class="filter" method="get" action="/products"><label>Rechercher <input name="q" value="{_escape(search)}" placeholder="Nom ou catégorie"></label><button type="submit">Filtrer</button></form>'
    content = _heading("Produits", "Les seuils permettent d’anticiper les achats.", '<a class="button ghost" href="/export/products.csv">Exporter CSV</a>')
    content += '<section class="columns"><div class="panel"><h3>Nouveau produit</h3>' + _product_form(repository) + '</div><div>' + form + _products_table(lines, repository=repository) + '</div></section>'
    return content


def categories_page(repository: Repository) -> str:
    """Affiche la liste des catégories et le formulaire d'ajout."""

    categories = repository.list_categories()
    product_counts = repository.count_products_by_category()
    content = _heading(
        "Catégories",
        "Créez les catégories utilisées dans les fiches produits.",
    )
    content += (
        '<section class="columns">'
        '<div class="panel"><h3>Nouvelle catégorie</h3>'
        '<form method="post" action="/categories">'
        '<label>Nom <input name="name" autocomplete="off" required></label>'
        '<button type="submit">Ajouter la catégorie</button>'
        '</form></div><div>'
    )
    if not categories:
        content += '<p class="empty">Aucune catégorie enregistrée.</p>'
    else:
        rows = "".join(
            "<tr>"
            f"<td>{_escape(category.id)}</td>"
            f"<td><strong>{_escape(category.name)}</strong></td>"
            f"<td>{_escape(product_counts.get(category.id, 0))} produit(s)</td>"
            "</tr>"
            for category in categories
        )
        content += (
            "<table><thead><tr><th>ID</th><th>Catégorie</th><th>Produits</th>"
            "</tr></thead><tbody>"
            f"{rows}</tbody></table>"
        )
    content += "</div></section>"
    return content


def batches_page(repository: Repository, search: str = "") -> str:
    content = _heading("Lots", "Suivez les dates limites et l’ouverture des produits.", '<a class="button ghost" href="/export/batches.csv">Exporter CSV</a>')
    filter_form = f'<form class="filter" method="get" action="/batches"><label>Rechercher <input name="q" value="{_escape(search)}" placeholder="Numéro ou produit"></label><button type="submit">Filtrer</button></form>'
    products = repository.list_products()
    content += '<section class="columns"><div class="panel"><h3>Nouveau lot</h3>' + _batch_form(products) + '</div><div>' + filter_form + _batch_rows(repository, search, products) + '</div></section>'
    return content


def movements_page(repository: Repository, batch_id: Optional[int], limit: int) -> str:
    options = ['<option value="">Tous les lots</option>']
    for batch in repository.list_batches():
        selected = " selected" if batch.id == batch_id else ""
        options.append(f'<option value="{_escape(batch.id)}"{selected}>Lot #{_escape(batch.id)}</option>')
    content = _heading("Historique des mouvements", "Chaque entrée, sortie et perte est conservée.", '<a class="button ghost" href="/export/movements.csv">Exporter CSV</a>')
    content += f'<form class="filter" method="get" action="/movements"><label>Lot <select name="batch_id">{"".join(options)}</select></label><label>Nombre de lignes <input name="limit" type="number" min="1" value="{_escape(limit)}"></label><button type="submit">Filtrer</button></form>'
    content += _movements_table(repository, batch_id=batch_id, limit=limit)
    return content


def alerts_page(repository: Repository, days: int = 7, reference_date: Optional[date] = None) -> str:
    report = StockApplication(repository).alerts(days=days, reference_date=reference_date)
    below = (
        '<ul class="list">' + "".join(
            f'<li>#{_escape(product.id)} <strong>{_escape(product.name)}</strong></li>'
            for product in report.below_minimum
        ) + '</ul>'
        if report.below_minimum else '<p class="ok">Aucun produit sous le seuil.</p>'
    )
    content = _heading("Alertes", f"Référence : {report.reference_date.isoformat()} · fenêtre de {report.days} jours.")
    content += '<div class="columns three">'
    content += f'<section class="panel"><h3>Sous le seuil</h3>{below}</section>'
    content += f'<section class="panel"><h3>Lots périmés</h3>{_batch_alerts(list(report.expired))}</section>'
    content += f'<section class="panel"><h3>Échéance prochaine</h3>{_batch_alerts(list(report.expiring))}</section>'
    content += '</div>'
    return content
