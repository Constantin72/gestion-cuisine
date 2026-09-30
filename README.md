# Cuisine 4H

Cuisine 4H est une application locale de gestion des stocks d’une cuisine
associative. Elle suit les produits, les lots, les entrées, les sorties, les
pertes, les ouvertures et les dates limites. Les données restent dans une base
SQLite locale, sans dépendance applicative externe.

## Démarrage

Depuis la racine `gestion_cuisine` :

```bash
python3 -m pip install -e .
stock-cuisine web
```

Ouvrir ensuite <http://127.0.0.1:8000/>. Sans installation, le mode développement
reste disponible avec `PYTHONPATH=src python3 -m stock_cuisine web`.

La base utilisée par défaut est `stock.db` dans le dossier courant. Un autre
fichier peut être choisi avant la commande :

```bash
stock-cuisine --database donnees/stock.db web --port 8080
```

Le dossier parent est créé automatiquement. Le fichier `stock.db` fourni dans
le projet est conservé comme donnée locale et n’est jamais réinitialisé par
l’application.

## Parcours quotidien

Créer un produit puis un premier lot :

```bash
stock-cuisine product add \
  --name "Lait" --unit L --category "Frais" \
  --minimum 2 --shelf-life 3

stock-cuisine batch add \
  --product-id 1 --quantity 10 --unit-price 1.25 \
  --purchase-date 2026-09-29 --expiry-date 2026-10-10 \
  --supplier "Fournisseur local"
```

Enregistrer une consommation ou une perte :

```bash
stock-cuisine movement add \
  --batch-id 1 --type out --quantity 1.5 --reason "Déjeuner"
```

Les types de mouvement sont `in`, `out` et `loss`. Une sortie supérieure au
stock disponible est refusée et chaque lot crée automatiquement son entrée
initiale.

Consulter l’état du stock et les alertes :

```bash
stock-cuisine stock list
stock-cuisine movement list --limit 20
stock-cuisine alerts --days 14
```

Pour supprimer un produit qui n'a encore aucun lot, ouvrir la page
« Produits », cliquer sur « Supprimer » puis confirmer. En ligne de commande :
`stock-cuisine product delete --product-id 3`.

Un produit auquel un lot est associé ne peut pas être supprimé, même si son
stock est épuisé : son historique est conservé.

Les catégories se gèrent depuis la page « Catégories ». Après avoir ajouté une
catégorie, elle apparaît dans le menu déroulant du formulaire de création d'un
produit.

Les boutons « Modifier » des pages Produits et Lots permettent de corriger les
informations sans effacer l'historique. La quantité d'un lot continue de se
modifier par les mouvements de stock.

La valeur du stock est calculée automatiquement pour chaque lot à partir de la
quantité restante et du prix unitaire, puis agrégée par produit et pour
l'inventaire total.

Depuis la page Lots, « Inventaire » permet de saisir la quantité réellement
comptée. L'écart est enregistré automatiquement comme une entrée ou une perte.

## Exports et sauvegardes

Les données peuvent être exportées en CSV (`products`, `stock`, `batches` ou
`movements`) et la base peut être copiée avec l’API de sauvegarde SQLite :

```bash
stock-cuisine export stock --output exports/stock.csv
stock-cuisine export movements --output exports/mouvements.csv
stock-cuisine backup --output sauvegardes/stock-2026-09-29.db
```

Les mêmes exports sont disponibles depuis les pages Produits, Lots et Tableau
de bord via les liens « Exporter CSV ».

## Accès depuis Internet

Le projet fournit un déploiement Docker Compose prêt à l’emploi avec stockage
SQLite persistant, authentification et terminaison HTTPS via Caddy. La
procédure complète se trouve dans [DEPLOYMENT.md](DEPLOYMENT.md).

Le mode local reste inchangé. Pour une mise en ligne, utiliser un serveur ou
un hébergeur Docker, un nom de domaine et un volume persistant pour `/data`.

## Règles métier

- Les quantités sont arrondies à trois décimales avec un arrondi décimal.
- Les prix sont conservés en centimes entiers.
- La valeur d'un lot est la quantité restante multipliée par son prix unitaire,
  arrondie au centime.
- Une date d’expiration ou d’ouverture ne peut pas précéder l’achat.
- Un lot reste valable le jour exact de sa date limite et expire le lendemain.
- Après ouverture, la durée de conservation du produit peut avancer la date limite.
- Les produits et lots associés à un historique ne peuvent pas être supprimés.
- Les écritures de stock et leur mouvement sont atomiques.

## Architecture

```text
gestion_cuisine/
├── pyproject.toml
├── README.md
├── ROADMAP.md
├── src/stock_cuisine/
│   ├── models.py          modèles et montants
│   ├── db.py              connexion, schéma et transactions SQLite
│   ├── repository.py      persistance et écritures atomiques
│   ├── services.py        règles de stock et dates limites
│   ├── application.py     cas d’usage partagés par les interfaces
│   ├── export.py          exports CSV
│   ├── backup.py          sauvegardes SQLite
│   ├── cli.py             commande stock-cuisine
│   ├── web.py             routage HTTP local
│   └── web_views.py       rendu de l’interface web
└── tests/
```

Les interfaces ne contiennent pas de SQL et les règles métier restent
testables sans serveur web.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

La suite couvre SQLite, les règles métier, la CLI, les exports et le parcours
HTTP principal.
