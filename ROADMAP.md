# Feuille de route — Stock Cuisine

## Vision

Proposer une gestion de stock simple, fiable et compréhensible par une équipe
associative, avec une application locale et des données récupérables.

## Réalisé dans la refonte 2.0

- [x] Projet installable depuis sa racine avec `pyproject.toml`.
- [x] Couche applicative partagée entre la CLI et le web.
- [x] Interface web responsive avec tableau de bord, recherche et filtres.
- [x] Historique des mouvements et règles de stock conservés.
- [x] Exports CSV des produits, du stock, des lots et des mouvements.
- [x] Sauvegarde cohérente de la base via SQLite `backup`.
- [x] Transactions atomiques pour les opérations de stock.
- [x] Déploiement Docker avec stockage persistant, HTTPS et protection d’accès partagée.

## Étape suivante — qualité opérationnelle

- [ ] Ajouter une restauration guidée depuis une sauvegarde validée.
- [ ] Ajouter des migrations de schéma versionnées au fil des évolutions.
- [ ] Ajouter les corrections contrôlées de lots avec mouvement d’ajustement.
- [ ] Ajouter une liste de courses calculée à partir des seuils.

## Confort d’utilisation

- [ ] Ajouter une vue « à consommer en priorité » triée par date limite.
- [ ] Permettre la modification guidée des produits et des informations de lot.
- [ ] Ajouter un export imprimable de la liste de courses.
- [ ] Ajouter des messages d’aide et une validation plus progressive des formulaires.

## Déploiement associatif

- [ ] Documenter le choix entre poste local et serveur du réseau.
- [ ] Ajouter des comptes individuels et des rôles si plusieurs personnes utilisent l’application.
- [ ] Définir une politique de sauvegardes automatiques et de restauration testée.

## Décisions de conception

- L’application reste sans dépendance externe pour simplifier l’installation.
- SQLite reste le stockage de référence tant que l’usage reste local ou familial.
- Le repository ne porte que la persistance ; les règles sont exposées par les
  services et la couche applicative.
- Les exports et sauvegardes sont explicites pour éviter toute perte silencieuse
  de données.
