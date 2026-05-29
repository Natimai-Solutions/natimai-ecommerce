<template>
  <q-dialog v-model="open">
    <q-card class="product-details">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6 ellipsis">{{ product.name }}</div>
        <q-space />
        <q-btn v-close-popup icon="close" flat round dense aria-label="Fermer" />
      </q-card-section>

      <q-card-section class="row q-col-gutter-md">
        <!-- Images -->
        <div class="col-12 col-sm-5">
          <q-img
            :src="mainImage ?? placeholderImg"
            :ratio="1"
            fit="contain"
            class="rounded-borders bg-grey-1"
          >
            <template #error>
              <div class="absolute-full flex flex-center bg-grey-2">
                <q-icon name="image_not_supported" size="3rem" color="grey-5" />
              </div>
            </template>
          </q-img>
          <div v-if="gallery.length > 1" class="row q-gutter-xs q-mt-sm">
            <q-img
              v-for="(url, i) in gallery"
              :key="i"
              :src="url"
              :ratio="1"
              width="52px"
              fit="contain"
              class="cursor-pointer rounded-borders bg-grey-1 gallery-thumb"
              :class="{ 'gallery-thumb--active': url === mainImage }"
              @click="selectedImage = url"
            />
          </div>
        </div>

        <!-- Infos principales -->
        <div class="col-12 col-sm-7">
          <div class="text-caption text-grey-6">
            {{ product.manufacturer ?? product.supplier_name ?? '—' }}
          </div>
          <div v-if="product.vendor_part_number" class="text-caption text-grey-5">
            Réf. {{ product.vendor_part_number }}
          </div>
          <div v-if="product.ean" class="text-caption text-grey-5">
            EAN {{ product.ean }}
          </div>

          <div class="text-h5 text-weight-bold text-primary q-mt-md">
            {{ displayPrice }}
          </div>
          <div
            v-if="!selectedMode && product.base_price === '0.00'"
            class="text-caption text-grey-6"
          >
            Prix sur devis
          </div>

          <div
            class="text-body2 q-mt-sm"
            :class="isOutOfStock ? 'text-grey-6' : 'text-positive'"
          >
            <q-icon name="inventory_2" size="16px" class="q-mr-xs" />
            <span v-if="isOutOfStock">Sur commande</span>
            <span v-else>{{ stockQuantity }} en stock fournisseur</span>
          </div>

          <!-- Mode de livraison import -->
          <template v-if="shippingLoading || shippingModes.length > 0">
            <div class="text-caption text-grey-7 q-mb-xs q-mt-md">Mode de livraison</div>
            <q-skeleton v-if="shippingLoading" type="QInput" />
            <template v-else>
              <q-select
                v-model="selectedModeKey"
                :options="shippingModeOptions"
                option-value="value"
                option-label="label"
                emit-value
                map-options
                outlined
                dense
                @update:model-value="onShippingModeChange"
              >
                <template #prepend><q-icon name="local_shipping" /></template>
              </q-select>
              <div v-if="selectedMode" class="text-caption text-grey-7 q-mt-xs">
                Fret import&nbsp;: {{ formatXpf(parseFloat(selectedMode.freight)) }}
                <span v-if="selectedMode.eta_days">
                  &nbsp;·&nbsp;{{ selectedMode.eta_days }}&nbsp;j
                </span>
              </div>
            </template>
          </template>

          <div
            v-if="safeDescription"
            class="text-body2 q-mt-md product-description"
            v-html="safeDescription"
          ></div>
        </div>
      </q-card-section>

      <!-- Points clés -->
      <q-card-section v-if="features.length > 0" class="q-pt-none">
        <div class="text-subtitle2 q-mb-xs">Points clés</div>
        <ul class="q-pl-md q-my-none">
          <li v-for="(feat, i) in features" :key="i" class="text-body2">{{ feat }}</li>
        </ul>
      </q-card-section>

      <!-- Spécifications techniques -->
      <q-card-section v-if="specGroups.length > 0" class="q-pt-none">
        <div class="text-subtitle2 q-mb-sm">Caractéristiques techniques</div>
        <div v-for="grp in specGroups" :key="grp.group" class="q-mb-md">
          <div v-if="grp.group" class="text-caption text-grey-7 q-mb-xs">
            {{ grp.group }}
          </div>
          <q-markup-table flat dense bordered wrap-cells>
            <tbody>
              <tr v-for="(spec, i) in grp.specs" :key="i">
                <td class="text-grey-8" style="width: 45%">{{ spec.name }}</td>
                <td>{{ spec.value }}{{ spec.unit ? ' ' + spec.unit : '' }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </div>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Fermer" color="grey-7" v-close-popup />
        <q-btn
          flat
          color="primary"
          icon="open_in_new"
          label="Voir la fiche"
          :to="productRoute"
          @click="open = false"
        />
        <q-btn
          unelevated
          color="primary"
          icon="add_shopping_cart"
          label="Ajouter au panier"
          :disable="isOutOfStock"
          @click="emit('add-to-cart', product)"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DOMPurify from 'isomorphic-dompurify'
import type { components } from '@app/api-types'
import { formatXpf } from '@app/utils'
import {
  getProductShippingModes,
  type ShippingModePricePublic,
} from 'src/api/products'
import { getProductRoute } from 'src/utils/productRoute'

type ProductPublic = components['schemas']['ProductPublic']

const SHIPPING_MODE_STORAGE_KEY = 'shipping_mode_preference'

const props = defineProps<{ product: ProductPublic }>()
const emit = defineEmits<{ 'add-to-cart': [product: ProductPublic] }>()
const open = defineModel<boolean>({ default: false })
const productRoute = computed(() => getProductRoute(props.product))

const shippingModes = ref<ShippingModePricePublic[]>([])
const selectedModeKey = ref<string | null>(null)
const shippingLoading = ref(false)

watch(open, async (isOpen) => {
  if (isOpen) {
    await loadShippingModes()
  } else {
    shippingModes.value = []
    selectedModeKey.value = null
  }
})

async function loadShippingModes(): Promise<void> {
  shippingLoading.value = true
  try {
    const data = await getProductShippingModes(props.product.id)
    shippingModes.value = data.shipping_modes
    const saved = localStorage.getItem(SHIPPING_MODE_STORAGE_KEY)
    const available = data.shipping_modes.map((m) => m.service_level)
    selectedModeKey.value =
      saved !== null && available.includes(saved) ? saved : data.default_mode
  } catch {
    shippingModes.value = []
    selectedModeKey.value = null
  } finally {
    shippingLoading.value = false
  }
}

function onShippingModeChange(modeKey: string | null): void {
  selectedModeKey.value = modeKey
  if (modeKey) localStorage.setItem(SHIPPING_MODE_STORAGE_KEY, modeKey)
}

const selectedMode = computed(
  () => shippingModes.value.find((m) => m.service_level === selectedModeKey.value) ?? null,
)

const shippingModeOptions = computed(() =>
  shippingModes.value
    .filter((m) => m.service_level !== null)
    .map((m) => ({
      label: m.customer_label ?? m.service_level ?? m.route_id,
      value: m.service_level as string,
    })),
)

const placeholderImg = '/icons/placeholder-product.svg'

const isOutOfStock = computed(() => parseFloat(props.product.supplier_quantity) <= 0)

const stockQuantity = computed(() =>
  Math.max(0, Math.round(parseFloat(props.product.supplier_quantity))),
)

const displayPrice = computed(() => {
  if (selectedMode.value) {
    const price = parseFloat(selectedMode.value.sale_price)
    return price > 0 ? formatXpf(price) : '—'
  }
  const price = parseFloat(props.product.base_price)
  if (price === 0) return '—'
  return formatXpf(price)
})

const safeDescription = computed(() => {
  const raw = props.product.long_description ?? props.product.description ?? ''
  return raw ? DOMPurify.sanitize(raw) : ''
})

const features = computed(() =>
  (props.product.features ?? []).map((f) => String(f).trim()).filter(Boolean),
)

type Spec = { name: string; value: string; unit: string }

function toStr(v: unknown): string {
  return typeof v === 'string' || typeof v === 'number' ? String(v).trim() : ''
}

const specGroups = computed<{ group: string; specs: Spec[] }[]>(() => {
  const groups = new Map<string, Spec[]>()
  for (const raw of props.product.technical_specifications ?? []) {
    const name = toStr(raw['name']) || toStr(raw['label']) || toStr(raw['feature'])
    const value = toStr(raw['value']) || toStr(raw['presentation_value'])
    if (!name || !value) continue
    const group = toStr(raw['group'])
    const unit = toStr(raw['unit'])
    const arr = groups.get(group) ?? []
    arr.push({ name, value, unit })
    groups.set(group, arr)
  }
  return [...groups.entries()].map(([group, specs]) => ({ group, specs }))
})

function pickUrl(obj: unknown): string | null {
  if (typeof obj === 'string') return obj
  if (obj && typeof obj === 'object' && 'url' in obj) {
    const u = (obj as Record<string, unknown>)['url']
    return typeof u === 'string' ? u : null
  }
  return null
}

const gallery = computed<string[]>(() => {
  const urls: string[] = []
  const main = props.product.image_url ?? props.product.supplier_image_url
  if (main) urls.push(main)
  for (const raw of props.product.icecat_images ?? []) {
    const url =
      pickUrl(raw['medium']) ??
      pickUrl(raw['low']) ??
      pickUrl(raw['high']) ??
      pickUrl(raw['thumb']) ??
      pickUrl(raw)
    if (url && !urls.includes(url)) urls.push(url)
  }
  return urls
})

const selectedImage = ref<string | null>(null)
const mainImage = computed(() => selectedImage.value ?? gallery.value[0] ?? null)
</script>

<style scoped lang="scss">
.product-details {
  width: 820px;
  max-width: 92vw;
}

.gallery-thumb {
  border: 1px solid transparent;

  &--active {
    border-color: var(--q-primary);
  }
}

.product-description {
  :deep(p) {
    margin: 0 0 0.5em;
  }

  :deep(ul),
  :deep(ol) {
    margin: 0 0 0.5em;
    padding-left: 1.2em;
  }

  :deep(img) {
    max-width: 100%;
    height: auto;
  }
}
</style>
