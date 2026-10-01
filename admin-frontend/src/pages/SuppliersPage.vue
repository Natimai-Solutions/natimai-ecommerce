<template>
  <q-page class="admin-page">
    <PageHeader title="Fournisseurs">
      <template #hint>
        Un fournisseur est déclaré ici avec son entrepôt d'origine et son régime douanier. Sa
        méthode d'approvisionnement décide comment ses articles arrivent : à la main, par fichier
        CSV / Excel, ou par une intégration API.
      </template>
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          :loading="loading"
          @click="load"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          label="Nouveau fournisseur"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <q-table
      :rows="rows"
      :columns="columns"
      row-key="code"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-code="props">
        <q-td :props="props" class="font-mono">{{ props.row.code }}</q-td>
      </template>
      <template #body-cell-kind="props">
        <q-td :props="props">
          <StatusTag :label="kindLabel(props.row.kind)" :icon="kindIcon(props.row.kind)" />
          <span v-if="props.row.kind === 'api'" class="text-caption text-muted font-mono q-ml-xs">
            {{ props.row.adapter_key }}
          </span>
        </q-td>
      </template>
      <template #body-cell-origin="props">
        <q-td :props="props">{{ placeName(props.row.origin_place_id) }}</q-td>
      </template>
      <template #body-cell-domestic="props">
        <q-td :props="props">
          <StatusTag v-if="props.row.is_domestic" label="Local — sans douane" icon="ph:map-pin" />
          <StatusTag v-else label="Import — CAF + douane" icon="ph:globe-hemisphere-west" />
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <StatusTag
            v-if="!props.row.is_active"
            label="Désactivé"
            tone="neutral"
            icon="ph:minus-circle"
          />
          <span v-else-if="props.row.kind === 'api' && !props.row.configured">
            <StatusTag label="À configurer" tone="warn" icon="ph:warning" />
            <q-tooltip>Identifiants absents de l'environnement</q-tooltip>
          </span>
          <StatusTag v-else label="Actif" tone="ok" icon="ph:check-circle" />
          <span v-if="props.row.kind === 'api'" class="text-caption text-muted q-ml-xs">
            {{
              props.row.sync_enabled
                ? props.row.sync_interval_hours > 0
                  ? `sync toutes les ${props.row.sync_interval_hours} h`
                  : 'sync manuelle'
                : 'sync désactivée'
            }}
          </span>
          <q-chip
            v-if="props.row.sku_allowlist?.length"
            dense
            icon="ph:list-checks"
            class="q-ml-xs"
            :label="`${props.row.sku_allowlist.length} réf. suivie(s)`"
            data-testid="supplier-allowlist-badge"
          >
            <q-tooltip>Seules ces références sont créées et rafraîchies</q-tooltip>
          </q-chip>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            round
            dense
            v-if="shopConfig.moduleOn('file_import')"
            icon="ph:file-arrow-up"
            :disable="!props.row.is_active"
            @click="openImport(props.row)"
          >
            <q-tooltip>Importer un catalogue CSV / Excel</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.kind === 'api'"
            flat
            round
            dense
            icon="ph:arrows-clockwise"
            :disable="!props.row.is_active || !props.row.configured"
            :loading="busy === props.row.code"
            @click="onSync(props.row)"
          >
            <q-tooltip>Lancer la synchronisation catalogue</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.kind === 'api'"
            flat
            round
            dense
            icon="ph:heartbeat"
            :disable="!props.row.is_active"
            @click="onHealth(props.row)"
          >
            <q-tooltip>Tester la connexion</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.kind !== 'manual'"
            flat
            round
            dense
            icon="ph:tree-structure"
            data-testid="supplier-categories"
            @click="openCategories(props.row)"
          >
            <q-tooltip>Catégories : où ranger les articles de ce fournisseur</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.kind !== 'manual'"
            flat
            round
            dense
            icon="ph:list-checks"
            :disable="!props.row.is_active"
            data-testid="supplier-allowlist"
            @click="openAllowlist(props.row)"
          >
            <q-tooltip>Références suivies (liste blanche de SKU)</q-tooltip>
          </q-btn>
          <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.is_active"
            flat
            round
            dense
            icon="ph:prohibit"
            color="negative"
            data-testid="supplier-deactivate"
            @click="openDeactivate(props.row)"
          >
            <q-tooltip>Désactiver (les articles gardent leur lien)</q-tooltip>
          </q-btn>
          <q-btn
            v-else
            flat
            round
            dense
            icon="ph:power"
            :loading="busy === props.row.code"
            data-testid="supplier-reactivate"
            @click="onReactivate(props.row)"
          >
            <q-tooltip>Réactiver (synchronisations comprises)</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">Aucun fournisseur déclaré.</div>
      </template>
    </q-table>

    <!-- Désactivation -->
    <q-dialog v-model="deactivateDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Désactiver {{ deactivating?.name }}</h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <p class="q-mb-sm">
            Plus aucune synchronisation ni vérification au paiement. Le fournisseur reste déclaré et
            peut être réactivé à tout moment ; rien n'est supprimé.
          </p>
          <p class="text-subtle q-mb-xs">Et ses articles ?</p>
          <q-option-group
            v-model="deactivateProducts"
            :options="deactivateOptions"
            type="radio"
            data-testid="supplier-deactivate-products"
          />
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn v-close-popup flat no-caps label="Annuler" />
          <q-btn
            color="negative"
            unelevated
            no-caps
            label="Désactiver"
            :loading="busy === deactivating?.code"
            data-testid="supplier-deactivate-confirm"
            @click="confirmDeactivate"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Création / édition -->
    <q-dialog v-model="formDialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editing ? `Modifier ${editing.name}` : 'Nouveau fournisseur' }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submitForm">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>

            <div class="row" style="gap: 8px">
              <q-input
                v-model="form.code"
                label="Code *"
                hint="Clé technique (a-z, 0-9, _), immuable après création"
                outlined
                dense
                class="col"
                :disable="!!editing"
                :rules="editing ? [] : codeRules"
              />
              <q-input v-model="form.name" label="Nom *" outlined dense class="col" :rules="req" />
            </div>

            <q-select
              v-model="form.kind"
              :options="kindOptions"
              label="Méthode d'approvisionnement *"
              outlined
              dense
              emit-value
              map-options
            />

            <q-select
              v-if="form.kind === 'api'"
              v-model="form.adapter_key"
              :options="adapterOptions"
              label="Intégration *"
              hint="Le code de l'intégration doit exister dans l'application"
              outlined
              dense
              emit-value
              map-options
            />
            <AppNotice
              v-if="form.kind === 'api' && selectedAdapter && !selectedAdapter.configured"
              tone="warning"
              dense
            >
              Les identifiants de cette intégration ne sont pas configurés dans l'environnement du
              serveur : la synchronisation restera impossible tant qu'ils manquent.
            </AppNotice>

            <q-select
              v-model="form.origin_place_id"
              :options="placeOptions"
              label="Entrepôt d'origine (lieu)"
              hint="Recopié sur les articles : premier tronçon logistique et suivi"
              outlined
              dense
              emit-value
              map-options
              clearable
            />

            <q-toggle
              v-model="form.is_domestic"
              label="Fournisseur local — même territoire douanier que notre entrepôt"
            />
            <div class="text-caption text-muted q-ml-md">
              {{
                form.is_domestic
                  ? 'Articles créés en mode « local » : coût + marge + taxe, sans douane ni fret import.'
                  : 'Articles créés en mode « import » : CAF (coût + fret + assurance), douane, marge, taxe.'
              }}
            </div>

            <div class="row" style="gap: 8px">
              <q-select
                v-model="form.price_currency"
                :options="currencyOptions"
                label="Devise des prix"
                hint="Quand la source ne la précise pas"
                outlined
                dense
                emit-value
                map-options
                clearable
                class="col"
              />
              <q-input
                v-if="form.kind === 'api'"
                v-model.number="form.sync_interval_hours"
                label="Cadence catalogue (heures)"
                hint="0 = jamais planifiée"
                type="number"
                min="0"
                outlined
                dense
                class="col"
              />
            </div>

            <template v-if="form.kind !== 'manual'">
              <q-toggle
                v-model="form.import_as_draft"
                label="Nouveaux articles en brouillon"
                data-testid="supplier-import-as-draft"
              />
              <div class="text-caption text-muted q-ml-md">
                Un article créé par une synchronisation ou un import reste invisible en vitrine
                (enrichi et rafraîchi quand même) jusqu'à ce que vous le publiiez depuis la page
                Articles. Les articles existants ne changent pas.
              </div>
              <div class="row q-mt-sm" style="gap: 8px">
                <q-input
                  v-model="form.min_quantity"
                  label="Quantité minimale (import fichier)"
                  hint="Vide = pas de seuil"
                  type="number"
                  min="0"
                  outlined
                  dense
                  class="col"
                  data-testid="supplier-min-quantity"
                />
                <q-input
                  v-model="form.min_price"
                  label="Prix d'achat minimal (import fichier)"
                  hint="Dans la devise du fichier ; vide = pas de seuil"
                  type="number"
                  min="0"
                  step="any"
                  outlined
                  dense
                  class="col"
                  data-testid="supplier-min-price"
                />
              </div>
              <div class="text-caption text-muted q-ml-md">
                Sous le seuil, une référence nouvelle n'est pas créée et un article existant est mis
                à jour puis retiré de la vitrine (il revient quand il repasse au-dessus). Une ligne
                sans quantité n'est pas jugée sur la quantité.
              </div>
              <q-select
                v-model="form.unmapped_category_action"
                :options="unmappedOptions"
                label="Catégories sans règle"
                hint="Les règles se règlent par l'icône « Catégories » de la liste"
                outlined
                dense
                emit-value
                map-options
                class="q-mt-sm"
                data-testid="supplier-unmapped-action"
              />
            </template>

            <template v-if="form.kind === 'api'">
              <q-toggle v-model="form.sync_enabled" label="Synchronisations autorisées" />
              <template v-if="selectedAdapter?.supports_purchase_orders">
                <q-toggle
                  v-model="form.auto_purchase_order"
                  label="Commande fournisseur automatique à l'encaissement"
                  data-testid="supplier-auto-po"
                />
                <div class="text-caption text-muted q-ml-md">
                  Chaque commande client payée (hors départ groupé) déclenche une commande chez ce
                  fournisseur pour ses articles, livrée à l'entrepôt principal (son adresse doit
                  être renseignée dans Trajets et lieux). Suivi : Commandes fournisseurs.
                </div>
              </template>
              <q-select
                v-model="form.default_categories"
                label="Catégories fournisseur synchronisées"
                hint="Tapez une catégorie puis Entrée"
                multiple
                use-chips
                use-input
                hide-dropdown-icon
                new-value-mode="add-unique"
                input-debounce="0"
                outlined
                dense
              />
              <div v-if="adapterFields.length" class="q-gutter-sm">
                <h3 class="admin-subtitle q-mb-none">Réglages de l'intégration</h3>
                <template v-for="field in adapterFields" :key="field.key">
                  <q-select
                    v-if="field.kind === 'choice'"
                    v-model="form.settings[field.key]"
                    :options="choiceOptions(field)"
                    :label="field.label"
                    :hint="field.hint || undefined"
                    outlined
                    dense
                    clearable
                    emit-value
                    map-options
                  />
                  <q-input
                    v-else
                    v-model="form.settings[field.key]"
                    :label="field.label"
                    :hint="fieldHint(field)"
                    :type="field.kind === 'json' ? 'textarea' : 'text'"
                    :autogrow="field.kind === 'json'"
                    :inputmode="field.kind === 'number' ? 'decimal' : undefined"
                    :input-class="field.kind === 'json' ? 'font-mono' : undefined"
                    outlined
                    dense
                  />
                </template>
                <AppNotice v-if="isFeedForm" tone="info" dense>
                  Le fichier est téléchargé à la cadence ci-dessus puis importé comme un fichier
                  déposé à la main (mapping de colonnes, seuils, règles de catégories). Le mapping
                  se règle depuis l'icône « Importer » → « Lire le flux ». Les portails qui exigent
                  JavaScript ou un captcha ne sont pas pris en charge.
                </AppNotice>
              </div>
              <div v-if="isFeedForm && editing" class="q-gutter-sm" data-testid="feed-credentials">
                <h3 class="admin-subtitle q-mb-none">
                  Identifiants du portail
                  <StatusTag
                    v-if="editing.has_credentials"
                    tone="ok"
                    icon="ph:lock-key"
                    label="Enregistrés"
                    class="q-ml-sm"
                  />
                </h3>
                <div class="text-caption text-muted">
                  Chiffrés sur le serveur, jamais réaffichés. Saisissez-les pour les remplacer.
                </div>
                <div class="row" style="gap: 8px">
                  <q-input
                    v-model="credentials.username"
                    label="Identifiant"
                    autocomplete="off"
                    outlined
                    dense
                    class="col"
                  />
                  <q-input
                    v-model="credentials.password"
                    label="Mot de passe"
                    type="password"
                    autocomplete="new-password"
                    outlined
                    dense
                    class="col"
                  />
                </div>
                <div class="row" style="gap: 8px">
                  <q-btn
                    outline
                    dense
                    no-caps
                    icon="ph:floppy-disk"
                    label="Enregistrer les identifiants"
                    :disable="!credentials.username || !credentials.password"
                    :loading="credentialsBusy"
                    @click="onSaveCredentials"
                  />
                  <q-btn
                    v-if="editing.has_credentials"
                    flat
                    dense
                    no-caps
                    icon="ph:trash"
                    label="Effacer"
                    :loading="credentialsBusy"
                    @click="onClearCredentials"
                  />
                </div>
              </div>
              <AppNotice v-else-if="isFeedForm" tone="info" dense>
                Enregistrez d'abord le fournisseur : les identifiants du portail se saisissent
                ensuite, en le modifiant.
              </AppNotice>
            </template>

            <div class="row" style="gap: 8px">
              <q-input
                v-model="form.contact_email"
                label="Email de contact"
                outlined
                dense
                class="col"
              />
              <q-input v-model="form.contact_phone" label="Téléphone" outlined dense class="col" />
            </div>
            <q-input v-model="form.notes" label="Notes" type="textarea" autogrow outlined dense />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              label="Enregistrer"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Références suivies (liste blanche de SKU) -->
    <q-dialog v-model="allowlistDialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Références suivies — {{ allowlistSupplier?.name }}</h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="allowlistError" tone="error" dense>{{ allowlistError }}</AppNotice>
          <div class="text-caption text-muted">
            Collez ici les références fournisseur (SKU) que la boutique vend, une par ligne. Liste
            vide : tout le catalogue synchronisé est suivi. Liste renseignée : seules ces références
            sont créées et rafraîchies (prix / stock), et les articles de ce fournisseur hors liste
            sont retirés de la vitrine dès l'enregistrement. Une référence inconnue est créée par la
            prochaine synchronisation catalogue.
          </div>
          <q-input
            v-model="allowlistText"
            type="textarea"
            outlined
            dense
            autogrow
            :input-style="{ minHeight: '160px', fontFamily: 'monospace' }"
            placeholder="IM-12345&#10;IM-67890"
            data-testid="allowlist-text"
          />
          <div v-if="allowlistView" class="text-caption text-muted">
            {{ allowlistView.entries.length }} référence(s) — {{ allowlistView.known }} au
            catalogue, {{ allowlistView.unknown.length }} à créer à la prochaine synchronisation,
            {{ allowlistView.outside }} article(s) hors liste retiré(s) de la vitrine.
            <span v-if="allowlistView.deactivated">
              ({{ allowlistView.deactivated }} retiré(s) à l'instant)
            </span>
          </div>
          <q-expansion-item
            v-if="allowlistView?.entries.length"
            dense
            label="Détail des références"
            class="q-mt-xs"
          >
            <q-markup-table dense flat bordered>
              <thead>
                <tr>
                  <th class="text-left">Référence</th>
                  <th class="text-left">Article</th>
                  <th class="text-left">État</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in allowlistView.entries" :key="e.supplier_sku">
                  <td class="font-mono">{{ e.supplier_sku }}</td>
                  <td>{{ e.product_name ?? '— à créer' }}</td>
                  <td>
                    <StatusTag
                      v-if="e.is_active === true"
                      label="en vitrine"
                      tone="ok"
                      icon="ph:eye"
                    />
                    <StatusTag
                      v-else-if="e.is_active === false"
                      label="masqué"
                      tone="neutral"
                      icon="ph:eye-slash"
                    />
                    <span v-else class="text-subtle">inconnu</span>
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
          </q-expansion-item>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps label="Fermer" v-close-popup />
          <q-btn
            color="primary"
            unelevated
            no-caps
            label="Enregistrer la liste"
            :loading="allowlistSaving"
            data-testid="allowlist-save"
            @click="saveAllowlist"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Catégories du fournisseur -->
    <q-dialog v-model="categoriesDialog">
      <q-card class="app-dialog app-dialog--xl">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Catégories — {{ categoriesOf?.name }}</h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="categoriesError" tone="error" dense>{{ categoriesError }}</AppNotice>
          <AppNotice v-if="categoriesNotice" tone="success" dense>{{ categoriesNotice }}</AppNotice>
          <p class="admin-hint">
            Les catégories que ce fournisseur donne à ses articles déjà en base, et où la boutique
            les range. Une règle sur la catégorie seule vaut pour toutes ses sous-catégories. Sans
            règle : {{ unmappedLabel }}. Les nouvelles règles valent pour les prochains imports ; «
            Réappliquer » y range aussi les articles existants (sauf catégorie choisie à la main).
          </p>
          <div v-if="categoriesLoading" class="text-center q-pa-md"><q-spinner size="2em" /></div>
          <CategoryPairsTable
            v-else
            :pairs="observed"
            :categories="categories"
            :saving="categoriesSaving"
            @save="saveSupplierRules"
          />
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps label="Fermer" v-close-popup />
          <q-btn
            outline
            no-caps
            icon="ph:arrows-counter-clockwise"
            label="Réappliquer aux articles existants"
            :loading="reapplying"
            data-testid="supplier-categories-reapply"
            @click="onReapply"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Import fichier -->
    <q-dialog v-model="importDialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Importer un catalogue — {{ importing?.name }}</h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="importError" tone="error" dense>{{ importError }}</AppNotice>

          <div v-if="importing?.adapter_key === FEED_ADAPTER_KEY" class="row items-center q-mb-sm">
            <q-btn
              outline
              no-caps
              dense
              icon="ph:cloud-arrow-down"
              label="Lire le flux"
              :loading="feedReading"
              data-testid="feed-inspect"
              @click="onReadFeed"
            />
            <span class="text-caption text-muted q-ml-sm">
              ou déposez un exemplaire du fichier ci-dessous
            </span>
            <q-space />
            <q-btn
              v-if="inspection"
              color="primary"
              unelevated
              no-caps
              dense
              icon="ph:floppy-disk"
              label="Enregistrer le mapping"
              :loading="mappingSaving"
              @click="onSaveFeedMapping"
            />
          </div>
          <q-file
            v-model="importFile"
            label="Fichier CSV ou Excel (.xlsx)"
            accept=".csv,.txt,.xlsx,.xlsm"
            outlined
            dense
            clearable
            @update:model-value="onFileChosen"
          >
            <template #prepend><q-icon name="ph:paperclip" /></template>
          </q-file>

          <template v-if="inspection">
            <div class="text-caption text-muted">
              {{ inspection.total_rows }} ligne(s) détectée(s) — colonnes :
              {{ inspection.headers.join(', ') }}
            </div>
            <h3 class="admin-subtitle q-mt-sm q-mb-none">Correspondance des colonnes</h3>
            <div class="text-caption text-muted q-mb-xs">
              Associez chaque champ de notre système à une colonne du fichier. Les champs marqués *
              sont obligatoires. La correspondance est mémorisée sur le fournisseur.
            </div>
            <div class="text-caption text-muted q-mb-xs">
              Un article déjà présent chez ce fournisseur est reconnu par sa référence, sinon par
              son code-barres EAN/UPC, sinon par marque + référence fabricant : mappez ces colonnes
              pour qu'un changement de référence ne crée pas de doublon. Un article saisi à la main
              et rattaché à ce fournisseur est adopté (son contenu est conservé). Les articles des
              autres fournisseurs ne sont jamais rapprochés.
            </div>
            <div class="row q-col-gutter-sm">
              <div
                v-for="target in inspection.mapping_targets"
                :key="target"
                class="col-12 col-md-6"
              >
                <q-select
                  v-model="mapping[target]"
                  :options="inspection.headers"
                  :label="mappingLabel(target)"
                  outlined
                  dense
                  clearable
                  options-dense
                />
              </div>
            </div>
            <q-select
              v-model="importDefaultCategory"
              :options="categoryOptions"
              label="Catégorie pour tout le fichier (facultatif)"
              hint="Pour les lignes qu'aucune règle ne place — utile sans colonne catégorie"
              outlined
              dense
              emit-value
              map-options
              clearable
              class="q-mt-sm"
              data-testid="import-default-category"
            />
            <div class="row q-mt-sm" style="gap: 8px">
              <q-input
                v-model="importMinQuantity"
                label="Quantité minimale (cet import)"
                hint="Réglage du fournisseur par défaut ; 0 = aucun seuil"
                type="number"
                min="0"
                outlined
                dense
                class="col"
                data-testid="import-min-quantity"
              />
              <q-input
                v-model="importMinPrice"
                label="Prix d'achat minimal (cet import)"
                hint="Dans la devise du fichier ; 0 = aucun seuil"
                type="number"
                min="0"
                step="any"
                outlined
                dense
                class="col"
                data-testid="import-min-price"
              />
            </div>
            <q-checkbox
              v-model="publishNew"
              dense
              class="q-mt-sm"
              label="Afficher les nouveaux articles en boutique sans attendre l’enrichissement Icecat"
            />
            <div class="text-caption text-muted q-mb-xs">
              Décoché, un article créé reste masqué tant qu’Icecat ne l’a pas reconnu (page
              Produits, filtre « Masqués », pour le publier ensuite).
            </div>
            <q-expansion-item dense label="Aperçu des premières lignes" class="q-mt-sm">
              <q-markup-table dense flat bordered>
                <thead>
                  <tr>
                    <th v-for="h in inspection.headers" :key="h" class="text-left">{{ h }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in inspection.sample_rows" :key="i">
                    <td v-for="h in inspection.headers" :key="h">{{ row[h] }}</td>
                  </tr>
                </tbody>
              </q-markup-table>
            </q-expansion-item>
          </template>

          <AppNotice v-if="queuedImport" tone="info" icon="ph:hourglass" dense>
            <q-spinner size="1em" class="q-mr-xs" />
            Import en tâche de fond ({{ queuedImport.totalRows }} lignes) — l'avancement se met à
            jour ici ; vous pouvez fermer cette fenêtre, le résultat restera dans le journal de
            synchronisation.
          </AppNotice>

          <AppNotice v-if="importResult" :tone="importResult.dry_run ? 'info' : 'success'" dense>
            <div>
              <strong>{{ importResult.dry_run ? 'Simulation' : 'Import' }}</strong> :
              {{ importResult.parsed_products }} article(s) lisible(s),
              {{ importResult.rejected_rows }} ligne(s) rejetée(s)
              <span v-if="!importResult.dry_run">
                — {{ importResult.statistics.new_products ?? 0 }} créé(s),
                {{ importResult.statistics.updated_products ?? 0 }} mis à jour,
                {{ importResult.statistics.adopted_products ?? 0 }} adopté(s),
                {{ importResult.statistics.ambiguous_products ?? 0 }} ambigu(s),
                {{ importResult.statistics.errors ?? 0 }} erreur(s)
                <template v-if="belowThresholdLine">— {{ belowThresholdLine }}</template>
                <span v-if="importResult.published_new">— publiés en boutique</span>
                <span v-else>— masqués jusqu’à enrichissement</span>
              </span>
              <span v-else>
                — {{ importResult.resolution.new ?? 0 }} nouveau(x),
                {{ importResult.resolution.updated ?? 0 }} reconnu(s),
                {{ importResult.resolution.adopted ?? 0 }} adopté(s),
                {{ importResult.resolution.ambiguous ?? 0 }} ambigu(s)
                <template v-if="importResult.resolution.filtered">
                  , {{ importResult.resolution.filtered }} écartée(s) par un filtre
                </template>
                <template v-if="importResult.resolution.below_threshold">
                  , {{ importResult.resolution.below_threshold }} sous le seuil
                </template>
              </span>
            </div>
            <div v-if="importResult.resolution_limited_to" class="text-caption">
              Fichier volumineux : reconnaissance simulée sur les
              {{ importResult.resolution_limited_to }} premières lignes seulement ; l'import réel
              tournera en tâche de fond.
            </div>
            <div v-if="importResult.dry_run && matchedByLine" class="text-caption">
              Reconnus par : {{ matchedByLine }}
            </div>
            <q-expansion-item
              v-if="importResult.sample_resolutions.length"
              dense
              :label="`Détail des ${importResult.sample_resolutions.length} premières lignes`"
              class="q-mt-xs"
            >
              <q-markup-table dense flat bordered>
                <thead>
                  <tr>
                    <th class="text-left">Référence</th>
                    <th class="text-left">Désignation</th>
                    <th class="text-left">Action</th>
                    <th class="text-left">Reconnu par</th>
                    <th class="text-left">Article existant</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="r in importResult.sample_resolutions"
                    :key="r.supplier_sku + r.action"
                    :class="r.action === 'ambiguous' ? 'text-negative' : ''"
                  >
                    <td class="font-mono">{{ r.supplier_sku }}</td>
                    <td>{{ r.name }}</td>
                    <td>{{ actionLabel(r.action) }}</td>
                    <td>{{ r.match_key ? matchKeyLabel(r.match_key) : '—' }}</td>
                    <td>{{ r.product_name ?? r.message ?? '—' }}</td>
                  </tr>
                </tbody>
              </q-markup-table>
            </q-expansion-item>
            <q-expansion-item
              v-if="importResult.dry_run && importResult.category_pairs?.length"
              dense
              default-opened
              :label="`Catégories du fichier (${importResult.category_pairs.length})`"
              class="q-mt-xs"
            >
              <CategoryPairsTable
                :pairs="importResult.category_pairs"
                :categories="categories"
                :saving="categoriesSaving"
                count-label="Lignes"
                @save="saveImportRules"
              />
            </q-expansion-item>
            <ul v-if="importResult.row_errors.length" class="q-mb-none">
              <li v-for="e in importResult.row_errors.slice(0, 10)" :key="e.row_number">
                Ligne {{ e.row_number }} : {{ e.message }}
              </li>
            </ul>
            <ul v-if="importResult.sync_errors.length" class="q-mb-none">
              <li v-for="e in importResult.sync_errors.slice(0, 10)" :key="e.sku">
                {{ e.sku }} : {{ e.error }}
              </li>
            </ul>
          </AppNotice>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps label="Fermer" v-close-popup />
          <q-btn
            outline
            no-caps
            label="Simuler"
            :disable="!importFile || !inspection"
            :loading="importBusy === 'dry'"
            @click="runImport(true)"
          />
          <q-btn
            color="primary"
            unelevated
            no-caps
            label="Importer"
            :disable="!importFile || !inspection || !!queuedImport"
            :loading="importBusy === 'run'"
            @click="runImport(false)"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  MAPPING_TARGET_LABELS,
  MATCH_KEY_LABELS,
  RESOLUTION_ACTION_LABELS,
  SUPPLIER_KIND_LABELS,
  checkSupplierHealth,
  createSupplier,
  deactivateSupplier,
  getImportStatus,
  getSkuAllowlist,
  importCatalogFile,
  inspectCatalogFile,
  listAdapters,
  listSuppliers,
  saveSkuAllowlist,
  triggerProductSync,
  updateSupplier,
  type AdapterDescriptor,
  type AllowlistView,
  type FileImportResponse,
  type FileImportStatus,
  type FileInspectResponse,
  type ImportMatchKey,
  type ImportResolutionAction,
  type Supplier,
  type SupplierCreate,
  type SupplierKind,
  type SupplierWithdrawal,
  UNMAPPED_ACTION_LABELS,
  listObservedCategories,
  reapplyCategoryMappings,
  saveCategoryMappings,
  type CategoryMappingWrite,
  type ObservedCategory,
  type UnmappedCategoryAction,
  FEED_ADAPTER_KEY,
  deleteSupplierCredentials,
  inspectSupplierFeed,
  saveSupplierCredentials,
} from '@/api/suppliers';
import { categoryLabel, listAdminCategories, type AdminCategory } from '@/api/categories';
import CategoryPairsTable from '@/components/CategoryPairsTable.vue';
import { useShopConfigStore } from '@/stores/shopConfig';
import { listPlaces, type Place } from '@/api/logistics';
import { extractApiError } from '@/api/errors';
import {
  fieldsFromSchema,
  fromFormValue,
  toFormValue,
  type SchemaField,
} from '@/utils/settingsSchema';

const shopConfig = useShopConfigStore();
const rows = ref<Supplier[]>([]);
const adapters = ref<AdapterDescriptor[]>([]);
const places = ref<Place[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const busy = ref<string | null>(null);

const req = [(v: string) => (!!v && v.trim().length > 0) || 'Requis'];
const codeRules = [
  (v: string) => (!!v && /^[a-z0-9][a-z0-9_]{1,49}$/.test(v.trim().toLowerCase())) || 'a-z, 0-9, _',
];

const columns: QTableColumn[] = [
  { name: 'name', label: 'Nom', field: 'name', align: 'left' },
  { name: 'code', label: 'Code', field: 'code', align: 'left' },
  { name: 'kind', label: 'Méthode', field: 'kind', align: 'left' },
  { name: 'origin', label: 'Entrepôt d’origine', field: 'origin_place_id', align: 'left' },
  { name: 'domestic', label: 'Régime', field: 'is_domestic', align: 'left' },
  { name: 'status', label: 'État', field: 'is_active', align: 'left' },
  { name: 'actions', label: '', field: 'code', align: 'right' },
];

const kindOptions = (Object.keys(SUPPLIER_KIND_LABELS) as SupplierKind[]).map((k) => ({
  label: SUPPLIER_KIND_LABELS[k],
  value: k,
}));
const currencyOptions = ['XPF', 'EUR', 'USD'].map((c) => ({ label: c, value: c }));
const adapterOptions = computed(() =>
  adapters.value.map((a) => ({
    label: a.configured ? a.display_name : `${a.display_name} (identifiants manquants)`,
    value: a.key,
  })),
);
const placeOptions = computed(() =>
  places.value.map((p) => ({ label: p.code ? `${p.name} (${p.code})` : p.name, value: p.id })),
);

function kindLabel(kind: SupplierKind): string {
  return SUPPLIER_KIND_LABELS[kind] ?? kind;
}
function kindIcon(kind: SupplierKind): string {
  return kind === 'api' ? 'ph:plugs-connected' : kind === 'file' ? 'ph:file-arrow-up' : 'ph:hand';
}
function placeName(id: string | null): string {
  if (!id) return '—';
  const place = places.value.find((p) => p.id === id);
  return place ? (place.code ? `${place.name} (${place.code})` : place.name) : id;
}
function mappingLabel(target: string): string {
  return MAPPING_TARGET_LABELS[target] ?? target;
}
function actionLabel(action: ImportResolutionAction): string {
  return RESOLUTION_ACTION_LABELS[action] ?? action;
}
function matchKeyLabel(key: ImportMatchKey): string {
  return MATCH_KEY_LABELS[key] ?? key;
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    [rows.value, adapters.value, places.value] = await Promise.all([
      listSuppliers(),
      listAdapters(),
      listPlaces(),
    ]);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

// --- Formulaire -----------------------------------------------------------

interface FormState {
  code: string;
  name: string;
  kind: SupplierKind;
  adapter_key: string | null;
  origin_place_id: string | null;
  is_domestic: boolean;
  sync_enabled: boolean;
  import_as_draft: boolean;
  min_quantity: string;
  min_price: string;
  sync_interval_hours: number;
  default_categories: string[];
  unmapped_category_action: UnmappedCategoryAction;
  auto_purchase_order: boolean;
  price_currency: string | null;
  settings: Record<string, string>;
  contact_email: string;
  contact_phone: string;
  notes: string;
}

function emptyForm(): FormState {
  return {
    code: '',
    name: '',
    kind: 'manual',
    adapter_key: null,
    origin_place_id: null,
    is_domestic: false,
    sync_enabled: true,
    import_as_draft: false,
    min_quantity: '',
    min_price: '',
    sync_interval_hours: 0,
    default_categories: [],
    unmapped_category_action: 'auto',
    auto_purchase_order: false,
    price_currency: null,
    settings: {},
    contact_email: '',
    contact_phone: '',
    notes: '',
  };
}

const formDialog = ref(false);
const editing = ref<Supplier | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const form = reactive<FormState>(emptyForm());

const selectedAdapter = computed(
  () => adapters.value.find((a) => a.key === form.adapter_key) ?? null,
);

function openCreate() {
  editing.value = null;
  dialogError.value = null;
  Object.assign(form, emptyForm());
  formDialog.value = true;
}

function openEdit(supplier: Supplier) {
  editing.value = supplier;
  dialogError.value = null;
  credentials.username = '';
  credentials.password = '';
  const adapter = adapters.value.find((a) => a.key === supplier.adapter_key);
  const fields = fieldsFromSchema(adapter?.settings_schema, SETTING_LABELS);
  const settings: Record<string, string> = {};
  for (const [k, v] of Object.entries(supplier.settings ?? {})) {
    settings[k] = toFormValue(
      fields.find((f) => f.key === k),
      v,
    );
  }
  Object.assign(form, {
    code: supplier.code,
    name: supplier.name,
    kind: supplier.kind,
    adapter_key: supplier.adapter_key,
    origin_place_id: supplier.origin_place_id,
    is_domestic: supplier.is_domestic,
    sync_enabled: supplier.sync_enabled,
    import_as_draft: supplier.import_as_draft,
    min_quantity: supplier.min_quantity != null ? String(Number(supplier.min_quantity)) : '',
    min_price: supplier.min_price != null ? String(Number(supplier.min_price)) : '',
    sync_interval_hours: supplier.sync_interval_hours,
    default_categories: [...(supplier.default_categories ?? [])],
    unmapped_category_action: supplier.unmapped_category_action ?? 'auto',
    auto_purchase_order: !!supplier.auto_purchase_order,
    price_currency: supplier.price_currency,
    settings,
    contact_email: supplier.contact_email ?? '',
    contact_phone: supplier.contact_phone ?? '',
    notes: supplier.notes ?? '',
  });
  formDialog.value = true;
}

/** Champ numérique facultatif : vide → null. */
function optionalNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || String(value).trim() === '') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function buildPayload(): SupplierCreate {
  const settings: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(form.settings)) {
    const value = fromFormValue(
      adapterFields.value.find((f) => f.key === k),
      String(v ?? ''),
    );
    if (value !== undefined) settings[k] = value;
  }
  const categories = form.default_categories.map((c) => c.trim()).filter(Boolean);
  return {
    code: form.code.trim().toLowerCase(),
    name: form.name.trim(),
    kind: form.kind,
    adapter_key: form.kind === 'api' ? form.adapter_key : null,
    origin_place_id: form.origin_place_id,
    is_domestic: form.is_domestic,
    sync_enabled: form.sync_enabled,
    import_as_draft: form.kind !== 'manual' && form.import_as_draft,
    unmapped_category_action: form.unmapped_category_action,
    auto_purchase_order:
      form.kind === 'api' && !!selectedAdapter.value?.supports_purchase_orders
        ? form.auto_purchase_order
        : false,
    min_quantity: optionalNumber(form.min_quantity),
    min_price: optionalNumber(form.min_price),
    sync_interval_hours: form.kind === 'api' ? Number(form.sync_interval_hours) || 0 : 0,
    default_categories: categories.length ? categories : null,
    price_currency: form.price_currency,
    settings: form.kind === 'api' ? settings : null,
    contact_email: form.contact_email.trim() || null,
    contact_phone: form.contact_phone.trim() || null,
    notes: form.notes.trim() || null,
  };
}

async function submitForm() {
  saving.value = true;
  dialogError.value = null;
  try {
    const payload = buildPayload();
    if (editing.value) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { code, ...rest } = payload;
      await updateSupplier(editing.value.code, rest);
      notice.value = `Fournisseur ${payload.name} mis à jour.`;
    } else {
      await createSupplier(payload);
      notice.value = `Fournisseur ${payload.name} créé.`;
    }
    formDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value =
      extractApiError(err) ?? (err instanceof Error ? err.message : 'Enregistrement impossible.');
  } finally {
    saving.value = false;
  }
}

// --- Références suivies (liste blanche de SKU) ---------------------------

const allowlistDialog = ref(false);
const allowlistSupplier = ref<Supplier | null>(null);
const allowlistText = ref('');
const allowlistView = ref<AllowlistView | null>(null);
const allowlistError = ref<string | null>(null);
const allowlistSaving = ref(false);

async function openAllowlist(supplier: Supplier) {
  allowlistSupplier.value = supplier;
  allowlistError.value = null;
  allowlistView.value = null;
  allowlistText.value = (supplier.sku_allowlist ?? []).join('\n');
  allowlistDialog.value = true;
  try {
    allowlistView.value = await getSkuAllowlist(supplier.code);
  } catch (err) {
    allowlistError.value = extractApiError(err) ?? 'Chargement de la liste impossible.';
  }
}

async function saveAllowlist() {
  const supplier = allowlistSupplier.value;
  if (!supplier) return;
  allowlistSaving.value = true;
  allowlistError.value = null;
  try {
    const skus = allowlistText.value
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    const view = await saveSkuAllowlist(supplier.code, skus);
    allowlistView.value = view;
    allowlistText.value = view.entries.map((e) => e.supplier_sku).join('\n');
    notice.value = view.entries.length
      ? `${supplier.name} : ${view.entries.length} référence(s) suivie(s), ${view.deactivated} article(s) retiré(s) de la vitrine.`
      : `${supplier.name} : liste vidée, tout le catalogue synchronisé est suivi.`;
    await load();
  } catch (err) {
    allowlistError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    allowlistSaving.value = false;
  }
}

const deactivateDialog = ref(false);
const deactivating = ref<Supplier | null>(null);
const deactivateProducts = ref<SupplierWithdrawal>('keep');
const deactivateOptions: { value: SupplierWithdrawal; label: string }[] = [
  { value: 'keep', label: 'Les laisser tels quels (le dernier stock synchronisé reste vendable)' },
  {
    value: 'zero_stock',
    label: 'Remettre leur stock fournisseur à zéro (plus vendus sur ce stock)',
  },
  { value: 'hide', label: 'Stock fournisseur à zéro et retirés de la vitrine' },
];

function openDeactivate(supplier: Supplier) {
  deactivating.value = supplier;
  deactivateProducts.value = 'keep';
  deactivateDialog.value = true;
}

async function confirmDeactivate() {
  const supplier = deactivating.value;
  if (!supplier) return;
  busy.value = supplier.code;
  error.value = null;
  try {
    const res = await deactivateSupplier(supplier.code, deactivateProducts.value);
    const withdrawn =
      res.products_withdrawn != null ? ` ${res.products_withdrawn} article(s) retiré(s).` : '';
    notice.value = `Fournisseur ${supplier.name} désactivé.${withdrawn}`;
    deactivateDialog.value = false;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Désactivation impossible.';
  } finally {
    busy.value = null;
  }
}

async function onReactivate(supplier: Supplier) {
  busy.value = supplier.code;
  error.value = null;
  try {
    await updateSupplier(supplier.code, { is_active: true, sync_enabled: true });
    notice.value =
      supplier.kind === 'api' && !supplier.configured
        ? `${supplier.name} réactivé — ses identifiants manquent encore dans l'environnement.`
        : `${supplier.name} réactivé : les synchronisations reprennent sans redémarrage.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Réactivation impossible.';
  } finally {
    busy.value = null;
  }
}

async function onSync(supplier: Supplier) {
  busy.value = supplier.code;
  error.value = null;
  try {
    const res = await triggerProductSync(supplier.code);
    notice.value = `${supplier.name} : ${res.message} (job ${res.job_id}).`;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Synchronisation impossible.';
  } finally {
    busy.value = null;
  }
}

async function onHealth(supplier: Supplier) {
  error.value = null;
  try {
    const res = await checkSupplierHealth(supplier.code);
    notice.value = `${supplier.name} : ${res.status} — ${res.message}`;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Test impossible.';
  }
}

// --- Import fichier -------------------------------------------------------

// --- Catégories (R4 / S5) ---
const categories = ref<AdminCategory[]>([]);
const categoryOptions = computed(() =>
  categories.value.map((c) => ({ label: categoryLabel(c), value: c.id })),
);
const unmappedOptions = (Object.keys(UNMAPPED_ACTION_LABELS) as UnmappedCategoryAction[]).map(
  (value) => ({ value, label: UNMAPPED_ACTION_LABELS[value] }),
);

async function loadCategories() {
  try {
    categories.value = (await listAdminCategories()).filter(
      (c) => c.is_active && !c.merged_into_id,
    );
  } catch {
    categories.value = [];
  }
}

const categoriesDialog = ref(false);
const categoriesOf = ref<Supplier | null>(null);
const observed = ref<ObservedCategory[]>([]);
const categoriesLoading = ref(false);
const categoriesSaving = ref(false);
const reapplying = ref(false);
const categoriesError = ref<string | null>(null);
const categoriesNotice = ref<string | null>(null);
const unmappedLabel = computed(() =>
  UNMAPPED_ACTION_LABELS[categoriesOf.value?.unmapped_category_action ?? 'auto'].toLowerCase(),
);

async function refreshObserved() {
  if (!categoriesOf.value) return;
  categoriesLoading.value = true;
  try {
    observed.value = await listObservedCategories(categoriesOf.value.code);
  } catch (err) {
    categoriesError.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    categoriesLoading.value = false;
  }
}

function openCategories(supplier: Supplier) {
  categoriesOf.value = supplier;
  categoriesError.value = null;
  categoriesNotice.value = null;
  observed.value = [];
  categoriesDialog.value = true;
  void loadCategories();
  void refreshObserved();
}

async function saveSupplierRules(rules: CategoryMappingWrite[]) {
  if (!categoriesOf.value) return;
  categoriesSaving.value = true;
  categoriesError.value = null;
  try {
    await saveCategoryMappings(categoriesOf.value.code, rules);
    categoriesNotice.value = `${rules.length} règle(s) enregistrée(s).`;
    await refreshObserved();
  } catch (err) {
    categoriesError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    categoriesSaving.value = false;
  }
}

async function onReapply() {
  if (!categoriesOf.value) return;
  reapplying.value = true;
  categoriesError.value = null;
  try {
    const res = await reapplyCategoryMappings(categoriesOf.value.code);
    categoriesNotice.value = `${res.moved} article(s) rangé(s), ${res.deactivated} retiré(s) de la vitrine.`;
    await refreshObserved();
  } catch (err) {
    categoriesError.value = extractApiError(err) ?? 'Réapplication impossible.';
  } finally {
    reapplying.value = false;
  }
}

const importDefaultCategory = ref<string | null>(null);

async function saveImportRules(rules: CategoryMappingWrite[]) {
  if (!importing.value) return;
  categoriesSaving.value = true;
  importError.value = null;
  try {
    await saveCategoryMappings(importing.value.code, rules);
    // The simulation reflects the new rules at once.
    await runImport(true);
  } catch (err) {
    importError.value = extractApiError(err) ?? 'Enregistrement des règles impossible.';
  } finally {
    categoriesSaving.value = false;
  }
}

// --- Fichier en ligne (R4 / S3) ---
const SETTING_LABELS: Record<string, string> = {
  feed_url: 'Adresse du fichier (https://…)',
  auth_mode: 'Connexion au portail',
  login_url: 'Adresse du formulaire de connexion',
  username_field: "Nom du champ identifiant (formulaire, défaut 'username')",
  password_field: "Nom du champ mot de passe (formulaire, défaut 'password')",
  file_format: 'Format du fichier',
  sheet_name: 'Feuille Excel (réservé)',
};
const SETTING_CHOICES: Record<string, { label: string; value: string }[]> = {
  auth_mode: [
    { label: 'Aucune (lien direct)', value: 'none' },
    { label: 'Authentification HTTP (basic)', value: 'basic' },
    { label: 'Formulaire de connexion + cookies', value: 'form' },
  ],
  environment: [
    { label: 'Bac à sable (sandbox)', value: 'sandbox' },
    { label: 'Production', value: 'production' },
  ],
  file_format: [
    { label: "Deviner d'après le lien", value: 'auto' },
    { label: 'CSV', value: 'csv' },
    { label: 'Excel (.xlsx)', value: 'xlsx' },
  ],
};
const adapterFields = computed<SchemaField[]>(() =>
  fieldsFromSchema(selectedAdapter.value?.settings_schema, SETTING_LABELS),
);

function choiceOptions(field: SchemaField): { label: string; value: string }[] {
  const named = SETTING_CHOICES[field.key] ?? [];
  return (field.choices ?? []).map(
    (value) => named.find((c) => c.value === value) ?? { label: value, value },
  );
}

function fieldHint(field: SchemaField): string | undefined {
  if (field.kind === 'list') {
    return `${field.hint} Valeurs séparées par des virgules ; « [] » = toutes.`.trim();
  }
  if (field.kind === 'json') return `${field.hint} Format JSON.`.trim();
  return field.hint || undefined;
}

const isFeedForm = computed(() => form.kind === 'api' && form.adapter_key === FEED_ADAPTER_KEY);
const credentials = reactive({ username: '', password: '' });
const credentialsBusy = ref(false);

async function onSaveCredentials() {
  if (!editing.value) return;
  credentialsBusy.value = true;
  dialogError.value = null;
  try {
    editing.value = await saveSupplierCredentials(editing.value.code, { ...credentials });
    credentials.username = '';
    credentials.password = '';
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement des identifiants impossible.';
  } finally {
    credentialsBusy.value = false;
  }
}

async function onClearCredentials() {
  if (!editing.value) return;
  credentialsBusy.value = true;
  dialogError.value = null;
  try {
    editing.value = await deleteSupplierCredentials(editing.value.code);
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Suppression impossible.';
  } finally {
    credentialsBusy.value = false;
  }
}

const importDialog = ref(false);
const importing = ref<Supplier | null>(null);
const importFile = ref<File | null>(null);
const inspection = ref<FileInspectResponse | null>(null);
const importResult = ref<FileImportResponse | null>(null);
const publishNew = ref(true);
const importMinQuantity = ref<string>('');
const importMinPrice = ref<string>('');

const belowThresholdLine = computed(() => {
  const stats = importResult.value?.statistics ?? {};
  const skipped = stats.below_threshold_skipped ?? 0;
  const hidden = stats.below_threshold_deactivated ?? 0;
  if (!skipped && !hidden) return '';
  return `sous le seuil : ${skipped} non créé(s), ${hidden} retiré(s) de la vitrine`;
});
const importError = ref<string | null>(null);
const importBusy = ref<'dry' | 'run' | null>(null);

// --- Import en tâche de fond : suivi du journal de synchronisation ----------
const POLL_INTERVAL_MS = 3000;
const queuedImport = ref<{ code: string; syncLogId: string; totalRows: number } | null>(null);
let pollTimer: ReturnType<typeof setTimeout> | null = null;

function stopPolling() {
  if (pollTimer !== null) clearTimeout(pollTimer);
  pollTimer = null;
  queuedImport.value = null;
}

/** Le journal terminé, présenté comme un import en ligne. */
function statusToResult(status: FileImportStatus, supplierCode: string): FileImportResponse {
  return {
    supplier_name: supplierCode,
    filename: status.filename ?? '',
    dry_run: false,
    total_rows: status.total_rows ?? 0,
    parsed_products: status.parsed_products ?? 0,
    rejected_rows: status.rejected_rows ?? 0,
    row_errors: status.row_errors,
    statistics: status.statistics,
    sync_errors: status.sync_errors,
    sync_log_id: status.sync_log_id,
    published_new: status.published_new,
    queued: false,
    job_id: null,
    message: null,
    sample: [],
    resolution: {},
    sample_resolutions: [],
    resolution_limited_to: null,
  };
}

async function pollQueuedImport() {
  const current = queuedImport.value;
  if (!current) return;
  try {
    const status = await getImportStatus(current.code, current.syncLogId);
    if (status.status === 'pending' || status.status === 'running') {
      pollTimer = setTimeout(() => void pollQueuedImport(), POLL_INTERVAL_MS);
      return;
    }
    stopPolling();
    if (status.status === 'failed') {
      importError.value = status.error_message ?? 'Import échoué.';
      return;
    }
    importResult.value = statusToResult(status, current.code);
    notice.value = `Import ${status.filename ?? ''} terminé (${status.status}).`;
    await load();
  } catch (err) {
    stopPolling();
    importError.value = extractApiError(err) ?? 'Suivi de l’import impossible.';
  }
}

watch(importDialog, (open) => {
  if (!open) stopPolling();
});
onUnmounted(stopPolling);
const mapping = reactive<Record<string, string | null>>({});

/** « 3 par référence, 2 par code-barres » — seules les clés non nulles. */
const matchedByLine = computed(() => {
  const res = importResult.value?.resolution ?? {};
  return (Object.keys(MATCH_KEY_LABELS) as ImportMatchKey[])
    .map((key) => ({ key, n: res[`matched_by_${key}`] ?? 0 }))
    .filter((e) => e.n > 0)
    .map((e) => `${e.n} par ${MATCH_KEY_LABELS[e.key]}`)
    .join(', ');
});

function openImport(supplier: Supplier) {
  importing.value = supplier;
  importFile.value = null;
  inspection.value = null;
  importResult.value = null;
  importError.value = null;
  importMinQuantity.value =
    supplier.min_quantity != null ? String(Number(supplier.min_quantity)) : '';
  importMinPrice.value = supplier.min_price != null ? String(Number(supplier.min_price)) : '';
  importDefaultCategory.value = null;
  void loadCategories();
  for (const key of Object.keys(mapping)) delete mapping[key];
  for (const [k, v] of Object.entries(supplier.column_mapping ?? {})) mapping[k] = v;
  importDialog.value = true;
}

async function onFileChosen(file: File | null) {
  inspection.value = null;
  importResult.value = null;
  importError.value = null;
  if (!file || !importing.value) return;
  try {
    applyInspection(await inspectCatalogFile(importing.value.code, file));
  } catch (err) {
    importError.value = extractApiError(err) ?? 'Lecture du fichier impossible.';
  }
}

const feedReading = ref(false);
const mappingSaving = ref(false);

async function onReadFeed() {
  if (!importing.value) return;
  feedReading.value = true;
  importError.value = null;
  importResult.value = null;
  try {
    applyInspection(await inspectSupplierFeed(importing.value.code));
    notice.value = null;
  } catch (err) {
    importError.value = extractApiError(err) ?? 'Lecture du flux impossible.';
  } finally {
    feedReading.value = false;
  }
}

async function onSaveFeedMapping() {
  if (!importing.value) return;
  mappingSaving.value = true;
  importError.value = null;
  try {
    const saved = await updateSupplier(importing.value.code, {
      column_mapping: currentMapping(),
    });
    importing.value = saved;
    notice.value = `Mapping de ${saved.name} enregistré : la prochaine synchronisation l'utilise.`;
    importDialog.value = false;
    await load();
  } catch (err) {
    importError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    mappingSaving.value = false;
  }
}

function applyInspection(result: FileInspectResponse) {
  inspection.value = result;
  {
    // Drop stored mappings that point at columns the file does not have.
    for (const [k, v] of Object.entries(mapping)) {
      if (v && !result.headers.includes(v)) mapping[k] = null;
    }
    // Pre-fill obvious matches when nothing is mapped yet.
    for (const target of result.mapping_targets) {
      if (mapping[target]) continue;
      const hit = result.headers.find((h) => h.trim().toLowerCase() === target.toLowerCase());
      if (hit) mapping[target] = hit;
    }
  }
}

function currentMapping(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(mapping)) if (v) out[k] = v;
  return out;
}

async function runImport(dryRun: boolean) {
  if (!importFile.value || !importing.value) return;
  importBusy.value = dryRun ? 'dry' : 'run';
  importError.value = null;
  importResult.value = null;
  const chosen = currentMapping();
  try {
    if (!dryRun) {
      // Remember the mapping on the supplier for the next file.
      await updateSupplier(importing.value.code, { column_mapping: chosen });
    }
    const result = await importCatalogFile(importing.value.code, importFile.value, {
      mapping: chosen,
      dryRun,
      publishNew: publishNew.value,
      minQuantity: optionalNumber(importMinQuantity.value),
      minPrice: optionalNumber(importMinPrice.value),
      defaultCategoryId: importDefaultCategory.value,
    });
    if (result.queued && result.sync_log_id) {
      // Large file: the worker imports it; follow the sync log until it ends.
      queuedImport.value = {
        code: importing.value.code,
        syncLogId: result.sync_log_id,
        totalRows: result.total_rows,
      };
      pollTimer = setTimeout(() => void pollQueuedImport(), POLL_INTERVAL_MS);
      return;
    }
    importResult.value = result;
    if (!dryRun) {
      notice.value = `Import ${result.filename} terminé pour ${importing.value.name}.`;
      await load();
    }
  } catch (err) {
    importError.value = extractApiError(err) ?? 'Import impossible.';
  } finally {
    importBusy.value = null;
  }
}

onMounted(load);
</script>
