<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Transporteurs</div>
      <q-toggle v-model="showRetired" label="Afficher les retirés" class="q-mr-md" />
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
      <q-btn color="primary" icon="add" label="Nouveau transporteur" no-caps @click="openCreate" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      DHL, Chronopost, Colissimo, coursier local… Aucune intégration d'API : le numéro de suivi est
      saisi à la remise au transporteur. Le gabarit d'URL (avec <code v-pre>{ref}</code>) sert à
      construire le lien « Suivre le colis » affiché au client.
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" dense rounded>{{
      notice
    }}</q-banner>

    <q-table
      :rows="rows"
      :columns="columns"
      row-key="id"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-template="props">
        <q-td :props="props">
          <span v-if="props.row.tracking_url_template" class="text-caption">{{
            props.row.tracking_url_template
          }}</span>
          <span v-else class="text-grey-6">— (pas de lien de suivi)</span>
        </q-td>
      </template>
      <template #body-cell-active="props">
        <q-td :props="props">
          <q-chip
            dense
            size="sm"
            :color="props.row.is_active ? 'green' : 'grey-6'"
            text-color="white"
            :label="props.row.is_active ? 'Actif' : 'Retiré'"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat dense icon="edit" color="primary" @click="openEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.is_active"
            flat
            dense
            icon="visibility_off"
            color="grey-8"
            @click="retire(props.row)"
          >
            <q-tooltip>Retirer du sélecteur (les expéditions passées gardent leur suivi)</q-tooltip>
          </q-btn>
          <q-btn v-else flat dense icon="visibility" color="positive" @click="restore(props.row)">
            <q-tooltip>Réactiver</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucun transporteur.</div>
      </template>
    </q-table>

    <q-dialog v-model="dialog">
      <q-card style="min-width: 460px">
        <q-card-section class="text-h6">{{
          editId ? 'Modifier le transporteur' : 'Nouveau transporteur'
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
              v-model="form.code"
              label="Code *"
              hint="Identifiant stable (ex. dhl, chronopost). Minuscules, sans espace."
              outlined
              dense
              :rules="[(v: string) => !!v.trim() || 'Code requis']"
            />
            <q-input
              v-model="form.tracking_url_template"
              label="Gabarit d'URL de suivi (optionnel)"
              hint="https://… contenant {ref}, ex. https://www.dhl.com/track?id={ref}"
              outlined
              dense
              clearable
            />
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
  createCarrier,
  listCarriers,
  retireCarrier,
  updateCarrier,
  type Carrier,
} from 'src/api/shipping';
import { extractApiError } from 'src/api/errors';

const carriers = ref<Carrier[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const showRetired = ref(false);

const rows = computed(() =>
  showRetired.value ? carriers.value : carriers.value.filter((c) => c.is_active),
);

const columns: QTableColumn[] = [
  { name: 'name', label: 'Nom', field: 'name', align: 'left' },
  { name: 'code', label: 'Code', field: 'code', align: 'left' },
  { name: 'template', label: 'Lien de suivi', field: 'tracking_url_template', align: 'left' },
  { name: 'active', label: 'État', field: 'is_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    carriers.value = await listCarriers(true);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

// --- Create / edit ---
const dialog = ref(false);
const editId = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const form = reactive<{ name: string; code: string; tracking_url_template: string | null }>({
  name: '',
  code: '',
  tracking_url_template: '',
});

function openCreate() {
  editId.value = null;
  form.name = '';
  form.code = '';
  form.tracking_url_template = '';
  dialogError.value = null;
  dialog.value = true;
}

function openEdit(c: Carrier) {
  editId.value = c.id;
  form.name = c.name;
  form.code = c.code;
  form.tracking_url_template = c.tracking_url_template ?? '';
  dialogError.value = null;
  dialog.value = true;
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  const payload = {
    name: form.name.trim(),
    code: form.code.trim(),
    // q-input clearable sets null; the API stores blank as "no tracking page".
    tracking_url_template: (form.tracking_url_template ?? '').trim() || null,
  };
  try {
    if (editId.value) {
      await updateCarrier(editId.value, payload);
    } else {
      await createCarrier(payload);
    }
    dialog.value = false;
    notice.value = 'Transporteur enregistré.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

async function retire(c: Carrier) {
  error.value = null;
  try {
    await retireCarrier(c.id);
    notice.value = `${c.name} retiré du sélecteur.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Opération impossible.';
  }
}

async function restore(c: Carrier) {
  error.value = null;
  try {
    await updateCarrier(c.id, { is_active: true });
    notice.value = `${c.name} réactivé.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Opération impossible.';
  }
}

watch(showRetired, () => {
  notice.value = null;
});

onMounted(load);
</script>
