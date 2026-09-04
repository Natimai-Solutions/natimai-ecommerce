<template>
  <q-page class="catalogue-page">
    <div class="row q-col-gutter-md q-pa-md">
      <!-- Sidebar filtres -->
      <div class="col-12 col-md-3 col-lg-2">
        <q-card flat bordered class="q-pa-md">
          <div class="text-subtitle2 q-mb-sm">Filtres</div>

          <!-- Catégorie -->
          <div v-if="categoryOptions.length > 0" class="q-mb-md">
            <div class="text-caption text-grey-7 q-mb-xs">Catégorie</div>
            <q-select
              v-model="selectedCategory"
              :options="categoryOptions"
              option-value="value"
              option-label="label"
              emit-value
              map-options
              clearable
              dense
              outlined
              placeholder="Toutes"
              @update:model-value="onCategoryChange"
            />
          </div>

          <!-- Caractéristiques (specs) — dépend de la catégorie sélectionnée -->
          <div v-if="store.specFacets.length > 0" class="q-mb-md">
            <div class="text-caption text-weight-medium text-grey-8 q-mb-xs">Caractéristiques</div>
            <div v-for="facet in store.specFacets" :key="facet.key" class="q-mb-sm">
              <div class="text-caption text-grey-7">{{ facet.label_fr }}</div>

              <!-- numérique : minimum (≥) -->
              <q-select
                v-if="facet.type === 'numeric'"
                :model-value="numericMin[facet.key] ?? null"
                :options="numericOptions(facet)"
                option-value="value"
                option-label="label"
                emit-value
                map-options
                clearable
                dense
                outlined
                :placeholder="`≥ minimum${facet.unit ? ' (' + facet.unit + ')' : ''}`"
                @update:model-value="(v: number | null) => onNumericChange(facet.key, v)"
              />

              <!-- enum : cases à cocher -->
              <template v-else>
                <q-checkbox
                  v-for="val in facet.values ?? []"
                  :key="String(val.value_text)"
                  :model-value="(enumSelections[facet.key] ?? []).includes(val.value_text ?? '')"
                  :label="`${val.value_text} (${val.count})`"
                  dense
                  size="sm"
                  class="block"
                  @update:model-value="
                    (c: boolean) => onEnumToggle(facet.key, val.value_text ?? '', c)
                  "
                />
              </template>
            </div>
          </div>

          <!-- Fabricant -->
          <div v-if="manufacturerOptions.length > 0" class="q-mb-md">
            <div class="text-caption text-grey-7 q-mb-xs">Fabricant</div>
            <q-select
              v-model="selectedManufacturer"
              :options="manufacturerOptions"
              option-value="value"
              option-label="label"
              emit-value
              map-options
              clearable
              dense
              outlined
              placeholder="Tous"
              @update:model-value="onManufacturerChange"
            />
          </div>

          <!-- Stock
          <div class="q-mb-md">
            <q-toggle
              v-model="inStockOnly"
              label="En stock uniquement"
              dense
              @update:model-value="onStockToggle"
            />
          </div>
          -->

          <!-- Prix -->
          <div class="q-mb-md">
            <div class="text-caption text-grey-7 q-mb-xs">Prix (XPF)</div>
            <div class="row q-col-gutter-xs">
              <div class="col-6">
                <q-input
                  v-model.number="priceMin"
                  type="number"
                  dense
                  outlined
                  placeholder="Min"
                  @keyup.enter="onPriceChange"
                />
              </div>
              <div class="col-6">
                <q-input
                  v-model.number="priceMax"
                  type="number"
                  dense
                  outlined
                  placeholder="Max"
                  @keyup.enter="onPriceChange"
                />
              </div>
            </div>
            <q-btn
              flat
              dense
              size="sm"
              color="primary"
              label="Appliquer"
              class="q-mt-xs"
              @click="onPriceChange"
            />
          </div>

          <q-btn
            flat
            dense
            color="grey-7"
            label="Réinitialiser"
            icon="filter_alt_off"
            class="full-width"
            @click="resetFilters"
          />
        </q-card>
      </div>

      <!-- Contenu principal -->
      <div class="col-12 col-md-9 col-lg-10">
        <!-- Barre de recherche -->
        <div class="row items-center q-mb-md q-col-gutter-sm">
          <div class="col">
            <q-input
              v-model="searchQuery"
              outlined
              dense
              placeholder="Rechercher un produit, une référence…"
              clearable
              @keyup.enter="onSearch"
              @clear="onSearch"
            >
              <template #prepend>
                <q-icon name="search" />
              </template>
              <template #append>
                <q-btn flat dense round icon="search" color="primary" @click="onSearch" />
              </template>
            </q-input>
          </div>
          <div class="col-auto">
            <span class="text-caption text-grey-6">
              {{ store.count }} résultat{{ store.count !== 1 ? 's' : '' }}
            </span>
          </div>
        </div>

        <q-banner
          v-if="cartFeedback"
          :class="cartFeedback.ok ? 'bg-green-1 text-green-9' : 'bg-orange-1 text-orange-10'"
          class="q-mb-md"
          rounded
        >
          <template #avatar>
            <q-icon :name="cartFeedback.ok ? 'check_circle' : 'warning_amber'" />
          </template>
          {{ cartFeedback.message }}
        </q-banner>

        <!-- État chargement -->
        <div v-if="store.loading" class="row q-col-gutter-md">
          <div v-for="n in 12" :key="n" class="col-12 col-sm-6 col-md-4 col-lg-3">
            <q-card flat bordered>
              <q-skeleton height="180px" square />
              <q-card-section>
                <q-skeleton type="text" />
                <q-skeleton type="text" width="60%" />
              </q-card-section>
            </q-card>
          </div>
        </div>

        <!-- Erreur -->
        <q-banner v-else-if="store.error" class="bg-red-1 text-red-8 q-mb-md" rounded>
          <template #avatar><q-icon name="error_outline" /></template>
          {{ store.error }}
          <template #action>
            <q-btn flat label="Réessayer" @click="store.search()" />
          </template>
        </q-banner>

        <!-- Aucun résultat -->
        <div v-else-if="store.items.length === 0" class="column items-center q-py-xl text-grey-6">
          <q-icon name="search_off" size="4rem" class="q-mb-md" />
          <div class="text-h6">Aucun produit trouvé</div>
          <div class="text-body2">Modifiez vos critères de recherche</div>
        </div>

        <!-- Grille produits -->
        <div v-else class="row q-col-gutter-md">
          <div
            v-for="product in store.items"
            :key="product.id"
            class="col-12 col-sm-6 col-md-4 col-lg-3"
          >
            <ProductCard :product="product" @add-to-cart="onAddToCart" />
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="store.totalPages > 1" class="row justify-center q-mt-lg">
          <q-pagination
            v-model="currentPage"
            :max="store.totalPages"
            :max-pages="7"
            boundary-numbers
            direction-links
            color="primary"
            @update:model-value="store.setPage($event)"
          />
        </div>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, onServerPrefetch, ref } from 'vue';
import { useMeta } from 'quasar';
import { useRoute, useRouter } from 'vue-router';
import { useProductsStore } from 'src/stores/products';
import { useCartStore } from 'src/stores/cart';
import ProductCard from 'src/components/ProductCard.vue';
import type { components } from '@app/api-types';

type ProductPublic = components['schemas']['ProductPublic'];
type SpecFacet = components['schemas']['SpecFacet'];

const store = useProductsStore();
const cartStore = useCartStore();
const route = useRoute();
const router = useRouter();

useMeta(() => ({
  title: 'Catalogue | Natimai',
  meta: {
    description: {
      name: 'description',
      content: 'Explorez notre catalogue de produits avec filtres par fabricant et prix.',
    },
  },
}));

const searchQuery = ref<string>('');
const selectedManufacturer = ref<string | null>(null);
const selectedCategory = ref<string | null>(null);
// Spec filters: enum key → selected value_text[]; numeric key → minimum value.
const enumSelections = ref<Record<string, string[]>>({});
const numericMin = ref<Record<string, number | null>>({});
const priceMin = ref<number | null>(null);
const priceMax = ref<number | null>(null);
const cartFeedback = ref<{ ok: boolean; message: string } | null>(null);

const categoryOptions = computed(() =>
  store.categories.map((c) => ({ label: c.title ?? c.name, value: c.id })),
);

function numericOptions(facet: SpecFacet): { label: string; value: number }[] {
  const seen = new Set<number>();
  const opts: { label: string; value: number }[] = [];
  for (const v of facet.values ?? []) {
    if (v.value_numeric == null) continue;
    const num = Number.parseFloat(v.value_numeric);
    if (!Number.isFinite(num) || seen.has(num)) continue;
    seen.add(num);
    opts.push({
      label: `≥ ${num}${facet.unit ? ' ' + facet.unit : ''} (${v.count})`,
      value: num,
    });
  }
  return opts.sort((a, b) => a.value - b.value);
}

/** Build the `specs` search payload: enum → key:[values], numeric → key_min:value. */
function buildSpecs(): Record<string, unknown> {
  const specs: Record<string, unknown> = {};
  for (const [key, vals] of Object.entries(enumSelections.value)) {
    if (vals.length > 0) specs[key] = vals;
  }
  for (const [key, min] of Object.entries(numericMin.value)) {
    if (min != null) specs[`${key}_min`] = min;
  }
  return specs;
}

const currentPage = computed({
  get: () => store.currentPage,
  set: (v) => {
    store.currentPage = v;
  },
});

const manufacturerOptions = computed(() => {
  const mfrs = store.facets?.manufacturers ?? {};
  return Object.entries(mfrs)
    .sort((a, b) => b[1] - a[1])
    .map(([name, cnt]) => ({ label: `${name} (${cnt})`, value: name }));
});

async function onSearch() {
  await store.applyFilters({ q: searchQuery.value || null });
  syncQueryParams();
}

async function onManufacturerChange(val: string | null) {
  await store.applyFilters({ manufacturer: val });
  syncQueryParams();
}

async function onCategoryChange(catId: string | null) {
  selectedCategory.value = catId;
  // Spec facets are per-category — reset any previous spec selection.
  enumSelections.value = {};
  numericMin.value = {};
  await store.loadSpecFacets(catId);
  await store.applyFilters({ category_id: catId, specs: {} });
  syncQueryParams();
}

async function onSpecChange() {
  await store.applyFilters({ specs: buildSpecs() });
}

function onNumericChange(key: string, value: number | null) {
  numericMin.value = { ...numericMin.value, [key]: value };
  void onSpecChange();
}

function onEnumToggle(key: string, value: string, checked: boolean) {
  const current = enumSelections.value[key] ?? [];
  const next = checked ? [...current, value] : current.filter((v) => v !== value);
  enumSelections.value = { ...enumSelections.value, [key]: next };
  void onSpecChange();
}

async function onPriceChange() {
  await store.applyFilters({
    price_min: priceMin.value ?? null,
    price_max: priceMax.value ?? null,
  });
}

async function resetFilters() {
  searchQuery.value = '';
  selectedManufacturer.value = null;
  selectedCategory.value = null;
  enumSelections.value = {};
  numericMin.value = {};
  priceMin.value = null;
  priceMax.value = null;
  await store.loadSpecFacets(null);
  await store.applyFilters({
    q: null,
    manufacturer: null,
    category_id: null,
    in_stock: null,
    price_min: null,
    price_max: null,
    specs: {},
  });
  void router.replace({ query: {} });
}

function syncQueryParams() {
  const query: Record<string, string> = {};
  if (searchQuery.value) query['q'] = searchQuery.value;
  if (selectedManufacturer.value) query['mfr'] = selectedManufacturer.value;
  if (selectedCategory.value) query['cat'] = selectedCategory.value;
  void router.replace({ query });
}

async function onAddToCart(product: ProductPublic) {
  cartFeedback.value = null;
  const ok = await cartStore.addItem(product.id, 1, product);

  if (ok) {
    cartFeedback.value = {
      ok: true,
      message: `${product.name} ajoute au panier.`,
    };
    return;
  }

  cartFeedback.value = {
    ok: false,
    message: cartStore.error ?? "Impossible d'ajouter cet article au panier.",
  };
}

function initFromQuery() {
  const q = route.query['q'];
  const mfr = route.query['mfr'];
  const cat = route.query['cat'];
  if (typeof q === 'string') searchQuery.value = q;
  if (typeof mfr === 'string') selectedManufacturer.value = mfr;
  if (typeof cat === 'string') selectedCategory.value = cat;
}

async function loadCatalogueData() {
  initFromQuery();
  await store.loadCategories();
  if (selectedCategory.value) await store.loadSpecFacets(selectedCategory.value);
  await store.applyFilters({
    q: searchQuery.value || null,
    manufacturer: selectedManufacturer.value,
    category_id: selectedCategory.value,
    specs: buildSpecs(),
  });
}

onServerPrefetch(loadCatalogueData);

onMounted(async () => {
  await loadCatalogueData();
});
</script>

<style scoped lang="scss">
.catalogue-page {
  min-height: 100vh;
}
</style>
