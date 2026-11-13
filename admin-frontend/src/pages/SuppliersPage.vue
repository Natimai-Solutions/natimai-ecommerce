<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('suppliers.title')">
      <template #hint>
        {{ $t('suppliers.intro') }}
      </template>
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('suppliers.new')"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <HelpPanel :title="$t('help.suppliers_title')" :items="helpItems" storage-key="suppliers">
      {{ $t('help.suppliers_note') }}
      <router-link
        v-if="shopConfig.moduleOn('logistics_multileg')"
        to="/logistics-routes?view=places"
        class="admin-link"
        >{{ $t('layout.nav.routes') }}</router-link
      >
      <template v-else>{{ $t('layout.nav.routes') }}</template
      >.
    </HelpPanel>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

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
      <template #body-cell-code="props">
        <q-td :props="props" class="font-mono">{{ props.row.code }}</q-td>
      </template>
      <template #body-cell-kind="props">
        <q-td :props="props">
          <StatusTag :label="kindLabel(props.row.kind)" :icon="kindIcon(props.row.kind)" />
          <span v-if="props.row.kind === 'api'" class="text-caption text-muted font-mono q-ml-xs">
            {{ props.row.adapter_key }}
          </span>
        </q-td>
      </template>
      <template #body-cell-origin="props">
        <q-td :props="props">{{ placeName(props.row.origin_place_id) }}</q-td>
      </template>
      <template #body-cell-domestic="props">
        <q-td :props="props">
          <StatusTag
            v-if="props.row.is_domestic"
            :label="$t('suppliers.local')"
            icon="ph:map-pin"
          />
          <StatusTag v-else :label="$t('suppliers.import')" icon="ph:globe-hemisphere-west" />
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <StatusTag
            v-if="!props.row.is_active"
            :label="$t('suppliers.disabled')"
            tone="neutral"
            icon="ph:minus-circle"
          />
          <span v-else-if="props.row.kind === 'api' && !props.row.configured">
            <StatusTag :label="$t('suppliers.to_configure')" tone="warn" icon="ph:warning" />
            <q-tooltip>{{ $t('suppliers.no_creds') }}</q-tooltip>
          </span>
          <StatusTag v-else :label="$t('suppliers.active')" tone="ok" icon="ph:check-circle" />
          <span v-if="props.row.kind === 'api'" class="text-caption text-muted q-ml-xs">
            {{
              props.row.sync_enabled
                ? props.row.sync_interval_hours > 0
                  ? $t('suppliers.sync_every', { n: props.row.sync_interval_hours })
                  : $t('suppliers.sync_manual')
                : $t('suppliers.sync_off')
            }}
          </span>
          <q-chip
            v-if="props.row.sku_allowlist?.length"
            dense
            icon="ph:list-checks"
            class="q-ml-xs"
            :label="$t('suppliers.allowlist_badge', { n: props.row.sku_allowlist.length })"
            data-testid="supplier-allowlist-badge"
          >
            <q-tooltip>{{ $t('suppliers.allowlist_tip') }}</q-tooltip>
          </q-chip>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            :aria-label="$t('suppliers.import_tip')"
            flat
            round
            dense
            v-if="shopConfig.moduleOn('file_import')"
            icon="ph:file-arrow-up"
            :disable="!props.row.is_active"
            @click="openImport(props.row)"
          >
            <q-tooltip>{{ $t('suppliers.import_tip') }}</q-tooltip>
          </q-btn>
          <q-btn
            :aria-label="$t('suppliers.sync_tip')"
            v-if="props.row.kind === 'api'"
            flat
            round
            dense
            icon="ph:arrows-clockwise"
            :disable="!props.row.is_active || !props.row.configured"
            :loading="busy === props.row.code"
            @click="onSync(props.row)"
          >
            <q-tooltip>{{ $t('suppliers.sync_tip') }}</q-tooltip>
          </q-btn>
          <q-btn
            :aria-label="$t('suppliers.test_tip')"
            v-if="props.row.kind === 'api'"
            flat
            round
            dense
            icon="ph:heartbeat"
            :disable="!props.row.is_active"
            @click="onHealth(props.row)"
          >
            <q-tooltip>{{ $t('suppliers.test_tip') }}</q-tooltip>
          </q-btn>
          <q-btn
            :aria-label="$t('suppliers.categories_tip')"
            v-if="props.row.kind !== 'manual'"
            flat
            round
            dense
            icon="ph:tree-structure"
            data-testid="supplier-categories"
            @click="openCategories(props.row)"
          >
            <q-tooltip>{{ $t('suppliers.categories_tip') }}</q-tooltip>
          </q-btn>
          <q-btn
            :aria-label="$t('suppliers.allowlist_title_tip')"
            v-if="props.row.kind !== 'manual'"
            flat
            round
            dense
            icon="ph:list-checks"
            :disable="!props.row.is_active"
            data-testid="supplier-allowlist"
            @click="openAllowlist(props.row)"
          >
            <q-tooltip>{{ $t('suppliers.allowlist_title_tip') }}</q-tooltip>
          </q-btn>
          <q-btn
            :aria-label="$t('common.edit')"
            flat
            round
            dense
            icon="ph:pencil-simple"
            @click="openEdit(props.row)"
          >
            <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
          </q-btn>
          <q-btn
            :aria-label="$t('suppliers.disable_tip')"
            v-if="props.row.is_active"
            flat
            round
            dense
            icon="ph:prohibit"
            color="negative"
            data-testid="supplier-deactivate"
            @click="openDeactivate(props.row)"
          >
            <q-tooltip>{{ $t('suppliers.disable_tip') }}</q-tooltip>
          </q-btn>
          <q-btn
            :aria-label="$t('suppliers.enable_tip')"
            v-else
            flat
            round
            dense
            icon="ph:power"
            :loading="busy === props.row.code"
            data-testid="supplier-reactivate"
            @click="onReactivate(props.row)"
          >
            <q-tooltip>{{ $t('suppliers.enable_tip') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('suppliers.none') }}</div>
      </template>
    </q-table>

    <!-- Désactivation -->
    <q-dialog v-model="deactivateDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ $t('suppliers.disable_title', { name: deactivating?.name }) }}
          </h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <p class="q-mb-sm">
            {{ $t('suppliers.disable_hint') }}
          </p>
          <p class="text-subtle q-mb-xs">{{ $t('suppliers.and_items') }}</p>
          <q-option-group
            v-model="deactivateProducts"
            :options="deactivateOptions"
            type="radio"
            data-testid="supplier-deactivate-products"
          />
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn v-close-popup flat no-caps :label="$t('common.cancel')" />
          <q-btn
            color="negative"
            unelevated
            no-caps
            :label="$t('suppliers.disable')"
            :loading="busy === deactivating?.code"
            data-testid="supplier-deactivate-confirm"
            @click="confirmDeactivate"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Création / édition -->
    <q-dialog
      :model-value="formDialog"
      :persistent="formGuard.persistent.value"
      @update:model-value="formGuard.onToggle"
    >
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{
              editing
                ? $t('suppliers.edit_title', { name: editing.name })
                : $t('suppliers.new_title')
            }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submitForm">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>

            <div class="row" style="gap: 8px">
              <q-input
                v-model="form.code"
                :label="$t('suppliers.code')"
                :hint="$t('suppliers.code_hint')"
                outlined
                dense
                class="col"
                :disable="!!editing"
                :rules="editing ? [] : codeRules"
              />
              <q-input
                v-model="form.name"
                :label="$t('suppliers.name')"
                outlined
                dense
                class="col"
                :rules="req"
              />
            </div>

            <q-select
              v-model="form.kind"
              :options="kindOptions"
              :label="$t('suppliers.kind')"
              outlined
              dense
              emit-value
              map-options
            />

            <q-select
              v-if="form.kind === 'api'"
              v-model="form.adapter_key"
              :options="adapterOptions"
              :label="$t('suppliers.adapter')"
              :hint="$t('suppliers.adapter_hint')"
              outlined
              dense
              emit-value
              map-options
            />
            <AppNotice
              v-if="form.kind === 'api' && selectedAdapter && !selectedAdapter.configured"
              tone="warning"
              dense
            >
              {{ $t('suppliers.creds_missing') }}
            </AppNotice>

            <q-select
              v-model="form.origin_place_id"
              :options="placeOptions"
              :label="$t('suppliers.origin')"
              :hint="$t('suppliers.origin_hint')"
              outlined
              dense
              emit-value
              map-options
              clearable
            />

            <q-toggle v-model="form.is_domestic" :label="$t('suppliers.domestic')" />
            <div class="text-caption text-muted q-ml-md">
              {{ form.is_domestic ? $t('suppliers.local_hint') : $t('suppliers.import_hint') }}
            </div>

            <div class="row" style="gap: 8px">
              <q-select
                v-model="form.price_currency"
                :options="currencyOptions"
                :label="$t('suppliers.currency')"
                :hint="$t('suppliers.currency_hint')"
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
                :label="$t('suppliers.interval')"
                :hint="$t('suppliers.interval_hint')"
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
                :label="$t('suppliers.drafts')"
                data-testid="supplier-import-as-draft"
              />
              <div class="text-caption text-muted q-ml-md">
                {{ $t('suppliers.drafts_hint') }}
              </div>
              <div class="row q-mt-sm" style="gap: 8px">
                <q-input
                  v-model="form.min_quantity"
                  :label="$t('suppliers.min_qty')"
                  :hint="$t('suppliers.no_threshold')"
                  type="number"
                  min="0"
                  outlined
                  dense
                  class="col"
                  data-testid="supplier-min-quantity"
                />
                <q-input
                  v-model="form.min_price"
                  :label="$t('suppliers.min_price')"
                  :hint="$t('suppliers.min_price_hint')"
                  type="number"
                  min="0"
                  step="any"
                  outlined
                  dense
                  class="col"
                  data-testid="supplier-min-price"
                />
              </div>
              <div class="text-caption text-muted q-ml-md">
                {{ $t('suppliers.threshold_hint') }}
              </div>
              <q-select
                v-model="form.unmapped_category_action"
                :options="unmappedOptions"
                :label="$t('suppliers.unmapped')"
                :hint="$t('suppliers.unmapped_hint')"
                outlined
                dense
                emit-value
                map-options
                class="q-mt-sm"
                data-testid="supplier-unmapped-action"
              />
            </template>

            <template v-if="form.kind === 'api'">
              <q-toggle v-model="form.sync_enabled" :label="$t('suppliers.sync_enabled')" />
              <template v-if="selectedAdapter?.supports_purchase_orders">
                <q-toggle
                  v-model="form.auto_purchase_order"
                  :label="$t('suppliers.auto_po')"
                  data-testid="supplier-auto-po"
                />
                <div class="text-caption text-muted q-ml-md">
                  {{ $t('suppliers.auto_po_hint') }}
                </div>
              </template>
              <q-select
                v-model="form.default_categories"
                :label="$t('suppliers.synced_categories')"
                :hint="$t('suppliers.type_category')"
                multiple
                use-chips
                use-input
                hide-dropdown-icon
                new-value-mode="add-unique"
                input-debounce="0"
                outlined
                dense
              />
              <div v-if="adapterFields.length" class="q-gutter-sm">
                <h3 class="admin-subtitle q-mb-none">{{ $t('suppliers.adapter_settings') }}</h3>
                <template v-for="field in adapterFields" :key="field.key">
                  <q-select
                    v-if="field.kind === 'choice'"
                    v-model="form.settings[field.key]"
                    :options="choiceOptions(field)"
                    :label="field.label"
                    :hint="field.hint || undefined"
                    outlined
                    dense
                    clearable
                    emit-value
                    map-options
                  />
                  <q-input
                    v-else
                    v-model="form.settings[field.key]"
                    :label="field.label"
                    :hint="fieldHint(field)"
                    :type="field.kind === 'json' ? 'textarea' : 'text'"
                    :autogrow="field.kind === 'json'"
                    :inputmode="field.kind === 'number' ? 'decimal' : undefined"
                    :input-class="field.kind === 'json' ? 'font-mono' : undefined"
                    outlined
                    dense
                  />
                </template>
                <AppNotice v-if="isFeedForm" tone="info" dense>
                  {{ $t('suppliers.feed_hint') }}
                </AppNotice>
              </div>
              <div v-if="isFeedForm && editing" class="q-gutter-sm" data-testid="feed-credentials">
                <h3 class="admin-subtitle q-mb-none">
                  {{ $t('suppliers.portal_creds') }}
                  <StatusTag
                    v-if="editing.has_credentials"
                    tone="ok"
                    icon="ph:lock-key"
                    :label="$t('suppliers.saved_creds')"
                    class="q-ml-sm"
                  />
                </h3>
                <div class="text-caption text-muted">
                  {{ $t('suppliers.creds_hint') }}
                </div>
                <div class="row" style="gap: 8px">
                  <q-input
                    v-model="credentials.username"
                    :label="$t('suppliers.username')"
                    autocomplete="off"
                    outlined
                    dense
                    class="col"
                  />
                  <q-input
                    v-model="credentials.password"
                    :label="$t('suppliers.password')"
                    type="password"
                    autocomplete="new-password"
                    outlined
                    dense
                    class="col"
                  />
                </div>
                <div class="row" style="gap: 8px">
                  <q-btn
                    outline
                    dense
                    no-caps
                    icon="ph:floppy-disk"
                    :label="$t('suppliers.save_creds')"
                    :disable="!credentials.username || !credentials.password"
                    :loading="credentialsBusy"
                    @click="onSaveCredentials"
                  />
                  <q-btn
                    v-if="editing.has_credentials"
                    flat
                    dense
                    no-caps
                    icon="ph:trash"
                    :label="$t('suppliers.clear')"
                    :loading="credentialsBusy"
                    @click="onClearCredentials"
                  />
                </div>
              </div>
              <AppNotice v-else-if="isFeedForm" tone="info" dense>
                {{ $t('suppliers.save_first') }}
              </AppNotice>
            </template>

            <div class="row" style="gap: 8px">
              <q-input
                v-model="form.contact_email"
                :label="$t('suppliers.email')"
                outlined
                dense
                class="col"
              />
              <q-input
                v-model="form.contact_phone"
                :label="$t('suppliers.phone')"
                outlined
                dense
                class="col"
              />
            </div>
            <q-input
              v-model="form.notes"
              :label="$t('suppliers.notes')"
              type="textarea"
              autogrow
              outlined
              dense
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" @click="formGuard.requestClose()" />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('common.save')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Références suivies (liste blanche de SKU) -->
    <q-dialog
      :model-value="allowlistDialog"
      :persistent="allowlistGuard.persistent.value"
      @update:model-value="allowlistGuard.onToggle"
    >
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ $t('suppliers.allowlist_title', { name: allowlistSupplier?.name }) }}
          </h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="allowlistError" tone="error" dense>{{ allowlistError }}</AppNotice>
          <div class="text-caption text-muted">
            {{ $t('suppliers.allowlist_hint') }}
          </div>
          <q-input
            v-model="allowlistText"
            type="textarea"
            outlined
            dense
            autogrow
            :input-style="{ minHeight: '160px', fontFamily: 'monospace' }"
            :label="$t('suppliers.allowlist_title_tip')"
            stack-label
            placeholder="IM-12345&#10;IM-67890"
            data-testid="allowlist-text"
          />
          <div v-if="allowlistView" class="text-caption text-muted">
            {{
              $t('suppliers.allowlist_stats', {
                n: allowlistView.entries.length,
                known: allowlistView.known,
                unknown: allowlistView.unknown.length,
                outside: allowlistView.outside,
              })
            }}
            <span v-if="allowlistView.deactivated">
              {{ $t('suppliers.just_withdrawn', { n: allowlistView.deactivated }) }}
            </span>
          </div>
          <q-expansion-item
            v-if="allowlistView?.entries.length"
            dense
            :label="$t('suppliers.allowlist_detail')"
            class="q-mt-xs"
          >
            <q-markup-table dense flat bordered>
              <thead>
                <tr>
                  <th class="text-left">{{ $t('suppliers.h_reference') }}</th>
                  <th class="text-left">{{ $t('suppliers.h_item') }}</th>
                  <th class="text-left">{{ $t('suppliers.h_state') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in allowlistView.entries" :key="e.supplier_sku">
                  <td class="font-mono">{{ e.supplier_sku }}</td>
                  <td>{{ e.product_name ?? $t('suppliers.to_create') }}</td>
                  <td>
                    <StatusTag
                      v-if="e.is_active === true"
                      :label="$t('suppliers.in_shop')"
                      tone="ok"
                      icon="ph:eye"
                    />
                    <StatusTag
                      v-else-if="e.is_active === false"
                      :label="$t('suppliers.hidden')"
                      tone="neutral"
                      icon="ph:eye-slash"
                    />
                    <span v-else class="text-subtle">{{ $t('suppliers.unknown') }}</span>
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
          </q-expansion-item>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.close')" @click="allowlistGuard.requestClose()" />
          <q-btn
            color="primary"
            unelevated
            no-caps
            :label="$t('suppliers.save_list')"
            :loading="allowlistSaving"
            data-testid="allowlist-save"
            @click="saveAllowlist"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Catégories du fournisseur -->
    <q-dialog v-model="categoriesDialog">
      <q-card class="app-dialog app-dialog--xl">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ $t('suppliers.categories_title', { name: categoriesOf?.name }) }}
          </h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="categoriesError" tone="error" dense>{{ categoriesError }}</AppNotice>
          <AppNotice v-if="categoriesNotice" tone="success" dense>{{ categoriesNotice }}</AppNotice>
          <p class="admin-hint">
            {{ $t('suppliers.categories_hint', { fallback: unmappedLabel }) }}
          </p>
          <div v-if="categoriesLoading" class="text-center q-pa-md"><q-spinner size="2em" /></div>
          <CategoryPairsTable
            v-else
            :pairs="observed"
            :categories="categories"
            :saving="categoriesSaving"
            @save="saveSupplierRules"
          />
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.close')" v-close-popup />
          <q-btn
            outline
            no-caps
            icon="ph:arrows-counter-clockwise"
            :label="$t('suppliers.reapply')"
            :loading="reapplying"
            data-testid="supplier-categories-reapply"
            @click="onReapply"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Import fichier -->
    <q-dialog v-model="importDialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ $t('suppliers.import_title', { name: importing?.name }) }}
          </h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="importError" tone="error" dense>{{ importError }}</AppNotice>

          <div v-if="importing?.adapter_key === FEED_ADAPTER_KEY" class="row items-center q-mb-sm">
            <q-btn
              outline
              no-caps
              dense
              icon="ph:cloud-arrow-down"
              :label="$t('suppliers.read_feed')"
              :loading="feedReading"
              data-testid="feed-inspect"
              @click="onReadFeed"
            />
            <span class="text-caption text-muted q-ml-sm">
              {{ $t('suppliers.drop_hint') }}
            </span>
            <q-space />
            <q-btn
              v-if="inspection"
              color="primary"
              unelevated
              no-caps
              dense
              icon="ph:floppy-disk"
              :label="$t('suppliers.save_mapping')"
              :loading="mappingSaving"
              @click="onSaveFeedMapping"
            />
          </div>
          <q-file
            v-model="importFile"
            :label="$t('suppliers.file')"
            accept=".csv,.txt,.xlsx,.xlsm"
            outlined
            dense
            clearable
            @update:model-value="onFileChosen"
          >
            <template #prepend><q-icon name="ph:paperclip" /></template>
          </q-file>

          <template v-if="inspection">
            <div class="text-caption text-muted">
              {{
                $t('suppliers.rows_detected', {
                  n: inspection.total_rows,
                  headers: inspection.headers.join(', '),
                })
              }}
            </div>
            <h3 class="admin-subtitle q-mt-sm q-mb-none">{{ $t('suppliers.mapping') }}</h3>
            <div class="text-caption text-muted q-mb-xs">
              {{ $t('suppliers.mapping_hint') }}
            </div>
            <div class="text-caption text-muted q-mb-xs">
              {{ $t('suppliers.matching_hint') }}
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
            <q-select
              v-model="importDefaultCategory"
              :options="categoryOptions"
              :label="$t('suppliers.file_category')"
              :hint="$t('suppliers.file_category_hint')"
              outlined
              dense
              emit-value
              map-options
              clearable
              class="q-mt-sm"
              data-testid="import-default-category"
            />
            <div class="row q-mt-sm" style="gap: 8px">
              <q-input
                v-model="importMinQuantity"
                :label="$t('suppliers.import_min_qty')"
                :hint="$t('suppliers.import_min_hint')"
                type="number"
                min="0"
                outlined
                dense
                class="col"
                data-testid="import-min-quantity"
              />
              <q-input
                v-model="importMinPrice"
                :label="$t('suppliers.import_min_price')"
                :hint="$t('suppliers.import_min_price_hint')"
                type="number"
                min="0"
                step="any"
                outlined
                dense
                class="col"
                data-testid="import-min-price"
              />
            </div>
            <q-checkbox
              v-model="publishNew"
              dense
              class="q-mt-sm"
              :label="$t('suppliers.publish_new')"
            />
            <div class="text-caption text-muted q-mb-xs">
              {{ $t('suppliers.unchecked_hint') }}
            </div>
            <q-expansion-item dense :label="$t('suppliers.preview')" class="q-mt-sm">
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

          <AppNotice v-if="queuedImport" tone="info" icon="ph:hourglass" dense>
            <q-spinner size="1em" class="q-mr-xs" />
            {{ $t('suppliers.queued', { n: queuedImport.totalRows }) }}
          </AppNotice>

          <AppNotice v-if="importResult" :tone="importResult.dry_run ? 'info' : 'success'" dense>
            <div>
              <strong>{{
                importResult.dry_run ? $t('suppliers.simulation') : $t('suppliers.import_word')
              }}</strong>
              :
              {{
                $t('suppliers.parsed', {
                  parsed: importResult.parsed_products,
                  rejected: importResult.rejected_rows,
                })
              }}
              <span v-if="!importResult.dry_run">
                {{
                  $t('suppliers.stats', {
                    new: importResult.statistics.new_products ?? 0,
                    updated: importResult.statistics.updated_products ?? 0,
                    adopted: importResult.statistics.adopted_products ?? 0,
                    ambiguous: importResult.statistics.ambiguous_products ?? 0,
                    errors: importResult.statistics.errors ?? 0,
                  })
                }}
                <template v-if="belowThresholdLine">— {{ belowThresholdLine }}</template>
                <span v-if="importResult.published_new">{{ $t('suppliers.published_new') }}</span>
                <span v-else>{{ $t('suppliers.hidden_new') }}</span>
              </span>
              <span v-else>
                {{
                  $t('suppliers.resolution', {
                    new: importResult.resolution.new ?? 0,
                    updated: importResult.resolution.updated ?? 0,
                    adopted: importResult.resolution.adopted ?? 0,
                    ambiguous: importResult.resolution.ambiguous ?? 0,
                  })
                }}
                <template v-if="importResult.resolution.filtered">
                  {{ $t('suppliers.filtered', { n: importResult.resolution.filtered }) }}
                </template>
                <template v-if="importResult.resolution.below_threshold">
                  {{ $t('suppliers.below', { n: importResult.resolution.below_threshold }) }}
                </template>
              </span>
            </div>
            <div v-if="importResult.resolution_limited_to" class="text-caption">
              {{ $t('suppliers.limited', { n: importResult.resolution_limited_to }) }}
            </div>
            <div v-if="importResult.dry_run && matchedByLine" class="text-caption">
              {{ $t('suppliers.matched_by', { list: matchedByLine }) }}
            </div>
            <q-expansion-item
              v-if="importResult.sample_resolutions.length"
              dense
              :label="$t('suppliers.first_rows', { n: importResult.sample_resolutions.length })"
              class="q-mt-xs"
            >
              <q-markup-table dense flat bordered>
                <thead>
                  <tr>
                    <th class="text-left">{{ $t('suppliers.h_reference') }}</th>
                    <th class="text-left">{{ $t('suppliers.h_designation') }}</th>
                    <th class="text-left">{{ $t('suppliers.h_action') }}</th>
                    <th class="text-left">{{ $t('suppliers.h_matched') }}</th>
                    <th class="text-left">{{ $t('suppliers.h_existing') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="r in importResult.sample_resolutions"
                    :key="r.supplier_sku + r.action"
                    :class="r.action === 'ambiguous' ? 'text-negative' : ''"
                  >
                    <td class="font-mono">{{ r.supplier_sku }}</td>
                    <td>{{ r.name }}</td>
                    <td>{{ actionLabel(r.action) }}</td>
                    <td>{{ r.match_key ? matchKeyLabel(r.match_key) : '—' }}</td>
                    <td>{{ r.product_name ?? r.message ?? '—' }}</td>
                  </tr>
                </tbody>
              </q-markup-table>
            </q-expansion-item>
            <q-expansion-item
              v-if="importResult.dry_run && importResult.category_pairs?.length"
              dense
              default-opened
              :label="$t('suppliers.file_categories', { n: importResult.category_pairs.length })"
              class="q-mt-xs"
            >
              <CategoryPairsTable
                :pairs="importResult.category_pairs"
                :categories="categories"
                :saving="categoriesSaving"
                :count-label="$t('suppliers.import_rows')"
                @save="saveImportRules"
              />
            </q-expansion-item>
            <ul v-if="importResult.row_errors.length" class="q-mb-none">
              <li v-for="e in importResult.row_errors.slice(0, 10)" :key="e.row_number">
                {{ $t('suppliers.row_error', { n: e.row_number, message: e.message }) }}
              </li>
            </ul>
            <ul v-if="importResult.sync_errors.length" class="q-mb-none">
              <li v-for="e in importResult.sync_errors.slice(0, 10)" :key="e.sku">
                {{ e.sku }} : {{ e.error }}
              </li>
            </ul>
          </AppNotice>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.close')" v-close-popup />
          <q-btn
            outline
            no-caps
            :label="$t('suppliers.simulate')"
            :disable="!importFile || !inspection"
            :loading="importBusy === 'dry'"
            @click="runImport(true)"
          />
          <q-btn
            color="primary"
            unelevated
            no-caps
            :label="$t('suppliers.do_import')"
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
import { useI18n } from 'vue-i18n';
import { labels } from '@/i18n/global';
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import HelpPanel, { type HelpItem } from '@/components/HelpPanel.vue';
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
  type SupplierWithdrawal,
  UNMAPPED_ACTION_LABELS,
  listObservedCategories,
  reapplyCategoryMappings,
  saveCategoryMappings,
  type CategoryMappingWrite,
  type ObservedCategory,
  type UnmappedCategoryAction,
  FEED_ADAPTER_KEY,
  deleteSupplierCredentials,
  inspectSupplierFeed,
  saveSupplierCredentials,
} from '@/api/suppliers';
import { categoryLabel, listAdminCategories, type AdminCategory } from '@/api/categories';
import CategoryPairsTable from '@/components/CategoryPairsTable.vue';
import { useShopConfigStore } from '@/stores/shopConfig';
import { listPlaces, type Place } from '@/api/logistics';
import { extractApiError } from '@/api/errors';
import { useConfirm } from '@/composables/useConfirm';
import { useDialogGuard, useFormSnapshot } from '@/composables/useUnsavedGuard';
import {
  fieldsFromSchema,
  fromFormValue,
  toFormValue,
  type SchemaField,
} from '@/utils/settingsSchema';

const { t } = useI18n();
// Aide : les trois méthodes d'approvisionnement.
const helpItems = computed<HelpItem[]>(() => [
  { title: t('help.suppliers_manual_title'), text: t('help.suppliers_manual'), icon: 'ph:hand' },
  { title: t('help.suppliers_file_title'), text: t('help.suppliers_file'), icon: 'ph:file-csv' },
  {
    title: t('help.suppliers_api_title'),
    text: t('help.suppliers_api'),
    icon: 'ph:plugs-connected',
  },
]);
const { ask } = useConfirm();

const shopConfig = useShopConfigStore();
const rows = ref<Supplier[]>([]);
const adapters = ref<AdapterDescriptor[]>([]);
const places = ref<Place[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const busy = ref<string | null>(null);

const req = [(v: string) => (!!v && v.trim().length > 0) || t('common.required')];
const codeRules = [
  (v: string) => (!!v && /^[a-z0-9][a-z0-9_]{1,49}$/.test(v.trim().toLowerCase())) || 'a-z, 0-9, _',
];

const columns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('suppliers.col_name'), field: 'name', align: 'left' },
  { name: 'code', label: t('suppliers.col_code'), field: 'code', align: 'left' },
  { name: 'kind', label: t('suppliers.col_kind'), field: 'kind', align: 'left' },
  { name: 'origin', label: t('suppliers.col_origin'), field: 'origin_place_id', align: 'left' },
  { name: 'domestic', label: t('suppliers.col_regime'), field: 'is_domestic', align: 'left' },
  { name: 'status', label: t('suppliers.col_state'), field: 'is_active', align: 'left' },
  { name: 'actions', label: '', field: 'code', align: 'right' },
]);

const kindOptions = computed(() =>
  (Object.keys(SUPPLIER_KIND_LABELS) as SupplierKind[]).map((k) => ({
    label: SUPPLIER_KIND_LABELS[k],
    value: k,
  })),
);
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
function kindIcon(kind: SupplierKind): string {
  return kind === 'api' ? 'ph:plugs-connected' : kind === 'file' ? 'ph:file-arrow-up' : 'ph:hand';
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
    error.value = extractApiError(err) ?? t('common.load_failed');
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
  min_quantity: string;
  min_price: string;
  sync_interval_hours: number;
  default_categories: string[];
  unmapped_category_action: UnmappedCategoryAction;
  auto_purchase_order: boolean;
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
    min_quantity: '',
    min_price: '',
    sync_interval_hours: 0,
    default_categories: [],
    unmapped_category_action: 'auto',
    auto_purchase_order: false,
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
// Unsaved edits are not lost on Escape, backdrop or navigation (R9 / T5).
// The feed credentials typed in this dialog count too (saved separately).
const formSnapshot = useFormSnapshot(() => ({ form, credentials }));
const formGuard = useDialogGuard({
  isOpen: () => formDialog.value,
  close: () => (formDialog.value = false),
  isDirty: formSnapshot.isDirty,
});

const selectedAdapter = computed(
  () => adapters.value.find((a) => a.key === form.adapter_key) ?? null,
);

function openCreate() {
  editing.value = null;
  dialogError.value = null;
  Object.assign(form, emptyForm());
  formSnapshot.take();
  formDialog.value = true;
}

function openEdit(supplier: Supplier) {
  editing.value = supplier;
  dialogError.value = null;
  credentials.username = '';
  credentials.password = '';
  const adapter = adapters.value.find((a) => a.key === supplier.adapter_key);
  const fields = fieldsFromSchema(adapter?.settings_schema, SETTING_LABELS);
  const settings: Record<string, string> = {};
  for (const [k, v] of Object.entries(supplier.settings ?? {})) {
    settings[k] = toFormValue(
      fields.find((f) => f.key === k),
      v,
    );
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
    min_quantity: supplier.min_quantity != null ? String(Number(supplier.min_quantity)) : '',
    min_price: supplier.min_price != null ? String(Number(supplier.min_price)) : '',
    sync_interval_hours: supplier.sync_interval_hours,
    default_categories: [...(supplier.default_categories ?? [])],
    unmapped_category_action: supplier.unmapped_category_action ?? 'auto',
    auto_purchase_order: !!supplier.auto_purchase_order,
    price_currency: supplier.price_currency,
    settings,
    contact_email: supplier.contact_email ?? '',
    contact_phone: supplier.contact_phone ?? '',
    notes: supplier.notes ?? '',
  });
  formSnapshot.take();
  formDialog.value = true;
}

/** Champ numérique facultatif : vide → null. */
function optionalNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || String(value).trim() === '') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function buildPayload(): SupplierCreate {
  const settings: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(form.settings)) {
    const value = fromFormValue(
      adapterFields.value.find((f) => f.key === k),
      String(v ?? ''),
    );
    if (value !== undefined) settings[k] = value;
  }
  const categories = form.default_categories.map((c) => c.trim()).filter(Boolean);
  return {
    code: form.code.trim().toLowerCase(),
    name: form.name.trim(),
    kind: form.kind,
    adapter_key: form.kind === 'api' ? form.adapter_key : null,
    origin_place_id: form.origin_place_id,
    is_domestic: form.is_domestic,
    sync_enabled: form.sync_enabled,
    import_as_draft: form.kind !== 'manual' && form.import_as_draft,
    unmapped_category_action: form.unmapped_category_action,
    auto_purchase_order:
      form.kind === 'api' && !!selectedAdapter.value?.supports_purchase_orders
        ? form.auto_purchase_order
        : false,
    min_quantity: optionalNumber(form.min_quantity),
    min_price: optionalNumber(form.min_price),
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
      notice.value = t('suppliers.updated', { name: payload.name });
    } else {
      await createSupplier(payload);
      notice.value = t('suppliers.created', { name: payload.name });
    }
    formDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
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
// Unsaved edits are not lost on Escape, backdrop or navigation (R9 / T5).
const allowlistSnapshot = useFormSnapshot(() => allowlistText.value);
const allowlistGuard = useDialogGuard({
  isOpen: () => allowlistDialog.value,
  close: () => (allowlistDialog.value = false),
  isDirty: allowlistSnapshot.isDirty,
});

async function openAllowlist(supplier: Supplier) {
  allowlistSupplier.value = supplier;
  allowlistError.value = null;
  allowlistView.value = null;
  allowlistText.value = (supplier.sku_allowlist ?? []).join('\n');
  allowlistSnapshot.take();
  allowlistDialog.value = true;
  try {
    allowlistView.value = await getSkuAllowlist(supplier.code);
  } catch (err) {
    allowlistError.value = extractApiError(err) ?? t('suppliers.list_failed');
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
    allowlistSnapshot.take();
    notice.value = view.entries.length
      ? `${supplier.name} : ${view.entries.length} référence(s) suivie(s), ${view.deactivated} article(s) retiré(s) de la vitrine.`
      : `${supplier.name} : liste vidée, tout le catalogue synchronisé est suivi.`;
    await load();
  } catch (err) {
    allowlistError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    allowlistSaving.value = false;
  }
}

const deactivateDialog = ref(false);
const deactivating = ref<Supplier | null>(null);
const deactivateProducts = ref<SupplierWithdrawal>('keep');
const deactivateOptions = computed<{ value: SupplierWithdrawal; label: string }[]>(() => [
  { value: 'keep', label: t('suppliers.w_keep') },
  {
    value: 'zero_stock',
    label: t('suppliers.w_zero'),
  },
  { value: 'hide', label: t('suppliers.w_hide') },
]);

function openDeactivate(supplier: Supplier) {
  deactivating.value = supplier;
  deactivateProducts.value = 'keep';
  deactivateDialog.value = true;
}

async function confirmDeactivate() {
  const supplier = deactivating.value;
  if (!supplier) return;
  busy.value = supplier.code;
  error.value = null;
  try {
    const res = await deactivateSupplier(supplier.code, deactivateProducts.value);
    const withdrawn =
      res.products_withdrawn != null ? t('suppliers.withdrawn', { n: res.products_withdrawn }) : '';
    notice.value = t('suppliers.disabled_msg', { name: supplier.name, withdrawn });
    deactivateDialog.value = false;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('suppliers.disable_failed');
  } finally {
    busy.value = null;
  }
}

async function onReactivate(supplier: Supplier) {
  busy.value = supplier.code;
  error.value = null;
  try {
    await updateSupplier(supplier.code, { is_active: true, sync_enabled: true });
    notice.value =
      supplier.kind === 'api' && !supplier.configured
        ? `${supplier.name} réactivé — ses identifiants manquent encore dans l'environnement.`
        : `${supplier.name} réactivé : les synchronisations reprennent sans redémarrage.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('suppliers.enable_failed');
  } finally {
    busy.value = null;
  }
}

async function onSync(supplier: Supplier) {
  busy.value = supplier.code;
  error.value = null;
  try {
    const res = await triggerProductSync(supplier.code);
    notice.value = `${supplier.name} : ${res.message} (job ${res.job_id}).`;
  } catch (err) {
    error.value = extractApiError(err) ?? t('suppliers.sync_failed');
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
    error.value = extractApiError(err) ?? t('suppliers.test_failed');
  }
}

// --- Import fichier -------------------------------------------------------

// --- Catégories (R4 / S5) ---
const categories = ref<AdminCategory[]>([]);
const categoryOptions = computed(() =>
  categories.value.map((c) => ({ label: categoryLabel(c), value: c.id })),
);
const unmappedOptions = computed(() =>
  (Object.keys(UNMAPPED_ACTION_LABELS) as UnmappedCategoryAction[]).map((value) => ({
    value,
    label: UNMAPPED_ACTION_LABELS[value],
  })),
);

async function loadCategories() {
  try {
    categories.value = (await listAdminCategories()).filter(
      (c) => c.is_active && !c.merged_into_id,
    );
  } catch {
    categories.value = [];
  }
}

const categoriesDialog = ref(false);
const categoriesOf = ref<Supplier | null>(null);
const observed = ref<ObservedCategory[]>([]);
const categoriesLoading = ref(false);
const categoriesSaving = ref(false);
const reapplying = ref(false);
const categoriesError = ref<string | null>(null);
const categoriesNotice = ref<string | null>(null);
const unmappedLabel = computed(() =>
  UNMAPPED_ACTION_LABELS[categoriesOf.value?.unmapped_category_action ?? 'auto'].toLowerCase(),
);

async function refreshObserved() {
  if (!categoriesOf.value) return;
  categoriesLoading.value = true;
  try {
    observed.value = await listObservedCategories(categoriesOf.value.code);
  } catch (err) {
    categoriesError.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    categoriesLoading.value = false;
  }
}

function openCategories(supplier: Supplier) {
  categoriesOf.value = supplier;
  categoriesError.value = null;
  categoriesNotice.value = null;
  observed.value = [];
  categoriesDialog.value = true;
  void loadCategories();
  void refreshObserved();
}

async function saveSupplierRules(rules: CategoryMappingWrite[]) {
  if (!categoriesOf.value) return;
  categoriesSaving.value = true;
  categoriesError.value = null;
  try {
    await saveCategoryMappings(categoriesOf.value.code, rules);
    categoriesNotice.value = `${rules.length} règle(s) enregistrée(s).`;
    await refreshObserved();
  } catch (err) {
    categoriesError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    categoriesSaving.value = false;
  }
}

async function onReapply() {
  if (!categoriesOf.value) return;
  reapplying.value = true;
  categoriesError.value = null;
  try {
    const res = await reapplyCategoryMappings(categoriesOf.value.code);
    categoriesNotice.value = `${res.moved} article(s) rangé(s), ${res.deactivated} retiré(s) de la vitrine.`;
    await refreshObserved();
  } catch (err) {
    categoriesError.value = extractApiError(err) ?? t('suppliers.reapply_failed');
  } finally {
    reapplying.value = false;
  }
}

const importDefaultCategory = ref<string | null>(null);

async function saveImportRules(rules: CategoryMappingWrite[]) {
  if (!importing.value) return;
  categoriesSaving.value = true;
  importError.value = null;
  try {
    await saveCategoryMappings(importing.value.code, rules);
    // The simulation reflects the new rules at once.
    await runImport(true);
  } catch (err) {
    importError.value = extractApiError(err) ?? t('suppliers.rules_failed');
  } finally {
    categoriesSaving.value = false;
  }
}

// --- Fichier en ligne (R4 / S3) ---
const SETTING_LABELS: Record<string, string> = labels({
  feed_url: 'suppliers.s_feed_url',
  auth_mode: 'suppliers.s_auth_mode',
  login_url: 'suppliers.s_login_url',
  username_field: 'suppliers.s_username_field',
  password_field: 'suppliers.s_password_field',
  file_format: 'suppliers.s_file_format',
  sheet_name: 'suppliers.s_sheet_name',
});
const SETTING_CHOICES = computed<Record<string, { label: string; value: string }[]>>(() => ({
  auth_mode: [
    { label: t('suppliers.a_none'), value: 'none' },
    { label: t('suppliers.a_basic'), value: 'basic' },
    { label: t('suppliers.a_form'), value: 'form' },
  ],
  environment: [
    { label: t('suppliers.e_sandbox'), value: 'sandbox' },
    { label: t('suppliers.e_production'), value: 'production' },
  ],
  file_format: [
    { label: t('suppliers.f_auto'), value: 'auto' },
    { label: t('suppliers.f_csv'), value: 'csv' },
    { label: t('suppliers.f_xlsx'), value: 'xlsx' },
  ],
}));
const adapterFields = computed<SchemaField[]>(() =>
  fieldsFromSchema(selectedAdapter.value?.settings_schema, SETTING_LABELS),
);

function choiceOptions(field: SchemaField): { label: string; value: string }[] {
  const named = SETTING_CHOICES.value[field.key] ?? [];
  return (field.choices ?? []).map(
    (value) => named.find((c) => c.value === value) ?? { label: value, value },
  );
}

function fieldHint(field: SchemaField): string | undefined {
  if (field.kind === 'list') {
    return `${field.hint} Valeurs séparées par des virgules ; « [] » = toutes.`.trim();
  }
  if (field.kind === 'json') return `${field.hint} Format JSON.`.trim();
  return field.hint || undefined;
}

const isFeedForm = computed(() => form.kind === 'api' && form.adapter_key === FEED_ADAPTER_KEY);
const credentials = reactive({ username: '', password: '' });
const credentialsBusy = ref(false);

async function onSaveCredentials() {
  if (!editing.value) return;
  credentialsBusy.value = true;
  dialogError.value = null;
  try {
    editing.value = await saveSupplierCredentials(editing.value.code, { ...credentials });
    credentials.username = '';
    credentials.password = '';
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('suppliers.creds_failed');
  } finally {
    credentialsBusy.value = false;
  }
}

async function onClearCredentials() {
  if (!editing.value) return;
  if (!(await ask({ title: t('suppliers.clear_q'), okLabel: t('suppliers.clear') }))) return;
  credentialsBusy.value = true;
  dialogError.value = null;
  try {
    editing.value = await deleteSupplierCredentials(editing.value.code);
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.delete_failed');
  } finally {
    credentialsBusy.value = false;
  }
}

const importDialog = ref(false);
const importing = ref<Supplier | null>(null);
const importFile = ref<File | null>(null);
const inspection = ref<FileInspectResponse | null>(null);
const importResult = ref<FileImportResponse | null>(null);
const publishNew = ref(true);
const importMinQuantity = ref<string>('');
const importMinPrice = ref<string>('');

const belowThresholdLine = computed(() => {
  const stats = importResult.value?.statistics ?? {};
  const skipped = stats.below_threshold_skipped ?? 0;
  const hidden = stats.below_threshold_deactivated ?? 0;
  if (!skipped && !hidden) return '';
  return t('suppliers.below_line', { skipped, hidden });
});
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
      importError.value = status.error_message ?? t('suppliers.import_failed');
      return;
    }
    importResult.value = statusToResult(status, current.code);
    notice.value = t('suppliers.import_done', {
      file: status.filename ?? '',
      status: status.status,
    });
    await load();
  } catch (err) {
    stopPolling();
    importError.value = extractApiError(err) ?? t('suppliers.follow_failed');
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
  importMinQuantity.value =
    supplier.min_quantity != null ? String(Number(supplier.min_quantity)) : '';
  importMinPrice.value = supplier.min_price != null ? String(Number(supplier.min_price)) : '';
  importDefaultCategory.value = null;
  void loadCategories();
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
    applyInspection(await inspectCatalogFile(importing.value.code, file));
  } catch (err) {
    importError.value = extractApiError(err) ?? t('suppliers.read_failed');
  }
}

const feedReading = ref(false);
const mappingSaving = ref(false);

async function onReadFeed() {
  if (!importing.value) return;
  feedReading.value = true;
  importError.value = null;
  importResult.value = null;
  try {
    applyInspection(await inspectSupplierFeed(importing.value.code));
    notice.value = null;
  } catch (err) {
    importError.value = extractApiError(err) ?? t('suppliers.feed_failed');
  } finally {
    feedReading.value = false;
  }
}

async function onSaveFeedMapping() {
  if (!importing.value) return;
  mappingSaving.value = true;
  importError.value = null;
  try {
    const saved = await updateSupplier(importing.value.code, {
      column_mapping: currentMapping(),
    });
    importing.value = saved;
    notice.value = t('suppliers.mapping_saved', { name: saved.name });
    importDialog.value = false;
    await load();
  } catch (err) {
    importError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    mappingSaving.value = false;
  }
}

function applyInspection(result: FileInspectResponse) {
  inspection.value = result;
  {
    // Drop stored mappings that point at columns the file does not have.
    for (const [k, v] of Object.entries(mapping)) {
      if (v && !result.headers.includes(v)) mapping[k] = null;
    }
    // Pre-fill obvious matches when nothing is mapped yet.
    for (const target of result.mapping_targets) {
      if (mapping[target]) continue;
      const hit = result.headers.find((h) => h.trim().toLowerCase() === target.toLowerCase());
      if (hit) mapping[target] = hit;
    }
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
      minQuantity: optionalNumber(importMinQuantity.value),
      minPrice: optionalNumber(importMinPrice.value),
      defaultCategoryId: importDefaultCategory.value,
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
      notice.value = t('suppliers.import_done_for', {
        file: result.filename,
        name: importing.value.name,
      });
      await load();
    }
  } catch (err) {
    importError.value = extractApiError(err) ?? t('suppliers.import_impossible');
  } finally {
    importBusy.value = null;
  }
}

onMounted(load);
</script>
