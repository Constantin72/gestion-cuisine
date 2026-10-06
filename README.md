# Cuisine 4H

Application de gestion des stocks d'une cuisine associative : catégories, produits,
lots, mouvements, inventaires, dates limites et valeur du stock. Elle fonctionne
sur un ordinateur ou sur un hébergeur, avec une interface web et une commande de
maintenance. SQLite conserve les données sur la machine qui exécute l'application.

Python 3.9 ou supérieur est requis. L'application utilise uniquement la bibliothèque
standard ; l'installation du paquet utilise setuptools.

## Repères rapides

| Besoin | Où agir | Référence |
| --- | --- | --- |
| Tester ou utiliser l'application localement | Terminal de l'ordinateur | [Démarrer localement](#démarrer-sur-son-ordinateur) |
| Publier une modification de code | Terminal de l'ordinateur puis GitHub | [Publier une modification](#publier-une-modification) |
| Mettre à jour le site partagé | Terminal SSH Alwaysdata puis panneau web | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Sauvegarder ou restaurer les données | Terminal de la machine qui héberge SQLite | [Sauvegarder et restaurer](#sauvegarder-et-restaurer) |

Les commandes ci-dessous sont à lancer depuis la racine du projet, sauf mention
contraire. Les commandes locales utilisent `python3` et `.venv/bin/python` ;
Alwaysdata utilise `python` dans la configuration de son site.

## Démarrer sur son ordinateur

### Première installation

Dans un terminal :

```bash
cd /chemin/vers/gestion-cuisine
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
```

Puis démarrer l'interface :

```bash
./.venv/bin/python -m stock_cuisine \
  --database donnees/stock.db web
```

Ouvrir <http://127.0.0.1:8000/>. La commande doit rester active ; `Ctrl+C` arrête
le serveur.

### Démarrages suivants

```bash
cd /chemin/vers/gestion-cuisine
./.venv/bin/python -m stock_cuisine \
  --database donnees/stock.db web
```

Sans installation du paquet, le lancement équivalent est :

```bash
PYTHONPATH=src python3 -m stock_cuisine \
  --database donnees/stock.db web
```

Le dossier et la base sont créés au premier démarrage s'ils n'existent pas.
Conserver les bases de travail hors de Git. `stock.db` et `donnees/stock.db`
sont deux fichiers distincts : choisir un chemin et le conserver.
Les chemins relatifs partent du dossier courant. L'option `--database` se place
avant la sous-commande ; sans elle, le programme utilise `stock.db`.

### Vérifier l'installation

Depuis la racine du projet :

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
git diff --check
```

Le serveur local doit ensuite permettre de créer un produit, un lot, un
mouvement et un inventaire global depuis **Inventaire**. Pour arrêter le
serveur, utiliser `Ctrl+C` dans le terminal qui l'exécute.

Pour une instance partagée hébergée, suivre [DEPLOYMENT.md](DEPLOYMENT.md).
Les collaborateurs utilisent leur navigateur sans compte GitHub. GitHub distribue
le code ; l'hébergeur exécute le serveur et conserve la base partagée.

## Utiliser le stock

1. Dans **Catégories**, créer les familles de produits.
2. Dans **Produits**, saisir le nom, l'unité (`kg`, `L`, `pièce`), le seuil minimal
   et éventuellement la durée de conservation après ouverture.
3. Dans **Lots**, ajouter quantité, prix unitaire, dates et fournisseur. Le menu
   des produits et la liste des lots sont classés par catégorie puis nom.
4. Depuis le **Tableau de bord**, enregistrer une entrée, une sortie ou une perte.
5. Dans **Inventaire**, saisir les quantités réellement comptées pour les lots
   concernés, puis enregistrer le comptage en une seule fois. La page **Lots**
   conserve aussi l'action d'inventaire individuel pour une correction ponctuelle.
6. Consulter **Historique** et **Alertes** pour suivre changements et échéances.

La page **Inventaire** regroupe les lots actifs par catégorie et produit. Le
stock théorique sert de repère, tandis qu'une ligne laissée vide n'est pas
enregistrée. Chaque écart est ajouté à l'historique comme une entrée ou une
perte ; l'enregistrement du comptage est atomique.

Le prix d'un lot est le prix **par unité du produit**, pas le total de l'achat.
Ainsi, 3 kg à 2,50 €/kg valent 7,50 €. Après une sortie de 1 kg, la valeur restante
est 5 €. Chaque lot garde son propre prix ; les valeurs sont additionnées par
produit et pour l'ensemble du stock.

**Modifier** corrige les informations d'un produit ou d'un lot. Le produit associé
à un lot est fixe. La quantité se change par mouvement ou inventaire, avec une
trace dans l'historique. Quand sa quantité totale atteint zéro, le produit
n'apparaît plus dans les vues de stock ni dans le tableau des produits ; il reste
conservé dans l'historique et les alertes. Un produit n'est supprimable que s'il
n'a aucun lot, y compris épuisé. L'accès hébergé utilise un identifiant partagé :
il n'y a pas encore de rôles ni d'attribution des mouvements à une personne.

## Commandes utiles

Tous les exemples utilisent `donnees/stock.db` depuis la racine du projet.
Après installation, `./.venv/bin/stock-cuisine` peut remplacer
`./.venv/bin/python -m stock_cuisine`.

```bash
./.venv/bin/python -m stock_cuisine --database donnees/stock.db product add \
  --name "Lait" --unit L --category "Frais" --minimum 2 --shelf-life 3
./.venv/bin/python -m stock_cuisine --database donnees/stock.db product list
```

Reprendre l'identifiant affiché à la création du produit pour ajouter le lot,
puis l'identifiant du lot pour enregistrer un mouvement :

```bash
./.venv/bin/python -m stock_cuisine --database donnees/stock.db batch add \
  --product-id 1 --quantity 10 --unit-price 1.25
./.venv/bin/python -m stock_cuisine --database donnees/stock.db movement add \
  --batch-id 1 --type out --quantity 1.5 --reason "Déjeuner"
./.venv/bin/python -m stock_cuisine --database donnees/stock.db stock list
./.venv/bin/python -m stock_cuisine --database donnees/stock.db alerts --days 14
```

Les dates explicites utilisent `AAAA-MM-JJ`. Les types de mouvement sont `in`
(entrée), `out` (sortie), `loss` (perte). Consulter `--help` pour les options de
chaque commande. La modification et l'inventaire sont disponibles dans le web.

## Exporter et sauvegarder

```bash
./.venv/bin/python -m stock_cuisine --database donnees/stock.db export stock \
  --output exports/stock.csv
./.venv/bin/python -m stock_cuisine --database donnees/stock.db backup \
  --output sauvegardes/stock-2026-10-01.db
```

Les exports `products`, `stock`, `batches` et `movements` sont des CSV UTF-8
séparés par des virgules. Les montants sont en centimes ; les quantités utilisent
le point décimal. Des liens d'export existent aussi dans l'interface.

Le CSV ne remplace pas une sauvegarde. `backup` produit une copie SQLite
cohérente même lorsque le serveur fonctionne. La commande refuse une source
absente et une destination identique à la source. Une destination existante
peut être remplacée : choisir un nom daté et conserver une copie hors du serveur.
Voir [DEPLOYMENT.md](DEPLOYMENT.md) pour l'exploitation et la restauration.

## Règles et architecture

- Quantités arrondies à trois décimales ; prix en centimes entiers.
- Valeur d'un lot arrondie au centime après multiplication quantité × prix unitaire.
- Stock négatif interdit ; création d'un lot et entrée initiale atomiques.
- Inventaire enregistré comme entrée ou perte correspondant à l'écart constaté.
- Expiration et ouverture ne peuvent pas précéder l'achat.
- Un lot expire le lendemain de sa date limite ; la conservation après ouverture
  peut avancer cette date. Les alertes ignorent les lots épuisés.

| Module | Responsabilité |
| --- | --- |
| `models.py` | Objets métier et conversions monétaires |
| `db.py` | Connexions, transactions et migration SQLite |
| `repository.py` | Validation avant écriture, persistance et historique atomique |
| `services.py` | Calculs communs de stock, valeur et péremption |
| `application.py` | Composition des vues et actions partagées |
| `formatting.py` | Formats d'affichage et tri des produits |
| `cli.py` | Commande terminal et maintenance |
| `web.py`, `web_views.py` | HTTP, authentification, formulaires et rendu |
| `export.py`, `backup.py` | CSV et sauvegarde SQLite |

## Développer et vérifier

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
git diff --check
```

Les tests utilisent des bases en mémoire ou temporaires ; les tests HTTP ouvrent
des ports locaux temporaires. Les conventions sont : indentation de quatre
espaces, noms Python en anglais et `snake_case`, annotations de types, messages
et documentation en français. Les règles communes se placent dans les services
ou le repository, et non dans les formulaires.

Voir [ROADMAP.md](ROADMAP.md) pour les évolutions restantes.

## Publier une modification

Cette procédure se fait sur l'ordinateur de développement, pas dans le terminal
SSH du serveur :

```bash
cd /chemin/vers/gestion-cuisine
git status
PYTHONPATH=src python3 -m unittest discover -s tests -v
git diff --check
git add -A
git diff --cached --check
git status --short
git commit -m "Décrire la modification"
git push origin main
```

Avant `git commit`, vérifier que la liste des fichiers ne contient ni base
SQLite, ni `.env`, ni secret. Si `git push` signale un problème d'identification,
configurer l'accès GitHub sur l'ordinateur ; ne jamais inscrire un jeton dans un
fichier du projet.

Après le `git push`, la mise à jour d'Alwaysdata se fait séparément avec la
sauvegarde préalable et `git pull --ff-only` décrits dans [DEPLOYMENT.md](DEPLOYMENT.md).

## Sauvegarder et restaurer

Créer une sauvegarde cohérente avec l'application, même si le serveur utilise
SQLite en mode WAL :

```bash
./.venv/bin/python -m stock_cuisine \
  --database donnees/stock.db backup \
  --output sauvegardes/stock-2026-10-06.db
```

Vérifier qu'elle existe et la conserver hors de la machine qui héberge le stock.
Pour contrôler une copie avant restauration, le résultat attendu est `ok` :

```bash
./.venv/bin/python -c 'import sqlite3; print(sqlite3.connect("sauvegardes/stock-2026-10-06.db").execute("PRAGMA integrity_check").fetchone()[0])'
```

Ne pas remplacer une base active sans :

1. arrêter le site ;
2. sauvegarder l'état actuel ;
3. vérifier la copie avec `PRAGMA integrity_check` ;
4. rétablir les droits d'écriture du dossier et de la base ;
5. redémarrer puis contrôler le stock et l'historique.

La sauvegarde n'est pas automatique. La fréquence doit correspondre à la perte
de données que l'association pourrait accepter.
