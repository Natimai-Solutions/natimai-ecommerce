<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Catalogue de specs</div>
      <q-btn color="primary" icon="add" label="Nouvelle spec" no-caps @click="openCreate" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      Définitions canoniques projetées depuis Icecat. Modifier les alias puis re-projeter
      côté backend pour réindexer.
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

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
      <template #body-cell-categories="props">
        <q-td :props="props">
          <q-chip v-for="c in props.row.categories" :key="c" dense outline color="primary" :label="c" />
          <span v-if="props.row.categories.length === 0" class="text-grey-5">—</span>
        </q-td>
      </template>
      <template #body-cell-aliases="props">
        <q-td :props="props">
          <span class="text-grey-7">{{ props.row.aliases.length }} alias</span>
        </q-td>
      </template>
      <template #body-cell-is_active="props">
        <q-td :props="props" align="center">
          <q-chip dense :color="props.row.is_active ? 'green' : 'grey-5'" text-color="white" :label="props.row.is_active ? 'actif' : 'inactif'" />
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
            icon="delete"
            color="negative"
            @click="confirmDelete(props.row)"
          >
            <q-tooltip>Désactiver</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>

    <!-- Create / edit dialog -->
    <q-dialog v-model="dialog">
      <q-card style="min-width: 420px; max-width: 560px">
        <q-card-section class="text-h6">{{ editingKey ? `Modifier ${editingKey}` : 'Nouvelle spec' }}</q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{ dialogError }}</q-banner>
            <q-input
              v-model="form.key"
              label="Clé canonique (ex: memory_gb) *"
              outlined
              dense
              :readonly="!!editingKey"
              :rules="req"
            />
            <q-input v-model="form.label_fr" label="Libellé FR *" outlined dense :rules="req" />
            <q-select v-model="form.type" :options="typeOptions" label="Type *" outlined dense emit-value map-options :rules="req" />
            <q-input v-model="form.unit" label="Unité (ex: GB)" outlined dense />
            <q-select
              v-model="form.categories"
              label="Catégories"
              outlined
              dense
              multiple
              use-input
              use-chips
              hide-dropdown-icon
              new-value-mode="add-unique"
              :options="[]"
            />
            <q-select
              v-model="form.aliases"
              label="Alias Icecat"
              outlined
              dense
              multiple
              use-input
              use-chips
              hide-dropdown-icon
              new-value-mode="add-unique"
              :options="[]"
            />
            <q-toggle v-if="editingKey" v-model="form.is_active" label="Actif" />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" :label="editingKey ? 'Enregistrer' : 'Créer'" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Delete confirm -->
    <q-dialog v-model="deleteDialog">
      <q-card>
        <q-card-section class="row items-center">
          <q-icon name="warning" color="negative" size="md" class="q-mr-sm" />
          <span>Désactiver la spec « {{ toDelete?.key }} » ?</span>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Annuler" v-close-popup />
          <q-btn flat label="Désactiver" color="negative" :loading="deleting" @click="performDelete" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import {
  createSpecDefinition,
  deleteSpecDefinition,
  listSpecDefinitions,
  updateSpecDefinition,
  type SpecDefinition,
} from 'src/api/specDefinitions'
import { extractApiError } from 'src/api/errors'

const rows = ref<SpecDefinition[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || 'Requis',
]
const typeOptions = [
  { label: 'Numérique', value: 'numeric' },
  { label: 'Énuméré', value: 'enum' },
]

const columns: QTableColumn[] = [
  { name: 'key', label: 'Clé', field: 'key', align: 'left' },
  { name: 'label_fr', label: 'Libellé', field: 'label_fr', align: 'left' },
  { name: 'type', label: 'Type', field: 'type', align: 'left' },
  { name: 'unit', label: 'Unité', field: (r) => r.unit ?? '—', align: 'left' },
  { name: 'categories', label: 'Catégories', field: 'categories', align: 'left' },
  { name: 'aliases', label: 'Alias', field: 'aliases', align: 'left' },
  { name: 'is_active', label: 'Statut', field: 'is_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]

async function load() {
  loading.value = true
  error.value = null
  try {
    rows.value = await listSpecDefinitions()
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.'
  } finally {
    loading.value = false
  }
}

const dialog = ref(false)
const editingKey = ref<string | null>(null)
const saving = ref(false)
const dialogError = ref<string | null>(null)
const form = reactive({
  key: '',
  label_fr: '',
  type: 'numeric',
  unit: '',
  categories: [] as string[],
  aliases: [] as string[],
  is_active: true,
})

function openCreate() {
  dialogError.value = null
  editingKey.value = null
  form.key = ''
  form.label_fr = ''
  form.type = 'numeric'
  form.unit = ''
  form.categories = []
  form.aliases = []
  form.is_active = true
  dialog.value = true
}

function openEdit(spec: SpecDefinition) {
  dialogError.value = null
  editingKey.value = spec.key
  form.key = spec.key
  form.label_fr = spec.label_fr
  form.type = spec.type
  form.unit = spec.unit ?? ''
  form.categories = [...spec.categories]
  form.aliases = [...spec.aliases]
  form.is_active = spec.is_active
  dialog.value = true
}

async function submit() {
  saving.value = true
  dialogError.value = null
  try {
    if (editingKey.value) {
      await updateSpecDefinition(editingKey.value, {
        label_fr: form.label_fr,
        type: form.type,
        unit: form.unit || null,
        categories: form.categories,
        aliases: form.aliases,
        is_active: form.is_active,
      })
    } else {
      await createSpecDefinition({
        key: form.key,
        label_fr: form.label_fr,
        type: form.type,
        unit: form.unit || null,
        categories: form.categories,
        aliases: form.aliases,
      })
    }
    dialog.value = false
    await load()
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.'
  } finally {
    saving.value = false
  }
}

const deleteDialog = ref(false)
const deleting = ref(false)
const toDelete = ref<SpecDefinition | null>(null)

function confirmDelete(spec: SpecDefinition) {
  toDelete.value = spec
  deleteDialog.value = true
}

async function performDelete() {
  if (!toDelete.value) return
  deleting.value = true
  try {
    await deleteSpecDefinition(toDelete.value.key)
    deleteDialog.value = false
    toDelete.value = null
    await load()
  } catch (err) {
    error.value = extractApiError(err) ?? 'Désactivation impossible.'
    deleteDialog.value = false
  } finally {
    deleting.value = false
  }
}

onMounted(load)
</script>
