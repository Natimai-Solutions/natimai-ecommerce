# Tests end-to-end (Q4)

Un seul parcours, celui qui doit toujours marcher : **catalogue → panier →
checkout → commande**. Le paiement passe par la méthode **virement manuel**
seedée par `initial_data`, donc aucun appel à PayZen : la commande est créée,
un numéro séquentiel est attribué (M5) et les instructions de virement
s'affichent. Cela couvre toute la chaîne serveur — tarification, réservation de
stock, création de commande, numérotation — sans passerelle dans la boucle.

## Lancer en local

```bash
# 1. La pile (postgres, redis, api, vitrine)
docker compose up -d postgres redis api frontend
docker compose run --rm migrate          # alembic upgrade head + initial_data

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

Variables surchargeables : `E2E_BASE_URL`, `E2E_EMAIL`, `E2E_PASSWORD`.

## Sélecteurs

Les tests ciblent des `data-testid` posés sur les éléments du parcours, jamais
des textes ou des classes CSS : un libellé se reformule, une classe Quasar
change de version, et le test casserait sans que rien ne soit cassé.

Deux pièges rencontrés, documentés ici pour éviter de les redécouvrir :

- Quasar transmet les attributs *fallthrough* à l'`<input>` **natif**, pas au
  wrapper `q-field` — `getByTestId(...)` cible donc directement l'élément
  remplissable, sans `.locator('input')`.
- La case CGV se clique sur `.q-checkbox__inner` : son libellé contient un lien
  vers les CGV avec `@click.stop`, et un clic au centre de la ligne y atterrit
  et se fait avaler.
