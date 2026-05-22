# Conventions de code — fastapi-ecommerce (backend)

Document de référence pour uniformiser le code, le nommage et l'organisation,
quel que soit le développeur ou l'agent IA. À consulter avant chaque
session de développement et à mettre à jour quand un pattern évolue.

---

## 1. Organisation des modules

### 1.1 Découpage `app/`

```
app/
├── api/routes/            # Endpoints FastAPI (un fichier par domaine)
├── core/                  # Configuration (settings, security, db)
├── features/              # Logique métier découpée par domaine
│   └── <domain>/
│       ├── crud/          # Accès données (un fichier par entité)
│       ├── models/        # SQLModel (un fichier par entité)
│       ├── services/      # Logique métier transverse (workflow, orchestration)
│       ├── providers/     # Plugins de provider (paiement, notif, storage…)
│       └── utils/         # Helpers spécifiques au domaine
├── handlers/              # Handlers outbox (un fichier par domaine)
├── outbox/                # Infrastructure outbox/event-driven
├── tasks/                 # Jobs ARQ
├── tests/                 # Mirror de la structure `app/`
├── alembic/versions/      # Migrations (chronologiques)
└── utils/                 # Helpers généraux (money, ids, validators)
```

### 1.2 Règle d'or pour `features/`

- **Un domaine = un dossier `features/<domain>/`** contenant tous les
  artefacts liés (modèles, CRUD, services, providers).
- **Pas de logique métier dans les routes** : les routes orchestrent (parse
  request, appelle service, retourne réponse). La logique vit dans
  `services/` ou `crud/`.
- **Pas d'I/O dans les modèles** : un `models/*.py` ne fait que définir
  les SQLModel (Base/Create/Update/Public/...). Aucun appel DB.

---

## 2. Nommage des fichiers et entités

### 2.1 Fichiers

| Type            | Convention                                   | Exemple                          |
|-----------------|----------------------------------------------|----------------------------------|
| Modèle          | `<entity_snake>.py`                          | `payment.py`, `payment_status.py`|
| CRUD            | `<entity_snake>.py`                          | `payment.py`                     |
| Service         | `<domain>_<action>.py` ou `<workflow>.py`    | `manual_payment.py`, `notifications.py` |
| Provider        | `<provider_kind>.py`                         | `manual.py`, `payzen.py`         |
| Route           | `<domain>.py` ou `<domain>_<sub>.py`         | `payments.py`, `admin_payments.py` |
| Handler outbox  | `<domain>.py`                                | `handlers/payment.py`            |
| Test            | `test_<module_or_phase>.py`                  | `test_manual_payment_service.py` |

### 2.2 SQLModel — pattern Base/Create/Update/Public

Pour **chaque entité**, on définit cinq classes dans ce ordre dans le
fichier `models/<entity>.py` :

```python
class PaymentBase(Base):
    # Champs métier communs à toutes les vues
    ...

class PaymentCreate(PaymentBase, BaseCreate):
    # Champs supplémentaires nécessaires à la création (foreign keys)
    ...

class PaymentUpdate(PaymentBase, BaseUpdate):
    # Tous les champs en Optional (None) pour patch partiel
    ...

class Payment(PaymentBase, table=True):
    __tablename__ = "payments"   # Toujours pluriel
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    # Champs persistés (foreign keys, JSON, etc.)

class PaymentPublic(PaymentBase, BasePublic):
    # Vue API publique (id + champs exposés)
    ...

class PaymentsPublic(SQLModel):
    # Collection paginée
    data: list[PaymentPublic] = Field(default_factory=list, ...)
    count: int = Field(default=0, ...)
```

**Règles** :
- `__tablename__` au pluriel snake_case (`payments`, `payment_logs`).
- IDs : `uuid.UUID` avec `default_factory=uuid.uuid4`, `primary_key=True`, `index=True`.
- Foreign keys nommées `<entity>_id` avec `foreign_key="<table>.id"`.
- Pas de relations SQLAlchemy `relationship()` sauf cas justifié — on
  charge explicitement via CRUD.
- Le `PaymentsPublic` (pluriel) est utilisé pour les endpoints list.

### 2.3 Classes CRUD

| Élément            | Convention                                   |
|--------------------|----------------------------------------------|
| Classe             | `<Entity>Crud(CrudBase[Entity, Create, Update])` |
| Instance singleton | `crud_<entity>` au bas du fichier            |
| Méthode lookup     | `get_by_<champ>(session, *, <champ>=...)`    |
| Méthode liste      | `get_by_<filter>(session, *, ...)`           |
| Création custom    | `create_<entity>_with_<aspect>(...)`         |
| Update custom      | `update_<entity>_from_<source>(...)`         |

```python
class PaymentCrud(CrudBase[Payment, PaymentCreate, PaymentUpdate]):
    async def get_by_provider_reference(
        self, session: AsyncSession, *, provider_code: str, provider_reference: str
    ) -> Payment | None: ...

crud_payment = PaymentCrud(
    model=Payment,
    schema_create=PaymentCreate,
    schema_update=PaymentUpdate,
    order_by=Payment.created_at,
)
```

**Règles** :
- **Toujours utiliser des kwargs nommés** (`session, *, ...`) pour les lookups.
- Filtrer systématiquement `is_admin_active=True` et `is_active=True` sur les lectures.
- Les noms de méthode **ne portent pas le nom d'un provider concret**
  (`get_by_provider_reference`, pas `get_by_payzen_order_id`).

### 2.4 Services

Les services exposent des **fonctions async snake_case** (pas de classes
sauf nécessité d'état).

```python
async def approve_manual_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    admin: User,
    reference: str | None,
    comment: str | None,
) -> ManualValidationOutcome: ...
```

**Règles** :
- Signature : `session` en premier, puis tout en kwargs-only (`*,`).
- Type de retour explicite — préférer un `@dataclass(slots=True)` nommé
  `<Action>Outcome` ou `<Action>Result` plutôt que des tuples.
- Les services écrivent dans la session mais **ne commitent pas** : le
  commit appartient à l'endpoint appelant.
- Préfixer les helpers privés du module avec `_` (`_build_event_payload`,
  `_get_or_create_status`).

### 2.5 Providers (pattern plugin)

Chaque type de plugin (paiement, notification, antivirus, storage) suit le
même pattern :

```python
# providers/base.py
class PaymentProvider(ABC):
    code: str    # ID stable utilisé pour le routing

class ApiPaymentProvider(PaymentProvider, ABC):
    @abstractmethod
    async def initiate_payment(self, request: InitiationRequest) -> InitiationResult: ...

# providers/__init__.py
SUPPORTED_PROVIDERS: dict[str, type[PaymentProvider]] = {
    PayzenProvider.code: PayzenProvider,
    ManualCheckProvider.code: ManualCheckProvider,
    ...
}

def get_provider(provider_code: str) -> PaymentProvider:
    normalized_code = provider_code.strip().lower()
    provider_class = SUPPORTED_PROVIDERS.get(normalized_code)
    if provider_class is None:
        raise UnknownPaymentProviderError(normalized_code)
    return provider_class()
```

**Règles** :
- Le `code` est une **constante de classe**, snake_case
  (`"payzen"`, `"manual_check"`, `"public_purchase_order"`).
- Les inputs/outputs des méthodes du provider sont des **dataclasses
  `slots=True`** (`InitiationRequest`, `InitiationResult`, etc.).
- L'inconnu lève une exception spécifique : `Unknown<Kind>ProviderError`.

### 2.6 Routes FastAPI

```python
router = APIRouter(prefix="/payments", tags=["payment"])

class PaymentsInitiateRequest(BaseModel):
    payment_method_id: uuid.UUID = Field(..., description=...)
    ...

class PaymentsInitiateResponse(BaseModel):
    payment_id: uuid.UUID
    ...

@router.post("/initiate", response_model=PaymentsInitiateResponse)
async def initiate_payment(
    session: SessionDep,
    request: PaymentsInitiateRequest,
    current_user: CurrentUser,
) -> PaymentsInitiateResponse: ...
```

**Règles** :
- Les Pydantic Request/Response sont déclarés **dans le même fichier** que
  l'endpoint, juste avant la définition de l'endpoint.
- Préfixe `prefix="/<domain>"` au niveau du router, **pas dans chaque endpoint**.
- `tags=[...]` au singulier (`"payment"`, pas `"payments"`).
- Dépendances : `session: SessionDep`, `current_user: CurrentUser`,
  `admin: AdminUser` (alias définis dans `app/api/deps.py`).
- Les helpers privés à la route sont préfixés `_` et placés au-dessus des
  endpoints qui les utilisent.

---

## 3. Nommage des variables et fonctions

### 3.1 Style général

- **Tout en snake_case** : variables, fonctions, méthodes, modules, attributs.
- **PascalCase** pour les classes et les types.
- **UPPER_SNAKE_CASE** pour les constantes au niveau module.
- Pas d'abbréviations cryptiques : `payment_id` (pas `pid`), `provider_code` (pas `pc`).

### 3.2 Vocabulaire métier — uniformisation

| Concept                          | Forme canonique           | À éviter                  |
|----------------------------------|---------------------------|---------------------------|
| Référence côté provider          | `provider_reference`      | `external_ref`, `tx_id`   |
| Code du provider                 | `provider_code`           | `provider`, `provider_name` |
| Payload brut du provider         | `provider_data`           | `raw_data`, `payzen_data` |
| ID de paiement (UUID)            | `payment_id`              | `pid`, `id` (hors model)  |
| ID de l'admin qui valide         | `admin_user_id`           | `admin_id`, `validator_id`|
| Statut de transaction provider   | `trans_status`            | `status`, `payment_state` |
| ID de transaction provider       | `trans_id` / `trans_uuid` | `transaction_id`          |
| Raison de rejet                  | `reason`                  | `comment`, `note`         |
| Action de validation             | `action`                  | `type`, `kind`            |

### 3.3 Helpers privés

- Fonction interne au module → préfixe `_` : `_get_or_create_status`,
  `_build_event_payload`, `_normalize_trans_status`.
- Constante interne au module → préfixe `_` : `_PAID_TRANS_STATUS`,
  `_TERMINAL_TRANS_STATUSES`.

### 3.4 Constantes métier

Définies au top du fichier qui les utilise, regroupées par thème :

```python
EVENT_AWAITING_VALIDATION = "payment.awaiting_validation"
EVENT_CAPTURED = "payment.captured"
EVENT_REJECTED = "payment.rejected"

ACTION_REGISTER_INTENT = "register_intent"
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"

MANUAL_STATUS_AWAITING_VALIDATION = "AwaitingValidation"
MANUAL_STATUS_COMPLETED = "Completed"
MANUAL_STATUS_FAILED = "Failed"
```

**Règles** :
- Pas de string literal pour un event type, action ou statut métier dans
  le corps du code — passer par une constante nommée.
- Les **noms de statuts en base** (PaymentStatus.name, OrderStatus.name)
  sont en **PascalCase** (`"Completed"`, `"PaymentFailed"`).
- Les **event_type outbox** sont en `domain.action` (`"payment.captured"`).

---

## 4. Outbox / événements

### 4.1 Publier un événement

```python
await outbox_registry.publish(
    session=session,
    event_type=EVENT_CAPTURED,
    payload={
        "payment_id": str(payment.id),
        "order_id": str(payment.order_id) if payment.order_id else None,
        "user_id": str(payment.user_id),
        "provider_code": payment.provider_code,
        "provider_reference": payment.provider_reference,
        "action": ACTION_APPROVE,
        "admin_user_id": str(admin.id) if admin else None,
        "reason": comment,
        "reference": reference,
        "metadata": extra_data,
    },
    correlation_id=payment.id,
)
```

**Règles** :
- Publier **avant le commit** : l'event est inséré dans la même transaction
  que la mutation métier (garantie outbox).
- `payload` est **toujours JSON-sérialisable** : convertir les UUID en `str`,
  les Decimal en `str` ou `float` selon le contexte.
- `correlation_id` est l'UUID de l'entité racine (le `payment_id` pour
  les events paiement) — utilisé pour le tracing.
- Le payload contient **systématiquement** : `payment_id`, `order_id`,
  `user_id`, `provider_code`, `action`. Les détails spécifiques vont dans
  `metadata`.

### 4.2 Handler outbox

```python
@outbox_handler("payment.captured")
async def on_payment_captured(session: AsyncSession, payload: dict[str, Any]) -> None:
    logger.info("Payment captured: payment_id=%s order_id=%s",
                payload.get("payment_id"), payload.get("order_id"))
    await _sync_order_status(session, payload=payload,
                             target_status_name=ORDER_STATUS_PAID)
```

**Règles** :
- Nommer la fonction `on_<event_name>` (snake_case).
- Décorée par `@outbox_handler("<event.type>")` — le string doit matcher
  une constante `EVENT_*` du publisher.
- Signature : `(session: AsyncSession, payload: dict[str, Any]) -> None`.
- Si le handler n'utilise pas la session, la nommer `_session`.
- **Idempotent** : un même event peut être rejoué.

---

## 5. Gestion d'erreurs

### 5.1 Exceptions métier

Définies dans le service qui les lève, suffixées `Error` :

```python
class PaymentNotManualError(RuntimeError):
    """Raised when a payment does not belong to a manual provider."""

class PaymentNotDocumentValidatedError(RuntimeError):
    """Raised when a payment is not associated with a document workflow."""
```

**Règles** :
- Hériter de `RuntimeError` pour les erreurs métier transientes.
- Hériter de `Exception` (via une base custom) pour les hiérarchies plus
  larges (`PaymentProviderError` → `UnknownPaymentProviderError`).
- Une docstring d'une ligne suffit.

### 5.2 Conversion en AppError (routes et services exposés)

```python
from app.core.errors import AppError

try:
    result = await approve_manual_payment(session, ...)
except PaymentNotManualError as e:
    await session.rollback()
    raise AppError(
        code="payment.not_manual",
        status_code=400,
        message=str(e),
        details={"payment_id": str(payment_id), "provider_code": payment.provider_code},
    ) from e
except RecordNotFoundError as e:
    raise AppError(
        code="payment.not_found",
        status_code=404,
        message=f"Payment {payment_id} not found",
        details={"payment_id": str(payment_id)},
    ) from e
```

**Règles** :
- Lever **AppError** (et non `HTTPException`) pour toutes les erreurs applicatives.
- Respecter le contrat payload géré globalement :
  `{ "error": { "code", "message", "details" } }`.
- Le `code` est **stable**, en snake_case avec segments (`domain.subdomain.what`) et
  doit être déclaré dans `docs/development/ERROR_CODES.md`.
- `details` contient uniquement des primitives JSON-serializables utiles au front/log.
- Les utilitaires et providers appelés par les routes (ex: paiement, IA, storage)
  lèvent aussi `AppError` pour éviter des formats d'erreur hétérogènes.
- Toujours `from e` pour préserver la stack trace.
- `await session.rollback()` avant de re-raise quand on est dans un workflow
  qui a déjà commencé à muter la session.
- Codes HTTP : `400` = input invalide, `403` = ownership, `404` = absent,
  `409` = conflit métier, `500` = inattendu, `502/503` = dépendance externe.

### 5.3 Cas spéciaux

- Le format FastAPI natif est conservé pour la validation request (`422`).
- Les exceptions inattendues non mappées sont gérées par le handler global
  (`internal.server_error`) sans exposer de détail sensible.

---

## 6. Tests

### 6.1 Organisation

- `tests/api/` = tests d'endpoints (peuvent toucher la DB de test).
- `tests/test_<module>.py` = tests unitaires de services/CRUD (mockés).
- Un fichier de test par phase fonctionnelle pour les refontes :
  `test_phase_<code>_<aspect>.py`.

### 6.2 Fixtures et patterns

```python
@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

@pytest.mark.anyio
async def test_<scenario>_<expected>(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    session.add = Mock()

    payment = cast(
        Payment,
        SimpleNamespace(id=uuid4(), order_id=uuid4(), ...),
    )
    monkeypatch.setattr(crud_payment, "get_by_provider_reference",
                        AsyncMock(return_value=payment))
    ...
    assert ...
```

**Règles** :
- Marker `@pytest.mark.anyio` sur tous les tests async + fixture `anyio_backend`.
- Pour mocker un objet du domaine : `cast(Payment, SimpleNamespace(...))`.
- `AsyncMock()` pour les sessions et les fonctions async.
- `Mock()` pour `session.add` (sync).
- Nom du test descriptif : `test_<sujet>_<action>_<résultat_attendu>`.
- Préférer **monkeypatch sur l'instance/string path** (`monkeypatch.setattr(crud_payment, "method", AsyncMock(...))`) plutôt que sur la classe.
- Quand un test appelle directement une fonction de route : `pytest.raises(AppError)`
  + assertion sur `exc.code`.
- Quand un test passe par `TestClient` : assertion sur `response.json()["error"]["code"]`
  (pas sur `detail`).

### 6.3 Anti-patterns à éviter

- Pas de `time.sleep` ou retry loops dans les tests.
- Pas de patch global qui fuit entre tests — toujours utiliser
  `monkeypatch` (qui auto-nettoie).
- Pas de tests qui appellent une vraie DB sauf dans `tests/api/` avec une
  fixture de session dédiée.
- Pas de dependence ordering entre tests.

---

## 7. Migrations Alembic

### 7.1 Nommage du fichier

```
<revision_id>_<description_snake_case>.py
```

Exemple : `1a2c9e5f7b31_drop_legacy_payzen_columns_from_payments.py`

### 7.2 Structure

```python
"""<Description courte>

Revision ID: <revision_id>
Revises: <down_revision>
Create Date: 2026-...
"""

revision: str = "<revision_id>"
down_revision: str = "<down_revision>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ... opérations ...


def downgrade() -> None:
    # ... opérations inverses ...
```

**Règles** :
- **Toujours fournir un `downgrade()` fonctionnel** (rollback testé).
- Migrations destructives (drop colonne) en **2 étapes minimum** :
  1. Ajouter la nouvelle colonne + backfill (migration N).
  2. Supprimer l'ancienne colonne (migration N+1).
- Pour un backfill complexe : utiliser `sa.table()` + `op.bulk_insert()` ou
  une boucle `connection.execute()` plutôt que du SQL raw quand c'est portable.
- Indexer les FK et les champs souvent filtrés.

---

## 8. Imports et typage

### 8.1 Ordre des imports

1. `from __future__ import annotations` (si nécessaire, pour les
   références cycliques ou les types modernes en runtime ancien).
2. Stdlib (`import uuid`, `from typing import ...`).
3. Tiers (`from fastapi import ...`, `from sqlmodel import ...`).
4. Locaux (`from app.features.payment...`).

Trié alphabétiquement à l'intérieur de chaque bloc (ruff le fait).

### 8.2 Types modernes

- `dict[str, Any]` pas `Dict[str, Any]`.
- `list[Foo]` pas `List[Foo]`.
- `str | None` pas `Optional[str]`.
- `Type | None` pas `Union[Type, None]`.

### 8.3 Annotations

- **Toutes les fonctions publiques** ont une annotation de retour
  (`-> Payment`, `-> None`, `-> dict[str, Any]`).
- Les paramètres `session: AsyncSession`, `payment: Payment`, `*, user: User | None`.
- Pour les configs/payloads JSON : `dict[str, Any]` (et non `dict`).

---

## 9. Logging et commentaires

### 9.1 Logging

```python
logger = logging.getLogger(__name__)

logger.info("Payment captured: payment_id=%s order_id=%s",
            payload.get("payment_id"), payload.get("order_id"))
```

**Règles** :
- **Toujours `logger = logging.getLogger(__name__)`** en tête de fichier.
- **Lazy formatting** (`%s` + args) — pas de f-string dans les `.info/.warning`
  (évite la sérialisation si le niveau est désactivé).
- Format clé=valeur lisible : `payment_id=%s, status=%s` plutôt que
  `"Payment %s with status %s"`.
- `info` = workflow normal, `warning` = anomalie récupérable,
  `error` = échec inattendu, `debug` = trace fine.

### 9.2 Commentaires

- **Par défaut, pas de commentaire**. Un nom de variable/fonction clair suffit.
- **Commenter le pourquoi**, jamais le quoi : raison non-évidente,
  contrainte cachée, workaround d'un bug spécifique.
- Pas de docstrings multi-paragraphes — une ligne max sauf API publique
  d'un module.
- Pas de commentaires "historiques" (`# fix issue #123`, `# added for X`) —
  ça vit dans le commit message.

---

## 10. Style async et transactions

### 10.1 Patterns transactionnels

```python
try:
    # 1. Lecture + mutation
    payment = await crud_payment.read(session, id=payment_id)
    payment.payment_status_id = new_status.id
    session.add(payment)

    # 2. Publication outbox dans la MÊME transaction
    await outbox_registry.publish(session=session, event_type=..., payload=...)

    # 3. Commit
    await session.commit()
    await session.refresh(payment)
except SomeKnownError as e:
    await session.rollback()
    raise AppError(
        code="domain.action.failed",
        status_code=400,
        message=str(e),
        details={"reason": type(e).__name__},
    ) from e
except AppError:
    await session.rollback()
    raise
except Exception:
    await session.rollback()
    raise
```

**Règles** :
- **Une seule transaction par requête HTTP** : commit/rollback dans la route.
- Les services internes appellent `session.add(...)` mais **ne commitent jamais**.
- Toujours appeler `session.rollback()` en cas d'erreur avant de relancer
  ou de retourner une erreur 4xx/5xx.
- L'event outbox est publié **avant** le commit (garantie d'atomicité).
- `await session.refresh(record)` après commit si on retourne le record au client.

### 10.2 Async

- Toutes les I/O (DB, HTTP externe, stockage) sont `async`.
- Pas de `asyncio.run(...)` dans le code applicatif — c'est FastAPI/ARQ
  qui gère la boucle.
- Pour les libs sync uniquement : `await asyncio.to_thread(...)` ou
  `loop.run_in_executor(...)`.

---

## 11. Configuration et secrets

- Tout passe par `app.core.config.settings` (Pydantic Settings).
- Les noms d'env vars sont en **UPPER_SNAKE_CASE** :
  `PAYZEN_USERNAME`, `FILE_STORAGE_BACKEND`, `CLAMAV_ENABLED`.
- Les flags booléens : `<DOMAIN>_<FEATURE>_ENABLED` (`CLAMAV_ENABLED`,
  `PAYMENT_NOTIFICATIONS_EMAIL_ENABLED`).
- Pas de secret en clair dans les commits — utiliser `.env.example` comme template.

---

## 12. Linting et CI

### 12.1 Outils

- **Ruff** : lint + format. Configuration dans `pyproject.toml`.
- **Mypy** : check types stricts sur le code, plus permissif sur les tests.
- **Pytest** : tests + coverage.

### 12.2 Avant chaque commit

```powershell
# Depuis backend/
ruff check app/ ; ruff format app/ ; pytest -q
```

Aucune erreur ruff, aucun test rouge. Mypy peut être en warning sur
certaines zones legacy mais ne doit pas régresser.

### 12.3 Désactivation locale

Si un fichier doit ignorer une règle mypy spécifique, le faire en tête :
```python
# mypy: disable-error-code="assignment,misc,override"
```
Ne pas ajouter de nouvelles désactivations sans justification.

---

## 13. Quand modifier ce document

Ajouter une section / mettre à jour une règle quand :
- Une convention émerge dans plusieurs PRs (formaliser tôt).
- Un agent IA ou un nouveau dev pose la même question deux fois.
- Une règle de ce doc devient obsolète (la noter comme deprecated avant
  suppression).

Le doc vit avec le code — pas une référence morte.
