# Guide de déploiement — Kubernetes sur Akamai LKE

Ce document décrit la procédure complète pour déployer l'application sur un cluster Kubernetes
Akamai LKE et configurer l'intégration continue via GitHub Actions.

## Table des matières

1. [Prérequis locaux](#1-prérequis-locaux)
2. [Créer le cluster LKE](#2-créer-le-cluster-lke)
3. [Installer les composants cluster](#3-installer-les-composants-cluster)
4. [Configurer le DNS](#4-configurer-le-dns)
5. [Configurer GitHub](#5-configurer-github)
6. [Premier déploiement](#6-premier-déploiement)
7. [Flux CI/CD au quotidien](#7-flux-cicd-au-quotidien)
8. [Référence des secrets GitHub](#8-référence-des-secrets-github)
9. [Maintenance](#9-maintenance)

---

## 1. Prérequis locaux

Outils à installer sur ta machine pour la phase de setup initiale :

```powershell
# kubectl
winget install Kubernetes.kubectl

# helm (gestionnaire de paquets Kubernetes)
winget install Helm.Helm
```

Vérifie les versions :

```powershell
kubectl version --client
helm version
```

---

## 2. Créer le cluster LKE

### Sur cloud.linode.com

1. **Kubernetes → Create Cluster**
   - Région : choisir en fonction de la localisation des utilisateurs
   - Node Pool : 3 × **Shared CPU 4 GB** (minimum recommandé pour backend + frontends + Redis)
   - Version Kubernetes : dernière stable disponible

2. **Télécharger le kubeconfig** (bouton "Download kubeconfig" dans l'interface LKE)

3. **Tester la connexion** :

```powershell
$env:KUBECONFIG = "C:\chemin\vers\kubeconfig.yaml"
kubectl get nodes
# → 3 nœuds en état Ready
```

4. **Encoder le kubeconfig en base64** (nécessaire pour GitHub Secrets) :

```powershell
[Convert]::ToBase64String(
  [System.IO.File]::ReadAllBytes("C:\chemin\vers\kubeconfig.yaml")
) | Set-Clipboard
# → le résultat est copié dans le presse-papier, colle-le dans le secret KUBECONFIG
```

---

## 3. Installer les composants cluster

Ces deux composants doivent être installés **une seule fois** sur le cluster, avant le premier déploiement.

### nginx-ingress

Controller qui expose les services sur internet via un LoadBalancer Akamai.

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  --wait
```

**Récupérer l'IP publique du LoadBalancer** — tu en auras besoin pour configurer le DNS :

```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller
# Colonne EXTERNAL-IP → ex: 194.233.64.12
```

> L'IP peut prendre 1-2 minutes à apparaître après l'installation.

### cert-manager

Gestion automatique des certificats TLS (Let's Encrypt).

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update

helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --set crds.enabled=true \
  --wait
```

---

## 4. Configurer le DNS

Dans l'interface de ton registrar, créer trois enregistrements A pointant vers l'IP du LoadBalancer :

| Nom | Type | Valeur |
|-----|------|--------|
| `@` (ou ton domaine nu) | A | `<EXTERNAL-IP>` |
| `api` | A | `<EXTERNAL-IP>` |
| `admin` | A | `<EXTERNAL-IP>` |

Résultat attendu :
- `https://ton-domaine.com` → frontend SSR (vitrine)
- `https://api.ton-domaine.com` → API FastAPI
- `https://admin.ton-domaine.com` → frontend admin

> La propagation DNS peut prendre quelques minutes à quelques heures selon le registrar.

---

## 5. Configurer GitHub

### Rendre les images Docker accessibles

Les images sont publiées sur **GitHub Container Registry** (ghcr.io) automatiquement par le workflow.

Par défaut, les packages d'un repo privé sont privés. Pour simplifier le pull depuis le cluster sans
configurer un `imagePullSecret`, rendre les images publiques :

**GitHub → ton profil → Packages** → après le premier deploy, ouvrir chaque image
(`api`, `frontend`, `admin`) → **Package settings → Change visibility → Public**

### Créer les secrets

**Settings → Secrets and variables → Actions → New repository secret**

Voir la [référence complète des secrets](#8-référence-des-secrets-github) ci-dessous.

### Créer l'environnement "production" (optionnel mais recommandé)

**Settings → Environments → New environment** → nommer `production`

Cela permet d'ajouter une **protection manuelle** : le deploy ne se lance qu'après approbation
d'un reviewer désigné.

---

## 6. Premier déploiement

Une fois les secrets GitHub configurés et le DNS propagé, déclencher le premier deploy :

```bash
git commit --allow-empty -m "chore: trigger initial deploy"
git push origin main
```

Le workflow effectue dans l'ordre :

```
1. Build 3 images Docker → push ghcr.io
   ├── api      (backend FastAPI + arq-worker + outbox-poller)
   ├── frontend (SSR Node.js)
   └── admin    (SPA Nginx)

2. kubectl apply namespace (ecommerce) + Redis

3. Sync des secrets Kubernetes depuis GitHub Secrets

4. Job de migration Alembic (attend la fin avant de continuer)

5. kubectl apply backend + frontend + admin + ingress

6. kubectl rollout status (vérifie que tout démarre correctement)
```

### Vérifier le déploiement

```bash
# État des pods
kubectl get pods -n ecommerce

# Logs d'un pod spécifique
kubectl logs -n ecommerce deployment/backend --follow

# État des certificats TLS (quelques minutes après le premier deploy)
kubectl get certificate -n ecommerce
```

---

## 7. Flux CI/CD au quotidien

### Pull Request → CI (`.github/workflows/ci.yml`)

À chaque PR, automatiquement :
- **Backend** : `ruff check` + `mypy`
- **Frontend** : `vue-tsc --noEmit`
- **Admin** : `vue-tsc --noEmit`

### Push sur `main` → Deploy (`.github/workflows/deploy.yml`)

À chaque merge sur `main`, automatiquement :
- Build et push des 3 images avec le tag `:<sha-git>` (et `:latest`)
- Les placeholders dans les manifests sont remplacés à la volée :
  - `YOURDOMAIN.COM` → secret `DOMAIN`
  - `LETSENCRYPT_EMAIL` → secret `LETSENCRYPT_EMAIL`
  - `GITHUB_OWNER` / `REPO_NAME` → variables GitHub automatiques
- Migration, puis rollout des deployments

---

## 8. Référence des secrets GitHub

| Secret | Description | Exemple |
|--------|-------------|---------|
| `KUBECONFIG` | kubeconfig LKE encodé en base64 | _(voir étape 2)_ |
| `DOMAIN` | Domaine racine sans sous-domaine | `natimai.pf` |
| `LETSENCRYPT_EMAIL` | Email pour les certificats Let's Encrypt | `admin@natimai.pf` |
| `SECRET_KEY` | Clé secrète FastAPI (JWT, sessions) | `openssl rand -hex 32` |
| `DATABASE_URL` | URL Akamai Managed Database | `postgresql+asyncpg://user:pass@host/db` |
| `INGRAM_CLIENT_ID` | Credentials API Ingram Micro | |
| `INGRAM_CLIENT_SECRET` | | |
| `INGRAM_CUSTOMER_NUMBER` | | |
| `ICECAT_USERNAME` | Credentials API Icecat | |
| `ICECAT_API_KEY` | | |
| `MAILGUN_API_KEY` | Clé API Mailgun (emails transactionnels) | |
| `MAILGUN_DOMAIN` | Domaine expéditeur Mailgun | `mail.natimai.pf` |

> `REDIS_URL` n'est pas un secret — il est fixé à `redis://redis:6379` (service interne K8s)
> directement dans le workflow.

### Ajouter un nouveau secret

Chaque variable d'environnement sensible nécessite deux modifications :

**1.** Ajouter le secret dans GitHub — Settings → Secrets and variables → Actions → New repository secret

**2.** Ajouter la ligne correspondante dans `.github/workflows/deploy.yml`, dans l'étape
`Sync Kubernetes secrets` :

```yaml
--from-literal=MA_VARIABLE="${{ secrets.MA_VARIABLE }}" \
```

Le secret Kubernetes `app-secrets` est entièrement recréé à chaque deploy — la nouvelle variable
sera disponible dans tous les pods backend au prochain push sur `main`.

---

## 9. Maintenance

### Mettre à jour le domaine

Modifier le secret GitHub `DOMAIN`. Le prochain deploy appliquera la nouvelle valeur.
Le certificat TLS sera renouvelé automatiquement par cert-manager.

### Rotation des secrets applicatifs

Modifier la valeur dans GitHub Secrets, puis déclencher un deploy (push vide ou re-run du workflow).
Le workflow recrée le secret Kubernetes avec `--dry-run=client | kubectl apply` — les pods existants
ne redémarrent pas automatiquement. Pour forcer le redémarrage :

```bash
kubectl rollout restart deployment/backend -n ecommerce
```

### Scaler un deployment

```bash
# Passer l'API à 3 réplicas
kubectl scale deployment/backend --replicas=3 -n ecommerce
```

> Pour que le changement soit permanent, modifier `replicas` dans
> `infra/k8s/backend/deployment.yaml` et pusher sur main.

### Consulter les logs de migration

```bash
kubectl logs -n ecommerce job/migrate
```

### ClamAV — démarrage lent

ClamAV charge sa base de signatures virales au démarrage (~2 minutes). Le pod sera en état
`0/1 Running` pendant ce temps, c'est normal. Le backend attend que ClamAV soit prêt via
sa readinessProbe avant d'accepter du trafic.

```bash
# Suivre le démarrage de ClamAV
kubectl logs -n ecommerce deployment/clamav --follow

# Vérifier l'état de la readinessProbe
kubectl describe pod -n ecommerce -l app=clamav
```

La base de signatures est persistée dans un PVC (1 Gi) — les redémarrages ultérieurs
sont donc beaucoup plus rapides car les signatures sont déjà sur disque.
