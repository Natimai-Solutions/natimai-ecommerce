<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="col">
        <div class="text-h6">Fournisseurs</div>
        <div class="text-caption text-grey-7">
          Un fournisseur est déclaré ici avec son entrepôt d'origine et son régime douanier. Sa
          méthode d'approvisionnement décide comment ses articles arrivent : à la main, par fichier
          CSV / Excel, ou par une intégration API.
        </div>
      </div>
      <q-btn color="primary" icon="add" label="Nouveau fournisseur" no-caps @click="openCreate" />
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" rounded dense>{{
      notice
    }}</q-banner>

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
      <template #body-cell-kind="props">
        <q-td :props="props">
          <q-badge :color="kindColor(props.row.kind)" :label="kindLabel(props.row.kind)" />
          <span v-if="props.row.kind === 'api'" class="text-caption text-grey-7 q-ml-xs">
            {{ props.row.adapter_key }}
          </span>
        </q-td>
      </template>
      <template #body-cell-origin="props">
        <q-td :props="props">{{ placeName(props.row.origin_place_id) }}</q-td>
      </template>
      <template #body-cell-domestic="props">
        <q-td :props="props">
          <q-badge v-if="props.row.is_domestic" color="teal" label="Local — sans douane" />
          <q-badge v-else color="orange" label="Import — CAF + douane" />
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-icon v-if="!props.row.is_active" name="block" color="grey" size="sm">
            <q-tooltip>Désactivé</q-tooltip>
          </q-icon>
          <q-icon
            v-else-if="props.row.kind === 'api' && !props.row.configured"
            name="warning"
            color="orange"
            size="sm"
          >
            <q-tooltip>Identifiants absents de l'environnement</q-tooltip>
          </q-icon>
          <q-icon v-else name="check_circle" color="positive" size="sm" />
          <span v-if="props.row.kind === 'api'" class="text-caption text-grey-7 q-ml-xs">
            {{
              props.row.sync_enabled
                ? props.row.sync_interval_hours > 0
                  ? `sync toutes les ${props.row.sync_interval_hours} h`
                  : 'sync manuelle'
                : 'sync désactivée'
            }}
          </span>
          <q-badge
            v-if="props.row.sku_allowlist?.length"
            color="deep-purple"
            class="q-ml-xs"
            :label="`${props.row.sku_allowlist.length} réf. suivie(s)`"
            data-testid="supplier-allowlist-badge"
          >
            <q-tooltip>Seules ces références sont créées et rafraîchies</q-tooltip>
          </q-badge>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            icon="upload_file"
            color="primary"
            :disable="!props.row.is_active"
            @click="openImport(props.row)"
          >
            <q-tooltip>Importer un catalogue CSV / Excel</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.kind === 'api'"
            flat
            dense
            icon="sync"
            color="primary"
            :disable="!props.row.is_active || !props.row.configured"
            :loading="busy === props.row.code"
            @click="onSync(props.row)"
          >
            <q-tooltip>Lancer la synchronisation catalogue</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.kind === 'api'"
            flat
            dense
            icon="monitor_heart"
            color="primary"
            :disable="!props.row.is_active"
            @click="onHealth(props.row)"
          >
            <q-tooltip>Tester la connexion</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.kind !== 'manual'"
            flat
            dense
            icon="playlist_add_check"
            color="deep-purple"
            :disable="!props.row.is_active"
            data-testid="supplier-allowlist"
            @click="openAllowlist(props.row)"
          >
            <q-tooltip>Références suivies (liste blanche de SKU)</q-tooltip>
          </q-btn>
          <q-btn flat dense icon="edit" color="primary" @click="openEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.is_active"
            flat
            dense
            icon="block"
            color="negative"
            @click="onDeactivate(props.row)"
          >
            <q-tooltip>Désactiver (les articles gardent leur lien)</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucun fournisseur déclaré.</div>
      </template>
    </q-table>

    <!-- Création / édition -->
    <q-dialog v-model="formDialog">
      <q-card style="min-width: 620px; max-width: 92vw">
        <q-card-section class="text-h6">
          {{ editing ? `Modifier ${editing.name}` : 'Nouveau fournisseur' }}
        </q-card-section>
        <q-form @submit.prevent="submitForm">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>

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
            <q-banner
              v-if="form.kind === 'api' && selectedAdapter && !selectedAdapter.configured"
              class="bg-orange-1 text-orange-10"
              dense
              rounded
            >
              Les identifiants de cette intégration ne sont pas configurés dans l'environnement du
              serveur : la synchronisation restera impossible tant qu'ils manquent.
            </q-banner>

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
            <div class="text-caption text-grey-7 q-ml-md">
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
              <div class="text-caption text-grey-7 q-ml-md">
                Un article créé par une synchronisation ou un import reste invisible en vitrine
                (enrichi et rafraîchi quand même) jusqu'à ce que vous le publiiez depuis la page
                Articles. Les articles existants ne changent pas.
              </div>
            </template>

            <template v-if="form.kind === 'api'">
              <q-toggle v-model="form.sync_enabled" label="Synchronisations autorisées" />
              <q-input
                v-model="form.default_categories_text"
                label="Catégories fournisseur synchronisées"
                hint="Une par ligne"
                type="textarea"
                autogrow
                outlined
                dense
              />
              <div v-if="selectedAdapter?.settings_keys.length" class="q-gutter-sm">
                <div class="text-subtitle2">Réglages de l'intégration</div>
                <q-input
                  v-for="key in selectedAdapter.settings_keys"
                  :key="key"
                  v-model="form.settings[key]"
                  :label="key"
                  outlined
                  dense
                />
              </div>
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
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Enregistrer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Références suivies (liste blanche de SKU) -->
    <q-dialog v-model="allowlistDialog">
      <q-card style="min-width: 640px; max-width: 92vw">
        <q-card-section class="text-h6">
          Références suivies — {{ allowlistSupplier?.name }}
        </q-card-section>
        <q-card-section class="q-pt-none q-gutter-sm">
          <q-banner v-if="allowlistError" class="bg-red-1 text-red-9" dense rounded>{{
            allowlistError
          }}</q-banner>
          <div class="text-caption text-grey-7">
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
          <div v-if="allowlistView" class="text-caption text-grey-8">
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
                  <td>{{ e.supplier_sku }}</td>
                  <td>{{ e.product_name ?? '— à créer' }}</td>
                  <td>
                    <q-badge v-if="e.is_active === true" color="positive" label="en vitrine" />
                    <q-badge v-else-if="e.is_active === false" color="grey" label="masqué" />
                    <span v-else class="text-grey-6">inconnu</span>
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
          </q-expansion-item>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Fermer" v-close-popup />
          <q-btn
            color="primary"
            label="Enregistrer la liste"
            :loading="allowlistSaving"
            data-testid="allowlist-save"
            @click="saveAllowlist"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Import fichier -->
    <q-dialog v-model="importDialog">
      <q-card style="min-width: 720px; max-width: 95vw">
        <q-card-section class="text-h6">
          Importer un catalogue — {{ importing?.name }}
        </q-card-section>
        <q-card-section class="q-pt-none q-gutter-sm">
          <q-banner v-if="importError" class="bg-red-1 text-red-9" dense rounded>{{
            importError
          }}</q-banner>

          <q-file
            v-model="importFile"
            label="Fichier CSV ou Excel (.xlsx)"
            accept=".csv,.txt,.xlsx,.xlsm"
            outlined
            dense
            clearable
            @update:model-value="onFileChosen"
          >
            <template #prepend><q-icon name="attach_file" /></template>
          </q-file>

          <template v-if="inspection">
            <div class="text-caption text-grey-7">
              {{ inspection.total_rows }} ligne(s) détectée(s) — colonnes :
              {{ inspection.headers.join(', ') }}
            </div>
            <div class="text-subtitle2 q-mt-sm">Correspondance des colonnes</div>
            <div class="text-caption text-grey-7 q-mb-xs">
              Associez chaque champ de notre système à une colonne du fichier. Les champs marqués *
              sont obligatoires. La correspondance est mémorisée sur le fournisseur.
            </div>
            <div class="text-caption text-grey-7 q-mb-xs">
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
            <q-checkbox
              v-model="publishNew"
              dense
              class="q-mt-sm"
              label="Afficher les nouveaux articles en boutique sans attendre l’enrichissement Icecat"
            />
            <div class="text-caption text-grey-7 q-mb-xs">
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

          <q-banner v-if="queuedImport" class="bg-blue-1 text-blue-10" dense rounded>
            <template #avatar>
              <q-spinner color="primary" size="sm" />
            </template>
            Import en tâche de fond ({{ queuedImport.totalRows }} lignes) — l'avancement se met à
            jour ici ; vous pouvez fermer cette fenêtre, le résultat restera dans le journal de
            synchronisation.
          </q-banner>

          <q-banner
            v-if="importResult"
            :class="importResult.dry_run ? 'bg-blue-1 text-blue-10' : 'bg-green-1 text-green-9'"
            dense
            rounded
          >
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
                <span v-if="importResult.published_new">— publiés en boutique</span>
                <span v-else>— masqués jusqu’à enrichissement</span>
              </span>
              <span v-else>
                — {{ importResult.resolution.new ?? 0 }} nouveau(x),
                {{ importResult.resolution.updated ?? 0 }} reconnu(s),
                {{ importResult.resolution.adopted ?? 0 }} adopté(s),
                {{ importResult.resolution.ambiguous ?? 0 }} ambigu(s)
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
                    <td>{{ r.supplier_sku }}</td>
                    <td>{{ r.name }}</td>
                    <td>{{ actionLabel(r.action) }}</td>
                    <td>{{ r.match_key ? matchKeyLabel(r.match_key) : '—' }}</td>
                    <td>{{ r.product_name ?? r.message ?? '—' }}</td>
                  </tr>
                </tbody>
              </q-markup-table>
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
          </q-banner>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Fermer" v-close-popup />
          <q-btn
            flat
            color="primary"
            label="Simuler"
            :disable="!importFile || !inspection"
            :loading="importBusy === 'dry'"
            @click="runImport(true)"
          />
          <q-btn
            color="primary"
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
} from '@/api/suppliers';
import { listPlaces, type Place } from '@/api/logistics';
import { extractApiError } from '@/api/errors';

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
function kindColor(kind: SupplierKind): string {
  return kind === 'api' ? 'indigo' : kind === 'file' ? 'blue-grey' : 'grey-7';
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
  sync_interval_hours: number;
  default_categories_text: string;
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
    sync_interval_hours: 0,
    default_categories_text: '',
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
  const settings: Record<string, string> = {};
  for (const [k, v] of Object.entries(supplier.settings ?? {})) {
    settings[k] = typeof v === 'string' ? v : v == null ? '' : JSON.stringify(v);
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
    sync_interval_hours: supplier.sync_interval_hours,
    default_categories_text: (supplier.default_categories ?? []).join('\n'),
    price_currency: supplier.price_currency,
    settings,
    contact_email: supplier.contact_email ?? '',
    contact_phone: supplier.contact_phone ?? '',
    notes: supplier.notes ?? '',
  });
  formDialog.value = true;
}

function buildPayload(): SupplierCreate {
  const settings: Record<string, string> = {};
  for (const [k, v] of Object.entries(form.settings)) if (v.trim()) settings[k] = v.trim();
  const categories = form.default_categories_text
    .split('\n')
    .map((c) => c.trim())
    .filter(Boolean);
  return {
    code: form.code.trim().toLowerCase(),
    name: form.name.trim(),
    kind: form.kind,
    adapter_key: form.kind === 'api' ? form.adapter_key : null,
    origin_place_id: form.origin_place_id,
    is_domestic: form.is_domestic,
    sync_enabled: form.sync_enabled,
    import_as_draft: form.kind !== 'manual' && form.import_as_draft,
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
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
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

async function onDeactivate(supplier: Supplier) {
  error.value = null;
  try {
    await deactivateSupplier(supplier.code);
    notice.value = `Fournisseur ${supplier.name} désactivé.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Désactivation impossible.';
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

const importDialog = ref(false);
const importing = ref<Supplier | null>(null);
const importFile = ref<File | null>(null);
const inspection = ref<FileInspectResponse | null>(null);
const importResult = ref<FileImportResponse | null>(null);
const publishNew = ref(true);
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
    inspection.value = await inspectCatalogFile(importing.value.code, file);
    // Drop stored mappings that point at columns the file does not have.
    for (const [k, v] of Object.entries(mapping)) {
      if (v && !inspection.value.headers.includes(v)) mapping[k] = null;
    }
    // Pre-fill obvious matches when nothing is mapped yet.
    for (const target of inspection.value.mapping_targets) {
      if (mapping[target]) continue;
      const hit = inspection.value.headers.find(
        (h) => h.trim().toLowerCase() === target.toLowerCase(),
      );
      if (hit) mapping[target] = hit;
    }
  } catch (err) {
    importError.value = extractApiError(err) ?? 'Lecture du fichier impossible.';
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
