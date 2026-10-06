# Hébergement et maintenance

Cette page distingue le terminal local, le terminal SSH Alwaysdata et le panneau
d'administration web. Le code se met à jour par Git, mais la base SQLite reste
sur l'hébergeur. **Ne jamais envoyer `stock.db` dans Git et ne jamais remplacer
la base de production lors d'une simple mise à jour du code.**

Les noms en majuscules sont des placeholders à remplacer :

- `UTILISATEUR_SSH` : utilisateur SSH créé dans Alwaysdata ;
- `NOM_DU_COMPTE` : nom du compte Alwaysdata, utilisé dans `/home/...` ;
- `$IP` et `$PORT` : variables à conserver telles quelles dans la commande du site.

## Alwaysdata

### 1. Publier le code depuis l'ordinateur local

Dans le terminal local, depuis la racine du projet :

```bash
git status
PYTHONPATH=src python3 -m unittest discover -s tests -v
git diff --check
git add -A
git diff --cached --check
git status --short
git commit -m "Décrire la modification"
git push origin main
```

Si les tests échouent, arrêter la procédure et corriger avant de pousser. Le
serveur ne doit recevoir que le code ; la base et les secrets restent ailleurs.

### 2. Préparer le code en SSH

Reprendre le nom d'utilisateur et l'hôte indiqués dans **Remote access →
SSH/SFTP**. `UTILISATEUR_SSH` est le compte de connexion ; `NOM_DU_COMPTE`
est le compte d'hébergement et son dossier `/home/NOM_DU_COMPTE`. Ils peuvent
différer. Voir aussi la documentation officielle [SSH/SFTP
Alwaysdata](https://help.alwaysdata.com/en/docs/web-hosting/remote-access/ssh/).

```bash
ssh UTILISATEUR_SSH@ssh-NOM_DU_COMPTE.alwaysdata.net
```

À exécuter ensuite dans le terminal SSH, uniquement lors du premier déploiement :

```bash
git clone https://github.com/Constantin72/gestion-cuisine.git ~/gestion-cuisine
cd ~/gestion-cuisine
mkdir -p donnees sauvegardes
```

Si le dossier existe déjà, ne pas le cloner une seconde fois :

```bash
cd ~/gestion-cuisine
git remote -v
git status --short
mkdir -p donnees sauvegardes
```

Si `git status` affiche des modifications sur le serveur, s'arrêter et les
examiner. La sortie doit être vide avant de continuer. Ne pas utiliser
`git reset --hard` pour débloquer la mise à jour. Une fois le dépôt propre :

```bash
git pull --ff-only
```

### 3. Configurer le site

Dans **Web → Sites**, ajouter ou modifier le site. Remplacer `NOM_DU_COMPTE`
dans les chemins et dans l'adresse.

| Champ | Valeur |
| --- | --- |
| Adresse | `NOM_DU_COMPTE.alwaysdata.net` ou le domaine configuré |
| Type | Programme utilisateur / User program |
| Répertoire de travail | `/home/NOM_DU_COMPTE/gestion-cuisine` |

Commande à saisir sur une seule ligne :

```bash
python -m stock_cuisine --database /home/NOM_DU_COMPTE/gestion-cuisine/donnees/stock.db web --host $IP --port $PORT
```

Conserver littéralement `$IP` et `$PORT` : Alwaysdata les remplace au démarrage.
Le projet demande Python 3.9 ou supérieur ; sélectionner une version compatible
dans **Environment** si le compte en propose plusieurs.
Dans **Environnement**, une variable par ligne, sans espaces autour de `=` :

```dotenv
PYTHONPATH=/home/NOM_DU_COMPTE/gestion-cuisine/src
STOCK_CUISINE_AUTH_USER=equipe
STOCK_CUISINE_AUTH_PASSWORD=REMPLACER_PAR_UN_SECRET_LONG_ET_UNIQUE
```

L'application ne lit pas automatiquement un fichier `.env` sur Alwaysdata.
Renseigner les variables dans la configuration du site, activer HTTPS, puis
redémarrer le site. Tester en navigation privée : une demande d'identification
HTTP Basic doit apparaître.

Documentation officielle : [ajouter un site](https://help.alwaysdata.com/en/docs/web-hosting/sites/add-a-site/),
[programme utilisateur](https://help.alwaysdata.com/en/docs/web-hosting/sites/http-servers/user-program/)
et [configuration Python](https://help.alwaysdata.com/en/docs/web-hosting/languages/python/configuration/).

### 4. Importer un stock existant au premier déploiement

Sur l'ordinateur qui possède la base, depuis la racine du projet :

```bash
./.venv/bin/python -m stock_cuisine \
  --database donnees/stock.db backup \
  --output sauvegardes/transfert-2026-10-06.db
scp sauvegardes/transfert-2026-10-06.db \
  UTILISATEUR_SSH@ssh-NOM_DU_COMPTE.alwaysdata.net:~/gestion-cuisine/donnees/transfert.db
```

Sur le serveur, vérifier les deux fichiers avant toute opération :

```bash
cd ~/gestion-cuisine
ls -lh donnees/
```

Si `donnees/stock.db` n'existe pas encore, installer la copie :

```bash
mv donnees/transfert.db donnees/stock.db
```

Si `donnees/stock.db` existe déjà, ne pas exécuter `mv` : il s'agit d'une
restauration et il faut d'abord arrêter le site et sauvegarder la base existante.

Le processus web doit pouvoir écrire dans la base **et** dans son dossier,
où SQLite crée ses journaux. Lorsque SSH et le web partagent le groupe du
compte, les droits suivants conviennent :

```bash
chmod 770 ~/gestion-cuisine/donnees
chmod 660 ~/gestion-cuisine/donnees/stock.db
```

### 5. Publier une mise à jour

Après avoir validé et poussé le code sur GitHub, dans le terminal SSH :

```bash
cd ~/gestion-cuisine
PYTHONPATH=src python -m stock_cuisine --database donnees/stock.db backup \
  --output sauvegardes/avant-mise-a-jour-2026-10-06.db
git status --short
```

Remplacer la date dans le nom de sauvegarde pour chaque mise à jour. La sortie
de `git status --short` doit être vide ; ensuite seulement exécuter :

```bash
git pull --ff-only
```

Si `git pull --ff-only` refuse d'avancer, ne pas forcer : vérifier les
modifications locales du serveur avant de recommencer.

Redémarrer ensuite le site dans l'administration Alwaysdata et vérifier :

1. l'ouverture en HTTPS et la demande d'identification ;
2. le tableau de bord et le nombre de produits ;
3. le stock d'un produit connu ;
4. **Inventaire**, **Alertes** et **Historique**.

La fermeture du terminal SSH n'arrête pas le site géré par l'hébergeur.
Garder les identifiants hors de Git et des captures de logs partagées.

### Résoudre les erreurs courantes

| Message ou symptôme | Vérification |
| --- | --- |
| `No module named stock_cuisine` | Depuis `~/gestion-cuisine`, utiliser `PYTHONPATH=src python ...` en SSH et le chemin absolu dans l'environnement du site |
| `python: command not found` | Sélectionner une version Python dans l'environnement Alwaysdata ; la commande du site est `python`, pas `python3` |
| `attempt to write a readonly database` | Droits de la base, du dossier et des éventuels fichiers `-wal` / `-shm` |
| Mauvais stock ou base vide | Chemin absolu de `--database` et emplacement de la copie transférée |
| Changement de code invisible | `git pull --ff-only` sur le serveur puis site redémarré |
| Pas de nouvelle demande de mot de passe | Navigation privée : le navigateur peut mémoriser HTTP Basic |

Les logs sont accessibles dans l'administration et sous
`/home/NOM_DU_COMPTE/admin/logs/sites/`.

## Alternative : Docker Compose et Caddy

Cette option nécessite un serveur avec Docker Compose, un domaine pointant
vers lui et les ports TCP 80/443 accessibles. Python reste dans le réseau
Docker ; Caddy reçoit les connexions HTTPS.

```bash
cp .env.example .env
```

Renseigner dans `.env` le domaine et les deux variables d'authentification,
puis démarrer :

```bash
docker compose up -d --build
docker compose logs -f
```

Le volume logique `stock_cuisine_data` conserve `/data/stock.db`. Son nom réel
peut être préfixé par le nom du projet Compose. Pour importer des données,
utiliser une sauvegarde cohérente avant le premier démarrage : une copie brute
d'une base active peut omettre son journal WAL.

Sauvegarder depuis le conteneur et récupérer la copie :

```bash
docker compose exec stock-cuisine \
  python -m stock_cuisine --database /data/stock.db backup \
  --output /data/avant-mise-a-jour.db
docker compose cp stock-cuisine:/data/avant-mise-a-jour.db ./sauvegarde-serveur.db
```

Après sauvegarde, `git pull --ff-only` puis `docker compose up -d --build`
appliquent une mise à jour. Ne pas supprimer les volumes de données.

## Sauvegardes et restauration

Conserver des sauvegardes datées hors de la machine qui héberge le stock.
La fréquence dépend du nombre de saisies que l'équipe peut accepter de perdre.
L'application fournit `backup`, mais aucune planification automatique.

Une restauration se fait site arrêté, après sauvegarde de l'état actuel.
Vérifier la copie avec `PRAGMA integrity_check` dans SQLite et l'ouvrir avec la
même version de l'application sur une instance de contrôle. Lors du remplacement,
conserver ensemble l'ancienne base et ses éventuels fichiers `-wal` / `-shm`
à l'écart ; ne pas associer les anciens journaux à la base restaurée. Rétablir
les droits d'écriture, redémarrer puis vérifier quantités et historique.

Depuis `~/gestion-cuisine`, le contrôle d'une copie distante se fait ainsi ; le
résultat attendu est `ok` :

```bash
python -c 'import sqlite3; print(sqlite3.connect("sauvegardes/avant-restauration.db").execute("PRAGMA integrity_check").fetchone()[0])'
```

Le schéma est versionné. L'application applique les migrations connues et
refuse une base dont le schéma est plus récent que celui qu'elle prend en charge.
L'accès est partagé : tous les collaborateurs authentifiés ont les mêmes actions.
Pour l'exploitation web, placer le serveur HTTP derrière le proxy HTTPS de
l'hébergeur ou Caddy.
