# Vérification des fonctionnalités du backend
## Fonctionnalités essentielles
- [ ] A0 Les fonctionnalités de base d'une API ecommerce sont en place : produits, catégorie, panier, checkout, paiement, factures, notification client
- [ ] A1 Au moment du checkout, le client peut choisir les routes selon le prix, le délai de livraison et l'aspect 'écologique' du transport. Prévoir options par défaut (price, speed et eco) sur les préférences utilisateurs
- [ ] A2 Le calcul de shipping se fait bien selon les tronçons (par exemple Paris->Papeete / Papeete->Arutua) avec prix fixe, calcul selon le prix, le poids ou formule avancé.
- [ ] A3 Vérifier que payment puisse contenir des paiements tels que chèque/virement/bon de commande (limité par utilisateur)/CB avec fonctions avancées.
- [ ] A4 Des endpoints existent permettant aux admins de regrouper des colis et de mettre à jour le tracking
- [ ] A5 Les produits peuvent être créés manuellement ou synchronisés avec l'API d'un fournisseur. Le prix et les quantités sont mis à jour régulièrement.
- [ ] A6 Si nécessaires, les infos produits et images sont synchronisés avec Icecat ou un autre fournisseur. Les caractéristiques des produits peuvent servir à la recherche de produit.
- [ ] A7 Les factures peuvent être exportées facilement pour traitement par la comptabilité.

## Fonctionnalités à prévoir à moyen terme
- [ ] M1 Les produits les plus vus sont mis en évidence (endpoint à prévoir).
- [ ] M2 Déploiement Kubernetes

## Fonctionnalités optionnelles ou à prévoir plus tard.
- [ ] Z1 Possibilité de payer en plusieurs fois.
- [ ] Z2 Avoir et remboursement.
- [ ] Z3 Relance client / paniers abandonnés.
- [ ] Z4 Recherche des produits par IA.