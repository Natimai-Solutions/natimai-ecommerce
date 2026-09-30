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
          <div class="text-h6 col">Demande de {{ detail?.full_name || detail?.email }}</div>
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
            L'email vers le support n'a pas pu être transmis : cette demande n'a été vue que par cet
            écran.
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

          <!-- Le devis : lignes au prix consenti, livraison, validité, PDF -->
          <div class="row items-center q-mb-xs q-gutter-sm">
            <div class="text-subtitle2 col">
              Devis
              <span v-if="detail.quote_number" class="text-primary">{{ detail.quote_number }}</span>
              <span v-if="detail.quoted_at" class="text-caption text-grey-7">
                — émis le {{ formatDate(detail.quoted_at) }}
              </span>
            </div>
            <q-btn
              v-if="detail.quote_number"
              flat
              dense
              no-caps
              icon="picture_as_pdf"
              label="PDF"
              @click="downloadQuotePdf(detail.quote_request_id, detail.quote_number)"
            />
          </div>
          <q-banner v-if="detail.order_id" class="bg-green-1 text-green-9 q-mb-sm" dense rounded>
            Devis commandé par le client :
            <router-link :to="`/orders/${detail.order_id}`">voir la commande</router-link>.
          </q-banner>
          <template v-else>
            <q-markup-table flat bordered dense class="q-mb-sm">
              <thead>
                <tr>
                  <th class="text-left">Désignation</th>
                  <th class="text-right">Qté</th>
                  <th class="text-right">PU TTC</th>
                  <th class="text-right">Total</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, index) in issueLines" :key="index">
                  <td>
                    <q-input v-model="line.product_name" dense outlined />
                    <div v-if="!line.product_id" class="text-caption text-orange-9">
                      Hors catalogue : non commandable en ligne
                    </div>
                  </td>
                  <td>
                    <q-input
                      v-model.number="line.quantity"
                      type="number"
                      min="1"
                      dense
                      outlined
                      style="width: 70px"
                    />
                  </td>
                  <td>
                    <q-input
                      v-model="line.unit_price"
                      type="number"
                      min="0"
                      dense
                      outlined
                      style="width: 120px"
                    />
                  </td>
                  <td class="text-right">{{ lineTotal(line) }}</td>
                  <td>
                    <q-btn
                      flat
                      dense
                      icon="close"
                      color="grey-7"
                      @click="issueLines.splice(index, 1)"
                    />
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
            <q-btn
              flat
              dense
              no-caps
              icon="add"
              label="Ligne libre"
              class="q-mb-sm"
              @click="
                issueLines.push({
                  product_id: null,
                  product_name: '',
                  quantity: 1,
                  unit_price: '0',
                })
              "
            />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="issueForm.shipping_fee_amount"
                class="col-4"
                type="number"
                min="0"
                label="Livraison (TTC)"
                dense
                outlined
              />
              <q-input
                v-model="issueForm.valid_until"
                class="col-4"
                type="date"
                label="Valable jusqu'au"
                dense
                outlined
                clearable
                hint="Défaut : 30 jours"
              />
              <div class="col-4 text-right text-weight-medium q-pt-sm">
                Total : {{ issueTotal }} {{ detail.currency ?? '' }}
              </div>
            </div>
            <q-input
              v-model="issueForm.customer_message"
              type="textarea"
              autogrow
              dense
              outlined
              label="Message au client (imprimé sur le devis)"
              class="q-mt-sm"
            />
            <div class="row items-center q-mt-sm q-gutter-sm">
              <q-toggle
                v-model="issueForm.send_email"
                label="Envoyer le PDF au client par e-mail"
                dense
              />
              <q-space />
              <q-btn
                color="primary"
                no-caps
                icon="send"
                :label="detail.quote_number ? 'Ré-émettre le devis' : 'Émettre le devis'"
                :loading="issuing"
                :disable="issueLines.length === 0"
                @click="issue"
              />
            </div>
          </template>

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
          <q-banner v-if="issueNotice" class="bg-green-1 text-green-9 q-mt-sm" dense rounded>
            {{ issueNotice }}
          </q-banner>
          <q-banner v-if="saveError" class="bg-red-1 text-red-9 q-mt-sm" dense rounded>
            {{ saveError }}
          </q-banner>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat label="Fermer" @click="dialog = false" />
          <q-btn color="primary" no-caps label="Enregistrer" :loading="saving" @click="save" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import {
  downloadQuotePdf,
  getQuoteRequest,
  issueQuote,
  listQuoteRequests,
  QUOTE_STATUS_OPTIONS,
  quoteStatusColor,
  quoteStatusLabel,
  updateQuoteRequest,
  type AdminQuoteRequestDetail,
  type AdminQuoteRequestListItem,
  type QuoteLine,
  type QuoteRequestStatus,
} from '@/api/quoteRequests';
import { extractApiError } from '@/api/errors';

// --- Issuing the quote (lines at the granted price, delivery, validity) ---
const issueLines = ref<QuoteLine[]>([]);
const issueForm = ref({
  shipping_fee_amount: '0',
  valid_until: '',
  customer_message: '',
  send_email: true,
});
const issuing = ref(false);
const issueNotice = ref<string | null>(null);

function lineTotal(line: QuoteLine): string {
  const total = (Number(line.quantity) || 0) * (Number(line.unit_price) || 0);
  return Number.isFinite(total) ? String(Math.round(total * 100) / 100) : '—';
}
const issueTotal = computed(() => {
  const lines = issueLines.value.reduce((sum, l) => sum + (Number(lineTotal(l)) || 0), 0);
  return String(
    Math.round((lines + (Number(issueForm.value.shipping_fee_amount) || 0)) * 100) / 100,
  );
});

function prefillIssue(loaded: AdminQuoteRequestDetail) {
  issueLines.value = loaded.proposed_lines.map((l) => ({
    ...l,
    unit_price: String(Number(l.unit_price)),
  }));
  const snapshot = loaded.quote_snapshot;
  issueForm.value = {
    shipping_fee_amount: snapshot ? String(Number(snapshot.shipping_fee_amount)) : '0',
    valid_until: loaded.valid_until ?? '',
    customer_message: snapshot?.customer_message ?? '',
    send_email: true,
  };
}

async function issue() {
  if (!detail.value) return;
  issuing.value = true;
  saveError.value = null;
  try {
    const result = await issueQuote(detail.value.quote_request_id, {
      lines: issueLines.value.map((l) => ({
        product_id: l.product_id,
        product_name: l.product_name.trim() || 'Article',
        quantity: Math.max(1, Math.floor(Number(l.quantity) || 1)),
        unit_price: String(Number(l.unit_price) || 0),
      })),
      shipping_fee_amount: String(Number(issueForm.value.shipping_fee_amount) || 0),
      valid_until: issueForm.value.valid_until || null,
      customer_message: issueForm.value.customer_message.trim() || null,
      send_email: issueForm.value.send_email,
    });
    detail.value = result;
    editStatus.value = result.status;
    prefillIssue(result);
    issueNotice.value = result.email_sent
      ? `Devis ${result.quote_number} émis et envoyé au client.`
      : `Devis ${result.quote_number} émis (sans e-mail).`;
    await load();
  } catch (err) {
    saveError.value = extractApiError(err) ?? 'Émission du devis impossible.';
  } finally {
    issuing.value = false;
  }
}

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
  {
    name: 'number',
    label: 'Devis',
    field: (r: AdminQuoteRequestListItem) => r.quote_number ?? '—',
    align: 'left',
  },
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
    prefillIssue(loaded);
    issueNotice.value = null;
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
