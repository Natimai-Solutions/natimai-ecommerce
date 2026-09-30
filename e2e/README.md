# Tests end-to-end (Q4)

Deux projets Playwright, un par application.

**Vitrine** (`tests/*.spec.ts`, `E2E_BASE_URL`) : le parcours qui doit toujours
marcher, **catalogue → panier → checkout → commande**, puis l'espace client.
Le paiement passe par la méthode **virement manuel** seedée par
`initial_data`, donc aucun appel à PayZen : la commande est créée,
un numéro séquentiel est attribué (M5) et les instructions de virement
s'affichent. Cela couvre toute la chaîne serveur — tarification, réservation de
stock, création de commande, numérotation — sans passerelle dans la boucle.

**Admin** (`tests/admin/*.spec.ts`, `E2E_ADMIN_URL`), avec le superutilisateur
créé par `initial_data` (`FIRST_SUPERUSER`) :

- `shell.spec.ts` : redirection vers la connexion puis retour à la page
  demandée, mauvais mot de passe, tableau de bord « À traiter », **chaque
  entrée du menu** ouvre son écran sans exception ni erreur 5xx, thème
  mémorisé après rechargement (qui prouve aussi la restauration de session par
  le cookie), déconnexion ;
- `payment-validation.spec.ts` : un client commande et paie par virement sur la
  vitrine, l'admin passe par la tuile « Paiements à valider », approuve le
  paiement, et la commande devient « Payée » ;
- `homepage-banner.spec.ts` : une bannière publiée depuis l'admin apparaît sur
  l'accueil de la vitrine, puis disparaît une fois supprimée.

Les parcours admin qui ont besoin de la vitrine ouvrent une seconde page sur
`E2E_BASE_URL`. Les aides communes sont dans `support/`.

## Lancer en local

```bash
# 1. La pile (postgres, redis, api, vitrine, admin) ; le .env doit contenir
#    BACKEND_CORS_ORIGINS=http://localhost:3001 et LOGIN_RATE_LIMIT_ATTEMPTS=1000
docker compose up -d postgres redis api frontend admin-frontend
docker compose run --rm migrate          # alembic upgrade head + initial_data
# Tâches de fond : l'approbation d'un paiement passe par l'outbox
docker compose up -d arq-worker outbox-poller

# 2. Les fixtures du parcours (client, adresse, produit en stock) — idempotent
docker compose cp e2e/seed_e2e_data.py api:/app/e2e_seed.py
docker compose exec -T api python /app/e2e_seed.py

# 3. Les tests
pnpm install
pnpm --filter e2e exec playwright install --with-deps chromium
pnpm --filter e2e test
```

Ou, sans installer les navigateurs sur la machine, avec l'image officielle
(sa version doit correspondre **exactement** à celle de `@playwright/test`) :

```bash
docker run --rm --network host -v "$PWD:/w" -w /w/e2e \
  mcr.microsoft.com/playwright:v1.62.1-jammy npx playwright test
```

## Configuration requise

`FRONTEND_HOST` doit valoir l'origine de la vitrine (`http://localhost:3000`),
sinon l'API rejette les appels du navigateur en CORS — l'API répond
parfaitement en direct (curl), et seul le navigateur échoue, ce qui rend le
symptôme déroutant.

L'admin (`http://localhost:3001`) appelle aussi l'API depuis le navigateur :
son origine doit figurer dans `BACKEND_CORS_ORIGINS`.

La suite enchaîne une douzaine de connexions en moins d'une minute depuis la
même IP. La limite par IP (10 par minute, couverte par les tests backend) doit
être relevée pour la pile de test : `LOGIN_RATE_LIMIT_ATTEMPTS=1000`.

Le parcours de validation de paiement attend que le **poller d'outbox** et le
**worker ARQ** fassent passer la commande à « Payée » (jusqu'à 60 s) : sans eux,
il échoue sur sa dernière étape.

Variables surchargeables : `E2E_BASE_URL`, `E2E_ADMIN_URL`, `E2E_EMAIL`,
`E2E_PASSWORD`, `E2E_ADMIN_EMAIL`, `E2E_ADMIN_PASSWORD`.

## Sélecteurs

Les tests ciblent des `data-testid` posés sur les éléments du parcours, jamais
des textes ou des classes CSS : un libellé se reformule, une classe Quasar
change de version, et le test casserait sans que rien ne soit cassé.

L'admin est routé par hash (`/#/orders`) et garde son jeton en mémoire :
naviguer entre écrans en changeant le hash (`openAdmin`), pas en rechargeant.

Deux pièges rencontrés, documentés ici pour éviter de les redécouvrir :

- Quasar transmet les attributs *fallthrough* à l'`<input>` **natif**, pas au
  wrapper `q-field` — `getByTestId(...)` cible donc directement l'élément
  remplissable, sans `.locator('input')`.
- La case CGV se clique sur `.q-checkbox__inner` : son libellé contient un lien
  vers les CGV avec `@click.stop`, et un clic au centre de la ligne y atterrit
  et se fait avaler.
