# Feuille de route — Cuisine 4H

## Objectif

Fournir à une petite équipe associative un stock partagé, compréhensible et
récupérable, utilisable localement ou sur un hébergeur.

## Fonctionnalités disponibles

- [x] Produits, catégories, lots et correction de leurs informations.
- [x] Entrées, sorties, pertes, première ouverture et historique.
- [x] Inventaire avec mouvement d'ajustement et écritures atomiques.
- [x] Alertes de seuil et de péremption, y compris après ouverture.
- [x] Valeur du stock selon les quantités restantes et le prix de chaque lot.
- [x] Tri par catégorie et nom dans les produits, lots et choix d'un produit.
- [x] Interface web, commande terminal et exports CSV.
- [x] Page d'inventaire globale, regroupée par produit, avec comptage atomique.
- [x] Sauvegarde par l'API SQLite et migration du schéma v1 vers v2.
- [x] Accès web partagé protégé par authentification et contrôle des formulaires.
- [x] Documentation Alwaysdata et alternative Docker/Caddy.

## Fiabilité et exploitation

- [ ] Restauration guidée avec validation préalable de la sauvegarde.
- [ ] Sauvegardes automatiques avec rétention et vérification de restauration.
- [ ] Vérifications automatiques sur plusieurs versions de Python.
- [ ] Pagination des grandes listes et limitation des exports volumineux.
- [ ] Gestion explicite des conflits lorsque deux personnes modifient une fiche.

## Ergonomie

- [ ] Vue « à consommer en priorité » utilisant la date limite effective.
- [ ] Liste de courses calculée à partir des seuils et export imprimable.
- [ ] Conservation des saisies lorsqu'un formulaire contient une erreur.
- [ ] Comptes individuels, rôles et identification de l'auteur des mouvements,
  si les besoins de l'association le justifient.

## Principes de maintenance

- Conserver la bibliothèque standard et SQLite tant qu'ils répondent à l'usage.
- Centraliser les calculs de stock et d'alertes, partagés entre web, CLI et exports.
- Valider les écritures dans le repository, au plus près de la transaction.
- Faire évoluer le schéma avec une migration testée et une sauvegarde préalable.
- Maintenir le guide d'exploitation à jour avec le mode de déploiement utilisé.

La présence d'une commande de sauvegarde ne signifie pas que des sauvegardes
automatiques sont déjà planifiées sur l'hébergement.
