<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('departures.title')">
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
          :label="$t('departures.new')"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <HelpPanel
      :title="$t('help.departures_title')"
      :items="helpItems"
      steps
      storage-key="departures"
    >
      {{ $t('help.departures_reminders') }}
    </HelpPanel>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <section class="app-section">
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
            <StatusTag
              :label="departureStatusLabel(props.row.status)"
              :tone="departureTone(props.row.status)"
              :icon="toneIcon(departureTone(props.row.status))"
            />
            <q-icon v-if="props.row.is_published" name="ph:eye" class="text-muted q-ml-sm">
              <q-tooltip>{{ $t('departures.published_text') }}</q-tooltip>
            </q-icon>
          </q-td>
        </template>
        <template #body-cell-orders="props">
          <q-td :props="props" class="font-mono">
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
              icon="ph:skip-forward"
              :label="departureStatusLabel(nextDepartureStatus(props.row.status) ?? '')"
              @click.stop="advance(props.row)"
            >
              <q-tooltip>{{ $t('departures.next_step') }}</q-tooltip>
            </q-btn>
            <q-btn flat round dense icon="ph:pencil-simple" @click.stop="openEdit(props.row)">
              <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
            </q-btn>
            <q-btn
              flat
              round
              dense
              color="negative"
              icon="ph:trash"
              :disable="props.row.orders_count > 0"
              @click.stop="remove(props.row)"
            >
              <q-tooltip>
                {{
                  props.row.orders_count > 0 ? $t('departures.move_first') : $t('departures.delete')
                }}
              </q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">
            {{ $t('departures.none') }}
          </div>
        </template>
      </q-table>
    </section>

    <!-- Orders of the selected departure -->
    <section v-if="selected" class="app-section" aria-labelledby="departure-detail-title">
      <div class="app-section__head">
        <h2 id="departure-detail-title" class="app-section__title">
          {{ $t('departures.orders_of', { name: selected.name }) }}
        </h2>
        <p class="app-section__hint">{{ cutoffLabel(selected) }}</p>
        <div class="app-section__action detail-actions">
          <q-btn
            flat
            no-caps
            icon="ph:download-simple"
            :label="$t('departures.orders_csv')"
            @click="downloadOrdersCsv(filters)"
          />
          <q-btn
            flat
            no-caps
            icon="ph:download-simple"
            :label="$t('departures.po_csv')"
            @click="downloadSkuSummaryCsv(filters)"
          />
          <q-btn
            v-if="selected.status === 'open' || selected.status === 'draft'"
            color="primary"
            unelevated
            no-caps
            icon="ph:lock"
            :label="$t('departures.close')"
            :loading="closing"
            @click="closeSelected(false)"
          >
            <q-tooltip>
              {{ $t('departures.close_tip') }}
            </q-tooltip>
          </q-btn>
        </div>
      </div>

      <div class="detail-block">
        <q-table
          v-model:selected="selectedOrders"
          :rows="orders"
          :columns="orderColumns"
          row-key="order_id"
          selection="multiple"
          :loading="ordersLoading"
          flat
          bordered
          dense
          :rows-per-page-options="[0]"
          hide-pagination
        >
          <template #top>
            <div class="admin-toolbar full-width q-mb-none">
              <q-select
                v-model="moveTarget"
                :options="moveOptions"
                :label="$t('departures.move_to')"
                dense
                outlined
                emit-value
                map-options
                style="min-width: 260px"
              />
              <q-btn
                outline
                no-caps
                :label="$t('departures.move')"
                :disable="selectedOrders.length === 0 || moveTarget === undefined"
                @click="moveSelected"
              />
              <q-toggle v-model="showUnassigned" :label="$t('departures.without')" dense />
            </div>
          </template>
          <template #body-cell-number="props">
            <q-td :props="props">
              <router-link
                :to="`/orders/${props.row.order_id}`"
                class="admin-link font-mono"
                :title="props.row.order_id"
                >{{ props.value }}</router-link
              >
            </q-td>
          </template>
          <template #body-cell-status="props">
            <q-td :props="props">
              <StatusTag
                :label="orderStatusLabel(props.row.status)"
                :tone="toneOf(orderStatusColor(props.row.status))"
                :icon="toneIcon(toneOf(orderStatusColor(props.row.status)))"
              />
            </q-td>
          </template>
          <template #body-cell-total="props">
            <q-td :props="props" class="font-mono">{{ props.value }}</q-td>
          </template>
          <template #body-cell-actions="props">
            <q-td :props="props" align="right">
              <q-btn flat round dense icon="ph:arrow-right" :to="`/orders/${props.row.order_id}`">
                <q-tooltip>{{ $t('departures.open_order') }}</q-tooltip>
              </q-btn>
            </q-td>
          </template>
          <template #no-data>
            <div class="full-width text-center text-subtle q-pa-md">
              {{ $t('departures.no_orders') }}
            </div>
          </template>
        </q-table>
      </div>

      <div v-if="!showUnassigned" class="detail-block">
        <h3 class="admin-subtitle">{{ $t('departures.po_title') }}</h3>
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
            <div class="full-width text-center text-subtle q-pa-md">
              {{ $t('departures.no_line') }}
            </div>
          </template>
        </q-table>
      </div>

      <!-- Real purchase orders placed with the suppliers -->
      <div v-if="!showUnassigned" class="detail-block">
        <div class="detail-head">
          <h3 class="admin-subtitle">{{ $t('departures.pos') }}</h3>
          <q-btn
            flat
            dense
            no-caps
            icon="ph:plus"
            :label="$t('departures.add_po')"
            @click="poDialog = true"
          />
        </div>
        <q-list
          v-if="selected.supplier_orders?.length"
          dense
          bordered
          separator
          class="rounded-borders"
        >
          <q-item v-for="(po, i) in selected.supplier_orders" :key="i">
            <q-item-section>
              <q-item-label>
                {{ po.supplier_name }} — n° <span class="font-mono">{{ po.order_number }}</span>
                <span class="text-muted">· {{ formatDate(po.ordered_at) }}</span>
              </q-item-label>
              <q-item-label caption>
                <span class="font-mono">{{ po.total_amount }} {{ po.currency }}</span
                ><template v-if="po.notes"> · {{ po.notes }}</template>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn flat round dense color="negative" icon="ph:trash" @click="removePo(i)">
                <q-tooltip>{{ $t('departures.delete_text') }}</q-tooltip>
              </q-btn>
            </q-item-section>
          </q-item>
        </q-list>
        <p v-else class="text-caption text-subtle q-mb-none">
          {{ $t('departures.no_po') }}
        </p>
      </div>

      <!-- Goods receipt: tally per product, orders reconciliation -->
      <div v-if="!showUnassigned" class="detail-block">
        <div class="detail-head">
          <h3 class="admin-subtitle">{{ $t('departures.reception') }}</h3>
          <span v-if="reception" class="text-caption text-muted">
            {{ $t('departures.expected') }}
            <span class="font-mono">{{ reception.expected_units }}</span> ·
            {{ $t('departures.received_s') }}
            <span class="font-mono">{{ reception.received_units }}</span> ·
            {{ $t('departures.damaged_s') }}
            <span class="font-mono">{{ reception.damaged_units }}</span> ·
            <span :class="reception.missing_units ? 'text-warning' : 'text-positive'"
              >{{ $t('departures.missing_s') }}
              <span class="font-mono">{{ reception.missing_units }}</span></span
            >
          </span>
        </div>
        <q-table
          :rows="reception?.lines ?? []"
          :columns="receiptColumns"
          row-key="product_id"
          :loading="receptionLoading"
          flat
          dense
          bordered
          :rows-per-page-options="[0]"
          hide-pagination
        >
          <template #body-cell-received="props">
            <q-td :props="props">
              <q-input
                v-model.number="receiptEdit(props.row).quantity_received"
                type="number"
                min="0"
                dense
                outlined
                style="width: 80px"
              />
            </q-td>
          </template>
          <template #body-cell-damaged="props">
            <q-td :props="props">
              <q-input
                v-model.number="receiptEdit(props.row).quantity_damaged"
                type="number"
                min="0"
                dense
                outlined
                style="width: 80px"
              />
            </q-td>
          </template>
          <template #body-cell-serials="props">
            <q-td :props="props">
              <q-input
                v-model="receiptEdit(props.row).serials"
                dense
                outlined
                autogrow
                :placeholder="$t('departures.serials')"
                style="min-width: 220px"
              />
            </q-td>
          </template>
          <template #body-cell-missing="props">
            <q-td
              :props="props"
              class="font-mono"
              :class="missingOf(props.row) ? 'text-warning' : 'text-positive'"
            >
              {{ missingOf(props.row) }}
            </q-td>
          </template>
          <template #body-cell-actions="props">
            <q-td :props="props" align="right">
              <q-btn
                color="primary"
                unelevated
                dense
                no-caps
                :label="$t('common.save')"
                :loading="savingReceipt === props.row.product_id"
                @click="saveReceipt(props.row)"
              >
                <q-tooltip>{{ $t('departures.checkin_tip') }}</q-tooltip>
              </q-btn>
            </q-td>
          </template>
          <template #no-data>
            <div class="full-width text-center text-subtle q-pa-md">
              {{ $t('departures.no_expected') }}
            </div>
          </template>
        </q-table>
        <div v-if="reception?.orders.length" class="q-mt-md">
          <div class="text-caption text-muted q-mb-xs">
            {{ $t('departures.matching') }}
          </div>
          <div class="fulfilment-list">
            <router-link
              v-for="o in reception.orders"
              :key="o.order_id"
              :to="`/orders/${o.order_id}`"
              class="fulfilment-link"
            >
              <StatusTag
                :label="
                  $t('departures.order_chip', {
                    number: o.order_number ?? o.order_id.slice(0, 8),
                    fulfilment: fulfilmentLabel(o.fulfilment),
                  })
                "
                :tone="toneOf(fulfilmentColor(o.fulfilment))"
                :icon="toneIcon(toneOf(fulfilmentColor(o.fulfilment)))"
              />
              <q-tooltip>
                <div v-for="ln in o.lines" :key="ln.product_id">
                  {{ ln.product_name }} : {{ ln.allocated }}/{{ ln.quantity }}
                  <template v-if="ln.serial_numbers.length">
                    ({{ ln.serial_numbers.join(', ') }})</template
                  >
                </div>
              </q-tooltip>
            </router-link>
          </div>
        </div>
      </div>

      <!-- Margin dashboard -->
      <div v-if="!showUnassigned && board" class="detail-block">
        <h3 class="admin-subtitle">{{ $t('departures.board') }}</h3>
        <div class="kpi-grid">
          <div v-for="tile in tiles" :key="tile.label" class="kpi">
            <span class="kpi__label">{{ tile.label }}</span>
            <span class="kpi__value font-mono" :class="tile.cls">{{ tile.value }}</span>
            <span v-if="tile.hint" class="kpi__hint">{{ tile.hint }}</span>
          </div>
        </div>
        <AppNotice v-if="board.unconverted_currencies.length" tone="warning" dense class="q-mt-md">
          {{
            $t('departures.unconverted', { currencies: board.unconverted_currencies.join(', ') })
          }}
        </AppNotice>
        <div class="admin-toolbar q-mt-md q-mb-none">
          <q-input
            v-model="costs.freight_cost"
            type="number"
            step="1"
            min="0"
            :label="$t('departures.freight', { currency: shopConfig.currency })"
            outlined
            dense
          />
          <q-input
            v-model="costs.customs_cost"
            type="number"
            step="1"
            min="0"
            :label="$t('departures.customs', { currency: shopConfig.currency })"
            outlined
            dense
          />
          <q-input
            v-model="costs.other_costs"
            type="number"
            step="1"
            min="0"
            :label="$t('departures.other', { currency: shopConfig.currency })"
            outlined
            dense
          />
          <q-btn
            color="primary"
            unelevated
            no-caps
            :label="$t('departures.save_costs')"
            :loading="saving"
            @click="saveCosts"
          />
        </div>
      </div>

      <!-- Social reminders -->
      <div v-if="!showUnassigned" class="detail-block">
        <div class="detail-head">
          <h3 class="admin-subtitle">{{ $t('departures.reminders') }}</h3>
          <q-btn
            flat
            dense
            no-caps
            icon="ph:plus"
            :label="$t('departures.add_reminder')"
            @click="openReminder()"
          />
        </div>
        <q-input
          v-model="webhookUrl"
          :label="$t('departures.webhook')"
          hint="https uniquement. Réglage global, commun à tous les départs."
          outlined
          dense
          class="q-mb-md"
          @blur="saveWebhook"
        >
          <template #append><q-icon name="ph:webhooks-logo" /></template>
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
              <StatusTag
                :label="reminderLabel(props.row.status)"
                :tone="toneOf(reminderColor(props.row.status))"
                :icon="toneIcon(toneOf(reminderColor(props.row.status)))"
              />
              <span v-if="props.row.error" class="text-caption text-negative q-ml-xs">
                {{ props.row.error }}
              </span>
            </q-td>
          </template>
          <template #body-cell-actions="props">
            <q-td :props="props" align="right">
              <q-btn flat round dense icon="ph:paper-plane-tilt" @click="publishNow(props.row)">
                <q-tooltip>{{ $t('departures.publish_now') }}</q-tooltip>
              </q-btn>
              <q-btn
                v-if="props.row.status !== 'sent'"
                flat
                round
                dense
                icon="ph:pencil-simple"
                @click="openReminder(props.row)"
              >
                <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
              </q-btn>
              <q-btn
                flat
                round
                dense
                color="negative"
                icon="ph:trash"
                @click="removeReminder(props.row)"
              >
                <q-tooltip>{{ $t('departures.delete_text') }}</q-tooltip>
              </q-btn>
            </q-td>
          </template>
          <template #no-data>
            <div class="full-width text-center text-subtle q-pa-md">
              {{ $t('departures.no_reminder') }}
            </div>
          </template>
        </q-table>
      </div>
    </section>

    <!-- Close result: what is left to arbitrate -->
    <q-dialog v-model="closeDialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ closeResult?.closed ? $t('departures.closed') : $t('departures.not_closed') }}
          </h2>
          <p v-if="closeResult" class="app-dialog__text">
            {{ $t('departures.paid_orders', { n: closeResult.orders_count }) }}
            <span class="font-mono">{{ formatMoney(Number(closeResult.orders_total)) }}</span>
          </p>
        </q-card-section>
        <q-card-section v-if="closeResult">
          <div
            v-if="!closeResult.threshold_reached || closeResult.unpaid_order_ids.length"
            class="admin-notices"
          >
            <AppNotice v-if="!closeResult.threshold_reached" tone="warning" dense>
              {{ $t('departures.threshold_missed') }}
            </AppNotice>
            <AppNotice v-if="closeResult.unpaid_order_ids.length" tone="info" dense>
              {{ $t('departures.unpaid_left', { n: closeResult.unpaid_order_ids.length }) }}
            </AppNotice>
          </div>
          <template v-if="closeResult.shortages.length">
            <h3 class="admin-subtitle">{{ $t('departures.shortages') }}</h3>
            <q-list dense bordered separator class="rounded-borders">
              <q-item v-for="s in closeResult.shortages" :key="s.product_id">
                <q-item-section>
                  <q-item-label
                    >{{ s.product_name }} (<span class="font-mono">{{ s.supplier_sku }}</span
                    >)</q-item-label
                  >
                  <q-item-label caption>
                    {{
                      $t('departures.shortage', {
                        ordered: s.ordered_quantity,
                        available: s.available_quantity,
                        orders: s.order_numbers.filter(Boolean).join(', ') || s.order_ids.length,
                      })
                    }}
                  </q-item-label>
                </q-item-section>
                <q-item-section side>
                  <q-btn
                    flat
                    dense
                    no-caps
                    :label="$t('departures.mark_shortage')"
                    @click="markBackordered(s.order_ids)"
                  >
                    <q-tooltip>{{ $t('departures.shortage_tip') }}</q-tooltip>
                  </q-btn>
                </q-item-section>
              </q-item>
            </q-list>
          </template>
          <div v-else class="text-positive">{{ $t('departures.stock_ok') }}</div>
          <div v-if="closeResult.next_departure_id" class="text-caption text-muted q-mt-sm">
            {{ $t('departures.next_created') }}
          </div>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn
            v-if="closeResult && !closeResult.closed"
            flat
            no-caps
            color="negative"
            :label="$t('departures.force_close')"
            @click="closeSelected(true)"
          />
          <q-btn flat no-caps :label="$t('common.close')" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Supplier purchase order -->
    <q-dialog v-model="poDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('departures.po_dialog') }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitPo">
          <q-card-section class="q-gutter-sm">
            <q-input
              v-model="poForm.supplier_name"
              :label="$t('departures.supplier')"
              outlined
              dense
              :rules="[(v: string) => !!v.trim() || $t('common.required')]"
            />
            <q-input
              v-model="poForm.order_number"
              :label="$t('departures.po_number')"
              outlined
              dense
              :rules="[(v: string) => !!v.trim() || $t('common.required')]"
            />
            <q-input
              v-model="poForm.ordered_at"
              type="date"
              :label="$t('departures.date')"
              outlined
              dense
              :rules="[(v: string) => !!v || $t('common.required')]"
            />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="poForm.total_amount"
                class="col-8"
                type="number"
                step="0.01"
                min="0"
                :label="$t('departures.paid')"
                outlined
                dense
              />
              <q-input
                v-model="poForm.currency"
                class="col-4"
                :label="$t('departures.currency')"
                outlined
                dense
              />
            </div>
            <q-input v-model="poForm.notes" :label="$t('departures.notes')" outlined dense />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
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

    <!-- Reminder -->
    <q-dialog v-model="reminderDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ reminderEditId ? $t('departures.edit_reminder') : $t('departures.new_reminder') }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submitReminder">
          <q-card-section class="q-gutter-sm">
            <div class="row q-col-gutter-sm">
              <q-input
                v-model.number="reminderForm.offset_days"
                class="col-6"
                type="number"
                min="0"
                :label="$t('departures.days_before')"
                outlined
                dense
              />
              <q-select
                v-model="reminderForm.anchor"
                class="col-6"
                :options="[
                  { label: $t('departures.anchor_cutoff'), value: 'cutoff' },
                  { label: $t('departures.anchor_departure'), value: 'departure' },
                ]"
                :label="$t('departures.before')"
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
              :label="$t('departures.message')"
              :hint="$t('departures.variables')"
              outlined
              dense
              :rules="[(v: string) => !!v.trim() || $t('common.required')]"
            />
            <q-input
              v-model="reminderForm.image_url"
              :label="$t('departures.image')"
              outlined
              dense
              clearable
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
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

    <!-- Create / edit -->
    <q-dialog v-model="dialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editId ? $t('departures.edit_title') : $t('departures.new_title') }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.name"
              :label="$t('departures.name')"
              outlined
              dense
              autofocus
              :rules="[(v: string) => !!v.trim() || $t('departures.name_rule')]"
            />
            <q-input
              v-model="form.order_cutoff_at"
              type="datetime-local"
              :label="$t('departures.cutoff')"
              :hint="$t('departures.cutoff_hint')"
              outlined
              dense
              :rules="[(v: string) => !!v || $t('departures.date_rule')]"
            />
            <q-input
              v-model="form.estimated_delivery_at"
              type="date"
              :label="$t('departures.delivery')"
              outlined
              dense
              clearable
            />
            <q-input
              v-model="form.departure_at"
              type="date"
              :label="$t('departures.physical')"
              outlined
              dense
              clearable
            />
            <q-select
              v-model="form.status"
              :options="statusOptions"
              :label="$t('common.status')"
              outlined
              dense
              emit-value
              map-options
            />
            <q-toggle v-model="form.is_published" :label="$t('departures.published')" />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model.number="form.min_amount"
                class="col"
                type="number"
                :label="$t('departures.threshold_amount', { currency: shopConfig.currency })"
                outlined
                dense
                clearable
              />
              <q-input
                v-model.number="form.min_units"
                class="col"
                type="number"
                :label="$t('departures.threshold_units')"
                outlined
                dense
                clearable
              />
              <q-input
                v-model.number="form.recurrence_days"
                class="col"
                type="number"
                :label="$t('departures.recurrence')"
                outlined
                dense
                clearable
              />
            </div>
            <q-input
              v-model="form.notes"
              type="textarea"
              :label="$t('departures.notes')"
              outlined
              dense
              autogrow
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
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
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { labels } from '@/i18n/global';
import { computed, onMounted, reactive, ref, watch } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, toneOf, type StatusTone } from '@app/ui/statusTone';
import {
  DEPARTURE_STATUSES,
  departureCutoffLabel,
  formatDate,
  formatDateTime,
  formatMoney as formatMoneyIn,
  nextDepartureStatus,
} from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import HelpPanel, { type HelpItem } from '@/components/HelpPanel.vue';
import {
  addSupplierOrder,
  assignOrders,
  closeDeparture,
  createDeparture,
  createReminder,
  deleteDeparture,
  deleteReminder,
  FULFILMENT_LABELS,
  getDashboard,
  getReception,
  listDepartures,
  listReminders,
  publishReminder,
  removeSupplierOrder,
  saveReceiptLine,
  updateDeparture,
  updateReminder,
  type CloseResult,
  type Departure,
  type DepartureDashboard,
  type DepartureWrite,
  type ReceiptLine,
  type ReceiptReport,
  type Reminder,
} from '@/api/departures';
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
} from '@/api/orders';
import { extractApiError } from '@/api/errors';
import { useConfirm } from '@/composables/useConfirm';
import { listSystemSettings, updateSystemSetting } from '@/api/systemSettings';
import { useShopConfigStore } from '@/stores/shopConfig';
import { setOrderStatus } from '@/api/orders';

const { t } = useI18n();
// Aide : le cycle d'un départ et ce que chaque étape déclenche.
const helpItems = computed<HelpItem[]>(() => [
  { title: t('help.departures_open_title'), text: t('help.departures_open') },
  { title: t('help.departures_close_title'), text: t('help.departures_close') },
  { title: t('help.departures_ordered_title'), text: t('help.departures_ordered') },
  { title: t('help.departures_transit_title'), text: t('help.departures_transit') },
  { title: t('help.departures_distributed_title'), text: t('help.departures_distributed') },
]);
const { confirmDelete } = useConfirm();
const departureStatusLabel = (status: string) => t(`departure_status.${status}`);

const departures = ref<Departure[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const shopConfig = useShopConfigStore();
const formatMoney = (n: number) =>
  Number.isFinite(n) ? formatMoneyIn(n, shopConfig.currency) : String(n);
const cutoffLabel = (d: Departure) => departureCutoffLabel(d);
const departureTone = (status: string): StatusTone => (status === 'open' ? 'ok' : 'neutral');

const columns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('departures.col_departure'), field: 'name', align: 'left' },
  {
    name: 'cutoff',
    label: t('departures.col_cutoff'),
    field: 'order_cutoff_at',
    align: 'left',
    format: (v: string) => formatDate(v),
  },
  {
    name: 'delivery',
    label: t('departures.col_delivery'),
    field: 'estimated_delivery_at',
    align: 'left',
    format: (v: string | null) => formatDate(v),
  },
  { name: 'status', label: t('departures.col_status'), field: 'status', align: 'left' },
  { name: 'orders', label: t('departures.col_orders'), field: 'orders_count', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    departures.value = await listDepartures();
    if (selected.value) {
      selected.value = departures.value.find((d) => d.id === selected.value?.id) ?? null;
    }
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
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
  { label: t('departures.detach'), value: null },
]);

const orderColumns = computed<QTableColumn[]>(() => [
  {
    name: 'number',
    label: t('departures.col_order'),
    field: (r: AdminOrderListItem) => r.order_number ?? `#${r.order_id.slice(0, 8)}`,
    align: 'left',
  },
  {
    name: 'date',
    label: t('departures.col_date'),
    field: 'created_at',
    align: 'left',
    format: (v: string | null) => formatDate(v),
  },
  {
    name: 'client',
    label: t('departures.col_customer'),
    field: (r: AdminOrderListItem) => r.user_name || r.user_email || '',
    align: 'left',
  },
  { name: 'status', label: t('departures.col_status'), field: 'status', align: 'left' },
  {
    name: 'total',
    label: t('departures.col_total'),
    field: 'total_amount',
    align: 'right',
    format: (v: number) => formatMoney(v),
  },
  { name: 'actions', label: '', field: 'order_id', align: 'right' },
]);

const skuColumns = computed<QTableColumn[]>(() => [
  { name: 'supplier', label: t('departures.col_supplier'), field: 'supplier_name', align: 'left' },
  {
    name: 'sku',
    label: t('departures.col_sku'),
    field: 'supplier_sku',
    align: 'left',
    classes: 'font-mono',
  },
  { name: 'product', label: t('departures.col_product'), field: 'product_name', align: 'left' },
  {
    name: 'qty',
    label: t('departures.col_qty'),
    field: 'quantity',
    align: 'right',
    classes: 'font-mono',
  },
  {
    name: 'orders',
    label: t('departures.col_n_orders'),
    field: 'orders_count',
    align: 'right',
    classes: 'font-mono',
  },
  {
    name: 'cost',
    label: t('departures.col_unit_cost'),
    field: (r: SkuSummaryRow) =>
      r.unit_cost === null ? '—' : `${r.unit_cost} ${r.cost_currency ?? ''}`,
    align: 'right',
    classes: 'font-mono',
  },
  {
    name: 'weight',
    label: t('departures.col_weight'),
    field: (r: SkuSummaryRow) => r.total_weight_kg ?? '—',
    align: 'right',
    classes: 'font-mono',
  },
]);

function select(row: Departure) {
  selected.value = row;
  showUnassigned.value = false;
  void loadReminders();
  void loadReception();
  void loadDashboard();
}

// --- Goods receipt (Lot C) ---
const reception = ref<ReceiptReport | null>(null);
const receptionLoading = ref(false);
const savingReceipt = ref<string | null>(null);
interface ReceiptEdit {
  quantity_received: number;
  quantity_damaged: number;
  serials: string;
}
const receiptEdits = reactive<Record<string, ReceiptEdit>>({});

const receiptColumns = computed<QTableColumn[]>(() => [
  {
    name: 'product',
    label: t('departures.col_item'),
    field: (r: ReceiptLine) => `${r.supplier_sku ?? '—'} · ${r.product_name}`,
    align: 'left',
  },
  {
    name: 'expected',
    label: t('departures.col_expected'),
    field: 'expected_quantity',
    align: 'right',
    classes: 'font-mono',
  },
  {
    name: 'received',
    label: t('departures.col_received'),
    field: 'quantity_received',
    align: 'right',
  },
  {
    name: 'damaged',
    label: t('departures.col_damaged'),
    field: 'quantity_damaged',
    align: 'right',
  },
  {
    name: 'missing',
    label: t('departures.col_missing'),
    field: 'expected_quantity',
    align: 'right',
  },
  { name: 'serials', label: t('departures.col_serials'), field: 'serial_numbers', align: 'left' },
  { name: 'actions', label: '', field: 'product_id', align: 'right' },
]);

/** Editable copy of a tally row (created on first access). */
function receiptEdit(row: ReceiptLine): ReceiptEdit {
  const existing = receiptEdits[row.product_id];
  if (existing) return existing;
  receiptEdits[row.product_id] = {
    quantity_received: row.quantity_received,
    quantity_damaged: row.quantity_damaged,
    serials: row.serial_numbers.join(', '),
  };
  return receiptEdits[row.product_id] as ReceiptEdit;
}

function missingOf(row: ReceiptLine): number {
  const edit = receiptEdit(row);
  return Math.max(
    0,
    row.expected_quantity - (Number(edit.quantity_received) - Number(edit.quantity_damaged)),
  );
}

const fulfilmentLabel = (s: string) => FULFILMENT_LABELS[s] ?? s;
const fulfilmentColor = (s: string) =>
  s === 'served' ? 'green' : s === 'partial' ? 'orange-8' : 'grey-7';

function applyReception(report: ReceiptReport) {
  reception.value = report;
  for (const key of Object.keys(receiptEdits)) delete receiptEdits[key];
}

async function loadReception() {
  if (!selected.value) return;
  receptionLoading.value = true;
  try {
    applyReception(await getReception(selected.value.id));
  } catch (err) {
    error.value = extractApiError(err) ?? t('departures.reception_failed');
  } finally {
    receptionLoading.value = false;
  }
}

async function saveReceipt(row: ReceiptLine) {
  if (!selected.value) return;
  const edit = receiptEdit(row);
  savingReceipt.value = row.product_id;
  error.value = null;
  try {
    applyReception(
      await saveReceiptLine(selected.value.id, row.product_id, {
        quantity_received: Number(edit.quantity_received) || 0,
        quantity_damaged: Number(edit.quantity_damaged) || 0,
        serial_numbers: edit.serials
          .split(/[,;\n]/)
          .map((s) => s.trim())
          .filter(Boolean),
        notes: row.notes,
      }),
    );
    notice.value = t('departures.checked_in', { name: row.product_name });
    void loadDashboard();
  } catch (err) {
    error.value = extractApiError(err) ?? t('departures.checkin_failed');
  } finally {
    savingReceipt.value = null;
  }
}

// --- Margin dashboard (Lot C) ---
const board = ref<DepartureDashboard | null>(null);
const costs = reactive({ freight_cost: '', customs_cost: '', other_costs: '' });

const tiles = computed(() => {
  const b = board.value;
  if (!b) return [];
  const n = (v: string | number | null) => Number(v ?? 0);
  const fees = n(b.freight_cost) + n(b.customs_cost) + n(b.other_costs);
  const margin = n(b.gross_margin);
  return [
    {
      label: t('departures.t_revenue', { orders: b.orders_count, units: b.units }),
      value: formatMoney(n(b.revenue)),
      cls: '',
      hint: '',
    },
    {
      label: t('departures.t_collected'),
      value: formatMoney(n(b.collected)),
      cls: '',
      hint: '',
    },
    {
      label:
        b.goods_cost_source === 'supplier_orders'
          ? t('departures.t_supplier_paid')
          : t('departures.t_goods_est'),
      value: formatMoney(
        b.goods_cost_source === 'supplier_orders' ? n(b.supplier_paid) : n(b.goods_cost_estimated),
      ),
      cls: '',
      hint:
        b.goods_cost_source === 'supplier_orders'
          ? t('departures.t_estimated', { amount: formatMoney(n(b.goods_cost_estimated)) })
          : t('departures.t_record_po'),
    },
    { label: t('departures.t_fees'), value: formatMoney(fees), cls: '', hint: '' },
    {
      label: t('departures.t_margin'),
      value: formatMoney(margin),
      cls: margin < 0 ? 'text-negative' : 'text-positive',
      hint: b.margin_rate_pct === null ? '' : t('departures.t_pct', { pct: b.margin_rate_pct }),
    },
  ];
});

async function loadDashboard() {
  if (!selected.value) return;
  try {
    board.value = await getDashboard(selected.value.id);
    Object.assign(costs, {
      freight_cost: selected.value.freight_cost ?? '',
      customs_cost: selected.value.customs_cost ?? '',
      other_costs: selected.value.other_costs ?? '',
    });
  } catch (err) {
    error.value = extractApiError(err) ?? t('departures.board_failed');
  }
}

async function saveCosts() {
  if (!selected.value) return;
  saving.value = true;
  error.value = null;
  const amount = (v: string) => (v === '' ? null : String(Number(v)));
  try {
    await updateDeparture(selected.value.id, {
      freight_cost: amount(costs.freight_cost),
      customs_cost: amount(costs.customs_cost),
      other_costs: amount(costs.other_costs),
    });
    await load();
    await loadDashboard();
    notice.value = t('departures.costs_saved');
  } catch (err) {
    error.value = extractApiError(err) ?? t('departures.costs_failed');
  } finally {
    saving.value = false;
  }
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
    error.value = extractApiError(err) ?? t('departures.orders_failed');
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
    error.value = extractApiError(err) ?? t('departures.move_failed');
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
    error.value = extractApiError(err) ?? t('departures.close_failed');
  } finally {
    closing.value = false;
  }
}

async function markBackordered(orderIds: string[]) {
  error.value = null;
  try {
    await Promise.all(
      orderIds.map((id) => setOrderStatus(id, 'Backordered', t('departures.shortage_reason'))),
    );
    notice.value = `${orderIds.length} commande(s) marquée(s) en rupture, clients prévenus.`;
    await loadOrders();
  } catch (err) {
    error.value = extractApiError(err) ?? t('departures.status_failed');
  }
}

// --- Supplier purchase orders ---
const poDialog = ref(false);
const poForm = reactive({
  supplier_name: '',
  order_number: '',
  ordered_at: '',
  total_amount: '',
  currency: shopConfig.currency,
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
      currency: poForm.currency.trim() || shopConfig.currency,
      notes: poForm.notes.trim() || null,
    });
    poDialog.value = false;
    Object.assign(poForm, {
      supplier_name: '',
      order_number: '',
      ordered_at: '',
      total_amount: '',
      notes: '',
    });
    notice.value = t('departures.po_saved', { n: updated.orders_updated ?? 0 });
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

async function removePo(index: number) {
  if (!selected.value) return;
  if (!(await confirmDelete(t('departures.po_n', { n: index + 1 })))) return;
  error.value = null;
  try {
    await removeSupplierOrder(selected.value.id, index);
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.delete_failed');
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

const reminderColumns = computed<QTableColumn[]>(() => [
  {
    name: 'when',
    label: t('departures.col_when'),
    field: 'scheduled_at',
    align: 'left',
    format: (v: string) => formatDateTime(v),
  },
  {
    name: 'offset',
    label: t('departures.col_before'),
    field: (r: Reminder) => `J-${r.offset_days}`,
    align: 'left',
  },
  {
    name: 'text',
    label: t('departures.col_text'),
    field: 'rendered_text',
    align: 'left',
    style: 'white-space: normal; max-width: 480px',
  },
  { name: 'status', label: t('departures.col_state'), field: 'status', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

const REMINDER_LABELS: Record<string, string> = labels({
  scheduled: 'departures.r_scheduled',
  sent: 'departures.r_sent',
  failed: 'departures.r_failed',
  cancelled: 'departures.r_cancelled',
});
const reminderLabel = (s: string) => REMINDER_LABELS[s] ?? s;
const reminderColor = (s: string) =>
  s === 'sent' ? 'green' : s === 'failed' ? 'negative' : s === 'cancelled' ? 'grey-6' : 'primary';

async function loadReminders() {
  if (!selected.value) return;
  remindersLoading.value = true;
  try {
    reminders.value = await listReminders(selected.value.id);
  } catch (err) {
    error.value = extractApiError(err) ?? t('departures.reminders_failed');
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
    notice.value = t('departures.webhook_saved');
  } catch (err) {
    error.value = extractApiError(err) ?? t('departures.webhook_failed');
  }
}

function openReminder(r?: Reminder) {
  reminderEditId.value = r?.id ?? null;
  Object.assign(reminderForm, {
    offset_days: r?.offset_days ?? 2,
    anchor: r?.anchor ?? 'cutoff',
    message_template: r?.message_template ?? t('departures.default_message'),
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
    error.value = extractApiError(err) ?? t('departures.reminder_failed');
  } finally {
    saving.value = false;
  }
}

async function publishNow(r: Reminder) {
  error.value = null;
  try {
    const result = await publishReminder(r.id);
    notice.value =
      result.status === 'sent'
        ? t('departures.reminder_sent')
        : t('departures.publish_failed_msg', { error: result.error ?? '' });
    await loadReminders();
  } catch (err) {
    error.value = extractApiError(err) ?? t('departures.publish_failed');
  }
}

async function removeReminder(r: Reminder) {
  if (!(await confirmDelete(t('departures.delete_text')))) return;
  error.value = null;
  try {
    await deleteReminder(r.id);
    await loadReminders();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.delete_failed');
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
    notice.value = t('departures.advanced', {
      name: d.name,
      status: departureStatusLabel(next),
      n: moved,
    });
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('departures.status_failed');
  }
}

async function remove(d: Departure) {
  if (!(await confirmDelete(d.name))) return;
  error.value = null;
  try {
    await deleteDeparture(d.id);
    if (selected.value?.id === d.id) selected.value = null;
    notice.value = t('departures.deleted', { name: d.name });
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.delete_failed');
  }
}

// --- Create / edit ---
const dialog = ref(false);
const editId = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const statusOptions = computed(() =>
  DEPARTURE_STATUSES.map((s) => ({ label: departureStatusLabel(s), value: s })),
);

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
    notice.value = t('departures.saved');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void load();
  void loadWebhook();
});
</script>

<style scoped lang="scss">
.detail-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.detail-block + .detail-block {
  margin-top: 32px;
}

.detail-head {
  margin-bottom: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;

  .admin-subtitle {
    margin: 0;
  }
}

.fulfilment-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.fulfilment-link {
  text-decoration: none;
  border-radius: 999px;

  &:hover :deep(.status-tag) {
    border-color: var(--n-ink-3);
  }
}

// Tuiles de chiffres : même grammaire que les KPI du tableau de bord.
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  border-top: 1px solid var(--n-line);
  border-left: 1px solid var(--n-line);
  border-radius: 8px;
  overflow: hidden;
}

.kpi {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-right: 1px solid var(--n-line);
  border-bottom: 1px solid var(--n-line);
  background: var(--n-surface);
}

.kpi__label {
  font-size: 12.5px;
  color: var(--n-ink-3);
}

.kpi__value {
  font-size: 21px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.kpi__hint {
  font-size: 12.5px;
  color: var(--n-ink-3);
}
</style>
