<template>
  <q-page class="admin-page">
    <PageHeader title="Départs groupés">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          :loading="loading"
          @click="load"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          label="Nouveau départ"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <p class="admin-hint">
      Un départ = une date limite de commande affichée en vitrine, les commandes qui s'y rattachent
      (automatiquement au checkout, déplaçables ici) et le bon de commande fournisseur agrégé par
      SKU. Un seul départ « ouvert » et publié à la fois.
    </p>

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
              <q-tooltip>Publié en vitrine</q-tooltip>
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
              <q-tooltip>Passer à l'étape suivante</q-tooltip>
            </q-btn>
            <q-btn flat round dense icon="ph:pencil-simple" @click.stop="openEdit(props.row)">
              <q-tooltip>Modifier</q-tooltip>
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
                  props.row.orders_count > 0
                    ? 'Déplacez les commandes rattachées avant de supprimer'
                    : 'Supprimer'
                }}
              </q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">
            Aucun départ groupé : la boutique fonctionne en mode classique.
          </div>
        </template>
      </q-table>
    </section>

    <!-- Orders of the selected departure -->
    <section v-if="selected" class="app-section" aria-labelledby="departure-detail-title">
      <div class="app-section__head">
        <h2 id="departure-detail-title" class="app-section__title">
          Commandes du départ « {{ selected.name }} »
        </h2>
        <p class="app-section__hint">{{ cutoffLabel(selected) }}</p>
        <div class="app-section__action detail-actions">
          <q-btn
            flat
            no-caps
            icon="ph:download-simple"
            label="Commandes (CSV)"
            @click="downloadOrdersCsv(filters)"
          />
          <q-btn
            flat
            no-caps
            icon="ph:download-simple"
            label="Bon de commande par SKU (CSV)"
            @click="downloadSkuSummaryCsv(filters)"
          />
          <q-btn
            v-if="selected.status === 'open' || selected.status === 'draft'"
            color="primary"
            unelevated
            no-caps
            icon="ph:lock"
            label="Clôturer le départ"
            :loading="closing"
            @click="closeSelected(false)"
          >
            <q-tooltip>
              Vérifie le stock fournisseur de chaque article commandé, les seuils, et crée le départ
              suivant si récurrent
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
                label="Déplacer la sélection vers…"
                dense
                outlined
                emit-value
                map-options
                style="min-width: 260px"
              />
              <q-btn
                outline
                no-caps
                label="Déplacer"
                :disable="selectedOrders.length === 0 || moveTarget === undefined"
                @click="moveSelected"
              />
              <q-toggle v-model="showUnassigned" label="Voir les commandes sans départ" dense />
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
                <q-tooltip>Ouvrir la commande</q-tooltip>
              </q-btn>
            </q-td>
          </template>
          <template #no-data>
            <div class="full-width text-center text-subtle q-pa-md">Aucune commande.</div>
          </template>
        </q-table>
      </div>

      <div v-if="!showUnassigned" class="detail-block">
        <h3 class="admin-subtitle">Bon de commande fournisseur (agrégé par SKU)</h3>
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
            <div class="full-width text-center text-subtle q-pa-md">Aucune ligne.</div>
          </template>
        </q-table>
      </div>

      <!-- Real purchase orders placed with the suppliers -->
      <div v-if="!showUnassigned" class="detail-block">
        <div class="detail-head">
          <h3 class="admin-subtitle">Bons de commande passés aux fournisseurs</h3>
          <q-btn
            flat
            dense
            no-caps
            icon="ph:plus"
            label="Enregistrer un BC"
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
                <q-tooltip>Supprimer</q-tooltip>
              </q-btn>
            </q-item-section>
          </q-item>
        </q-list>
        <p v-else class="text-caption text-subtle q-mb-none">
          Aucun bon de commande enregistré. Le premier BC passe le départ en « commandé » et
          prévient les clients.
        </p>
      </div>

      <!-- Goods receipt: tally per product, orders reconciliation -->
      <div v-if="!showUnassigned" class="detail-block">
        <div class="detail-head">
          <h3 class="admin-subtitle">Réception — pointage par SKU</h3>
          <span v-if="reception" class="text-caption text-muted">
            attendu <span class="font-mono">{{ reception.expected_units }}</span> · reçu
            <span class="font-mono">{{ reception.received_units }}</span> · endommagé
            <span class="font-mono">{{ reception.damaged_units }}</span> ·
            <span :class="reception.missing_units ? 'text-warning' : 'text-positive'"
              >manquant <span class="font-mono">{{ reception.missing_units }}</span></span
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
                placeholder="SN1, SN2… (un par exemplaire conforme)"
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
                flat
                round
                dense
                icon="ph:floppy-disk"
                :loading="savingReceipt === props.row.product_id"
                @click="saveReceipt(props.row)"
              >
                <q-tooltip
                  >Enregistrer le pointage ; les n° de série sont attribués aux commandes par ordre
                  d'arrivée</q-tooltip
                >
              </q-btn>
            </q-td>
          </template>
          <template #no-data>
            <div class="full-width text-center text-subtle q-pa-md">
              Aucun article attendu (aucune commande payée).
            </div>
          </template>
        </q-table>
        <div v-if="reception?.orders.length" class="q-mt-md">
          <div class="text-caption text-muted q-mb-xs">
            Rapprochement des commandes (servies par ordre d'arrivée)
          </div>
          <div class="fulfilment-list">
            <router-link
              v-for="o in reception.orders"
              :key="o.order_id"
              :to="`/orders/${o.order_id}`"
              class="fulfilment-link"
            >
              <StatusTag
                :label="`${o.order_number ?? o.order_id.slice(0, 8)} · ${fulfilmentLabel(o.fulfilment)}`"
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
        <h3 class="admin-subtitle">Tableau de bord du départ</h3>
        <div class="kpi-grid">
          <div v-for="tile in tiles" :key="tile.label" class="kpi">
            <span class="kpi__label">{{ tile.label }}</span>
            <span class="kpi__value font-mono" :class="tile.cls">{{ tile.value }}</span>
            <span v-if="tile.hint" class="kpi__hint">{{ tile.hint }}</span>
          </div>
        </div>
        <AppNotice v-if="board.unconverted_currencies.length" tone="warning" dense class="q-mt-md">
          Bons de commande en {{ board.unconverted_currencies.join(', ') }} ignorés : aucun taux de
          change actif.
        </AppNotice>
        <div class="admin-toolbar q-mt-md q-mb-none">
          <q-input
            v-model="costs.freight_cost"
            type="number"
            step="1"
            min="0"
            label="Fret réel (XPF)"
            outlined
            dense
          />
          <q-input
            v-model="costs.customs_cost"
            type="number"
            step="1"
            min="0"
            label="Douane réelle (XPF)"
            outlined
            dense
          />
          <q-input
            v-model="costs.other_costs"
            type="number"
            step="1"
            min="0"
            label="Autres frais (XPF)"
            outlined
            dense
          />
          <q-btn
            color="primary"
            unelevated
            no-caps
            label="Enregistrer les coûts"
            :loading="saving"
            @click="saveCosts"
          />
        </div>
      </div>

      <!-- Social reminders -->
      <div v-if="!showUnassigned" class="detail-block">
        <div class="detail-head">
          <h3 class="admin-subtitle">Rappels réseaux sociaux</h3>
          <q-btn
            flat
            dense
            no-caps
            icon="ph:plus"
            label="Ajouter un rappel"
            @click="openReminder()"
          />
        </div>
        <q-input
          v-model="webhookUrl"
          label="URL du webhook (Make, Zapier, Buffer…) — reçoit {text, link, image_url, departure}"
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
                <q-tooltip>Publier maintenant</q-tooltip>
              </q-btn>
              <q-btn
                v-if="props.row.status !== 'sent'"
                flat
                round
                dense
                icon="ph:pencil-simple"
                @click="openReminder(props.row)"
              >
                <q-tooltip>Modifier</q-tooltip>
              </q-btn>
              <q-btn
                flat
                round
                dense
                color="negative"
                icon="ph:trash"
                @click="removeReminder(props.row)"
              >
                <q-tooltip>Supprimer</q-tooltip>
              </q-btn>
            </q-td>
          </template>
          <template #no-data>
            <div class="full-width text-center text-subtle q-pa-md">Aucun rappel.</div>
          </template>
        </q-table>
      </div>
    </section>

    <!-- Close result: what is left to arbitrate -->
    <q-dialog v-model="closeDialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ closeResult?.closed ? 'Départ clôturé' : 'Départ non clôturé' }}
          </h2>
          <p v-if="closeResult" class="app-dialog__text">
            {{ closeResult.orders_count }} commande(s) payée(s) ·
            <span class="font-mono">{{ formatMoney(Number(closeResult.orders_total)) }}</span>
          </p>
        </q-card-section>
        <q-card-section v-if="closeResult">
          <div
            v-if="!closeResult.threshold_reached || closeResult.unpaid_order_ids.length"
            class="admin-notices"
          >
            <AppNotice v-if="!closeResult.threshold_reached" tone="warning" dense>
              Seuil minimum non atteint : le départ reste ouvert. Reportez la clôture ou forcez-la.
            </AppNotice>
            <AppNotice v-if="closeResult.unpaid_order_ids.length" tone="info" dense>
              {{ closeResult.unpaid_order_ids.length }} commande(s) non payée(s) restent rattachées
              : à exclure ou à déplacer vers le départ suivant depuis la liste des commandes.
            </AppNotice>
          </div>
          <template v-if="closeResult.shortages.length">
            <h3 class="admin-subtitle">Ruptures chez le fournisseur — à arbitrer</h3>
            <q-list dense bordered separator class="rounded-borders">
              <q-item v-for="s in closeResult.shortages" :key="s.product_id">
                <q-item-section>
                  <q-item-label
                    >{{ s.product_name }} (<span class="font-mono">{{ s.supplier_sku }}</span
                    >)</q-item-label
                  >
                  <q-item-label caption>
                    {{ s.ordered_quantity }} commandé(s), {{ s.available_quantity }} disponible(s) —
                    commandes {{ s.order_numbers.filter(Boolean).join(', ') || s.order_ids.length }}
                  </q-item-label>
                </q-item-section>
                <q-item-section side>
                  <q-btn
                    flat
                    dense
                    no-caps
                    label="Marquer en rupture"
                    @click="markBackordered(s.order_ids)"
                  >
                    <q-tooltip
                      >Statut « rupture / report » + e-mail aux clients concernés</q-tooltip
                    >
                  </q-btn>
                </q-item-section>
              </q-item>
            </q-list>
          </template>
          <div v-else class="text-positive">Stock fournisseur suffisant sur toutes les lignes.</div>
          <div v-if="closeResult.next_departure_id" class="text-caption text-muted q-mt-sm">
            Départ suivant créé et publié (récurrence).
          </div>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn
            v-if="closeResult && !closeResult.closed"
            flat
            no-caps
            color="negative"
            label="Forcer la clôture"
            @click="closeSelected(true)"
          />
          <q-btn flat no-caps label="Fermer" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Supplier purchase order -->
    <q-dialog v-model="poDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Bon de commande fournisseur</h2>
        </q-card-section>
        <q-form @submit.prevent="submitPo">
          <q-card-section class="q-gutter-sm">
            <q-input
              v-model="poForm.supplier_name"
              label="Fournisseur *"
              outlined
              dense
              :rules="[(v: string) => !!v.trim() || 'Requis']"
            />
            <q-input
              v-model="poForm.order_number"
              label="N° de commande *"
              outlined
              dense
              :rules="[(v: string) => !!v.trim() || 'Requis']"
            />
            <q-input
              v-model="poForm.ordered_at"
              type="date"
              label="Date *"
              outlined
              dense
              :rules="[(v: string) => !!v || 'Requis']"
            />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="poForm.total_amount"
                class="col-8"
                type="number"
                step="0.01"
                min="0"
                label="Montant payé *"
                outlined
                dense
              />
              <q-input v-model="poForm.currency" class="col-4" label="Devise" outlined dense />
            </div>
            <q-input v-model="poForm.notes" label="Notes" outlined dense />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              label="Enregistrer"
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
            {{ reminderEditId ? 'Modifier le rappel' : 'Nouveau rappel' }}
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
                label="Jours avant *"
                outlined
                dense
              />
              <q-select
                v-model="reminderForm.anchor"
                class="col-6"
                :options="[
                  { label: 'la clôture des commandes', value: 'cutoff' },
                  { label: 'le départ physique', value: 'departure' },
                ]"
                label="Avant…"
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
              label="Message *"
              hint="Variables : {name} {cutoff_date} {days_left} {delivery_date} {shop_url}"
              outlined
              dense
              :rules="[(v: string) => !!v.trim() || 'Requis']"
            />
            <q-input
              v-model="reminderForm.image_url"
              label="URL d'image (optionnel)"
              outlined
              dense
              clearable
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              label="Enregistrer"
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
            {{ editId ? 'Modifier le départ' : 'Nouveau départ groupé' }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.name"
              label="Nom *"
              outlined
              dense
              autofocus
              :rules="[(v: string) => !!v.trim() || 'Nom requis']"
            />
            <q-input
              v-model="form.order_cutoff_at"
              type="datetime-local"
              label="Date limite de commande *"
              hint="Affichée en vitrine : « Commandez avant le … »"
              outlined
              dense
              :rules="[(v: string) => !!v || 'Date requise']"
            />
            <q-input
              v-model="form.estimated_delivery_at"
              type="date"
              label="Livraison estimée"
              outlined
              dense
              clearable
            />
            <q-input
              v-model="form.departure_at"
              type="date"
              label="Départ physique (si différent de la clôture)"
              outlined
              dense
              clearable
            />
            <q-select
              v-model="form.status"
              :options="statusOptions"
              label="Statut"
              outlined
              dense
              emit-value
              map-options
            />
            <q-toggle v-model="form.is_published" label="Publié en vitrine" />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model.number="form.min_amount"
                class="col"
                type="number"
                label="Seuil montant (XPF)"
                outlined
                dense
                clearable
              />
              <q-input
                v-model.number="form.min_units"
                class="col"
                type="number"
                label="Seuil pièces"
                outlined
                dense
                clearable
              />
              <q-input
                v-model.number="form.recurrence_days"
                class="col"
                type="number"
                label="Récurrence (jours)"
                outlined
                dense
                clearable
              />
            </div>
            <q-input v-model="form.notes" type="textarea" label="Notes" outlined dense autogrow />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              label="Enregistrer"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, toneOf, type StatusTone } from '@app/ui/statusTone';
import {
  DEPARTURE_STATUSES,
  departureCutoffLabel,
  departureStatusLabel,
  formatDate,
  formatDateTime,
  formatMoney as formatMoneyIn,
  nextDepartureStatus,
} from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
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
import { listSystemSettings, updateSystemSetting } from '@/api/systemSettings';
import { useShopConfigStore } from '@/stores/shopConfig';
import { setOrderStatus } from '@/api/orders';

const departures = ref<Departure[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const shopConfig = useShopConfigStore();
const formatMoney = (n: number) =>
  Number.isFinite(n) ? formatMoneyIn(n, shopConfig.currency) : String(n);
const cutoffLabel = (d: Departure) => departureCutoffLabel(d);
const departureTone = (status: string): StatusTone => (status === 'open' ? 'ok' : 'neutral');

const columns: QTableColumn[] = [
  { name: 'name', label: 'Départ', field: 'name', align: 'left' },
  {
    name: 'cutoff',
    label: 'Limite de commande',
    field: 'order_cutoff_at',
    align: 'left',
    format: (v: string) => formatDate(v),
  },
  {
    name: 'delivery',
    label: 'Livraison estimée',
    field: 'estimated_delivery_at',
    align: 'left',
    format: (v: string | null) => formatDate(v),
  },
  { name: 'status', label: 'Statut', field: 'status', align: 'left' },
  { name: 'orders', label: 'Commandes · total', field: 'orders_count', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    departures.value = await listDepartures();
    if (selected.value) {
      selected.value = departures.value.find((d) => d.id === selected.value?.id) ?? null;
    }
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
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
  { label: '— Aucun départ (détacher)', value: null },
]);

const orderColumns: QTableColumn[] = [
  {
    name: 'number',
    label: 'Commande',
    field: (r: AdminOrderListItem) => r.order_number ?? `#${r.order_id.slice(0, 8)}`,
    align: 'left',
  },
  {
    name: 'date',
    label: 'Date',
    field: 'created_at',
    align: 'left',
    format: (v: string | null) => formatDate(v),
  },
  {
    name: 'client',
    label: 'Client',
    field: (r: AdminOrderListItem) => r.user_name || r.user_email || '',
    align: 'left',
  },
  { name: 'status', label: 'Statut', field: 'status', align: 'left' },
  {
    name: 'total',
    label: 'Total',
    field: 'total_amount',
    align: 'right',
    format: (v: number) => formatMoney(v),
  },
  { name: 'actions', label: '', field: 'order_id', align: 'right' },
];

const skuColumns: QTableColumn[] = [
  { name: 'supplier', label: 'Fournisseur', field: 'supplier_name', align: 'left' },
  { name: 'sku', label: 'SKU', field: 'supplier_sku', align: 'left', classes: 'font-mono' },
  { name: 'product', label: 'Produit', field: 'product_name', align: 'left' },
  { name: 'qty', label: 'Qté', field: 'quantity', align: 'right', classes: 'font-mono' },
  { name: 'orders', label: 'Cmdes', field: 'orders_count', align: 'right', classes: 'font-mono' },
  {
    name: 'cost',
    label: 'Coût unit.',
    field: (r: SkuSummaryRow) =>
      r.unit_cost === null ? '—' : `${r.unit_cost} ${r.cost_currency ?? ''}`,
    align: 'right',
    classes: 'font-mono',
  },
  {
    name: 'weight',
    label: 'Poids total (kg)',
    field: (r: SkuSummaryRow) => r.total_weight_kg ?? '—',
    align: 'right',
    classes: 'font-mono',
  },
];

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

const receiptColumns: QTableColumn[] = [
  {
    name: 'product',
    label: 'Article',
    field: (r: ReceiptLine) => `${r.supplier_sku ?? '—'} · ${r.product_name}`,
    align: 'left',
  },
  {
    name: 'expected',
    label: 'Attendu',
    field: 'expected_quantity',
    align: 'right',
    classes: 'font-mono',
  },
  { name: 'received', label: 'Reçu', field: 'quantity_received', align: 'right' },
  { name: 'damaged', label: 'Endommagé', field: 'quantity_damaged', align: 'right' },
  { name: 'missing', label: 'Manquant', field: 'expected_quantity', align: 'right' },
  { name: 'serials', label: 'N° de série', field: 'serial_numbers', align: 'left' },
  { name: 'actions', label: '', field: 'product_id', align: 'right' },
];

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
    error.value = extractApiError(err) ?? 'Chargement de la réception impossible.';
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
    notice.value = `Pointage enregistré : ${row.product_name}.`;
    void loadDashboard();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement du pointage impossible.';
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
      label: `Chiffre d'affaires (${b.orders_count} cmdes, ${b.units} pièces)`,
      value: formatMoney(n(b.revenue)),
      cls: '',
      hint: '',
    },
    {
      label: 'Encaissé (net des remboursements)',
      value: formatMoney(n(b.collected)),
      cls: '',
      hint: '',
    },
    {
      label:
        b.goods_cost_source === 'supplier_orders'
          ? 'Payé fournisseur (BC)'
          : 'Coût marchandises (estimé au checkout)',
      value: formatMoney(
        b.goods_cost_source === 'supplier_orders' ? n(b.supplier_paid) : n(b.goods_cost_estimated),
      ),
      cls: '',
      hint:
        b.goods_cost_source === 'supplier_orders'
          ? `estimé : ${formatMoney(n(b.goods_cost_estimated))}`
          : 'enregistrez les BC pour le réel',
    },
    { label: 'Fret + douane + autres (réels)', value: formatMoney(fees), cls: '', hint: '' },
    {
      label: 'Marge brute',
      value: formatMoney(margin),
      cls: margin < 0 ? 'text-negative' : 'text-positive',
      hint: b.margin_rate_pct === null ? '' : `${b.margin_rate_pct} % du CA`,
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
    error.value = extractApiError(err) ?? 'Chargement du tableau de bord impossible.';
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
    notice.value = 'Coûts réels enregistrés.';
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement des coûts impossible.';
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
    error.value = extractApiError(err) ?? 'Chargement des commandes impossible.';
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
    error.value = extractApiError(err) ?? 'Déplacement impossible.';
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
    error.value = extractApiError(err) ?? 'Clôture impossible.';
  } finally {
    closing.value = false;
  }
}

async function markBackordered(orderIds: string[]) {
  error.value = null;
  try {
    await Promise.all(
      orderIds.map((id) => setOrderStatus(id, 'Backordered', 'rupture fournisseur')),
    );
    notice.value = `${orderIds.length} commande(s) marquée(s) en rupture, clients prévenus.`;
    await loadOrders();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Changement de statut impossible.';
  }
}

// --- Supplier purchase orders ---
const poDialog = ref(false);
const poForm = reactive({
  supplier_name: '',
  order_number: '',
  ordered_at: '',
  total_amount: '',
  currency: 'XPF',
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
      currency: poForm.currency.trim() || 'XPF',
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
    notice.value = `Bon de commande enregistré. ${updated.orders_updated ?? 0} commande(s) passée(s) en « commandée au fournisseur ».`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

async function removePo(index: number) {
  if (!selected.value) return;
  error.value = null;
  try {
    await removeSupplierOrder(selected.value.id, index);
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Suppression impossible.';
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

const reminderColumns: QTableColumn[] = [
  {
    name: 'when',
    label: 'Publication',
    field: 'scheduled_at',
    align: 'left',
    format: (v: string) => formatDateTime(v),
  },
  { name: 'offset', label: 'Avant', field: (r: Reminder) => `J-${r.offset_days}`, align: 'left' },
  {
    name: 'text',
    label: 'Message (rendu)',
    field: 'rendered_text',
    align: 'left',
    style: 'white-space: normal; max-width: 480px',
  },
  { name: 'status', label: 'État', field: 'status', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

const REMINDER_LABELS: Record<string, string> = {
  scheduled: 'Planifié',
  sent: 'Publié',
  failed: 'Échec',
  cancelled: 'Annulé',
};
const reminderLabel = (s: string) => REMINDER_LABELS[s] ?? s;
const reminderColor = (s: string) =>
  s === 'sent' ? 'green' : s === 'failed' ? 'negative' : s === 'cancelled' ? 'grey-6' : 'primary';

async function loadReminders() {
  if (!selected.value) return;
  remindersLoading.value = true;
  try {
    reminders.value = await listReminders(selected.value.id);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement des rappels impossible.';
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
    notice.value = 'URL du webhook enregistrée.';
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement du webhook impossible.';
  }
}

function openReminder(r?: Reminder) {
  reminderEditId.value = r?.id ?? null;
  Object.assign(reminderForm, {
    offset_days: r?.offset_days ?? 2,
    anchor: r?.anchor ?? 'cutoff',
    message_template:
      r?.message_template ??
      '⏰ Plus que {days_left} jours pour rejoindre le départ groupé « {name} » (clôture le {cutoff_date}). {shop_url}',
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
    error.value = extractApiError(err) ?? 'Enregistrement du rappel impossible.';
  } finally {
    saving.value = false;
  }
}

async function publishNow(r: Reminder) {
  error.value = null;
  try {
    const result = await publishReminder(r.id);
    notice.value =
      result.status === 'sent' ? 'Rappel publié.' : `Publication échouée : ${result.error ?? ''}`;
    await loadReminders();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Publication impossible.';
  }
}

async function removeReminder(r: Reminder) {
  error.value = null;
  try {
    await deleteReminder(r.id);
    await loadReminders();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Suppression impossible.';
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
    notice.value = `« ${d.name} » → ${departureStatusLabel(next)}. ${moved} commande(s) mise(s) à jour et client(s) prévenu(s).`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Changement de statut impossible.';
  }
}

async function remove(d: Departure) {
  error.value = null;
  try {
    await deleteDeparture(d.id);
    if (selected.value?.id === d.id) selected.value = null;
    notice.value = `« ${d.name} » supprimé.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Suppression impossible.';
  }
}

// --- Create / edit ---
const dialog = ref(false);
const editId = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const statusOptions = DEPARTURE_STATUSES.map((s) => ({ label: departureStatusLabel(s), value: s }));

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
    notice.value = 'Départ enregistré.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
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
