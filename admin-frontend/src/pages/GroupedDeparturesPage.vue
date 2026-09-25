<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Départs groupés</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
      <q-btn color="primary" icon="add" label="Nouveau départ" no-caps @click="openCreate" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      Un départ = une date limite de commande affichée en vitrine, les commandes qui s'y
      rattachent (automatiquement au checkout, déplaçables ici) et le bon de commande fournisseur
      agrégé par SKU. Un seul départ « ouvert » et publié à la fois.
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" dense rounded>{{
      notice
    }}</q-banner>

    <q-table
      :rows="departures"
      :columns="columns"
      row-key="id"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
      :selected="selected ? [selected] : []"
      @row-click="(_evt: Event, row: Departure) => select(row)"
    >
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            dense
            size="sm"
            :color="props.row.status === 'open' ? 'green' : 'grey-7'"
            text-color="white"
            :label="departureStatusLabel(props.row.status)"
          />
          <q-icon
            v-if="props.row.is_published"
            name="visibility"
            color="primary"
            class="q-ml-xs"
          >
            <q-tooltip>Publié en vitrine</q-tooltip>
          </q-icon>
        </q-td>
      </template>
      <template #body-cell-orders="props">
        <q-td :props="props">
          {{ props.row.orders_count }} · {{ formatMoney(Number(props.row.orders_total)) }}
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            v-if="nextDepartureStatus(props.row.status)"
            flat
            dense
            no-caps
            icon="skip_next"
            color="primary"
            :label="departureStatusLabel(nextDepartureStatus(props.row.status) ?? '')"
            @click.stop="advance(props.row)"
          >
            <q-tooltip>Passer à l'étape suivante</q-tooltip>
          </q-btn>
          <q-btn flat dense icon="edit" color="primary" @click.stop="openEdit(props.row)" />
          <q-btn
            flat
            dense
            icon="delete"
            color="grey-8"
            :disable="props.row.orders_count > 0"
            @click.stop="remove(props.row)"
          >
            <q-tooltip>
              {{
                props.row.orders_count > 0
                  ? 'Déplacez les commandes rattachées avant de supprimer'
                  : 'Supprimer'
              }}
            </q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">
          Aucun départ groupé : la boutique fonctionne en mode classique.
        </div>
      </template>
    </q-table>

    <!-- Orders of the selected departure -->
    <q-card v-if="selected" flat bordered class="q-mt-md">
      <q-card-section class="row items-center q-gutter-sm">
        <div class="text-subtitle1 col">
          Commandes du départ « {{ selected.name }} »
          <span class="text-caption text-grey-7">— {{ cutoffLabel(selected) }}</span>
        </div>
        <q-btn
          v-if="selected.status === 'open' || selected.status === 'draft'"
          color="primary"
          no-caps
          icon="lock"
          label="Clôturer le départ"
          :loading="closing"
          @click="closeSelected(false)"
        >
          <q-tooltip>
            Vérifie le stock fournisseur de chaque article commandé, les seuils, et crée le
            départ suivant si récurrent
          </q-tooltip>
        </q-btn>
        <q-btn
          flat
          dense
          no-caps
          icon="download"
          label="Commandes (CSV)"
          @click="downloadOrdersCsv(filters)"
        />
        <q-btn
          flat
          dense
          no-caps
          icon="download"
          label="Bon de commande par SKU (CSV)"
          @click="downloadSkuSummaryCsv(filters)"
        />
      </q-card-section>

      <q-card-section class="q-pt-none">
        <q-table
          v-model:selected="selectedOrders"
          :rows="orders"
          :columns="orderColumns"
          row-key="order_id"
          selection="multiple"
          :loading="ordersLoading"
          flat
          dense
          :rows-per-page-options="[0]"
          hide-pagination
        >
          <template #top>
            <div class="row items-center q-gutter-sm full-width">
              <q-select
                v-model="moveTarget"
                :options="moveOptions"
                label="Déplacer la sélection vers…"
                dense
                outlined
                emit-value
                map-options
                style="min-width: 260px"
              />
              <q-btn
                color="primary"
                no-caps
                label="Déplacer"
                :disable="selectedOrders.length === 0 || moveTarget === undefined"
                @click="moveSelected"
              />
              <q-toggle v-model="showUnassigned" label="Voir les commandes sans départ" dense />
            </div>
          </template>
          <template #body-cell-status="props">
            <q-td :props="props">
              <q-chip
                dense
                size="sm"
                :color="orderStatusColor(props.row.status)"
                text-color="white"
                :label="orderStatusLabel(props.row.status)"
              />
            </q-td>
          </template>
          <template #body-cell-actions="props">
            <q-td :props="props" align="right">
              <q-btn flat dense icon="visibility" color="primary" :to="`/orders/${props.row.order_id}`" />
            </q-td>
          </template>
          <template #no-data>
            <div class="full-width text-center text-grey-6 q-pa-md">Aucune commande.</div>
          </template>
        </q-table>
      </q-card-section>

      <q-card-section v-if="!showUnassigned">
        <div class="text-subtitle2 q-mb-sm">Bon de commande fournisseur (agrégé par SKU)</div>
        <q-table
          :rows="sku"
          :columns="skuColumns"
          row-key="product_id"
          :loading="skuLoading"
          flat
          dense
          bordered
          :rows-per-page-options="[0]"
          hide-pagination
        >
          <template #no-data>
            <div class="full-width text-center text-grey-6 q-pa-md">Aucune ligne.</div>
          </template>
        </q-table>
      </q-card-section>

      <!-- Real purchase orders placed with the suppliers -->
      <q-card-section v-if="!showUnassigned">
        <div class="row items-center q-mb-sm q-gutter-sm">
          <div class="text-subtitle2 col">Bons de commande passés aux fournisseurs</div>
          <q-btn flat dense no-caps icon="add" label="Enregistrer un BC" @click="poDialog = true" />
        </div>
        <q-list v-if="selected.supplier_orders?.length" dense bordered separator>
          <q-item v-for="(po, i) in selected.supplier_orders" :key="i">
            <q-item-section>
              <q-item-label>
                {{ po.supplier_name }} — n° {{ po.order_number }}
                <span class="text-grey-7">· {{ formatDate(po.ordered_at) }}</span>
              </q-item-label>
              <q-item-label caption>
                {{ po.total_amount }} {{ po.currency }}<template v-if="po.notes"> · {{ po.notes }}</template>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn flat dense icon="delete" color="grey-8" @click="removePo(i)" />
            </q-item-section>
          </q-item>
        </q-list>
        <div v-else class="text-caption text-grey-6">
          Aucun bon de commande enregistré. Le premier BC passe le départ en « commandé »
          et prévient les clients.
        </div>
      </q-card-section>

      <!-- Social reminders -->
      <q-card-section v-if="!showUnassigned">
        <div class="row items-center q-mb-sm q-gutter-sm">
          <div class="text-subtitle2 col">Rappels réseaux sociaux</div>
          <q-btn flat dense no-caps icon="add" label="Ajouter un rappel" @click="openReminder()" />
        </div>
        <q-input
          v-model="webhookUrl"
          label="URL du webhook (Make, Zapier, Buffer…) — reçoit {text, link, image_url, departure}"
          hint="https uniquement. Réglage global, commun à tous les départs."
          outlined
          dense
          class="q-mb-sm"
          @blur="saveWebhook"
        >
          <template #append><q-icon name="webhook" /></template>
        </q-input>
        <q-table
          :rows="reminders"
          :columns="reminderColumns"
          row-key="id"
          :loading="remindersLoading"
          flat
          dense
          bordered
          :rows-per-page-options="[0]"
          hide-pagination
        >
          <template #body-cell-status="props">
            <q-td :props="props">
              <q-chip
                dense
                size="sm"
                :color="reminderColor(props.row.status)"
                text-color="white"
                :label="reminderLabel(props.row.status)"
              />
              <span v-if="props.row.error" class="text-caption text-negative q-ml-xs">
                {{ props.row.error }}
              </span>
            </q-td>
          </template>
          <template #body-cell-actions="props">
            <q-td :props="props" align="right">
              <q-btn flat dense icon="send" color="primary" @click="publishNow(props.row)">
                <q-tooltip>Publier maintenant</q-tooltip>
              </q-btn>
              <q-btn
                v-if="props.row.status !== 'sent'"
                flat
                dense
                icon="edit"
                color="primary"
                @click="openReminder(props.row)"
              />
              <q-btn flat dense icon="delete" color="grey-8" @click="removeReminder(props.row)" />
            </q-td>
          </template>
          <template #no-data>
            <div class="full-width text-center text-grey-6 q-pa-md">Aucun rappel.</div>
          </template>
        </q-table>
      </q-card-section>
    </q-card>

    <!-- Close result: what is left to arbitrate -->
    <q-dialog v-model="closeDialog">
      <q-card style="min-width: 560px; max-width: 90vw">
        <q-card-section class="text-h6">
          {{ closeResult?.closed ? 'Départ clôturé' : 'Départ non clôturé' }}
        </q-card-section>
        <q-card-section v-if="closeResult" class="q-pt-none">
          <div class="q-mb-sm">
            {{ closeResult.orders_count }} commande(s) payée(s) ·
            {{ formatMoney(Number(closeResult.orders_total)) }}
          </div>
          <q-banner v-if="!closeResult.threshold_reached" class="bg-orange-1 text-orange-10 q-mb-sm" dense rounded>
            Seuil minimum non atteint : le départ reste ouvert. Reportez la clôture ou forcez-la.
          </q-banner>
          <q-banner v-if="closeResult.unpaid_order_ids.length" class="bg-grey-2 q-mb-sm" dense rounded>
            {{ closeResult.unpaid_order_ids.length }} commande(s) non payée(s) restent rattachées :
            à exclure ou à déplacer vers le départ suivant depuis la liste des commandes.
          </q-banner>
          <template v-if="closeResult.shortages.length">
            <div class="text-subtitle2 q-mb-xs">Ruptures chez le fournisseur — à arbitrer</div>
            <q-list dense bordered separator>
              <q-item v-for="s in closeResult.shortages" :key="s.product_id">
                <q-item-section>
                  <q-item-label>{{ s.product_name }} ({{ s.supplier_sku }})</q-item-label>
                  <q-item-label caption>
                    {{ s.ordered_quantity }} commandé(s), {{ s.available_quantity }} disponible(s) —
                    commandes {{ s.order_numbers.filter(Boolean).join(', ') || s.order_ids.length }}
                  </q-item-label>
                </q-item-section>
                <q-item-section side>
                  <q-btn
                    flat
                    dense
                    no-caps
                    color="orange-9"
                    label="Marquer en rupture"
                    @click="markBackordered(s.order_ids)"
                  >
                    <q-tooltip>Statut « rupture / report » + e-mail aux clients concernés</q-tooltip>
                  </q-btn>
                </q-item-section>
              </q-item>
            </q-list>
          </template>
          <div v-else class="text-positive">Stock fournisseur suffisant sur toutes les lignes.</div>
          <div v-if="closeResult.next_departure_id" class="text-caption text-grey-7 q-mt-sm">
            Départ suivant créé et publié (récurrence).
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-if="closeResult && !closeResult.closed"
            flat
            color="orange-9"
            label="Forcer la clôture"
            @click="closeSelected(true)"
          />
          <q-btn flat label="Fermer" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Supplier purchase order -->
    <q-dialog v-model="poDialog">
      <q-card style="min-width: 460px">
        <q-card-section class="text-h6">Bon de commande fournisseur</q-card-section>
        <q-form @submit.prevent="submitPo">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-input v-model="poForm.supplier_name" label="Fournisseur *" outlined dense :rules="[(v: string) => !!v.trim() || 'Requis']" />
            <q-input v-model="poForm.order_number" label="N° de commande *" outlined dense :rules="[(v: string) => !!v.trim() || 'Requis']" />
            <q-input v-model="poForm.ordered_at" type="date" label="Date *" outlined dense :rules="[(v: string) => !!v || 'Requis']" />
            <div class="row q-col-gutter-sm">
              <q-input v-model="poForm.total_amount" class="col-8" type="number" step="0.01" min="0" label="Montant payé *" outlined dense />
              <q-input v-model="poForm.currency" class="col-4" label="Devise" outlined dense />
            </div>
            <q-input v-model="poForm.notes" label="Notes" outlined dense />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Enregistrer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Reminder -->
    <q-dialog v-model="reminderDialog">
      <q-card style="min-width: 520px">
        <q-card-section class="text-h6">{{ reminderEditId ? 'Modifier le rappel' : 'Nouveau rappel' }}</q-card-section>
        <q-form @submit.prevent="submitReminder">
          <q-card-section class="q-pt-none q-gutter-sm">
            <div class="row q-col-gutter-sm">
              <q-input v-model.number="reminderForm.offset_days" class="col-6" type="number" min="0" label="Jours avant *" outlined dense />
              <q-select
                v-model="reminderForm.anchor"
                class="col-6"
                :options="[{ label: 'la clôture des commandes', value: 'cutoff' }, { label: 'le départ physique', value: 'departure' }]"
                label="Avant…"
                outlined
                dense
                emit-value
                map-options
              />
            </div>
            <q-input
              v-model="reminderForm.message_template"
              type="textarea"
              autogrow
              label="Message *"
              hint="Variables : {name} {cutoff_date} {days_left} {delivery_date} {shop_url}"
              outlined
              dense
              :rules="[(v: string) => !!v.trim() || 'Requis']"
            />
            <q-input v-model="reminderForm.image_url" label="URL d'image (optionnel)" outlined dense clearable />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Enregistrer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Create / edit -->
    <q-dialog v-model="dialog">
      <q-card style="min-width: 520px">
        <q-card-section class="text-h6">{{
          editId ? 'Modifier le départ' : 'Nouveau départ groupé'
        }}</q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
            <q-input
              v-model="form.name"
              label="Nom *"
              outlined
              dense
              autofocus
              :rules="[(v: string) => !!v.trim() || 'Nom requis']"
            />
            <q-input
              v-model="form.order_cutoff_at"
              type="datetime-local"
              label="Date limite de commande *"
              hint="Affichée en vitrine : « Commandez avant le … »"
              outlined
              dense
              :rules="[(v: string) => !!v || 'Date requise']"
            />
            <q-input
              v-model="form.estimated_delivery_at"
              type="date"
              label="Livraison estimée"
              outlined
              dense
              clearable
            />
            <q-input
              v-model="form.departure_at"
              type="date"
              label="Départ physique (si différent de la clôture)"
              outlined
              dense
              clearable
            />
            <q-select
              v-model="form.status"
              :options="statusOptions"
              label="Statut"
              outlined
              dense
              emit-value
              map-options
            />
            <q-toggle v-model="form.is_published" label="Publié en vitrine" />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model.number="form.min_amount"
                class="col"
                type="number"
                label="Seuil montant (XPF)"
                outlined
                dense
                clearable
              />
              <q-input
                v-model.number="form.min_units"
                class="col"
                type="number"
                label="Seuil pièces"
                outlined
                dense
                clearable
              />
              <q-input
                v-model.number="form.recurrence_days"
                class="col"
                type="number"
                label="Récurrence (jours)"
                outlined
                dense
                clearable
              />
            </div>
            <q-input v-model="form.notes" type="textarea" label="Notes" outlined dense autogrow />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Enregistrer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import type { QTableColumn } from 'quasar';
import {
  DEPARTURE_STATUSES,
  departureCutoffLabel,
  departureStatusLabel,
  formatDate,
  formatDateTime,
  formatXpf,
  nextDepartureStatus,
} from '@app/utils';
import {
  addSupplierOrder,
  assignOrders,
  closeDeparture,
  createDeparture,
  createReminder,
  deleteDeparture,
  deleteReminder,
  listDepartures,
  listReminders,
  publishReminder,
  removeSupplierOrder,
  updateDeparture,
  updateReminder,
  type CloseResult,
  type Departure,
  type DepartureWrite,
  type Reminder,
} from 'src/api/departures';
import {
  downloadOrdersCsv,
  downloadSkuSummaryCsv,
  listOrders,
  orderStatusColor,
  orderStatusLabel,
  skuSummary,
  type AdminOrderListItem,
  type OrderFilters,
  type SkuSummaryRow,
} from 'src/api/orders';
import { extractApiError } from 'src/api/errors';
import { listSystemSettings, updateSystemSetting } from 'src/api/systemSettings';
import { setOrderStatus } from 'src/api/orders';

const departures = ref<Departure[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const formatMoney = (n: number) => (Number.isFinite(n) ? formatXpf(n) : String(n));
const cutoffLabel = (d: Departure) => departureCutoffLabel(d);

const columns: QTableColumn[] = [
  { name: 'name', label: 'Départ', field: 'name', align: 'left' },
  {
    name: 'cutoff',
    label: 'Limite de commande',
    field: 'order_cutoff_at',
    align: 'left',
    format: (v: string) => formatDate(v),
  },
  {
    name: 'delivery',
    label: 'Livraison estimée',
    field: 'estimated_delivery_at',
    align: 'left',
    format: (v: string | null) => formatDate(v),
  },
  { name: 'status', label: 'Statut', field: 'status', align: 'left' },
  { name: 'orders', label: 'Commandes · total', field: 'orders_count', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    departures.value = await listDepartures();
    if (selected.value) {
      selected.value = departures.value.find((d) => d.id === selected.value?.id) ?? null;
    }
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

// --- Selected departure: its orders + SKU summary ---
const selected = ref<Departure | null>(null);
const showUnassigned = ref(false);
const orders = ref<AdminOrderListItem[]>([]);
const ordersLoading = ref(false);
const selectedOrders = ref<AdminOrderListItem[]>([]);
const sku = ref<SkuSummaryRow[]>([]);
const skuLoading = ref(false);
const moveTarget = ref<string | null | undefined>(undefined);

const filters = computed<OrderFilters>(() =>
  showUnassigned.value ? { unassigned: true } : { departure_id: selected.value?.id ?? null },
);

const moveOptions = computed(() => [
  ...departures.value
    .filter((d) => d.id !== selected.value?.id || showUnassigned.value)
    .map((d) => ({ label: `${d.name} (${formatDate(d.order_cutoff_at)})`, value: d.id })),
  { label: '— Aucun départ (détacher)', value: null },
]);

const orderColumns: QTableColumn[] = [
  {
    name: 'number',
    label: 'Commande',
    field: (r: AdminOrderListItem) => r.order_number ?? `#${r.order_id.slice(0, 8)}`,
    align: 'left',
  },
  {
    name: 'date',
    label: 'Date',
    field: 'created_at',
    align: 'left',
    format: (v: string | null) => formatDate(v),
  },
  {
    name: 'client',
    label: 'Client',
    field: (r: AdminOrderListItem) => r.user_name || r.user_email || '',
    align: 'left',
  },
  { name: 'status', label: 'Statut', field: 'status', align: 'left' },
  {
    name: 'total',
    label: 'Total',
    field: 'total_amount',
    align: 'right',
    format: (v: number) => formatMoney(v),
  },
  { name: 'actions', label: '', field: 'order_id', align: 'right' },
];

const skuColumns: QTableColumn[] = [
  { name: 'supplier', label: 'Fournisseur', field: 'supplier_name', align: 'left' },
  { name: 'sku', label: 'SKU', field: 'supplier_sku', align: 'left' },
  { name: 'product', label: 'Produit', field: 'product_name', align: 'left' },
  { name: 'qty', label: 'Qté', field: 'quantity', align: 'right' },
  { name: 'orders', label: 'Cmdes', field: 'orders_count', align: 'right' },
  {
    name: 'cost',
    label: 'Coût unit.',
    field: (r: SkuSummaryRow) => (r.unit_cost === null ? '—' : `${r.unit_cost} ${r.cost_currency ?? ''}`),
    align: 'right',
  },
  {
    name: 'weight',
    label: 'Poids total (kg)',
    field: (r: SkuSummaryRow) => r.total_weight_kg ?? '—',
    align: 'right',
  },
];

function select(row: Departure) {
  selected.value = row;
  showUnassigned.value = false;
  void loadReminders();
}

async function loadOrders() {
  if (!selected.value) return;
  ordersLoading.value = true;
  skuLoading.value = true;
  selectedOrders.value = [];
  try {
    orders.value = await listOrders(filters.value);
    sku.value = showUnassigned.value ? [] : await skuSummary(filters.value);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement des commandes impossible.';
  } finally {
    ordersLoading.value = false;
    skuLoading.value = false;
  }
}

watch(filters, loadOrders);

async function moveSelected() {
  if (moveTarget.value === undefined) return;
  error.value = null;
  try {
    const updated = await assignOrders(
      selectedOrders.value.map((o) => o.order_id),
      moveTarget.value,
    );
    notice.value = `${updated} commande(s) déplacée(s).`;
    await Promise.all([load(), loadOrders()]);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Déplacement impossible.';
  }
}

// --- Assisted close ---
const closing = ref(false);
const closeDialog = ref(false);
const closeResult = ref<CloseResult | null>(null);

async function closeSelected(force: boolean) {
  if (!selected.value) return;
  closing.value = true;
  error.value = null;
  try {
    closeResult.value = await closeDeparture(selected.value.id, force);
    closeDialog.value = true;
    await load();
    await loadOrders();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Clôture impossible.';
  } finally {
    closing.value = false;
  }
}

async function markBackordered(orderIds: string[]) {
  error.value = null;
  try {
    await Promise.all(orderIds.map((id) => setOrderStatus(id, 'Backordered', 'rupture fournisseur')));
    notice.value = `${orderIds.length} commande(s) marquée(s) en rupture, clients prévenus.`;
    await loadOrders();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Changement de statut impossible.';
  }
}

// --- Supplier purchase orders ---
const poDialog = ref(false);
const poForm = reactive({
  supplier_name: '',
  order_number: '',
  ordered_at: '',
  total_amount: '',
  currency: 'XPF',
  notes: '',
});

async function submitPo() {
  if (!selected.value) return;
  saving.value = true;
  error.value = null;
  try {
    const updated = await addSupplierOrder(selected.value.id, {
      supplier_name: poForm.supplier_name.trim(),
      order_number: poForm.order_number.trim(),
      ordered_at: new Date(`${poForm.ordered_at}T12:00`).toISOString(),
      total_amount: poForm.total_amount || '0',
      currency: poForm.currency.trim() || 'XPF',
      notes: poForm.notes.trim() || null,
    });
    poDialog.value = false;
    Object.assign(poForm, { supplier_name: '', order_number: '', ordered_at: '', total_amount: '', notes: '' });
    notice.value = `Bon de commande enregistré. ${updated.orders_updated ?? 0} commande(s) passée(s) en « commandée au fournisseur ».`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

async function removePo(index: number) {
  if (!selected.value) return;
  error.value = null;
  try {
    await removeSupplierOrder(selected.value.id, index);
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Suppression impossible.';
  }
}

// --- Reminders ---
const reminders = ref<Reminder[]>([]);
const remindersLoading = ref(false);
const webhookUrl = ref('');
const reminderDialog = ref(false);
const reminderEditId = ref<string | null>(null);
const reminderForm = reactive<{
  offset_days: number;
  anchor: string;
  message_template: string;
  image_url: string | null;
}>({ offset_days: 2, anchor: 'cutoff', message_template: '', image_url: '' });

const reminderColumns: QTableColumn[] = [
  {
    name: 'when',
    label: 'Publication',
    field: 'scheduled_at',
    align: 'left',
    format: (v: string) => formatDateTime(v),
  },
  { name: 'offset', label: 'Avant', field: (r: Reminder) => `J-${r.offset_days}`, align: 'left' },
  { name: 'text', label: 'Message (rendu)', field: 'rendered_text', align: 'left', style: 'white-space: normal; max-width: 480px' },
  { name: 'status', label: 'État', field: 'status', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

const REMINDER_LABELS: Record<string, string> = {
  scheduled: 'Planifié',
  sent: 'Publié',
  failed: 'Échec',
  cancelled: 'Annulé',
};
const reminderLabel = (s: string) => REMINDER_LABELS[s] ?? s;
const reminderColor = (s: string) =>
  s === 'sent' ? 'green' : s === 'failed' ? 'negative' : s === 'cancelled' ? 'grey-6' : 'primary';

async function loadReminders() {
  if (!selected.value) return;
  remindersLoading.value = true;
  try {
    reminders.value = await listReminders(selected.value.id);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement des rappels impossible.';
  } finally {
    remindersLoading.value = false;
  }
}

async function loadWebhook() {
  try {
    const settings = await listSystemSettings();
    webhookUrl.value = settings.find((s) => s.key === 'social_webhook_url')?.value ?? '';
  } catch {
    // the field stays empty; saving it creates the setting
  }
}

async function saveWebhook() {
  error.value = null;
  try {
    await updateSystemSetting('social_webhook_url', { value: webhookUrl.value.trim() });
    notice.value = 'URL du webhook enregistrée.';
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement du webhook impossible.';
  }
}

function openReminder(r?: Reminder) {
  reminderEditId.value = r?.id ?? null;
  Object.assign(reminderForm, {
    offset_days: r?.offset_days ?? 2,
    anchor: r?.anchor ?? 'cutoff',
    message_template:
      r?.message_template ?? '⏰ Plus que {days_left} jours pour rejoindre le départ groupé « {name} » (clôture le {cutoff_date}). {shop_url}',
    image_url: r?.image_url ?? '',
  });
  reminderDialog.value = true;
}

async function submitReminder() {
  if (!selected.value) return;
  saving.value = true;
  error.value = null;
  const payload = {
    offset_days: Number(reminderForm.offset_days) || 0,
    anchor: reminderForm.anchor,
    message_template: reminderForm.message_template.trim(),
    image_url: (reminderForm.image_url ?? '').trim() || null,
  };
  try {
    if (reminderEditId.value) {
      await updateReminder(reminderEditId.value, payload);
    } else {
      await createReminder(selected.value.id, payload);
    }
    reminderDialog.value = false;
    await loadReminders();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement du rappel impossible.';
  } finally {
    saving.value = false;
  }
}

async function publishNow(r: Reminder) {
  error.value = null;
  try {
    const result = await publishReminder(r.id);
    notice.value = result.status === 'sent' ? 'Rappel publié.' : `Publication échouée : ${result.error ?? ''}`;
    await loadReminders();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Publication impossible.';
  }
}

async function removeReminder(r: Reminder) {
  error.value = null;
  try {
    await deleteReminder(r.id);
    await loadReminders();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Suppression impossible.';
  }
}

// --- Lifecycle / delete ---
async function advance(d: Departure) {
  const next = nextDepartureStatus(d.status);
  if (!next) return;
  error.value = null;
  try {
    const updated = await updateDeparture(d.id, { status: next });
    const moved = updated.orders_updated ?? 0;
    notice.value = `« ${d.name} » → ${departureStatusLabel(next)}. ${moved} commande(s) mise(s) à jour et client(s) prévenu(s).`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Changement de statut impossible.';
  }
}

async function remove(d: Departure) {
  error.value = null;
  try {
    await deleteDeparture(d.id);
    if (selected.value?.id === d.id) selected.value = null;
    notice.value = `« ${d.name} » supprimé.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Suppression impossible.';
  }
}

// --- Create / edit ---
const dialog = ref(false);
const editId = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const statusOptions = DEPARTURE_STATUSES.map((s) => ({ label: departureStatusLabel(s), value: s }));

interface DepartureForm {
  name: string;
  order_cutoff_at: string;
  estimated_delivery_at: string | null;
  departure_at: string | null;
  status: string;
  is_published: boolean;
  min_amount: number | null;
  min_units: number | null;
  recurrence_days: number | null;
  notes: string;
}

const form = reactive<DepartureForm>(blankForm());

function blankForm(): DepartureForm {
  return {
    name: '',
    order_cutoff_at: '',
    estimated_delivery_at: null,
    departure_at: null,
    status: 'open',
    is_published: true,
    min_amount: null,
    min_units: null,
    recurrence_days: null,
    notes: '',
  };
}

/** ISO → value of an `<input type="datetime-local">` / `type="date"` (local time). */
function toInput(iso: string | null, withTime: boolean): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return withTime ? `${date}T${pad(d.getHours())}:${pad(d.getMinutes())}` : date;
}

/** Input value (local) → ISO for the API. A bare date is sent at local noon so
 * it stays on the same calendar day once shown in Tahiti (UTC-10). */
function toIso(value: string | null): string | null {
  if (!value) return null;
  return new Date(value.includes('T') ? value : `${value}T12:00`).toISOString();
}

/** `v-model.number` yields '' on a cleared field: treat it as null. */
function numOrNull(value: number | string | null): number | null {
  return value === null || value === '' || Number.isNaN(Number(value)) ? null : Number(value);
}

function openCreate() {
  editId.value = null;
  Object.assign(form, blankForm());
  dialogError.value = null;
  dialog.value = true;
}

function openEdit(d: Departure) {
  editId.value = d.id;
  Object.assign(form, {
    name: d.name,
    order_cutoff_at: toInput(d.order_cutoff_at, true) ?? '',
    estimated_delivery_at: toInput(d.estimated_delivery_at, false),
    departure_at: toInput(d.departure_at, false),
    status: d.status,
    is_published: d.is_published,
    min_amount: d.min_amount === null ? null : Number(d.min_amount),
    min_units: d.min_units,
    recurrence_days: d.recurrence_days,
    notes: d.notes ?? '',
  });
  dialogError.value = null;
  dialog.value = true;
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  const payload: DepartureWrite = {
    name: form.name.trim(),
    order_cutoff_at: toIso(form.order_cutoff_at) ?? '',
    estimated_delivery_at: toIso(form.estimated_delivery_at),
    departure_at: toIso(form.departure_at),
    status: form.status,
    is_published: form.is_published,
    min_amount: numOrNull(form.min_amount) === null ? null : String(numOrNull(form.min_amount)),
    min_units: numOrNull(form.min_units),
    recurrence_days: numOrNull(form.recurrence_days),
    notes: form.notes.trim() || null,
  };
  try {
    if (editId.value) {
      await updateDeparture(editId.value, payload);
    } else {
      await createDeparture(payload);
    }
    dialog.value = false;
    notice.value = 'Départ enregistré.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void load();
  void loadWebhook();
});
</script>
