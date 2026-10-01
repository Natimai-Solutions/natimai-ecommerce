<template>
  <q-page class="admin-page">
    <PageHeader
      :title="order?.order_number ?? `Commande #${orderId.slice(0, 8)}`"
      :back="{ to: '/orders', label: 'Commandes' }"
      :hint="order ? `Passée le ${formatDate(order.created_at)}` : undefined"
    >
      <template v-if="order" #tags>
        <StatusTag
          data-testid="order-status"
          :label="orderStatusLabel(order.status)"
          :tone="toneOf(orderStatusColor(order.status))"
          :icon="toneIcon(toneOf(orderStatusColor(order.status)))"
        />
        <template v-if="order.payment_plan === 'deposit'">
          <StatusTag
            v-if="order.balance_paid_at"
            tone="ok"
            icon="ph:hand-coins"
            label="Solde réglé"
          />
          <StatusTag
            v-else-if="order.balance_requested_at"
            tone="warn"
            icon="ph:hand-coins"
            label="Solde demandé"
          />
          <StatusTag v-else tone="neutral" icon="ph:hand-coins" label="Acompte" />
        </template>
      </template>
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          data-testid="order-refresh"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="loading" class="text-center q-pa-lg">
      <q-spinner size="2em" />
    </div>

    <template v-else-if="order">
      <div class="order-layout">
        <!-- Contenu principal : articles, paiements, transport -->
        <div class="order-main">
          <!-- Lines -->
          <section class="app-section" aria-labelledby="order-lines-title">
            <div class="app-section__head">
              <h2 id="order-lines-title" class="app-section__title">Articles</h2>
            </div>
            <q-markup-table flat bordered dense>
              <thead>
                <tr>
                  <th class="text-left">Produit</th>
                  <th class="text-right">Qté</th>
                  <th class="text-right">PU TTC</th>
                  <th class="text-right">Total TTC</th>
                  <th class="text-right">Total HT</th>
                  <th class="text-right">Coût</th>
                  <th class="text-right">Marge HT</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="line in order.lines" :key="line.product_id">
                  <td class="text-left">{{ line.product_name || line.product_id.slice(0, 8) }}</td>
                  <td class="text-right font-mono">{{ line.quantity }}</td>
                  <td class="text-right font-mono">{{ formatMoney(line.unit_price) }}</td>
                  <td class="text-right font-mono">{{ formatMoney(line.line_total) }}</td>
                  <td class="text-right font-mono text-muted">
                    {{
                      line.line_total_excl_tax == null ? '—' : formatMoney(line.line_total_excl_tax)
                    }}
                  </td>
                  <td class="text-right font-mono text-muted">
                    {{ line.line_cost == null ? '—' : formatMoney(line.line_cost) }}
                  </td>
                  <td class="text-right" data-testid="order-line-margin">
                    <template v-if="line.line_margin != null">
                      <span class="font-mono" :class="{ 'text-negative': line.line_margin < 0 }">{{
                        formatMoney(line.line_margin)
                      }}</span>
                      <span v-if="line.margin_pct != null" class="text-caption text-subtle">
                        {{ formatPct(line.margin_pct) }}
                      </span>
                    </template>
                    <span v-else class="text-subtle">
                      —
                      <q-tooltip>Coût d'achat inconnu à la commande</q-tooltip>
                    </span>
                  </td>
                </tr>
                <tr v-if="order.lines.length === 0">
                  <td colspan="7" class="text-center text-subtle">Aucun article.</td>
                </tr>
              </tbody>
            </q-markup-table>
            <div v-if="order.margin" class="order-margin" data-testid="order-margin">
              <span class="text-muted">Marge brute sur les articles</span>
              <strong
                class="font-mono"
                :class="{ 'text-negative': order.margin.margin < 0 }"
                data-testid="order-margin-amount"
                >{{ formatMoney(order.margin.margin) }}</strong
              >
              <span v-if="order.margin.margin_pct != null" class="text-muted">
                soit {{ formatPct(order.margin.margin_pct) }} du CA HT ({{
                  formatMoney(order.margin.goods_excl_tax)
                }}
                − coût {{ formatMoney(order.margin.goods_cost) }})
              </span>
              <span v-if="!order.margin.complete" class="text-caption text-warning">
                {{ order.margin.lines_without_cost }} ligne(s) sans coût connu, non comptée(s)
              </span>
            </div>
          </section>

          <!-- Payments -->
          <section class="app-section" aria-labelledby="order-payments-title">
            <div class="app-section__head">
              <h2 id="order-payments-title" class="app-section__title">Paiements</h2>
            </div>
            <AppNotice v-if="refundNotice" tone="success" dense class="q-mb-sm">
              {{ refundNotice }}
            </AppNotice>
            <q-markup-table flat bordered dense>
              <thead>
                <tr>
                  <th class="text-left">Type</th>
                  <th class="text-left">Référence</th>
                  <th class="text-left">Statut</th>
                  <th class="text-right">Montant</th>
                  <th class="text-left">Date</th>
                  <th class="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in order.payments" :key="p.payment_id">
                  <td class="text-left">
                    {{ providerLabel(p.provider_code) }}
                    <q-chip
                      v-if="p.kind !== 'full'"
                      dense
                      size="sm"
                      class="q-ml-xs"
                      :label="PAYMENT_KIND_LABELS[p.kind] ?? p.kind"
                    />
                  </td>
                  <td class="text-left font-mono">{{ p.provider_reference || '—' }}</td>
                  <td class="text-left">{{ p.status || '—' }}</td>
                  <td class="text-right">
                    <div class="font-mono">{{ formatMoney(p.amount) }}</div>
                    <div
                      v-if="p.accepts_receipts && (p.received_amount ?? 0) > 0"
                      class="text-caption text-warning"
                    >
                      reçu <span class="font-mono">{{ formatMoney(p.received_amount ?? 0) }}</span>
                    </div>
                  </td>
                  <td class="text-left">{{ formatDate(p.created_at) }}</td>
                  <td class="text-right">
                    <q-btn
                      v-if="p.accepts_receipts"
                      flat
                      dense
                      no-caps
                      icon="ph:hand-coins"
                      label="Encaisser"
                      data-testid="order-payment-receipt"
                      @click="openPaymentReceipt(p)"
                    />
                    <q-btn
                      v-if="canCapture(p)"
                      flat
                      dense
                      no-caps
                      icon="ph:money"
                      label="Capturer"
                      :loading="capturingId === p.payment_id"
                      @click="captureRow(p)"
                    />
                    <q-btn
                      v-if="canRefund(p)"
                      flat
                      dense
                      no-caps
                      color="negative"
                      icon="ph:arrow-u-up-left"
                      label="Rembourser"
                      @click="openRefund(p)"
                    />
                  </td>
                </tr>
                <tr v-if="order.payments.length === 0">
                  <td colspan="6" class="text-center text-subtle">Aucun paiement.</td>
                </tr>
              </tbody>
            </q-markup-table>

            <div v-if="order.receipts?.length" class="order-receipts">
              <h3 class="admin-subtitle">Versements reçus</h3>
              <q-markup-table flat bordered dense data-testid="order-receipts">
                <thead>
                  <tr>
                    <th class="text-left">Reçu le</th>
                    <th class="text-right">Montant</th>
                    <th class="text-left">Mode</th>
                    <th class="text-left">Référence</th>
                    <th class="text-left">Note</th>
                    <th class="text-right"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="r in order.receipts"
                    :key="r.id"
                    :class="{ 'receipt--cancelled': !r.is_active }"
                  >
                    <td class="text-left">{{ formatDate(r.received_at) }}</td>
                    <td class="text-right font-mono">{{ formatMoney(Number(r.amount)) }}</td>
                    <td class="text-left">{{ RECEIPT_METHOD_LABELS[r.method] ?? r.method }}</td>
                    <td class="text-left font-mono">{{ r.reference || '—' }}</td>
                    <td class="text-left">{{ r.note || '' }}</td>
                    <td class="text-right">
                      <StatusTag
                        v-if="!r.is_active"
                        tone="danger"
                        icon="ph:x-circle"
                        :label="`Annulé${r.cancel_reason ? ` : ${r.cancel_reason}` : ''}`"
                      />
                      <q-btn
                        v-else-if="receiptCancellable(r)"
                        flat
                        dense
                        no-caps
                        color="negative"
                        icon="ph:arrow-counter-clockwise"
                        label="Annuler"
                        @click="openCancelReceipt(r)"
                      >
                        <q-tooltip>Chèque impayé, somme rendue…</q-tooltip>
                      </q-btn>
                    </td>
                  </tr>
                </tbody>
              </q-markup-table>
            </div>
          </section>

          <!-- Transport (journey legs, carrier hand-over) -->
          <section class="app-section" aria-labelledby="order-transport-title">
            <div class="app-section__head">
              <h2 id="order-transport-title" class="app-section__title">Transport</h2>
              <p v-if="order.delivery_type" class="app-section__hint">
                Mode choisi par le client : {{ prettifyMode(order.delivery_type) }}
              </p>
              <q-btn
                flat
                dense
                no-caps
                icon="ph:package"
                label="Page Logistique"
                to="/shipping"
                class="app-section__action"
              />
            </div>
            <div v-if="journeyNotice || journeyError" class="admin-notices">
              <AppNotice v-if="journeyNotice" tone="success" dense>{{ journeyNotice }}</AppNotice>
              <AppNotice v-if="journeyError" tone="error" dense>{{ journeyError }}</AppNotice>
            </div>
            <q-markup-table flat bordered dense>
              <thead>
                <tr>
                  <th class="text-left">#</th>
                  <th class="text-left">Tronçon</th>
                  <th class="text-left">Statut</th>
                  <th class="text-left">Transporteur</th>
                  <th class="text-left">N° de suivi</th>
                  <th class="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="leg in journey"
                  :key="leg.tracking_id"
                  :class="{ 'leg--current': leg.is_current }"
                >
                  <td class="text-left font-mono">{{ leg.sequence_order }}</td>
                  <td class="text-left">
                    <div>{{ leg.route_name || '—' }}</div>
                    <div class="text-caption text-muted">
                      {{ leg.from_place || '?' }} → {{ leg.to_place || '?' }}
                      <span v-if="leg.mode">({{ leg.mode }})</span>
                    </div>
                  </td>
                  <td class="text-left">
                    <StatusTag
                      :tone="leg.is_terminal ? 'ok' : 'neutral'"
                      :icon="
                        leg.is_terminal
                          ? 'ph:check-circle'
                          : leg.is_current
                            ? 'ph:truck'
                            : 'ph:circle'
                      "
                      :label="leg.status_name || leg.status_code || '—'"
                    />
                  </td>
                  <td class="text-left">
                    {{ leg.carrier_name || (leg.tracking_ref ? 'Suivi interne' : '—') }}
                  </td>
                  <td class="text-left font-mono">
                    <a
                      v-if="leg.tracking_url"
                      :href="leg.tracking_url"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="admin-link"
                      >{{ leg.tracking_ref }}</a
                    >
                    <span v-else>{{ leg.tracking_ref || '—' }}</span>
                  </td>
                  <td class="text-right">
                    <q-btn
                      flat
                      dense
                      no-caps
                      icon="ph:truck"
                      label="Remettre au transporteur"
                      :disable="leg.is_terminal || leg.status_code === 'shipped'"
                      @click="openShip(leg)"
                    >
                      <q-tooltip max-width="320px">
                        Enregistre le transporteur et le n° de suivi, marque le tronçon expédié et
                        notifie le client.
                      </q-tooltip>
                    </q-btn>
                    <q-btn
                      v-if="!leg.is_final_leg"
                      flat
                      dense
                      no-caps
                      icon="ph:skip-forward"
                      label="Tronçon suivant"
                      :disable="leg.is_terminal"
                      @click="advanceLeg(leg)"
                    />
                    <q-btn
                      v-else
                      flat
                      dense
                      no-caps
                      icon="ph:check-circle"
                      color="positive"
                      label="Livrer"
                      :disable="leg.is_terminal"
                      @click="deliverLeg(leg)"
                    />
                  </td>
                </tr>
                <tr v-if="journey.length === 0">
                  <td colspan="6" class="text-center text-subtle">
                    {{ journeyLoading ? 'Chargement…' : 'Aucun tronçon de transport.' }}
                  </td>
                </tr>
              </tbody>
            </q-markup-table>
          </section>
        </div>

        <!-- Colonne latérale : récapitulatif, suivi, client -->
        <aside class="order-side">
          <!-- Amounts -->
          <div class="app-panel">
            <div class="order-panel__head">
              <h2 class="admin-subtitle q-mb-none">Récapitulatif</h2>
              <q-btn
                flat
                dense
                no-caps
                icon="ph:piggy-bank"
                label="Avoir-crédit"
                @click="openCredit"
              >
                <q-tooltip
                  >Accorder (ou reprendre) un avoir au client, utilisable sur sa prochaine
                  commande</q-tooltip
                >
              </q-btn>
            </div>
            <AppNotice
              v-if="storeCredit && Number(storeCredit.balance) > 0"
              tone="success"
              dense
              class="q-mb-md"
            >
              Avoir disponible du client :
              <span class="font-mono">{{ formatMoney(Number(storeCredit.balance)) }}</span>
            </AppNotice>
            <div class="app-kv">
              <span>Sous-total</span>
              <span class="font-mono">{{ formatMoney(order.subtotal_amount) }}</span>
            </div>
            <div class="app-kv">
              <span>Frais de port</span>
              <span class="font-mono">{{ formatMoney(order.shipping_fee_amount) }}</span>
            </div>
            <div class="app-kv">
              <span>Frais de paiement</span>
              <span class="font-mono">{{ formatMoney(order.payment_fee_amount) }}</span>
            </div>
            <div v-if="order.discount_code" class="app-kv app-kv--credit">
              <span
                >Remise <span class="font-mono">{{ order.discount_code }}</span></span
              >
              <span class="font-mono">-{{ formatMoney(order.discount_amount ?? 0) }}</span>
            </div>
            <div v-if="order.deposit_fee_amount > 0" class="app-kv">
              <span>Frais option acompte</span>
              <span class="font-mono">{{ formatMoney(order.deposit_fee_amount) }}</span>
            </div>
            <div class="app-kv app-kv--total">
              <span>Total</span>
              <span class="font-mono">{{ formatMoney(order.total_amount) }}</span>
            </div>
            <div v-if="order.payment_plan === 'deposit'" class="order-deposit">
              <div class="app-kv">
                <span>Acompte à la commande</span>
                <span class="font-mono">{{ formatMoney(order.deposit_amount) }}</span>
              </div>
              <div class="app-kv">
                <span>
                  Solde
                  <span class="order-deposit__caption">
                    <template v-if="order.balance_paid_at"
                      >réglé le {{ formatDate(order.balance_paid_at) }}</template
                    >
                    <template v-else-if="order.balance_requested_at"
                      >demandé le {{ formatDate(order.balance_requested_at) }}</template
                    >
                    <template v-else>demandé automatiquement à la réception</template>
                  </span>
                </span>
                <span class="font-mono">{{ formatMoney(order.balance_amount) }}</span>
              </div>
              <q-btn
                v-if="!order.balance_paid_at"
                flat
                dense
                no-caps
                size="sm"
                icon="ph:envelope-simple"
                class="q-mt-sm"
                :label="order.balance_requested_at ? 'Renvoyer la demande' : 'Demander le solde'"
                :loading="requestingBalance"
                @click="sendBalanceRequest"
              />
            </div>
          </div>

          <!-- Encaissé / reste dû -->
          <div class="app-panel" data-testid="order-money">
            <h2 class="admin-subtitle">Encaissements</h2>
            <div class="app-kv">
              <span>Encaissé</span>
              <span class="font-mono" data-testid="order-amount-paid">{{
                formatMoney(order.amount_paid ?? 0)
              }}</span>
            </div>
            <div class="app-kv app-kv--total">
              <span>Reste dû</span>
              <span class="font-mono" data-testid="order-amount-due">{{
                formatMoney(order.amount_due ?? 0)
              }}</span>
            </div>
            <q-btn
              v-if="(order.next_part_due ?? 0) > 0"
              color="primary"
              unelevated
              no-caps
              icon="ph:hand-coins"
              class="full-width q-mt-md"
              label="Enregistrer un encaissement"
              data-testid="order-counter-payment"
              @click="openCounterPayment"
            />
            <p
              v-if="(order.next_part_due ?? 0) > 0 && order.next_part_kind !== 'full'"
              class="admin-hint q-mt-sm q-mb-none"
            >
              Part due maintenant :
              {{ PAYMENT_KIND_LABELS[order.next_part_kind ?? 'full']?.toLowerCase() }}
              (<span class="font-mono">{{ formatMoney(order.next_part_due ?? 0) }}</span
              >).
            </p>
          </div>

          <!-- Status + grouped departure -->
          <div class="app-panel">
            <h2 class="admin-subtitle">Suivi</h2>
            <div class="order-panel__fields">
              <q-select
                :model-value="order.status"
                :options="statusOptions"
                label="Changer le statut"
                dense
                outlined
                emit-value
                map-options
                :loading="statusSaving"
                @update:model-value="changeStatus"
              />
              <q-select
                :model-value="order.grouped_departure_id"
                :options="departureOptions"
                label="Départ groupé"
                dense
                outlined
                emit-value
                map-options
                :loading="departureSaving"
                @update:model-value="setDeparture"
              />
            </div>
          </div>

          <!-- Client -->
          <div class="app-panel">
            <h2 class="admin-subtitle">Client</h2>
            <dl class="admin-dl">
              <dt>Client</dt>
              <dd>{{ order.user_name || order.user_email || order.user_id.slice(0, 8) }}</dd>
              <template v-if="order.user_email">
                <dt>Email</dt>
                <dd class="order-panel__wrap">{{ order.user_email }}</dd>
              </template>
              <dt>Livraison</dt>
              <dd class="order-panel__wrap">{{ order.shipping_address || '—' }}</dd>
              <template v-if="order.notes">
                <dt>Notes</dt>
                <dd class="order-panel__wrap">{{ order.notes }}</dd>
              </template>
            </dl>
          </div>
        </aside>
      </div>

      <!-- Ship dialog (carrier + tracking ref) -->
      <q-dialog v-model="shipDialog">
        <q-card class="app-dialog">
          <q-card-section class="app-dialog__head">
            <h2 class="app-dialog__title">Remise au transporteur</h2>
          </q-card-section>
          <q-form @submit.prevent="submitShip">
            <q-card-section class="q-gutter-sm">
              <AppNotice v-if="shipError" tone="error" dense>{{ shipError }}</AppNotice>
              <q-select
                v-model="shipCarrierId"
                :options="carrierOptions"
                label="Transporteur"
                outlined
                dense
                emit-value
                map-options
              />
              <q-input
                v-model="shipRef"
                label="Numéro de suivi (optionnel)"
                hint="Laisser vide si vous n'avez pas de numéro (suivi géré en interne)."
                outlined
                dense
                autofocus
              />
            </q-card-section>
            <q-card-actions align="right" class="app-dialog__actions">
              <q-btn flat no-caps label="Annuler" v-close-popup />
              <q-btn
                type="submit"
                color="primary"
                unelevated
                no-caps
                label="Remettre au transporteur"
                :loading="shipping"
              />
            </q-card-actions>
          </q-form>
        </q-card>
      </q-dialog>

      <!-- Store credit dialog -->
      <q-dialog v-model="creditDialog">
        <q-card class="app-dialog">
          <q-card-section class="app-dialog__head">
            <h2 class="app-dialog__title">Avoir-crédit client</h2>
            <p class="app-dialog__text">
              Solde actuel :
              <span class="font-mono">{{
                storeCredit ? formatMoney(Number(storeCredit.balance)) : '—'
              }}</span
              >. Un montant négatif reprend de l'avoir.
            </p>
          </q-card-section>
          <q-form @submit.prevent="submitCredit">
            <q-card-section class="q-gutter-sm">
              <AppNotice v-if="creditError" tone="error" dense>{{ creditError }}</AppNotice>
              <q-input
                v-model="creditAmount"
                type="number"
                step="1"
                label="Montant (XPF) *"
                outlined
                dense
                autofocus
              />
              <q-input
                v-model="creditReason"
                label="Motif *"
                outlined
                dense
                :rules="[(v: string) => !!v.trim() || 'Requis']"
              />
              <q-list v-if="storeCredit?.entries.length" dense bordered class="q-mt-sm">
                <q-item v-for="e in storeCredit.entries.slice(0, 5)" :key="e.id">
                  <q-item-section>
                    <q-item-label
                      >{{ STORE_CREDIT_KIND_LABELS[e.kind] ?? e.kind }} ·
                      {{ e.reason }}</q-item-label
                    >
                    <q-item-label caption>{{ formatDate(e.created_at) }}</q-item-label>
                  </q-item-section>
                  <q-item-section side class="font-mono">{{
                    formatMoney(Number(e.amount))
                  }}</q-item-section>
                </q-item>
              </q-list>
            </q-card-section>
            <q-card-actions align="right" class="app-dialog__actions">
              <q-btn flat no-caps label="Annuler" v-close-popup />
              <q-btn
                type="submit"
                color="primary"
                unelevated
                no-caps
                label="Enregistrer"
                :loading="creditSaving"
              />
            </q-card-actions>
          </q-form>
        </q-card>
      </q-dialog>

      <!-- Refund dialog -->
      <ReceiptDialog
        v-model="receiptDialog"
        :target="receiptTarget"
        :remaining="receiptRemaining"
        :default-method="receiptMethod"
        :title="receiptTitle"
        @done="onReceiptDone"
      />

      <q-dialog v-model="cancelReceiptDialog">
        <q-card class="app-dialog app-dialog--narrow">
          <q-card-section class="app-dialog__head">
            <h2 class="app-dialog__title">Annuler le versement</h2>
            <p class="app-dialog__text">
              <span class="font-mono">{{
                cancelTarget ? formatMoney(Number(cancelTarget.amount)) : ''
              }}</span>
              ne comptera plus dans ce qui a été encaissé. Le versement reste dans l'historique.
            </p>
          </q-card-section>
          <q-card-section>
            <AppNotice v-if="cancelError" tone="error" dense class="q-mb-sm">{{
              cancelError
            }}</AppNotice>
            <q-input
              v-model="cancelReason"
              label="Motif (chèque impayé, somme rendue…)"
              outlined
              dense
              autofocus
              maxlength="500"
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Retour" v-close-popup />
            <q-btn
              color="negative"
              unelevated
              no-caps
              label="Annuler le versement"
              :disable="!cancelReason.trim()"
              :loading="cancelling"
              @click="submitCancelReceipt"
            />
          </q-card-actions>
        </q-card>
      </q-dialog>

      <q-dialog v-model="refundDialog">
        <q-card class="app-dialog">
          <q-card-section class="app-dialog__head">
            <h2 class="app-dialog__title">Rembourser le paiement</h2>
            <p class="app-dialog__text">
              Montant du paiement :
              <span class="font-mono">{{
                refundTarget ? formatMoney(refundTarget.amount) : ''
              }}</span
              >. Laissez le montant vide pour un remboursement total.
            </p>
          </q-card-section>
          <q-form @submit.prevent="submitRefund">
            <q-card-section class="q-gutter-sm">
              <AppNotice v-if="refundError" tone="error" dense>{{ refundError }}</AppNotice>
              <q-input
                v-model.number="refundAmount"
                label="Montant à rembourser (optionnel)"
                type="number"
                step="0.01"
                outlined
                dense
                clearable
              />
              <q-input
                v-model="refundReason"
                label="Motif (optionnel)"
                type="textarea"
                autogrow
                outlined
                dense
              />
            </q-card-section>
            <q-card-actions align="right" class="app-dialog__actions">
              <q-btn flat no-caps label="Annuler" v-close-popup />
              <q-btn
                type="submit"
                color="negative"
                unelevated
                no-caps
                label="Rembourser"
                :loading="refunding"
              />
            </q-card-actions>
          </q-form>
        </q-card>
      </q-dialog>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { providerLabel } from '@/utils/payments';
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, toneOf } from '@app/ui/statusTone';
import { formatMoney as money, intlLocale } from '@app/utils';
import { useShopConfigStore } from '@/stores/shopConfig';
import PageHeader from '@/components/PageHeader.vue';
import {
  getOrder,
  listOrderStatuses,
  orderStatusColor,
  orderStatusLabel,
  PAYMENT_KIND_LABELS,
  requestBalance,
  setOrderStatus,
  type AdminOrderDetail,
  type AdminOrderPaymentItem,
} from '@/api/orders';

// --- Deposit order: ask for (or re-send) the balance ---
const requestingBalance = ref(false);

// --- Store credit (« avoir-crédit ») of the customer ---
const storeCredit = ref<StoreCreditBalance | null>(null);
const creditDialog = ref(false);
const creditAmount = ref('');
const creditReason = ref('');
const creditSaving = ref(false);
const creditError = ref<string | null>(null);

async function loadStoreCredit() {
  if (!order.value) return;
  storeCredit.value = await getUserStoreCredit(order.value.user_id).catch(() => null);
}

function openCredit() {
  creditAmount.value = '';
  creditReason.value = '';
  creditError.value = null;
  creditDialog.value = true;
}

async function submitCredit() {
  if (!order.value) return;
  creditSaving.value = true;
  creditError.value = null;
  try {
    storeCredit.value = await grantStoreCredit(order.value.user_id, {
      amount: String(Number(creditAmount.value) || 0),
      reason: creditReason.value.trim(),
      order_id: order.value.order_id,
    });
    creditDialog.value = false;
    refundNotice.value = `Avoir enregistré. Solde du client : ${formatMoney(Number(storeCredit.value.balance))}.`;
  } catch (err) {
    creditError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    creditSaving.value = false;
  }
}
async function sendBalanceRequest() {
  if (!order.value) return;
  requestingBalance.value = true;
  error.value = null;
  try {
    const result = await requestBalance(order.value.order_id);
    order.value.balance_requested_at = new Date().toISOString();
    refundNotice.value = result.sent
      ? `Demande de solde (${formatMoney(result.balance_amount)}) envoyée au client.`
      : "Demande enregistrée, mais l'e-mail n'a pas pu partir (notifications désactivées ?).";
  } catch (err) {
    error.value = extractApiError(err) ?? 'Demande de solde impossible.';
  } finally {
    requestingBalance.value = false;
  }
}
import {
  cancelReceipt,
  capturePayment,
  RECEIPT_METHOD_LABELS,
  refundPayment,
  type PaymentReceipt,
  type ReceiptMethod,
  type ReceiptResult,
} from '@/api/paymentValidations';
import ReceiptDialog from '@/components/ReceiptDialog.vue';
import {
  advanceTracking,
  deliverTracking,
  getOrderJourney,
  listCarriers,
  shipTracking,
  type Carrier,
  type JourneyLeg,
} from '@/api/shipping';
import { extractApiError } from '@/api/errors';
import { assignOrders, listDepartures, type Departure } from '@/api/departures';
import {
  getUserStoreCredit,
  grantStoreCredit,
  STORE_CREDIT_KIND_LABELS,
  type StoreCreditBalance,
} from '@/api/storeCredit';

// --- Order status (one order by hand; the departure handles the bulk case) ---
const statusNames = ref<string[]>([]);
const statusSaving = ref(false);
const statusOptions = computed(() =>
  statusNames.value.map((s) => ({ label: orderStatusLabel(s), value: s })),
);

async function changeStatus(status: string) {
  if (!order.value || status === order.value.status) return;
  statusSaving.value = true;
  error.value = null;
  try {
    await setOrderStatus(order.value.order_id, status);
    order.value.status = status;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Changement de statut impossible.';
  } finally {
    statusSaving.value = false;
  }
}

const route = useRoute();
const orderId = computed(() => String(route.params.id ?? ''));

const order = ref<AdminOrderDetail | null>(null);

// --- Grouped departure (attach / move / detach from the order itself) ---
const departures = ref<Departure[]>([]);
const departureSaving = ref(false);
const departureOptions = computed(() => [
  { label: '— Aucun (commande classique)', value: null },
  ...departures.value.map((d) => ({
    label: `${d.name} (${formatDate(d.order_cutoff_at)})`,
    value: d.id,
  })),
]);

async function setDeparture(departureId: string | null) {
  if (!order.value) return;
  departureSaving.value = true;
  error.value = null;
  try {
    await assignOrders([order.value.order_id], departureId);
    order.value.grouped_departure_id = departureId;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Rattachement impossible.';
  } finally {
    departureSaving.value = false;
  }
}
const loading = ref(false);
const error = ref<string | null>(null);

function formatPct(value: number): string {
  return `${value.toLocaleString(intlLocale(), { maximumFractionDigits: 1 })} %`;
}

const shopConfig = useShopConfigStore();

/** Amount in its own currency (the order's), else the reference currency. */
function formatMoney(amount: number, currency?: string | null): string {
  return Number.isFinite(amount)
    ? money(amount, currency || order.value?.currency || shopConfig.currency)
    : String(amount);
}

function formatDate(raw: string | null): string {
  if (!raw) return '—';
  const d = new Date(raw);
  return Number.isNaN(d.getTime())
    ? raw
    : d.toLocaleString(intlLocale(), {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
}

// --- Encaissements : versements, comptoir, annulation (R3-P2) ---
const receiptDialog = ref(false);
const receiptTarget = ref<{ paymentId: string } | { orderId: string } | null>(null);
const receiptRemaining = ref(0);
const receiptMethod = ref<ReceiptMethod>('cash');
const receiptTitle = ref('Encaisser un versement');

function methodForProvider(code: string | null): ReceiptMethod {
  if (code === 'manual_check') return 'check';
  if (code === 'manual_transfer') return 'transfer';
  return 'cash';
}

function openPaymentReceipt(p: AdminOrderPaymentItem) {
  receiptTarget.value = { paymentId: p.payment_id };
  receiptRemaining.value = p.amount - (p.received_amount ?? 0);
  receiptMethod.value = methodForProvider(p.provider_code);
  receiptTitle.value = `Encaisser — ${providerLabel(p.provider_code)}`;
  receiptDialog.value = true;
}

function openCounterPayment() {
  if (!order.value) return;
  receiptTarget.value = { orderId: order.value.order_id };
  receiptRemaining.value = order.value.next_part_due ?? 0;
  const pending = order.value.payments.find((p) => p.accepts_receipts);
  receiptMethod.value = pending ? methodForProvider(pending.provider_code) : 'cash';
  receiptTitle.value = 'Enregistrer un encaissement';
  receiptDialog.value = true;
}

async function onReceiptDone(result: ReceiptResult) {
  refundNotice.value = result.payment_settled
    ? 'Encaissement enregistré : le paiement est validé.'
    : `Versement enregistré — reste ${formatMoney(Number(result.remaining_amount))}.`;
  await load();
}

function receiptCancellable(r: PaymentReceipt): boolean {
  return (
    r.is_active &&
    (order.value?.payments.some((p) => p.payment_id === r.payment_id && p.accepts_receipts) ??
      false)
  );
}

const cancelReceiptDialog = ref(false);
const cancelTarget = ref<PaymentReceipt | null>(null);
const cancelReason = ref('');
const cancelling = ref(false);
const cancelError = ref<string | null>(null);

function openCancelReceipt(r: PaymentReceipt) {
  cancelTarget.value = r;
  cancelReason.value = '';
  cancelError.value = null;
  cancelReceiptDialog.value = true;
}

async function submitCancelReceipt() {
  if (!cancelTarget.value) return;
  cancelling.value = true;
  cancelError.value = null;
  try {
    await cancelReceipt(cancelTarget.value.id, cancelReason.value.trim());
    cancelReceiptDialog.value = false;
    refundNotice.value = 'Versement annulé.';
    await load();
  } catch (err) {
    cancelError.value = extractApiError(err) ?? 'Annulation impossible.';
  } finally {
    cancelling.value = false;
  }
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    order.value = await getOrder(orderId.value);
    await loadStoreCredit();
    departures.value = await listDepartures().catch(() => []);
    statusNames.value = await listOrderStatuses().catch(() => []);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
  await loadJourney();
}

// --- Transport (journey legs) ---
const journey = ref<JourneyLeg[]>([]);
const journeyLoading = ref(false);
const journeyError = ref<string | null>(null);
const journeyNotice = ref<string | null>(null);
const carriers = ref<Carrier[]>([]);

function prettifyMode(mode: string): string {
  return mode.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

async function loadJourney() {
  journeyLoading.value = true;
  journeyError.value = null;
  try {
    journey.value = await getOrderJourney(orderId.value);
  } catch (err) {
    // 404 = no tracked leg yet (e.g. an order placed before the logistics
    // phase): an empty table, not an error banner.
    journey.value = [];
    const msg = extractApiError(err);
    if (msg && !/aucun tronçon/i.test(msg)) journeyError.value = msg;
  } finally {
    journeyLoading.value = false;
  }
}

const shipDialog = ref(false);
const shipTarget = ref<JourneyLeg | null>(null);
const shipRef = ref('');
const shipCarrierId = ref<string | null>(null);
const shipping = ref(false);
const shipError = ref<string | null>(null);

const carrierOptions = computed<{ label: string; value: string | null }[]>(() => [
  { label: '— Suivi interne (sans transporteur) —', value: null },
  ...carriers.value.map((c) => ({ label: c.name, value: c.id })),
]);

async function openShip(leg: JourneyLeg) {
  shipTarget.value = leg;
  shipRef.value = leg.tracking_ref ?? '';
  shipCarrierId.value = leg.carrier_id;
  shipError.value = null;
  shipDialog.value = true;
  if (carriers.value.length === 0) {
    try {
      carriers.value = await listCarriers();
    } catch {
      // The selector still offers « suivi interne ».
    }
  }
}

async function submitShip() {
  if (!shipTarget.value) return;
  shipping.value = true;
  shipError.value = null;
  try {
    await shipTracking(
      shipTarget.value.tracking_id,
      shipRef.value.trim() || null,
      shipCarrierId.value,
    );
    shipDialog.value = false;
    journeyNotice.value = 'Remise au transporteur enregistrée (client notifié).';
    await loadJourney();
  } catch (err) {
    shipError.value = extractApiError(err) ?? 'Expédition impossible.';
  } finally {
    shipping.value = false;
  }
}

async function advanceLeg(leg: JourneyLeg) {
  journeyError.value = null;
  try {
    const result = await advanceTracking(leg.tracking_id);
    journeyNotice.value = result.message;
    await loadJourney();
  } catch (err) {
    journeyError.value = extractApiError(err) ?? 'Progression impossible.';
  }
}

async function deliverLeg(leg: JourneyLeg) {
  journeyError.value = null;
  try {
    await deliverTracking(leg.tracking_id);
    journeyNotice.value = 'Colis marqué livré (client notifié).';
    await loadJourney();
  } catch (err) {
    journeyError.value = extractApiError(err) ?? 'Livraison impossible.';
  }
}

// --- Refund ---
const refundDialog = ref(false);
const refundTarget = ref<AdminOrderPaymentItem | null>(null);
const refundAmount = ref<number | null>(null);
const refundReason = ref('');
const refunding = ref(false);
const refundError = ref<string | null>(null);
const refundNotice = ref<string | null>(null);

/**
 * Show the refund button only when the backend says so: the provider supports
 * an in-app refund (card / PayZen) and the payment is in a refundable state.
 * Manual / document payments are refunded out-of-band, so no button is shown.
 */
function canRefund(p: AdminOrderPaymentItem): boolean {
  return p.can_refund === true;
}

function openRefund(p: AdminOrderPaymentItem) {
  refundTarget.value = p;
  refundAmount.value = null;
  refundReason.value = '';
  refundError.value = null;
  refundDialog.value = true;
}

async function submitRefund() {
  if (!refundTarget.value) return;
  refunding.value = true;
  refundError.value = null;
  try {
    const amount =
      typeof refundAmount.value === 'number' && !Number.isNaN(refundAmount.value)
        ? refundAmount.value
        : null;
    const result = await refundPayment(refundTarget.value.payment_id, {
      amount,
      reason: refundReason.value.trim() || null,
    });
    refundDialog.value = false;
    refundNotice.value =
      result.message ??
      (result.fully_refunded ? 'Remboursement total effectué.' : 'Remboursement effectué.');
    await load();
  } catch (err) {
    refundError.value = extractApiError(err) ?? 'Remboursement impossible.';
  } finally {
    refunding.value = false;
  }
}

// --- Capture (deferred CB debit) ---
const capturingId = ref<string | null>(null);

/** Only authorised (not-yet-debited) card payments can be captured. */
function canCapture(p: AdminOrderPaymentItem): boolean {
  return p.status === 'Authorized';
}

async function captureRow(p: AdminOrderPaymentItem) {
  capturingId.value = p.payment_id;
  error.value = null;
  try {
    const result = await capturePayment(p.payment_id);
    refundNotice.value = result.message ?? 'Paiement capturé.';
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Capture impossible.';
  } finally {
    capturingId.value = null;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
// Fiche commande : contenu principal à gauche, récapitulatif et client à droite.
.order-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 40px;
  align-items: start;

  @media (max-width: 1199px) {
    grid-template-columns: minmax(0, 1fr);
  }
}

.order-main {
  min-width: 0;
}

.order-margin {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
  margin-top: 10px;
  font-size: 13px;

  strong {
    font-size: 15px;
    color: var(--n-ok);
  }

  strong.text-negative {
    color: var(--n-danger);
  }
}

.order-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.order-panel__head {
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.order-panel__fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.order-panel__wrap {
  overflow-wrap: anywhere;
  white-space: pre-line;
}

.order-deposit {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--n-line);
}

.order-deposit__caption {
  display: block;
  font-size: 12px;
  color: var(--n-ink-3);
}

// Tronçon en cours : repère discret dans le tableau de transport.
.leg--current > td {
  background: var(--n-tile);
}

.receipt--cancelled td {
  color: var(--n-ink-3);
  text-decoration: line-through;
  text-decoration-color: var(--n-line-2);
}

.receipt--cancelled td:last-child {
  text-decoration: none;
}

.order-receipts {
  margin-top: 24px;
}
</style>
