<template>
  <q-dialog
    :model-value="modelValue"
    :persistent="guard.persistent.value"
    @update:model-value="guard.onToggle"
  >
    <q-card class="app-dialog app-dialog--xl product-form">
      <q-form @submit="onSubmit">
        <q-card-section class="app-dialog__head">
          <div class="product-form__head">
            <h2 class="app-dialog__title">
              {{
                isEdit
                  ? $t('product_form.edit_title')
                  : isDuplicate
                    ? $t('product_form.duplicate_title')
                    : $t('product_form.new_title')
              }}
            </h2>
            <StatusTag
              v-if="isEdit && product?.is_supplier_managed"
              :label="$t('product_form.supplier')"
              icon="ph:truck"
            />
            <StatusTag v-else-if="isEdit" :label="$t('product_form.manual')" icon="ph:hand" />
          </div>
        </q-card-section>

        <q-card-section class="product-form__body">
          <div
            v-if="error || isDuplicate || (isEdit && product?.is_supplier_managed)"
            class="admin-notices"
          >
            <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
            <AppNotice v-if="isDuplicate" tone="info" dense data-testid="product-duplicate-notice">
              {{ $t('product_form.duplicate_notice', { name: duplicateOf?.name ?? '' }) }}
            </AppNotice>
            <AppNotice v-if="isEdit && product?.is_supplier_managed" tone="info" dense>
              {{ $t('product_form.synced_notice') }}
            </AppNotice>
          </div>

          <div v-if="isEdit && lockedFields.length" class="product-form__locks">
            <p class="admin-hint q-mb-xs">
              {{ $t('product_form.locked') }}
            </p>
            <q-chip
              v-for="field in lockedFields"
              :key="field"
              dense
              removable
              icon="ph:lock"
              :label="fieldLabel(field)"
              :disable="releasing === field"
              @remove="onRelease(field)"
            />
          </div>

          <!-- 1. Fiche : textes affichés sur la vitrine, par langue -->
          <section class="product-form__section" data-testid="product-section-content">
            <header class="product-form__section-head">
              <q-icon name="ph:text-aa" class="product-form__section-icon" />
              <h3 class="product-form__section-title">{{ $t('product_form.sec_content') }}</h3>
              <p class="product-form__section-hint">{{ $t('product_form.sec_content_hint') }}</p>
            </header>
            <div class="product-form__fields">
              <ContentLanguageTabs
                v-model="content.lang.value"
                :source="content.source.value"
                :locales="content.locales.value"
                :status-of="content.statusOf"
                :reviewed="content.reviewed.value"
                @review="content.markReviewed"
              />
              <q-input
                v-model="texts.name"
                :label="$t('product_form.name')"
                outlined
                dense
                hide-bottom-space
                :rules="content.isSource.value ? req : []"
                data-testid="product-name"
              />
              <q-input
                v-model="texts.description"
                :label="$t('product_form.short')"
                outlined
                dense
                hide-bottom-space
              />
              <RichTextEditor
                v-model="texts.long_description"
                :label="$t('product_form.long')"
                media-kind="product"
              />
            </div>
          </section>

          <!-- 2. Identification : toujours saisissable, article manuel compris.
               La référence (SKU) est dans « Approvisionnement » quand les
               fournisseurs sont activés. -->
          <section class="product-form__section" data-testid="product-section-identification">
            <header class="product-form__section-head">
              <q-icon name="ph:barcode" class="product-form__section-icon" />
              <h3 class="product-form__section-title">
                {{ $t('product_form.identification') }}
              </h3>
              <p class="product-form__section-hint">
                {{ $t('product_form.identification_hint') }}
              </p>
            </header>
            <div class="product-form__row product-form__row--ids">
              <q-input
                v-if="!suppliersOn"
                v-model="form.supplier_sku"
                :label="$t('product_form.sku')"
                outlined
                dense
                hide-bottom-space
              />
              <!-- Marques déjà connues : une seule orthographe par marque.
                   Une marque nouvelle se tape quand même. -->
              <q-select
                :model-value="form.manufacturer || null"
                :options="manufacturerOptions"
                :label="$t('product_form.manufacturer')"
                use-input
                fill-input
                hide-selected
                input-debounce="0"
                new-value-mode="add-unique"
                outlined
                dense
                hide-bottom-space
                clearable
                data-testid="product-manufacturer"
                @filter="filterManufacturers"
                @input-value="(value: string) => (form.manufacturer = value)"
                @update:model-value="(value: string | null) => (form.manufacturer = value ?? '')"
              />
              <q-input
                v-model="form.vendor_part_number"
                :label="$t('product_form.mpn')"
                :hint="$t('product_form.mpn_hint')"
                outlined
                dense
                hide-bottom-space
              />
              <q-input
                v-model="form.ean"
                :label="$t('product_form.ean')"
                outlined
                dense
                hide-bottom-space
              />
            </div>
          </section>

          <div class="product-form__grid">
            <!-- 3. Approvisionnement et stock -->
            <section class="product-form__section" data-testid="product-section-supply">
              <header class="product-form__section-head">
                <q-icon name="ph:truck" class="product-form__section-icon" />
                <h3 class="product-form__section-title">
                  {{ suppliersOn ? $t('product_form.supply') : $t('product_form.sec_stock') }}
                </h3>
                <p class="product-form__section-hint">
                  {{
                    suppliersOn ? $t('product_form.supply_hint') : $t('product_form.sec_stock_hint')
                  }}
                </p>
              </header>
              <div class="product-form__fields">
                <div v-if="suppliersOn" class="product-form__row">
                  <q-select
                    v-model="form.supplier_name"
                    :options="supplierOptions"
                    :label="$t('product_form.supplier')"
                    :hint="$t('product_form.supplier_hint')"
                    outlined
                    dense
                    hide-bottom-space
                    emit-value
                    map-options
                    clearable
                    :disable="isEdit && linkedManaged"
                    @update:model-value="onSupplierChange"
                  />
                  <q-input
                    v-model="form.supplier_sku"
                    :label="$t('product_form.supplier_ref')"
                    outlined
                    dense
                    hide-bottom-space
                  />
                </div>
                <div
                  v-if="suppliersOn && isEdit && product && !product.has_variants"
                  class="product-form__inline"
                >
                  <q-btn
                    v-if="!linkedManaged"
                    outline
                    dense
                    no-caps
                    icon="ph:link"
                    :label="$t('product_form.attach')"
                    :disable="!form.supplier_name || !form.supplier_sku.trim()"
                    :loading="linking === 'attach'"
                    data-testid="product-attach-supplier"
                    @click="onAttach"
                  >
                    <q-tooltip>
                      {{ $t('product_form.attach_tip') }}
                    </q-tooltip>
                  </q-btn>
                  <q-btn
                    v-if="linkedManaged || (managedAfterLink === null && product.supplier_name)"
                    flat
                    dense
                    no-caps
                    icon="ph:link-break"
                    :label="$t('product_form.detach')"
                    :loading="linking === 'detach'"
                    data-testid="product-detach-supplier"
                    @click="onDetach"
                  >
                    <q-tooltip>
                      {{ $t('product_form.detach_tip') }}
                    </q-tooltip>
                  </q-btn>
                </div>
                <AppNotice v-if="linkNotice" tone="success" dense>
                  {{ linkNotice }}
                </AppNotice>
                <q-input
                  v-if="suppliersOn && form.supplier_name && !product?.is_supplier_managed"
                  v-model="form.supplier_quantity"
                  :label="$t('product_form.supplier_stock')"
                  :hint="$t('product_form.supplier_stock_hint')"
                  type="number"
                  step="1"
                  min="0"
                  outlined
                  dense
                  hide-bottom-space
                />
                <q-input
                  v-model="form.local_quantity"
                  :label="$t('product_form.local_stock')"
                  :hint="localStockHint"
                  type="number"
                  step="1"
                  min="0"
                  outlined
                  dense
                  hide-bottom-space
                />
              </div>
            </section>

            <!-- 4. État et disponibilité -->
            <section class="product-form__section" data-testid="product-section-condition">
              <header class="product-form__section-head">
                <q-icon name="ph:arrows-counter-clockwise" class="product-form__section-icon" />
                <h3 class="product-form__section-title">
                  {{ $t('product_form.sec_condition') }}
                </h3>
                <p class="product-form__section-hint">{{ $t('product_form.condition_hint') }}</p>
              </header>
              <div class="product-form__fields">
                <div class="product-form__choice">
                  <span class="product-form__choice-label">{{ $t('product_form.condition') }}</span>
                  <q-option-group
                    v-model="form.condition"
                    :options="conditionOptions"
                    inline
                    dense
                  />
                </div>
                <div v-if="form.condition === 'refurbished'" class="product-form__row">
                  <q-input
                    v-model="form.condition_grade"
                    :label="$t('product_form.grade')"
                    hint="A, B, C…"
                    outlined
                    dense
                    hide-bottom-space
                    maxlength="5"
                  />
                  <q-input
                    v-model="form.battery_health_pct"
                    type="number"
                    min="0"
                    max="100"
                    :label="$t('product_form.battery')"
                    outlined
                    dense
                    hide-bottom-space
                  />
                  <q-input
                    v-model="form.os_licence"
                    :label="$t('product_form.os')"
                    outlined
                    dense
                    hide-bottom-space
                  />
                  <q-input
                    v-model="form.warranty_months"
                    type="number"
                    min="0"
                    :label="$t('product_form.warranty')"
                    outlined
                    dense
                    hide-bottom-space
                  />
                </div>

                <div class="product-form__choice">
                  <span class="product-form__choice-label">
                    {{ $t('product_form.availability') }}
                  </span>
                  <q-option-group
                    v-model="form.availability_mode"
                    :options="availabilityModeOptions"
                    inline
                    dense
                  />
                  <p class="product-form__help">{{ availabilityModeHint }}</p>
                </div>
              </div>
            </section>

            <!-- 5. Prix et taxes -->
            <section class="product-form__section" data-testid="product-section-pricing">
              <header class="product-form__section-head">
                <q-icon name="ph:tag" class="product-form__section-icon" />
                <h3 class="product-form__section-title">{{ $t('product_form.pricing') }}</h3>
                <p class="product-form__section-hint">{{ $t('product_form.pricing_hint') }}</p>
              </header>
              <div class="product-form__fields">
                <div class="product-form__choice">
                  <q-option-group
                    v-model="form.pricing_mode"
                    :options="pricingModeOptions"
                    inline
                    dense
                  />
                  <p class="product-form__help">{{ pricingModeHint }}</p>
                </div>

                <q-input
                  v-if="form.pricing_mode === 'fixed'"
                  v-model="form.base_price"
                  :label="$t('product_form.price')"
                  :hint="$t('product_form.price_hint')"
                  type="number"
                  step="0.01"
                  min="0"
                  outlined
                  dense
                  hide-bottom-space
                  data-testid="product-base-price"
                />
                <div class="product-form__row">
                  <q-input
                    v-model="form.cost_amount"
                    :label="
                      form.pricing_mode === 'fixed'
                        ? $t('product_form.cost_ht')
                        : $t('product_form.cost')
                    "
                    :hint="form.pricing_mode === 'fixed' ? $t('product_form.cost_hint') : ''"
                    type="number"
                    step="0.01"
                    min="0"
                    outlined
                    dense
                    hide-bottom-space
                    data-testid="product-cost"
                  />
                  <q-select
                    v-model="form.cost_currency"
                    :options="currencyOptions"
                    :label="$t('product_form.cost_currency')"
                    outlined
                    dense
                    hide-bottom-space
                    emit-value
                    map-options
                  />
                </div>
                <div v-if="form.pricing_mode !== 'fixed'" class="product-form__row">
                  <q-input
                    v-if="form.pricing_mode === 'import'"
                    v-model="form.customs_rate_pct"
                    :label="$t('product_form.customs')"
                    :hint="$t('product_form.customs_hint')"
                    type="number"
                    step="0.01"
                    outlined
                    dense
                    hide-bottom-space
                  />
                  <q-input
                    v-model="form.margin_rate_pct"
                    :label="$t('product_form.margin')"
                    :hint="marginHint"
                    type="number"
                    step="0.01"
                    outlined
                    dense
                    hide-bottom-space
                  />
                </div>
                <div class="product-form__row">
                  <q-select
                    v-model="form.category_id"
                    :options="categoryOptions"
                    :label="$t('product_form.category')"
                    outlined
                    dense
                    hide-bottom-space
                    emit-value
                    map-options
                    clearable
                  />
                  <q-select
                    v-model="form.tax_rate_id"
                    :options="taxRateOptions"
                    :label="$t('product_form.vat')"
                    :hint="$t('product_form.vat_hint')"
                    outlined
                    dense
                    hide-bottom-space
                    emit-value
                    map-options
                    clearable
                  />
                </div>
                <div class="product-form__inline">
                  <q-toggle
                    :model-value="form.gift_card_amount !== ''"
                    :label="$t('product_form.gift_card')"
                    dense
                    data-testid="product-gift-card"
                    @update:model-value="
                      (on: boolean) => (form.gift_card_amount = on ? form.base_price || '1' : '')
                    "
                  />
                  <q-input
                    v-if="form.gift_card_amount !== ''"
                    v-model="form.gift_card_amount"
                    :label="$t('product_form.gift_card_amount', { currency: shopConfig.currency })"
                    :hint="$t('product_form.gift_card_hint')"
                    type="number"
                    step="1"
                    min="1"
                    outlined
                    dense
                    hide-bottom-space
                    class="product-form__inline-field"
                    data-testid="product-gift-card-amount"
                  />
                </div>
                <MarginPreviewPanel
                  v-if="modelValue"
                  v-model:group-prices="groupPrices"
                  :input="marginInput"
                />
              </div>
            </section>

            <!-- 6. Logistique, puis mise en avant -->
            <div class="product-form__stack">
              <section class="product-form__section" data-testid="product-section-logistics">
                <header class="product-form__section-head">
                  <q-icon name="ph:package" class="product-form__section-icon" />
                  <h3 class="product-form__section-title">{{ $t('product_form.logistics') }}</h3>
                  <p class="product-form__section-hint">
                    {{ $t('product_form.logistics_hint') }}
                  </p>
                </header>
                <div class="product-form__fields">
                  <q-select
                    v-model="form.supplier_place_id"
                    :options="placeOptions"
                    :label="$t('product_form.origin')"
                    outlined
                    dense
                    hide-bottom-space
                    emit-value
                    map-options
                    clearable
                  />
                  <div class="product-form__row product-form__row--dims">
                    <q-input
                      v-model.number="form.weight"
                      :label="$t('product_form.weight')"
                      type="number"
                      step="0.001"
                      outlined
                      dense
                      hide-bottom-space
                    />
                    <q-input
                      v-model.number="form.dimensions_length"
                      :label="$t('product_form.length')"
                      type="number"
                      outlined
                      dense
                      hide-bottom-space
                    />
                    <q-input
                      v-model.number="form.dimensions_width"
                      :label="$t('product_form.width')"
                      type="number"
                      outlined
                      dense
                      hide-bottom-space
                    />
                    <q-input
                      v-model.number="form.dimensions_height"
                      :label="$t('product_form.height')"
                      type="number"
                      outlined
                      dense
                      hide-bottom-space
                    />
                  </div>
                </div>
              </section>

              <section class="product-form__section" data-testid="product-section-display">
                <header class="product-form__section-head">
                  <q-icon name="ph:star" class="product-form__section-icon" />
                  <h3 class="product-form__section-title">{{ $t('product_form.display') }}</h3>
                  <p class="product-form__section-hint">{{ $t('product_form.display_hint') }}</p>
                </header>
                <div class="product-form__inline">
                  <q-toggle v-model="form.is_featured" :label="$t('product_form.featured')" />
                  <q-input
                    v-if="form.is_featured"
                    v-model.number="form.featured_position"
                    :label="$t('product_form.featured_pos')"
                    type="number"
                    outlined
                    dense
                    hide-bottom-space
                    class="product-form__inline-field"
                  />
                </div>
              </section>
            </div>
          </div>

          <!-- 7. Images : la principale (cartes, panier, commandes) et la galerie -->
          <section class="product-form__section" data-testid="product-section-images">
            <header class="product-form__section-head">
              <q-icon name="ph:images" class="product-form__section-icon" />
              <h3 class="product-form__section-title">{{ $t('product_form.sec_images') }}</h3>
              <p class="product-form__section-hint">{{ $t('product_form.image_hint') }}</p>
            </header>
            <div class="product-form__images">
              <div class="product-form__image-main">
                <div class="product-form__frame product-form__frame--main">
                  <img v-if="form.image_url" :src="form.image_url" alt="" />
                  <q-icon v-else name="ph:image" size="40px" class="product-form__frame-glyph" />
                  <span class="product-form__frame-tag">{{ $t('product_form.image_main') }}</span>
                </div>
                <q-input
                  v-model="form.image_url"
                  :label="$t('product_form.image')"
                  outlined
                  dense
                  hide-bottom-space
                  clearable
                  data-testid="product-image-url"
                >
                  <template #append>
                    <q-btn
                      flat
                      dense
                      no-caps
                      icon="ph:images"
                      :label="$t('product_form.media')"
                      data-testid="product-image-pick"
                      @click="openPicker('main')"
                    />
                  </template>
                </q-input>
              </div>

              <div class="product-form__gallery" data-testid="product-gallery">
                <p class="product-form__gallery-title">
                  {{ $t('product_form.gallery') }}
                  <span class="text-subtle">{{
                    $t('product_form.gallery_count', { n: form.gallery_urls.length })
                  }}</span>
                </p>
                <div class="product-form__thumbs">
                  <div
                    v-for="(url, index) in form.gallery_urls"
                    :key="url"
                    class="product-form__thumb"
                    :data-testid="`product-gallery-item-${index}`"
                  >
                    <div class="product-form__frame">
                      <img :src="url" alt="" />
                    </div>
                    <div class="product-form__thumb-actions">
                      <q-btn
                        flat
                        round
                        dense
                        size="sm"
                        icon="ph:arrow-left"
                        :disable="index === 0"
                        :aria-label="$t('product_form.gallery_left')"
                        @click="moveGallery(index, -1)"
                      />
                      <q-btn
                        flat
                        round
                        dense
                        size="sm"
                        icon="ph:arrow-right"
                        :disable="index === form.gallery_urls.length - 1"
                        :aria-label="$t('product_form.gallery_right')"
                        @click="moveGallery(index, 1)"
                      />
                      <q-btn
                        flat
                        round
                        dense
                        size="sm"
                        icon="ph:star"
                        :aria-label="$t('product_form.gallery_make_main')"
                        @click="makeMain(index)"
                      >
                        <q-tooltip>{{ $t('product_form.gallery_make_main') }}</q-tooltip>
                      </q-btn>
                      <q-btn
                        flat
                        round
                        dense
                        size="sm"
                        icon="ph:x"
                        color="negative"
                        :aria-label="$t('product_form.gallery_remove')"
                        @click="form.gallery_urls.splice(index, 1)"
                      />
                    </div>
                  </div>
                  <button
                    type="button"
                    class="product-form__thumb product-form__thumb--add"
                    :disable="form.gallery_urls.length >= GALLERY_MAX"
                    data-testid="product-gallery-add"
                    @click="openPicker('gallery')"
                  >
                    <q-icon name="ph:plus" size="22px" />
                    <span>{{ $t('product_form.gallery_add') }}</span>
                  </button>
                </div>
                <q-input
                  v-model="galleryUrlDraft"
                  :label="$t('product_form.gallery_url')"
                  :hint="$t('product_form.gallery_hint', { max: GALLERY_MAX })"
                  outlined
                  dense
                  hide-bottom-space
                  class="product-form__gallery-url"
                  data-testid="product-gallery-url"
                  @keydown.enter.prevent="addGalleryUrl"
                >
                  <template #append>
                    <q-btn
                      flat
                      dense
                      round
                      icon="ph:plus"
                      :disable="!galleryUrlDraft.trim()"
                      :aria-label="$t('product_form.gallery_add')"
                      @click="addGalleryUrl"
                    />
                  </template>
                </q-input>
              </div>
            </div>
          </section>

          <!-- 8. Caractéristiques (filtres de la vitrine) -->
          <section v-if="specsOn" class="product-form__section" data-testid="product-specs">
            <header class="product-form__section-head">
              <q-icon name="ph:sliders-horizontal" class="product-form__section-icon" />
              <h3 class="product-form__section-title">{{ $t('product_form.specs') }}</h3>
              <p class="product-form__section-hint">{{ $t('product_form.specs_hint') }}</p>
            </header>
            <p v-if="specRows.length === 0 && !form.category_id" class="text-subtle q-mb-none">
              {{ $t('product_form.specs_no_category') }}
            </p>
            <p v-else-if="specRows.length === 0" class="text-subtle q-mb-none">
              {{ $t('product_form.specs_none') }}
              <a
                :href="specDefinitionsHref"
                target="_blank"
                rel="noopener"
                class="product-form__spec-link"
                >{{ $t('product_form.specs_define') }}</a
              >
            </p>
            <div v-else class="product-form__row product-form__row--specs">
              <div v-for="row in specRows" :key="row.key" class="product-form__spec">
                <q-input
                  v-if="row.type === 'numeric'"
                  v-model="specValues[row.key]"
                  :label="row.label"
                  :suffix="row.unit ?? undefined"
                  inputmode="decimal"
                  outlined
                  dense
                  hide-bottom-space
                  clearable
                  :data-testid="`product-spec-${row.key}`"
                />
                <q-select
                  v-else
                  :model-value="specValues[row.key] || null"
                  :options="specOptions(row)"
                  :label="row.label"
                  use-input
                  fill-input
                  hide-selected
                  input-debounce="0"
                  new-value-mode="add-unique"
                  outlined
                  dense
                  hide-bottom-space
                  clearable
                  :data-testid="`product-spec-${row.key}`"
                  @filter="
                    (needle: string, update: (fn: () => void) => void) =>
                      update(() => (specFilter[row.key] = needle))
                  "
                  @input-value="(value: string) => (specValues[row.key] = value)"
                  @update:model-value="
                    (value: string | null) => (specValues[row.key] = value ?? '')
                  "
                />
                <StatusTag
                  v-if="row.source === 'icecat' && specValues[row.key] === specOriginal[row.key]"
                  :label="$t('product_form.spec_icecat')"
                  tone="neutral"
                  class="product-form__spec-source"
                />
              </div>
            </div>
          </section>

          <!-- 9. Articles liés -->
          <section v-if="isEdit" class="product-form__section" data-testid="product-links">
            <header class="product-form__section-head">
              <q-icon name="ph:link-simple" class="product-form__section-icon" />
              <h3 class="product-form__section-title">{{ $t('product_form.links') }}</h3>
              <p class="product-form__section-hint">{{ $t('product_form.links_hint') }}</p>
            </header>
            <div class="product-form__fields">
              <div
                v-for="(link, index) in links"
                :key="link.linked_product_id"
                class="product-form__link"
              >
                <q-btn-toggle
                  v-model="link.kind"
                  :options="[
                    { value: 'accessory', label: $t('product_form.link_accessory') },
                    { value: 'alternative', label: $t('product_form.link_alternative') },
                  ]"
                  no-caps
                  dense
                  unelevated
                  toggle-color="primary"
                  class="product-form__link-kind"
                />
                <span class="product-form__link-name" :class="{ 'text-subtle': !link.is_active }">
                  {{ link.name }}
                  <span v-if="link.vendor_part_number" class="font-mono text-subtle">
                    {{ link.vendor_part_number }}
                  </span>
                </span>
                <q-btn
                  flat
                  round
                  dense
                  icon="ph:arrow-up"
                  :disable="index === 0"
                  :aria-label="$t('product_form.link_up')"
                  @click="moveLink(index, -1)"
                />
                <q-btn
                  flat
                  round
                  dense
                  icon="ph:arrow-down"
                  :disable="index === links.length - 1"
                  :aria-label="$t('product_form.link_down')"
                  @click="moveLink(index, 1)"
                />
                <q-btn
                  flat
                  round
                  dense
                  icon="ph:x"
                  color="negative"
                  :aria-label="$t('product_form.link_remove')"
                  @click="links.splice(index, 1)"
                />
              </div>
              <q-select
                :model-value="null"
                :options="linkCandidates"
                option-value="id"
                option-label="name"
                :label="$t('product_form.link_add')"
                :hint="$t('product_form.link_add_hint')"
                use-input
                input-debounce="300"
                outlined
                dense
                hide-bottom-space
                hide-selected
                data-testid="product-link-search"
                @filter="filterLinkCandidates"
                @update:model-value="addLink"
              >
                <template #no-option>
                  <q-item>
                    <q-item-section class="text-subtle">
                      {{ $t('product_form.link_no_match') }}
                    </q-item-section>
                  </q-item>
                </template>
              </q-select>
            </div>
          </section>

          <!-- 10. Variantes -->
          <section
            v-if="isEdit && product && !product.parent_product_id"
            class="product-form__section"
            data-testid="product-section-variants"
          >
            <ProductVariantsPanel
              :product-id="product.id"
              :parent-price="form.pricing_mode === 'fixed' ? form.base_price : null"
              @changed="emit('saved')"
            />
            <div class="product-form__inline q-mt-sm">
              <q-toggle
                v-model="form.variants_optional"
                :label="$t('product_form.variants_optional')"
                dense
                data-testid="product-variants-optional"
              />
            </div>
            <p class="admin-hint q-mb-none">{{ $t('product_form.variants_optional_hint') }}</p>
          </section>
          <p v-else-if="isEdit && product?.parent_product_id" class="admin-hint q-mt-md q-mb-none">
            {{ $t('product_form.variant_of') }}
            <span v-if="product.variant_options">
              ({{
                Object.entries(product.variant_options)
                  .map(([k, v]) => `${k} : ${v}`)
                  .join(', ')
              }})
            </span>
            {{ $t('product_form.variant_hint') }}
          </p>
        </q-card-section>

        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn
            flat
            no-caps
            :label="$t('common.cancel')"
            :disable="saving"
            data-testid="product-cancel"
            @click="guard.requestClose()"
          />
          <q-btn
            type="submit"
            color="primary"
            unelevated
            no-caps
            :label="isEdit ? $t('product_form.save') : $t('product_form.create')"
            :loading="saving"
          />
        </q-card-actions>
      </q-form>
    </q-card>
    <MediaPicker v-model="mediaPickerOpen" kind="product" @select="onMediaPicked" />
  </q-dialog>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { labels } from '@/i18n/global';
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useQuasar } from 'quasar';
import { useRouter } from 'vue-router';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import {
  categoryLabel,
  categoryPathOptions,
  listAdminCategories,
  listCategories,
  type Category,
} from '@/api/categories';
import { listTaxRates, type TaxRate } from '@/api/taxRates';
import { listPlaces, type Place } from '@/api/logistics';
import {
  attachProductToSupplier,
  detachProductFromSupplier,
  listSuppliers,
  type Supplier,
} from '@/api/suppliers';
import { extractApiError } from '@/api/errors';
import { adjustInventory } from '@/api/inventory';
import MarginPreviewPanel from '@/components/MarginPreviewPanel.vue';
import MediaPicker from '@/components/MediaPicker.vue';
import RichTextEditor from '@/components/RichTextEditor.vue';
import ContentLanguageTabs from '@/components/ContentLanguageTabs.vue';
import {
  cloneTranslations,
  useContentTranslations,
  type Translations,
} from '@/composables/useContentTranslations';
import { intlLocale } from '@app/utils';
import { getGroupPrices, setGroupPrices, type MarginPreviewRequest } from '@/api/margin';
import { getSpecForm, setProductSpecs, type SpecFormRow } from '@/api/productSpecs';
import { listManufacturers } from '@/api/manufacturers';
import {
  listProductLinks,
  searchProductsForLink,
  setProductLinks,
  type LinkCandidate,
  type ProductLink,
} from '@/api/productLinks';
import { useDialogGuard } from '@/composables/useUnsavedGuard';
import ProductVariantsPanel from '@/components/ProductVariantsPanel.vue';
import { useProductsStore, type ProductPublic } from '@/stores/products';
import { useShopConfigStore } from '@/stores/shopConfig';

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  /** Article à modifier (null : création). */
  product: ProductPublic | null;
  /** Création pré-remplie depuis cet article (ignoré quand `product` est fourni). */
  duplicateOf?: ProductPublic | null;
}>();
const mediaPickerOpen = ref(false);
/** Where the next picked image goes: the main image or the gallery. */
const pickerTarget = ref<'main' | 'gallery'>('main');
/** Same cap as the API (``GALLERY_MAX_IMAGES``). */
const GALLERY_MAX = 20;
const galleryUrlDraft = ref('');
function openPicker(target: 'main' | 'gallery') {
  pickerTarget.value = target;
  mediaPickerOpen.value = true;
}
function addGalleryImage(url: string) {
  const clean = url.trim();
  if (!clean || form.gallery_urls.includes(clean)) return;
  if (form.gallery_urls.length >= GALLERY_MAX) return;
  form.gallery_urls.push(clean);
}
function onMediaPicked(asset: { url: string }) {
  if (pickerTarget.value === 'main') form.image_url = asset.url;
  else addGalleryImage(asset.url);
}
function addGalleryUrl() {
  addGalleryImage(galleryUrlDraft.value);
  galleryUrlDraft.value = '';
}
function moveGallery(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= form.gallery_urls.length) return;
  const [item] = form.gallery_urls.splice(index, 1);
  if (item !== undefined) form.gallery_urls.splice(target, 0, item);
}
/** The clicked gallery picture becomes the main one; the old main joins the gallery. */
function makeMain(index: number) {
  const next = form.gallery_urls[index];
  if (next === undefined) return;
  const previous = form.image_url.trim();
  form.gallery_urls.splice(index, 1);
  if (previous && previous !== next && !form.gallery_urls.includes(previous)) {
    form.gallery_urls.splice(index, 0, previous);
  }
  form.image_url = next;
}
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  saved: [];
}>();

const store = useProductsStore();
const shopConfig = useShopConfigStore();
/** SHOP_MODE=simple: own stock sold at a fixed price, no supplier, no customs. */
const isSimpleShop = computed(() => shopConfig.isSimple);
/** Supply block (supplier, reference, attach): the suppliers module. */
const suppliersOn = computed(() => shopConfig.moduleOn('suppliers'));
/** « Caractéristiques » block (storefront filters typed by hand, R9 / T4). */
const specsOn = computed(() => shopConfig.moduleOn('specs'));

type PricingMode = 'import' | 'domestic' | 'fixed';
type AvailabilityMode = 'stock' | 'on_demand' | 'continuous' | 'lot';
type ProductCondition = 'new' | 'refurbished';

interface FormState {
  name: string;
  description: string;
  long_description: string;
  /** Translated texts per language (R9 / T3); the fields above are the source. */
  translations: Translations;
  supplier_name: string | null;
  supplier_sku: string;
  manufacturer: string;
  vendor_part_number: string;
  ean: string;
  supplier_quantity: string;
  /** Stock entrepôt — pas un champ produit : enregistré par un ajustement d'inventaire. */
  local_quantity: string;
  pricing_mode: PricingMode;
  availability_mode: AvailabilityMode;
  condition: ProductCondition;
  condition_grade: string;
  battery_health_pct: string;
  os_licence: string;
  warranty_months: string;
  margin_rate_pct: string;
  cost_amount: string;
  cost_currency: string;
  customs_rate_pct: string;
  base_price: string;
  /** Set: each unit sold issues a gift card of this amount (R8 / confort). */
  gift_card_amount: string;
  /** The variants are options over the base product, which stays sellable as is. */
  variants_optional: boolean;
  category_id: string | null;
  tax_rate_id: string | null;
  supplier_place_id: string | null;
  weight: number | null;
  dimensions_length: number | null;
  dimensions_width: number | null;
  dimensions_height: number | null;
  image_url: string;
  /** Extra pictures, after the main one (several images per product). */
  gallery_urls: string[];
  is_featured: boolean;
  featured_position: number | null;
}

/** Fields sent as decimal strings — never null (backend columns are non-nullable). */
const MONEY_FIELDS = ['cost_amount', 'base_price'] as const;

/**
 * Sent as a decimal string too, but blank means null: the product then inherits
 * its category's default customs rate. Defaulting it to '0.00' like the other
 * money fields would freeze a duty-free price on every product the admin ever
 * opens — the very bug the category default was introduced to fix.
 */
const NULLABLE_RATE_FIELDS = ['customs_rate_pct', 'margin_rate_pct', 'gift_card_amount'] as const;
/** Decimal string, blank → '0.00' (the column is non-nullable). */
const QUANTITY_FIELDS = ['supplier_quantity'] as const;

function emptyForm(): FormState {
  return {
    name: '',
    description: '',
    long_description: '',
    translations: {},
    supplier_name: null,
    supplier_sku: '',
    manufacturer: '',
    vendor_part_number: '',
    ean: '',
    supplier_quantity: '0',
    local_quantity: '0',
    pricing_mode: isSimpleShop.value ? 'fixed' : 'import',
    availability_mode: 'stock',
    condition: 'new',
    condition_grade: '',
    battery_health_pct: '',
    os_licence: '',
    warranty_months: '',
    margin_rate_pct: '',
    cost_amount: '0.00',
    cost_currency: shopConfig.currency,
    customs_rate_pct: '',
    base_price: '0.00',
    gift_card_amount: '',
    variants_optional: false,
    category_id: null,
    tax_rate_id: null,
    supplier_place_id: null,
    weight: null,
    dimensions_length: null,
    dimensions_width: null,
    dimensions_height: null,
    image_url: '',
    gallery_urls: [],
    is_featured: false,
    featured_position: null,
  };
}

const form = reactive<FormState>(emptyForm());
const content = useContentTranslations({
  form,
  fields: ['name', 'description', 'long_description'],
  status: () => props.product?.translation_status,
});
const texts = content.texts;
let original: FormState = emptyForm();

const saving = ref(false);
const error = ref<string | null>(null);
const req = [(v: string) => (!!v && v.trim().length > 0) || t('common.required')];

const currencyOptions = computed(() => {
  const codes = Array.from(new Set([shopConfig.currency, 'XPF', 'USD', 'EUR']));
  return codes.map((code) => ({ label: code, value: code }));
});
const categories = ref<Category[]>([]);
/** Marge par défaut de chaque catégorie (écran Catégories), pour montrer ce
 * qu'un champ « Marge » laissé vide appliquera. */
const categoryMargins = ref<Record<string, string | null>>({});
const marginHint = computed(() => {
  if (str(form.margin_rate_pct).trim() !== '') return t('product_form.margin_hint');
  const rate = form.category_id ? categoryMargins.value[form.category_id] : null;
  if (rate != null) {
    const category = categories.value.find((c) => c.id === form.category_id);
    return t('product_form.margin_inherit_category', {
      pct: Number(rate).toLocaleString(intlLocale()),
      category: category ? categoryLabel(category) : '',
    });
  }
  return t('product_form.margin_inherit_group');
});
const taxRates = ref<TaxRate[]>([]);
const places = ref<Place[]>([]);
const suppliers = ref<Supplier[]>([]);
const supplierOptions = ref<{ label: string; value: string }[]>([]);

const allPricingModeOptions = computed<{ label: string; value: PricingMode }[]>(() => [
  { label: t('product_form.pm_import'), value: 'import' },
  { label: t('product_form.pm_domestic'), value: 'domestic' },
  { label: t('product_form.pm_fixed'), value: 'fixed' },
]);
const pricingModeOptions = computed(() =>
  isSimpleShop.value
    ? allPricingModeOptions.value.filter((o) => o.value !== 'import')
    : allPricingModeOptions.value,
);
const PRICING_MODE_HINTS: Record<PricingMode, string> = labels({
  import: 'product_form.pm_hint_import',
  domestic: 'product_form.pm_hint_domestic',
  fixed: 'product_form.pm_hint_fixed',
});
const pricingModeHint = computed(() => PRICING_MODE_HINTS[form.pricing_mode]);

const availabilityModeOptions = computed<{ label: string; value: AvailabilityMode }[]>(() => [
  { label: t('product_form.am_stock'), value: 'stock' },
  { label: t('product_form.am_on_demand'), value: 'on_demand' },
  { label: t('product_form.am_continuous'), value: 'continuous' },
  { label: t('product_form.am_lot'), value: 'lot' },
]);
const conditionOptions = computed<{ label: string; value: ProductCondition }[]>(() => [
  { label: t('product_form.c_new'), value: 'new' },
  { label: t('product_form.c_refurbished'), value: 'refurbished' },
]);
const AVAILABILITY_MODE_HINTS: Record<AvailabilityMode, string> = labels({
  stock: 'product_form.am_hint_stock',
  on_demand: 'product_form.am_hint_on_demand',
  continuous: 'product_form.am_hint_continuous',
  lot: 'product_form.am_hint_lot',
});
const availabilityModeHint = computed(() => AVAILABILITY_MODE_HINTS[form.availability_mode]);

/**
 * The warehouse stock is what the checkout serves first; for a product with
 * no supplier it is the only sellable stock. Saved through the audited
 * inventory adjustment (a stock movement is written), not as a product field.
 */
const localStockHint = computed(() =>
  form.supplier_name || props.product?.is_supplier_managed
    ? t('product_form.local_hint_supplier')
    : t('product_form.local_hint_own'),
);

/**
 * Choosing a supplier pre-fills what the supplier decides: its origin
 * warehouse (first logistics leg) and its customs regime (pricing mode).
 * Both stay editable — the admin has the last word.
 */
function onSupplierChange(code: string | null) {
  const supplier = suppliers.value.find((s) => s.code === code);
  if (!supplier) return;
  if (supplier.origin_place_id) form.supplier_place_id = supplier.origin_place_id;
  if (form.pricing_mode !== 'fixed') {
    form.pricing_mode = supplier.is_domestic ? 'domestic' : 'import';
  }
  if (supplier.price_currency) form.cost_currency = supplier.price_currency;
}
const categoryOptions = ref<{ label: string; value: string }[]>([]);
// Marques connues (fabricants des produits + marques du catalogue).
const manufacturers = ref<string[]>([]);
const manufacturerFilter = ref('');
const manufacturerOptions = computed(() => {
  const needle = manufacturerFilter.value.trim().toLowerCase();
  return manufacturers.value.filter((m) => !needle || m.toLowerCase().includes(needle));
});
function filterManufacturers(needle: string, update: (fn: () => void) => void) {
  update(() => (manufacturerFilter.value = needle));
}
const taxRateOptions = ref<{ label: string; value: string }[]>([]);

// Caractéristiques (R9 / T4) : une ligne par définition de la catégorie ;
// la valeur saisie part dans product_specs en source « manual ».
const specRows = ref<SpecFormRow[]>([]);
const specValues = reactive<Record<string, string>>({});
const specFilter = reactive<Record<string, string>>({});
let specOriginal: Record<string, string> = {};

function specValueOf(row: SpecFormRow): string {
  if (row.value_numeric != null) return String(Number(row.value_numeric));
  return row.value_text ?? '';
}

function specOptions(row: SpecFormRow): string[] {
  const needle = (specFilter[row.key] ?? '').toLowerCase();
  return row.suggestions.filter((s) => !needle || s.toLowerCase().includes(needle));
}

async function loadSpecs(productId: string | null, categoryId: string | null) {
  if (!specsOn.value || (!productId && !categoryId)) {
    specRows.value = [];
    return;
  }
  try {
    const response = await getSpecForm({ productId, categoryId });
    specRows.value = response.specs;
    // Keep what the admin already typed for a key the new category still has.
    const typed = { ...specValues };
    for (const key of Object.keys(specValues)) delete specValues[key];
    specOriginal = {};
    for (const row of response.specs) {
      specOriginal[row.key] = specValueOf(row);
      const kept = typed[row.key];
      specValues[row.key] =
        kept !== undefined && kept !== specOriginal[row.key] ? kept : (specOriginal[row.key] ?? '');
    }
  } catch {
    specRows.value = [];
  }
}

/** Anything typed since the form was filled (fields, group prices, specs). */
function hasUnsavedChanges(): boolean {
  const keys = Object.keys(form) as (keyof FormState)[];
  if (keys.some((key) => JSON.stringify(form[key]) !== JSON.stringify(original[key]))) return true;
  if (specRows.value.some((row) => (specValues[row.key] ?? '') !== (specOriginal[row.key] ?? '')))
    return true;
  if (isEdit.value && linksKey(links.value) !== linksOriginal) return true;
  return (
    groupPrices.value !== null &&
    JSON.stringify(groupPrices.value) !== JSON.stringify(storedGroupPrices)
  );
}

// Unsaved edits are not lost on Escape, backdrop or navigation (R9 / T5).
const guard = useDialogGuard({
  isOpen: () => props.modelValue,
  close: () => emit('update:modelValue', false),
  isDirty: hasUnsavedChanges,
});

// Articles liés (R9 / T7) : accessoires et alternatives, dans l'ordre.
const links = ref<ProductLink[]>([]);
let linksOriginal = '';
const linkCandidates = ref<LinkCandidate[]>([]);

function linksKey(rows: ProductLink[]): string {
  return JSON.stringify(rows.map((l) => [l.linked_product_id, l.kind]));
}

async function loadLinks(productId: string | null) {
  links.value = [];
  linksOriginal = linksKey([]);
  if (!productId) return;
  try {
    links.value = await listProductLinks(productId);
  } catch {
    links.value = [];
  }
  linksOriginal = linksKey(links.value);
}

function moveLink(index: number, delta: number) {
  const target = index + delta;
  const row = links.value[index];
  const other = links.value[target];
  if (!row || !other) return;
  links.value.splice(index, 1, other);
  links.value.splice(target, 1, row);
}

function filterLinkCandidates(needle: string, update: (fn: () => void) => void) {
  const term = needle.trim();
  if (term.length < 2) {
    update(() => (linkCandidates.value = []));
    return;
  }
  void searchProductsForLink(term)
    .then((rows) => {
      const taken = new Set([props.product?.id, ...links.value.map((l) => l.linked_product_id)]);
      update(() => (linkCandidates.value = rows.filter((r) => !taken.has(r.id))));
    })
    .catch(() => update(() => (linkCandidates.value = [])));
}

function addLink(candidate: LinkCandidate | null) {
  if (!candidate) return;
  links.value.push({
    id: candidate.id,
    linked_product_id: candidate.id,
    kind: 'accessory',
    position: links.value.length,
    name: candidate.name,
    vendor_part_number: candidate.vendor_part_number ?? null,
    supplier_sku: null,
    image_url: null,
    is_active: true,
  });
}

async function saveLinks(productId: string) {
  if (!isEdit.value || linksKey(links.value) === linksOriginal) return;
  await setProductLinks(
    productId,
    links.value.map((l, index) => ({
      linked_product_id: l.linked_product_id,
      kind: l.kind === 'alternative' ? 'alternative' : 'accessory',
      position: index,
    })),
  );
}

async function saveSpecs(productId: string) {
  if (!specsOn.value) return;
  // A copy starts from the source's values, which the new article does not
  // have yet: every filled one is saved, not only what the admin retyped.
  const changed = specRows.value
    .filter((row) =>
      isDuplicate.value
        ? (specValues[row.key] ?? '').trim() !== ''
        : (specValues[row.key] ?? '') !== (specOriginal[row.key] ?? ''),
    )
    .map((row) => ({ key: row.key, value: (specValues[row.key] ?? '').trim() || null }));
  if (changed.length === 0) return;
  try {
    await setProductSpecs(productId, changed);
  } catch (err) {
    throw new Error(extractApiError(err) ?? t('product_form.specs_failed'), { cause: err });
  }
}

watch(
  () => form.category_id,
  (categoryId, previous) => {
    if (categoryId === previous) return;
    void loadSpecs(isEdit.value ? (props.product?.id ?? null) : null, categoryId);
  },
);

// Prix saisis par groupe de clients (group id → prix TTC) ; null tant que ceux
// de l'article ne sont pas chargés (l'aperçu prend alors ceux enregistrés).
const groupPrices = ref<Record<string, string> | null>(null);
let storedGroupPrices: Record<string, string> = {};

async function loadGroupPrices(product: ProductPublic | null) {
  groupPrices.value = null;
  storedGroupPrices = {};
  if (!product) {
    groupPrices.value = {};
    return;
  }
  try {
    storedGroupPrices = await getGroupPrices(product.id);
  } catch {
    storedGroupPrices = {};
  }
  groupPrices.value = { ...storedGroupPrices };
}

/** Enregistre les prix par groupe modifiés (après l'article lui-même). */
async function saveGroupPrices(productId: string) {
  if (groupPrices.value === null) return;
  const current = groupPrices.value;
  const ids = new Set([...Object.keys(storedGroupPrices), ...Object.keys(current)]);
  const changes = [...ids]
    .filter((id) =>
      // Same as the specs: a copy saves every price taken from the source.
      isDuplicate.value ? !!current[id] : (current[id] ?? '') !== (storedGroupPrices[id] ?? ''),
    )
    .map((id) => ({
      price_group_id: id,
      price: current[id] ? String(Number(current[id])) : null,
    }));
  if (changes.length) await setGroupPrices(productId, changes);
}

/** Valeurs de prix du formulaire, envoyées à l'aperçu de marge. */
const marginInput = computed<MarginPreviewRequest>(() => ({
  group_prices: groupPrices.value,
  product_id: isEdit.value ? (props.product?.id ?? null) : null,
  pricing_mode: form.pricing_mode,
  base_price: decimalOrNull(form.base_price),
  cost_amount: decimalOrNull(form.cost_amount),
  cost_currency: form.cost_currency || null,
  margin_rate_pct: decimalOrNull(form.margin_rate_pct),
  customs_rate_pct: decimalOrNull(form.customs_rate_pct),
  tax_rate_id: form.tax_rate_id,
  category_id: form.category_id,
}));

function decimalOrNull(value: string | number | null): string | null {
  const text = String(value ?? '').trim();
  return text === '' || Number.isNaN(Number(text)) ? null : String(Number(text));
}
const placeOptions = ref<{ label: string; value: string }[]>([]);

const isEdit = ref(false);
/** Article created by this dialog session (its later saves update it). */
const createdId = ref<string | null>(null);
/** Création pré-remplie depuis un autre article (« Dupliquer »). */
const isDuplicate = ref(false);

/** Libellés des champs verrouillables, pour les puces de verrous. */
const FIELD_LABELS: Record<string, string> = labels({
  name: 'product_form.f_name',
  description: 'product_form.f_description',
  long_description: 'product_form.f_long_description',
  supplier_name: 'product_form.f_supplier_name',
  supplier_sku: 'product_form.f_supplier_sku',
  manufacturer: 'product_form.f_manufacturer',
  vendor_part_number: 'product_form.f_vendor_part_number',
  ean: 'product_form.f_ean',
  supplier_quantity: 'product_form.f_supplier_quantity',
  pricing_mode: 'product_form.f_pricing_mode',
  availability_mode: 'product_form.f_availability_mode',
  condition: 'product_form.f_condition',
  condition_grade: 'product_form.f_condition_grade',
  battery_health_pct: 'product_form.f_battery_health_pct',
  os_licence: 'product_form.f_os_licence',
  warranty_months: 'product_form.f_warranty_months',
  margin_rate_pct: 'product_form.f_margin_rate_pct',
  cost_amount: 'product_form.f_cost_amount',
  cost_currency: 'product_form.f_cost_currency',
  customs_rate_pct: 'product_form.f_customs_rate_pct',
  base_price: 'product_form.f_base_price',
  gift_card_amount: 'product_form.f_gift_card_amount',
  variants_optional: 'product_form.variants_optional',
  category_id: 'product_form.f_category_id',
  tax_rate_id: 'product_form.f_tax_rate_id',
  supplier_place_id: 'product_form.f_supplier_place_id',
  weight: 'product_form.f_weight',
  dimensions_length: 'product_form.f_dimensions_length',
  dimensions_width: 'product_form.f_dimensions_width',
  dimensions_height: 'product_form.f_dimensions_height',
  image_url: 'product_form.f_image_url',
  gallery_urls: 'product_form.f_gallery_urls',
  is_featured: 'product_form.f_is_featured',
  featured_position: 'product_form.f_featured_position',
});
function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

const lockedFields = ref<string[]>([]);
const releasing = ref<string | null>(null);

const $q = useQuasar();
const router = useRouter();
/** Catalogue → Caractéristiques, pre-filtered on the product's category. */
const specDefinitionsHref = computed(
  () =>
    router.resolve({
      path: '/spec-definitions',
      query: form.category_id ? { category: form.category_id } : {},
    }).href,
);
const linking = ref<'attach' | 'detach' | null>(null);
const linkNotice = ref<string | null>(null);
/** Supplier state after an attach / detach in this dialog (the prop is stale). */
const managedAfterLink = ref<boolean | null>(null);
const linkedManaged = computed<boolean>(() =>
  managedAfterLink.value !== null ? managedAfterLink.value : !!props.product?.is_supplier_managed,
);

async function onAttach() {
  if (!props.product) return;
  linking.value = 'attach';
  error.value = null;
  linkNotice.value = null;
  try {
    const res = await attachProductToSupplier(props.product.id, {
      supplier_name: form.supplier_name,
      supplier_sku: form.supplier_sku.trim(),
    });
    linkNotice.value = res.message;
    managedAfterLink.value = !!res.product.is_supplier_managed;
    lockedFields.value = [...(res.product.overridden_fields ?? [])];
    emit('saved');
  } catch (err: unknown) {
    error.value = extractApiError(err) ?? t('product_form.attach_failed');
  } finally {
    linking.value = null;
  }
}

function onDetach() {
  const product = props.product;
  if (!product) return;
  $q.dialog({
    title: t('product_form.detach_q'),
    message: t('product_form.detach_msg'),
    cancel: { flat: true, noCaps: true, label: t('common.cancel') },
    ok: { color: 'negative', unelevated: true, noCaps: true, label: t('product_form.detach') },
  }).onOk(() => {
    void (async () => {
      linking.value = 'detach';
      error.value = null;
      linkNotice.value = null;
      try {
        await detachProductFromSupplier(product.id);
        form.supplier_name = null;
        managedAfterLink.value = false;
        linkNotice.value = t('product_form.detached');
        emit('saved');
      } catch (err: unknown) {
        error.value = extractApiError(err) ?? t('product_form.detach_failed');
      } finally {
        linking.value = null;
      }
    })();
  });
}

async function onRelease(field: string) {
  if (!props.product) return;
  releasing.value = field;
  error.value = null;
  try {
    const refreshed = await store.releaseOverride(props.product.id, field);
    lockedFields.value = [...(refreshed.overridden_fields ?? [])];
    emit('saved');
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : t('product_form.release_failed');
  } finally {
    releasing.value = null;
  }
}

function str(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return '';
}
/** Decimal string from the API ("12.00") → integer text for the field ("12"). */
function formatQty(v: unknown): string {
  const n = Number(v);
  return Number.isFinite(n) ? String(Math.max(0, Math.round(n))) : '0';
}
function num(v: unknown): number | null {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

/** Longueur maximale du nom côté API (`ProductBase.name`). */
const NAME_MAX = 100;

function loadFromProduct(p: ProductPublic | null, asCopy = false) {
  const base = emptyForm();
  if (p) {
    const rec = p as unknown as Record<string, unknown>;
    base.name = str(rec.name);
    base.description = str(rec.description);
    base.long_description = str(rec.long_description);
    base.translations = cloneTranslations(rec.translations);
    base.supplier_name = (rec.supplier_name as string | null) ?? null;
    base.supplier_sku = str(rec.supplier_sku);
    base.manufacturer = str(rec.manufacturer);
    base.vendor_part_number = str(rec.vendor_part_number);
    base.ean = str(rec.ean);
    base.supplier_quantity = str(rec.supplier_quantity) || '0';
    base.local_quantity = formatQty(rec.local_quantity);
    const mode = str(rec.pricing_mode);
    base.pricing_mode = mode === 'domestic' || mode === 'fixed' ? mode : 'import';
    const availability = str(rec.availability_mode);
    base.availability_mode =
      availability === 'on_demand' || availability === 'continuous' || availability === 'lot'
        ? availability
        : 'stock';
    base.condition = str(rec.condition) === 'refurbished' ? 'refurbished' : 'new';
    base.condition_grade = str(rec.condition_grade);
    base.battery_health_pct = str(rec.battery_health_pct);
    base.os_licence = str(rec.os_licence);
    base.warranty_months = str(rec.warranty_months);
    base.margin_rate_pct = str(rec.margin_rate_pct);
    base.gift_card_amount = str(rec.gift_card_amount);
    base.variants_optional = rec.variants_optional === true;
    base.cost_amount = str(rec.cost_amount) || '0.00';
    base.cost_currency = str(rec.cost_currency) || shopConfig.currency;
    base.customs_rate_pct = str(rec.customs_rate_pct);
    base.base_price = str(rec.base_price) || '0.00';
    base.category_id = (rec.category_id as string | null) ?? null;
    base.tax_rate_id = (rec.tax_rate_id as string | null) ?? null;
    base.supplier_place_id = (rec.supplier_place_id as string | null) ?? null;
    base.weight = num(rec.weight);
    base.dimensions_length = num(rec.dimensions_length);
    base.dimensions_width = num(rec.dimensions_width);
    base.dimensions_height = num(rec.dimensions_height);
    base.image_url = str(rec.image_url);
    base.gallery_urls = Array.isArray(rec.gallery_urls)
      ? (rec.gallery_urls as unknown[]).map((u) => str(u)).filter(Boolean)
      : [];
    base.is_featured = Boolean(rec.is_featured);
    base.featured_position = num(rec.featured_position);
  }
  if (p && asCopy) {
    // Copy of an article: the content, prices, category, images and
    // logistics carry over; what identifies or counts the original does not.
    base.name = t('product_form.copy_name', { name: base.name }).slice(0, NAME_MAX);
    base.supplier_name = null;
    base.supplier_sku = '';
    base.vendor_part_number = '';
    base.ean = '';
    base.supplier_quantity = '0';
    base.local_quantity = '0';
    base.is_featured = false;
    base.featured_position = null;
  }
  Object.assign(form, base);
  // Deep copy: the gallery is an array the form mutates in place.
  original = { ...base, gallery_urls: [...base.gallery_urls] };
  content.reset();
}

/** Build the payload: full for create, only changed fields for edit. */
function buildPayload(): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const keys = Object.keys(form) as (keyof FormState)[];
  for (const key of keys) {
    if (key === 'local_quantity') continue; // inventory adjustment, not a product field
    const value = form[key];
    if (isEdit.value && JSON.stringify(value) === JSON.stringify(original[key])) continue;
    if (MONEY_FIELDS.includes(key as (typeof MONEY_FIELDS)[number])) {
      out[key] = str(value).trim() || '0.00';
    } else if (QUANTITY_FIELDS.includes(key as (typeof QUANTITY_FIELDS)[number])) {
      out[key] = str(value).trim() || '0';
    } else if (NULLABLE_RATE_FIELDS.includes(key as (typeof NULLABLE_RATE_FIELDS)[number])) {
      out[key] = str(value).trim() || null;
    } else if (typeof value === 'string') {
      out[key] = value.trim() === '' ? null : value.trim();
    } else {
      out[key] = value;
    }
  }
  // `name` is required — never send it as null even if blanked.
  if (out.name == null && !isEdit.value) out.name = form.name.trim();
  return out;
}

async function onSubmit() {
  saving.value = true;
  error.value = null;
  try {
    const payload = buildPayload();
    let productId: string;
    const existingId = isEdit.value && props.product ? props.product.id : createdId.value;
    if (existingId) {
      await store.updateProduct(existingId, payload);
      productId = existingId;
    } else {
      productId = (await store.createProduct(payload)).id;
      // A later step (stock, group prices…) may still fail: the next
      // « Enregistrer » updates this article instead of creating a second
      // one (audit 2026-11).
      createdId.value = productId;
    }
    await saveLocalStock(productId);
    await saveGroupPrices(productId);
    await saveSpecs(productId);
    await saveLinks(productId);
    emit('saved');
    emit('update:modelValue', false);
  } catch (err: unknown) {
    // The API's message, never axios' « Request failed with status code… ».
    error.value =
      extractApiError(err) ??
      (err instanceof Error && !('response' in err) ? err.message : null) ??
      t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

/**
 * Warehouse stock goes through the audited inventory adjustment (the same
 * one as the « Inventaire » page): the quantity becomes the new absolute
 * local stock and a movement records the delta. Nothing is sent when it did
 * not change, so an edit never rewrites the stock silently.
 */
async function saveLocalStock(productId: string) {
  const next = formatQty(form.local_quantity);
  const previous = formatQty(original.local_quantity);
  if (next === previous) return;
  await adjustInventory({
    product_id: productId,
    place_id: null,
    quantity: next,
    reason: isEdit.value ? t('product_form.reason_edit') : t('product_form.reason_initial'),
  });
}

async function loadLookups() {
  void shopConfig.load();
  try {
    [categories.value, taxRates.value, places.value, suppliers.value] = await Promise.all([
      listCategories(),
      listTaxRates({ valid: true }),
      listPlaces(),
      listSuppliers(),
    ]);
    supplierOptions.value = suppliers.value
      .filter((s) => s.is_active)
      .map((s) => ({
        label: `${s.name}${s.is_domestic ? t('product_form.local') : ''} — ${s.code}`,
        value: s.code,
      }));
    // « Réseau › WiFi › Point d'accès » : le chemin complet lève l'ambiguïté
    // entre deux sous-catégories de même nom.
    categoryOptions.value = categoryPathOptions(categories.value);
    void listManufacturers()
      .then((rows) => (manufacturers.value = rows))
      .catch(() => undefined);
    void listAdminCategories()
      .then((rows) => {
        categoryMargins.value = Object.fromEntries(
          rows.map((c) => [c.id, c.default_margin_rate_pct]),
        );
      })
      .catch(() => undefined);
    taxRateOptions.value = taxRates.value.map((t) => ({
      label: `${t.label} (${t.rate_pct}%)`,
      value: t.id,
    }));
    placeOptions.value = places.value.map((p) => ({
      label: p.code ? `${p.name} (${p.code})` : p.name,
      value: p.id,
    }));
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : t('product_form.lists_failed');
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      isEdit.value = !!props.product;
      createdId.value = null;
      isDuplicate.value = !props.product && !!props.duplicateOf;
      // Edit: the article itself. Duplicate: the source, read but never written.
      const seed = props.product ?? (isDuplicate.value ? (props.duplicateOf ?? null) : null);
      error.value = null;
      linkNotice.value = null;
      managedAfterLink.value = null;
      lockedFields.value = [...(props.product?.overridden_fields ?? [])];
      loadFromProduct(seed, isDuplicate.value);
      for (const key of Object.keys(specValues)) delete specValues[key];
      void loadSpecs(seed?.id ?? null, seed?.category_id ?? null);
      // Linked articles are edited on an existing product only.
      void loadLinks(props.product?.id ?? null);
      void loadGroupPrices(seed);
    }
  },
);

onMounted(() => {
  void loadLookups();
});
</script>

<style scoped lang="scss">
.product-form__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.product-form__body {
  padding-top: 12px;
}

.product-form__locks {
  margin-bottom: 16px;
}

/* Une section = un bloc bordé, titré, avec son aide : le formulaire se lit
   bloc par bloc au lieu d'une seule colonne de champs. */
.product-form__section {
  padding: 16px 18px 18px;
  border: 1px solid var(--n-line);
  border-radius: 10px;
  background: var(--n-surface);
  min-width: 0;
}

.product-form__section + .product-form__section,
.product-form__grid,
.product-form__grid + .product-form__section,
.product-form__stack > .product-form__section + .product-form__section {
  margin-top: 16px;
}

.product-form__section-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  column-gap: 8px;
  align-items: center;
  margin-bottom: 14px;
}

.product-form__section-icon {
  font-size: 18px;
  color: var(--n-ink-3);
}

.product-form__section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--n-ink);
}

.product-form__section-hint {
  grid-column: 2;
  margin: 2px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--n-ink-2);
}

/* Les champs d'une section : une pile à écart constant. `hide-bottom-space`
   sur les champs évite la réserve de 20 px sous chacun ; une aide ou une
   erreur pousse simplement le champ suivant. */
.product-form__fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.product-form__row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 14px 12px;
  align-items: start;
  min-width: 0;

  &--ids {
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  }

  &--dims {
    grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  }

  &--specs {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
}

.product-form__inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
}

.product-form__inline-field {
  flex: 0 1 220px;
}

.product-form__choice {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.product-form__choice-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--n-ink-2);
}

.product-form__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  /* Les deux blocs d'une rangée ont la même hauteur : pas de « trou » sous
     le plus court. */
  align-items: stretch;

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
  }
}

.product-form__stack {
  min-width: 0;
}

.product-form__help {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--n-ink-2);
}

/* Images : la principale à gauche, la galerie à droite. */
.product-form__images {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 20px;
  align-items: start;

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
  }
}

.product-form__image-main {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.product-form__frame {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 1;
  overflow: hidden;
  border: 1px solid var(--n-line);
  border-radius: var(--n-radius);
  background: var(--n-photo);

  img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    padding: 6%;
  }
}

.product-form__frame-glyph {
  color: var(--n-photo-glyph);
}

.product-form__frame-tag {
  position: absolute;
  left: 8px;
  bottom: 8px;
  padding: 1px 8px;
  border-radius: var(--n-radius-pill);
  font-size: 11px;
  font-weight: 600;
  color: var(--n-on-ink);
  background: var(--n-ink);
}

.product-form__gallery {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.product-form__gallery-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--n-ink-2);
}

.product-form__thumbs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 10px;
}

.product-form__thumb {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  &--add {
    aspect-ratio: 1;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 8px;
    border: 1px dashed var(--n-line-2);
    border-radius: var(--n-radius);
    background: none;
    font: inherit;
    font-size: 12px;
    color: var(--n-ink-2);
    cursor: pointer;
    text-align: center;

    &:hover {
      border-color: var(--n-ink);
      color: var(--n-ink);
    }

    &[disable] {
      opacity: 0.5;
      cursor: default;
    }
  }
}

.product-form__thumb-actions {
  display: flex;
  justify-content: center;
  gap: 0;
}

.product-form__gallery-url {
  max-width: 520px;
}

.product-form__spec {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;

  > :first-child {
    flex: 1;
    min-width: 0;
  }
}

.product-form__spec-source {
  flex: none;
}

.product-form__spec-link {
  margin-left: 4px;
  color: var(--n-ink);
}

.product-form__link {
  display: flex;
  align-items: center;
  gap: 8px;
}

.product-form__link-kind {
  flex: none;
  border: 1px solid var(--n-line);
  border-radius: var(--n-radius);
}

.product-form__link-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
