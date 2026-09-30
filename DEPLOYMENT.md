# Hébergement et maintenance

Une instance hébergée permet à l'équipe de travailler sur la même base.
Les mises à jour du code se font par Git ; SQLite reste sur l'hébergeur.
Ne pas remettre une ancienne copie locale de la base lors d'une mise à jour.

## Alwaysdata

### Préparer le code en SSH

Reprendre le nom d'utilisateur et l'hôte indiqués dans l'administration SSH.
`UTILISATEUR_SSH` est le compte de connexion ; `NOM_DU_COMPTE` est le compte
d'hébergement et son dossier `/home/NOM_DU_COMPTE`. Ils peuvent différer.

```bash
ssh UTILISATEUR_SSH@ssh-NOM_DU_COMPTE.alwaysdata.net
git clone https://github.com/Constantin72/gestion-cuisine.git ~/gestion-cuisine
cd ~/gestion-cuisine
mkdir -p donnees sauvegardes
```

Si le dossier existe déjà, vérifier son origine avec
`git -C ~/gestion-cuisine remote -v`, puis utiliser `git pull --ff-only` dans
ce dépôt. Ne pas tenter de le cloner une seconde fois.

### Configurer le site

Dans **Web → Sites**, ajouter ou modifier le site. Remplacer `NOM_DU_COMPTE`
dans les chemins et dans l'adresse.

| Champ | Valeur |
| --- | --- |
| Adresse | `NOM_DU_COMPTE.alwaysdata.net` ou le domaine configuré |
| Type | Programme utilisateur / User program |
| Répertoire de travail | `/home/NOM_DU_COMPTE/gestion-cuisine` |

Commande, sur une seule ligne :

```bash
python -m stock_cuisine --database /home/NOM_DU_COMPTE/gestion-cuisine/donnees/stock.db web --host $IP --port $PORT
```

Conserver littéralement `$IP` et `$PORT` : Alwaysdata les fournit. Le serveur
prend en charge IPv4 et IPv6. Utiliser Python 3.9 ou supérieur.
Dans **Environnement**, une variable par ligne, sans espaces autour de `=` :

```dotenv
PYTHONPATH=/home/NOM_DU_COMPTE/gestion-cuisine/src
STOCK_CUISINE_AUTH_USER=equipe
STOCK_CUISINE_AUTH_PASSWORD=REMPLACER_PAR_UN_SECRET_LONG_ET_UNIQUE
```

L'application ne lit pas automatiquement un fichier `.env`. Sur Alwaysdata,
renseigner ces variables dans la configuration du site. Activer l'accès HTTPS
et ouvrir le site en navigation privée pour vérifier la demande d'identification.

Références : [Programme utilisateur](https://help.alwaysdata.com/en/docs/web-hosting/sites/http-servers/user-program/)
et [variables d'écoute HTTP](https://help.alwaysdata.com/en/docs/technical-specifications/migrations/2020-software-architecture/).

### Importer un stock existant au premier déploiement

Sur l'ordinateur qui possède la base, depuis la racine du projet :

```bash
./.venv/bin/python -m stock_cuisine --database donnees/stock.db backup \
  --output sauvegardes/transfert.db
scp sauvegardes/transfert.db UTILISATEUR_SSH@ssh-NOM_DU_COMPTE.alwaysdata.net:~/gestion-cuisine/donnees/transfert.db
```

Sur le serveur, avant de démarrer le site et uniquement si `stock.db` n'existe
pas encore, copier `transfert.db` vers `stock.db`. Si une base existe déjà,
il s'agit d'une restauration : arrêter le site et sauvegarder cette base avant
tout remplacement. Ne pas écraser les données d'une équipe déjà active.

Le processus web doit pouvoir écrire dans la base **et** dans son dossier,
où SQLite crée ses journaux. Lorsque SSH et le web partagent le groupe du
compte, les droits suivants conviennent :

```bash
chmod 770 ~/gestion-cuisine/donnees
chmod 660 ~/gestion-cuisine/donnees/stock.db
```

### Publier une mise à jour

Après avoir validé et poussé le code sur GitHub, dans le terminal SSH :

```bash
cd ~/gestion-cuisine
PYTHONPATH=src python -m stock_cuisine --database donnees/stock.db backup \
  --output sauvegardes/avant-mise-a-jour.db
git pull --ff-only
```

Choisir un autre nom de sauvegarde pour conserver les versions précédentes.
Redémarrer ensuite le site dans l'administration Alwaysdata et vérifier le stock.
La fermeture du terminal SSH n'arrête pas le site géré par l'hébergeur.
Garder les identifiants hors de Git et des captures de logs partagées.

### Résoudre les erreurs courantes

| Message ou symptôme | Vérification |
| --- | --- |
| `No module named stock_cuisine` | Chemin `PYTHONPATH`, sans espace dans le nom de variable |
| `attempt to write a readonly database` | Droits de la base, du dossier et des éventuels fichiers `-wal` / `-shm` |
| Mauvais stock ou base vide | Chemin absolu de `--database` et emplacement de la copie transférée |
| Changement de code invisible | `git pull` sur le serveur puis site redémarré |
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

Le schéma est versionné. L'application applique les migrations connues et
refuse une base dont le schéma est plus récent que celui qu'elle prend en charge.
L'accès est partagé : tous les collaborateurs authentifiés ont les mêmes actions.
Pour l'exploitation web, placer le serveur HTTP derrière le proxy HTTPS de
l'hébergeur ou Caddy.
