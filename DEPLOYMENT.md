# Mise en ligne

Le projet peut être déployé avec Docker Compose. Le service applicatif reste
privé dans le réseau Docker, tandis que Caddy fournit l’accès HTTPS public.

## Pré-requis

- un serveur ou VPS avec Docker et Docker Compose ;
- un nom de domaine dont l’enregistrement DNS pointe vers ce serveur ;
- les ports TCP 80 et 443 ouverts vers le serveur.

## Installation

Depuis la racine du projet :

```bash
cp .env.example .env
```

Modifier ensuite `.env` :

```dotenv
STOCK_CUISINE_DOMAIN=stock.mondomaine.fr
STOCK_CUISINE_AUTH_USER=equipe
STOCK_CUISINE_AUTH_PASSWORD=un-secret-long-et-unique
```

Démarrer l’application :

```bash
docker compose up -d --build
docker compose logs -f
```

L’interface sera disponible à l’adresse `https://stock.mondomaine.fr`. Caddy
gère le certificat TLS automatiquement lorsque le domaine résout vers le
serveur.

Pour reprendre une base locale existante, arrêter d’abord l’application puis
copier le fichier dans le volume persistant :

```bash
docker compose stop stock-cuisine
docker compose run --rm \
  -v "$PWD/stock.db:/import/stock.db:ro" \
  stock-cuisine sh -c 'test -e /data/stock.db || cp /import/stock.db /data/stock.db'
docker compose up -d
```

## Données et sauvegarde

La base SQLite est conservée dans le volume Docker `stock_cuisine_data`.
Effectuer régulièrement une sauvegarde :

```bash
docker compose exec stock-cuisine \
  python -m stock_cuisine --database /data/stock.db backup \
  --output /data/backup-$(date +%F).db
```

Conserver également une copie de ces sauvegardes hors du serveur. Une
restauration guidée n’est pas encore fournie par l’application.

SQLite convient à une petite équipe utilisant l’application simultanément.
Pour un volume d’utilisation beaucoup plus élevé, il faudra prévoir un
stockage serveur dédié.

## Sécurité

- Ne pas exposer directement le port 8000 sur Internet.
- Utiliser un mot de passe long, unique et non commité dans Git.
- L’accès actuel utilise un identifiant et un mot de passe partagés par
  l’équipe ; il ne fournit pas encore de comptes individuels ni de rôles.
- Le serveur refuse de démarrer sur une adresse publique si les identifiants
  d’authentification ne sont pas configurés.

Pour un hébergeur qui fournit déjà le HTTPS, le `Dockerfile` peut être utilisé
seul : conserver `/data` comme volume persistant, exposer le port 8000 et
définir les deux variables d’authentification.
