<template>
  <q-page class="product-page q-pa-md">
    <q-breadcrumbs class="text-grey-7 q-mb-md">
      <q-breadcrumbs-el icon="storefront" label="Catalogue" :to="{ name: 'catalogue' }" />
      <q-breadcrumbs-el :label="product?.name ?? 'Produit'" />
    </q-breadcrumbs>

    <div v-if="loading" class="row q-col-gutter-md">
      <div class="col-12 col-md-5">
        <q-skeleton height="420px" square />
      </div>
      <div class="col-12 col-md-7">
        <q-skeleton type="text" width="70%" />
        <q-skeleton type="text" width="40%" class="q-mt-sm" />
        <q-skeleton type="text" width="20%" class="q-mt-lg" />
        <q-skeleton type="text" width="95%" class="q-mt-md" />
        <q-skeleton type="text" width="85%" />
      </div>
    </div>

    <q-banner v-else-if="error" class="bg-red-1 text-red-8" rounded>
      <template #avatar><q-icon name="error_outline" /></template>
      {{ error }}
      <template #action>
        <q-btn flat color="primary" label="Retour au catalogue" :to="{ name: 'catalogue' }" />
      </template>
    </q-banner>

    <q-card v-else-if="product" class="product-page-card" flat bordered>
      <q-card-section class="row q-col-gutter-lg">
        <div class="col-12 col-md-5">
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
              width="68px"
              fit="contain"
              class="cursor-pointer rounded-borders bg-grey-1 gallery-thumb"
              :class="{ 'gallery-thumb--active': url === mainImage }"
              @click="selectedImage = url"
            />
          </div>
        </div>

        <div class="col-12 col-md-7">
          <h1 class="text-h5 text-weight-bold q-my-none">{{ product.name }}</h1>

          <div class="text-caption text-grey-6 q-mt-sm">
            {{ product.manufacturer ?? product.supplier_name ?? '—' }}
          </div>
          <div v-if="product.vendor_part_number" class="text-caption text-grey-5">
            Réf. {{ product.vendor_part_number }}
          </div>
          <div v-if="product.ean" class="text-caption text-grey-5">
            EAN {{ product.ean }}
          </div>

          <div class="text-h4 text-weight-bold text-primary q-mt-md">
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
            class="text-body1 q-mt-md product-description"
            v-html="safeDescription"
          ></div>
        </div>
      </q-card-section>

      <q-card-section v-if="features.length > 0" class="q-pt-none">
        <div class="text-subtitle2 q-mb-xs">Points clés</div>
        <ul class="q-pl-md q-my-none">
          <li v-for="(feat, i) in features" :key="i" class="text-body2">{{ feat }}</li>
        </ul>
      </q-card-section>

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
        <q-btn flat label="Retour au catalogue" color="grey-7" :to="{ name: 'catalogue' }" />
        <q-btn
          unelevated
          color="primary"
          icon="add_shopping_cart"
          label="Ajouter au panier"
          :disable="isOutOfStock"
          @click="onAddToCart"
        />
      </q-card-actions>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import DOMPurify from 'isomorphic-dompurify'
import { useMeta } from 'quasar'
import { computed, onMounted, onServerPrefetch, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { components } from '@app/api-types'
import { formatXpf } from '@app/utils'
import {
  getProductById,
  getProductShippingModes,
  type ShippingModePricePublic,
} from 'src/api/products'
import { getProductRouteByIdAndName, slugifyProductName } from 'src/utils/productRoute'

type ProductPublic = components['schemas']['ProductPublic']
type Spec = { name: string; value: string; unit: string }

const route = useRoute()
const router = useRouter()

const placeholderImg = '/icons/placeholder-product.svg'
const product = ref<ProductPublic | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
const selectedImage = ref<string | null>(null)

const SHIPPING_MODE_STORAGE_KEY = 'shipping_mode_preference'
const shippingModes = ref<ShippingModePricePublic[]>([])
const selectedModeKey = ref<string | null>(null)
const shippingLoading = ref(false)

const isOutOfStock = computed(() => {
  if (!product.value) return true
  return parseFloat(product.value.supplier_quantity) <= 0
})

const stockQuantity = computed(() => {
  if (!product.value) return 0
  return Math.max(0, Math.round(parseFloat(product.value.supplier_quantity)))
})

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

const displayPrice = computed(() => {
  if (selectedMode.value) {
    const price = parseFloat(selectedMode.value.sale_price)
    return price > 0 ? formatXpf(price) : '—'
  }
  if (!product.value) return '—'
  const price = parseFloat(product.value.base_price)
  if (price === 0) return '—'
  return formatXpf(price)
})

const safeDescription = computed(() => {
  const raw = product.value?.long_description ?? product.value?.description ?? ''
  return raw ? DOMPurify.sanitize(raw) : ''
})

const plainDescription = computed(() =>
  safeDescription.value.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(),
)

const features = computed(() =>
  (product.value?.features ?? []).map((f) => String(f).trim()).filter(Boolean),
)

function toStr(v: unknown): string {
  return typeof v === 'string' || typeof v === 'number' ? String(v).trim() : ''
}

const specGroups = computed<{ group: string; specs: Spec[] }[]>(() => {
  const groups = new Map<string, Spec[]>()
  for (const raw of product.value?.technical_specifications ?? []) {
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
  const main = product.value?.image_url ?? product.value?.supplier_image_url
  if (main) urls.push(main)
  for (const raw of product.value?.icecat_images ?? []) {
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

const mainImage = computed(() => selectedImage.value ?? gallery.value[0] ?? null)

const publicSiteUrl =
  import.meta.env.VITE_PUBLIC_SITE_URL?.replace(/\/$/, '') ?? ''

const canonicalHref = computed(() => {
  if (!publicSiteUrl || !product.value) return ''
  return `${publicSiteUrl}${route.path}`
})

useMeta(() => {
  const title = product.value ? `${product.value.name} | Natimai` : 'Produit | Natimai'
  const description =
    plainDescription.value || 'Consultez les détails et caractéristiques du produit.'
  const meta: Record<string, { name?: string; property?: string; content: string }> = {
    description: {
      name: 'description',
      content: description,
    },
    ogTitle: {
      property: 'og:title',
      content: title,
    },
    ogDescription: {
      property: 'og:description',
      content: description,
    },
    ogType: {
      property: 'og:type',
      content: 'product',
    },
  }

  const link: Record<string, { rel: string; href: string }> = {}
  if (canonicalHref.value) {
    meta['ogUrl'] = {
      property: 'og:url',
      content: canonicalHref.value,
    }
    link['canonical'] = {
      rel: 'canonical',
      href: canonicalHref.value,
    }
  }

  return {
    title,
    meta,
    link,
  }
})

async function loadProduct() {
  loading.value = true
  error.value = null
  selectedImage.value = null
  shippingModes.value = []
  selectedModeKey.value = null

  const routeId = typeof route.params.id === 'string' ? route.params.id : null
  if (!routeId) {
    product.value = null
    error.value = 'Produit introuvable'
    loading.value = false
    return
  }

  try {
    const data = await getProductById(routeId)
    product.value = data

    // Shipping modes are interactive/client-only — skip on SSR
    if (typeof window !== 'undefined') {
      void loadShippingModes(routeId)
    }

    const expectedSlug = slugifyProductName(data.name)
    const currentSlug = typeof route.params.slug === 'string' ? route.params.slug : ''
    if (expectedSlug && expectedSlug !== currentSlug) {
      void router.replace({
        ...getProductRouteByIdAndName(data.id, data.name),
        query: route.query,
      })
    }
  } catch (e) {
    product.value = null
    const requestError = e as {
      response?: { status?: number; data?: { detail?: string; message?: string } }
      message?: string
    }
    if (requestError.response?.status === 404) {
      error.value = 'Produit introuvable'
    } else {
      error.value =
        requestError.response?.data?.message ??
        requestError.response?.data?.detail ??
        requestError.message ??
        'Erreur inconnue'
    }
  } finally {
    loading.value = false
  }
}

function onAddToCart() {
  if (!product.value) return
  // TODO: brancher sur le store panier
  console.log('add to cart', product.value.id)
}

async function loadShippingModes(productId: string): Promise<void> {
  shippingLoading.value = true
  try {
    const data = await getProductShippingModes(productId)
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

onServerPrefetch(loadProduct)

onMounted(async () => {
  await loadProduct()
})

watch(
  () => route.params.id,
  (current, previous) => {
    if (current && current !== previous) {
      void loadProduct()
    }
  },
)
</script>

<style scoped lang="scss">
.product-page {
  max-width: 1200px;
  margin: 0 auto;
}

.product-page-card {
  overflow: hidden;
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
