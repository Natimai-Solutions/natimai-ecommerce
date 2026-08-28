<template>
  <q-page padding>
    <div class="row items-center q-col-gutter-sm q-mb-md">
      <div class="text-h6 col">Demandes de devis</div>
      <q-input
        v-model="search"
        dense
        outlined
        clearable
        debounce="300"
        placeholder="Email ou nom du client"
        style="min-width: 240px"
        @update:model-value="load"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
      <q-toggle v-model="openOnly" label="À traiter uniquement" @update:model-value="load" />
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

    <div v-if="loading" class="text-center q-pa-lg">
      <q-spinner color="primary" size="2em" />
    </div>

    <q-banner v-else-if="rows.length === 0" class="bg-blue-1 text-blue-10" rounded>
      <template #avatar><q-icon name="info" /></template>
      {{
        search || openOnly
          ? 'Aucune demande pour ces critères.'
          : 'Aucune demande de devis pour le moment.'
      }}
    </q-banner>

    <q-table
      v-else
      :rows="rows"
      :columns="columns"
      row-key="quote_request_id"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-client="props">
        <q-td :props="props">
          <div>{{ props.row.full_name || props.row.email }}</div>
          <div class="text-caption text-grey-6">
            {{ props.row.full_name ? props.row.email : '' }}
            <span v-if="props.row.phone"> — {{ props.row.phone }}</span>
          </div>
        </q-td>
      </template>
      <template #body-cell-origin="props">
        <q-td :props="props">
          <q-chip
            dense
            size="sm"
            :color="props.row.is_registered_customer ? 'primary' : 'grey-6'"
            text-color="white"
            :label="props.row.is_registered_customer ? 'Client' : 'Visiteur'"
          />
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            dense
            size="sm"
            :color="quoteStatusColor(props.row.status)"
            text-color="white"
            :label="quoteStatusLabel(props.row.status)"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="visibility"
            color="primary"
            label="Détail"
            :loading="openingId === props.row.quote_request_id"
            @click="openDetail(props.row.quote_request_id)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Détail + suivi -->
    <q-dialog v-model="dialog">
      <q-card style="min-width: 560px; max-width: 760px">
        <q-card-section class="row items-center">
          <div class="text-h6 col">
            Demande de {{ detail?.full_name || detail?.email }}
          </div>
          <q-chip
            v-if="detail"
            dense
            size="sm"
            :color="quoteStatusColor(detail.status)"
            text-color="white"
            :label="quoteStatusLabel(detail.status)"
          />
        </q-card-section>

        <q-card-section v-if="detail" class="q-pt-none">
          <div class="text-caption text-grey-7 q-mb-sm">
            Reçue le {{ formatDate(detail.created_at) }} —
            {{ detail.is_registered_customer ? 'client identifié' : 'visiteur non connecté' }}
            <span v-if="detail.phone"> — {{ detail.phone }}</span>
          </div>

          <q-banner
            v-if="detail.status === 'email_failed'"
            class="bg-red-1 text-red-9 q-mb-md"
            dense
            rounded
          >
            <template #avatar><q-icon name="report_problem" /></template>
            L'email vers le support n'a pas pu être transmis : cette demande n'a été vue
            que par cet écran.
          </q-banner>

          <div v-if="detail.shipping_address" class="q-mb-sm">
            <div class="text-caption text-grey-7">Adresse de livraison</div>
            <div>{{ detail.shipping_address }}</div>
          </div>

          <div v-if="detail.notes" class="q-mb-md">
            <div class="text-caption text-grey-7">Message du client</div>
            <div style="white-space: pre-line">{{ detail.notes }}</div>
          </div>

          <div class="text-caption text-grey-7 q-mb-xs">
            Panier au moment de la demande ({{ detail.item_count }} article(s))
          </div>
          <q-markup-table flat bordered dense class="q-mb-md">
            <thead>
              <tr>
                <th class="text-left">Produit</th>
                <th class="text-right">Qté</th>
                <th class="text-right">PU</th>
                <th class="text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in detail.items" :key="index">
                <td class="text-left">{{ item.product_name ?? '—' }}</td>
                <td class="text-right">{{ item.quantity ?? '—' }}</td>
                <td class="text-right">{{ item.unit_price ?? '—' }}</td>
                <td class="text-right">{{ item.line_total ?? '—' }}</td>
              </tr>
            </tbody>
          </q-markup-table>
          <div v-if="detail.subtotal_amount" class="text-right text-weight-medium q-mb-md">
            Sous-total : {{ detail.subtotal_amount }} {{ detail.currency }}
          </div>

          <q-separator class="q-my-md" />

          <q-select
            v-model="editStatus"
            :options="QUOTE_STATUS_OPTIONS"
            emit-value
            map-options
            outlined
            dense
            label="Statut"
            class="q-mb-sm"
          />
          <q-input
            v-model="editComment"
            type="textarea"
            outlined
            dense
            autogrow
            label="Suivi interne (non visible du client)"
          />
          <q-banner v-if="saveError" class="bg-red-1 text-red-9 q-mt-sm" dense rounded>
            {{ saveError }}
          </q-banner>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat label="Fermer" @click="dialog = false" />
          <q-btn
            color="primary"
            no-caps
            label="Enregistrer"
            :loading="saving"
            @click="save"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import {
  getQuoteRequest,
  listQuoteRequests,
  QUOTE_STATUS_OPTIONS,
  quoteStatusColor,
  quoteStatusLabel,
  updateQuoteRequest,
  type AdminQuoteRequestDetail,
  type AdminQuoteRequestListItem,
  type QuoteRequestStatus,
} from 'src/api/quoteRequests';
import { extractApiError } from 'src/api/errors';

const rows = ref<AdminQuoteRequestListItem[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const search = ref<string | null>(null);
// Vue de travail par défaut : une demande close n'a plus à encombrer la file.
const openOnly = ref(true);

const dialog = ref(false);
const detail = ref<AdminQuoteRequestDetail | null>(null);
const openingId = ref<string | null>(null);
const editStatus = ref<QuoteRequestStatus>('requested');
const editComment = ref('');
const saving = ref(false);
const saveError = ref<string | null>(null);

function formatDate(raw: string | null): string {
  if (!raw) return '—';
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime())
    ? raw
    : parsed.toLocaleString('fr-FR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
}

const columns: QTableColumn[] = [
  {
    name: 'created_at',
    label: 'Reçue le',
    field: 'created_at',
    align: 'left',
    format: (v: string | null) => formatDate(v),
  },
  { name: 'client', label: 'Client', field: 'email', align: 'left' },
  { name: 'origin', label: 'Origine', field: 'is_registered_customer', align: 'left' },
  { name: 'items', label: 'Articles', field: 'item_count', align: 'right' },
  {
    name: 'total',
    label: 'Sous-total',
    field: 'subtotal_amount',
    align: 'right',
    format: (v: string | null, row: AdminQuoteRequestListItem) =>
      v ? `${v} ${row.currency ?? ''}`.trim() : '—',
  },
  { name: 'status', label: 'Statut', field: 'status', align: 'left' },
  { name: 'actions', label: '', field: 'quote_request_id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = await listQuoteRequests({
      search: search.value ?? undefined,
      openOnly: openOnly.value,
    });
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

async function openDetail(id: string) {
  openingId.value = id;
  saveError.value = null;
  try {
    const loaded = await getQuoteRequest(id);
    detail.value = loaded;
    editStatus.value = loaded.status;
    editComment.value = loaded.admin_comment ?? '';
    dialog.value = true;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    openingId.value = null;
  }
}

async function save() {
  if (!detail.value) return;
  saving.value = true;
  saveError.value = null;
  try {
    await updateQuoteRequest(detail.value.quote_request_id, {
      status: editStatus.value,
      admin_comment: editComment.value,
    });
    dialog.value = false;
    // La demande peut sortir du filtre « à traiter » : on recharge la liste
    // plutôt que de patcher la ligne en place.
    await load();
  } catch (err) {
    saveError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
