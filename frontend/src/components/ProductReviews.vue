<template>
  <section class="reviews" aria-labelledby="reviews-title" data-testid="product-reviews">
    <h2 id="reviews-title" class="reviews__title">{{ $t('reviews.title') }}</h2>

    <div v-if="loading" class="reviews__summary" aria-busy="true">
      <q-skeleton type="text" width="40%" />
    </div>
    <template v-else>
      <div v-if="summary.count > 0" class="reviews__summary" data-testid="reviews-summary">
        <div class="reviews__average">
          <span class="reviews__average-value font-mono">{{ formatAverage(summary.average) }}</span>
          <StarRating :value="summary.average ?? 0" />
          <span class="reviews__count">
            {{ $t('reviews.count', { n: summary.count }, summary.count) }}
          </span>
        </div>
        <ul class="reviews__bars">
          <li v-for="star in [5, 4, 3, 2, 1]" :key="star" class="reviews__bar">
            <span class="font-mono">{{ star }}</span>
            <span class="reviews__bar-track" aria-hidden="true">
              <span class="reviews__bar-fill" :style="{ width: barWidth(star) }" />
            </span>
            <span class="reviews__bar-count font-mono">{{ distribution(star) }}</span>
          </li>
        </ul>
      </div>
      <p v-else class="reviews__empty">{{ $t('reviews.none') }}</p>

      <ol v-if="reviews.length > 0" class="reviews__list">
        <li v-for="review in reviews" :key="review.id" class="reviews__item">
          <div class="reviews__item-head">
            <StarRating :value="review.rating" />
            <span class="reviews__author">{{ review.author_name ?? $t('reviews.customer') }}</span>
            <span v-if="review.verified_purchase" class="reviews__verified">
              <q-icon name="ph:seal-check" size="14px" />
              {{ $t('reviews.verified') }}
            </span>
            <time v-if="review.created_at" class="reviews__date" :datetime="review.created_at">
              {{ formatDate(review.created_at) }}
            </time>
          </div>
          <p v-if="review.comment" class="reviews__comment">{{ review.comment }}</p>
        </li>
      </ol>
      <q-btn
        v-if="reviews.length < summary.count"
        flat
        no-caps
        color="primary"
        :label="$t('reviews.more')"
        :loading="loadingMore"
        @click="loadMore"
      />
    </template>

    <!-- Les acheteurs donnent leur avis ; il est publié après modération. -->
    <div v-if="mine?.can_review" class="reviews__form" data-testid="review-form">
      <h3 class="reviews__form-title">
        {{ mine.review ? $t('reviews.edit_title') : $t('reviews.write_title') }}
      </h3>
      <AppNotice v-if="mine.review" :tone="statusTone" dense data-testid="review-status">
        {{ $t(`reviews.status_${mine.review.status}`) }}
      </AppNotice>
      <fieldset class="reviews__stars-input">
        <legend class="sr-only">{{ $t('reviews.rating') }}</legend>
        <button
          v-for="star in 5"
          :key="star"
          type="button"
          class="reviews__star-btn"
          :class="{ 'reviews__star-btn--on': star <= draftRating }"
          :aria-label="$t('reviews.stars', { n: star }, star)"
          :aria-pressed="draftRating === star"
          :data-testid="`review-star-${star}`"
          @click="draftRating = star"
        >
          ★
        </button>
      </fieldset>
      <q-input
        v-model="draftComment"
        type="textarea"
        outlined
        autogrow
        maxlength="1000"
        counter
        :label="$t('reviews.comment')"
        data-testid="review-comment"
      />
      <AppNotice v-if="formError" tone="error" dense>{{ formError }}</AppNotice>
      <div class="reviews__form-actions">
        <q-btn
          unelevated
          no-caps
          color="primary"
          :label="$t('reviews.submit')"
          :disable="draftRating < 1"
          :loading="saving"
          data-testid="review-submit"
          @click="onSubmit"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { formatDate } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import StarRating from '@/components/StarRating.vue';
import {
  getMyReview,
  getProductReviews,
  putMyReview,
  type MyReviewState,
  type PublishedReview,
} from '@/api/reviews';
import { useAuthStore } from '@/stores/auth';
import { apiErrorMessage } from '@/utils/errors';

/**
 * « Avis clients » on the product page: the approved reviews and their
 * summary for everyone; for a signed-in buyer, their own review (written or
 * edited, published once the shop approves it).
 */
const props = defineProps<{ productId: string }>();

const PAGE = 10;
const { t, locale } = useI18n();
const auth = useAuthStore();

const loading = ref(true);
const loadingMore = ref(false);
const reviews = ref<PublishedReview[]>([]);
const summary = ref<{
  count: number;
  average: number | null;
  distribution: Record<string, number>;
}>({ count: 0, average: null, distribution: {} });
const mine = ref<MyReviewState | null>(null);
const draftRating = ref(0);
const draftComment = ref('');
const saving = ref(false);
const formError = ref<string | null>(null);

const statusTone = computed(() => {
  const status = mine.value?.review?.status;
  if (status === 'approved') return 'success';
  if (status === 'rejected') return 'warning';
  return 'info';
});

function formatAverage(value: number | null | undefined): string {
  return (value ?? 0).toLocaleString(locale.value, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function distribution(star: number): number {
  return summary.value.distribution[String(star)] ?? 0;
}

function barWidth(star: number): string {
  return summary.value.count ? `${(distribution(star) / summary.value.count) * 100}%` : '0%';
}

async function load() {
  loading.value = true;
  try {
    const page = await getProductReviews(props.productId, { limit: PAGE });
    reviews.value = page.data ?? [];
    summary.value = {
      count: page.summary.count ?? 0,
      average: page.summary.average ?? null,
      distribution: page.summary.distribution ?? {},
    };
  } catch {
    reviews.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  loadingMore.value = true;
  try {
    const page = await getProductReviews(props.productId, {
      skip: reviews.value.length,
      limit: PAGE,
    });
    reviews.value.push(...(page.data ?? []));
  } finally {
    loadingMore.value = false;
  }
}

async function loadMine() {
  if (!auth.isAuthenticated) {
    mine.value = null;
    return;
  }
  try {
    mine.value = await getMyReview(props.productId);
    draftRating.value = mine.value.review?.rating ?? 0;
    draftComment.value = mine.value.review?.comment ?? '';
  } catch {
    mine.value = null;
  }
}

async function onSubmit() {
  saving.value = true;
  formError.value = null;
  try {
    mine.value = await putMyReview(props.productId, {
      rating: draftRating.value,
      comment: draftComment.value.trim() || null,
    });
  } catch (err) {
    formError.value = apiErrorMessage(err) ?? t('reviews.save_failed');
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void load();
  void loadMine();
});
watch(
  () => props.productId,
  () => {
    void load();
    void loadMine();
  },
);
watch(
  () => auth.isAuthenticated,
  () => void loadMine(),
);
</script>

<style scoped lang="scss">
.reviews {
  display: grid;
  gap: 20px;
}

.reviews__title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.reviews__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 40px;
  align-items: center;
}

.reviews__average {
  display: grid;
  gap: 4px;
  justify-items: start;
}

.reviews__average-value {
  font-size: 2rem;
  line-height: 1;
}

.reviews__count,
.reviews__empty,
.reviews__date {
  margin: 0;
  font-size: 13px;
  color: var(--n-ink-3);
}

.reviews__bars {
  display: grid;
  gap: 4px;
  min-width: 220px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.reviews__bar {
  display: grid;
  grid-template-columns: 12px 1fr 28px;
  gap: 8px;
  align-items: center;
  font-size: 12px;
}

.reviews__bar-track {
  height: 6px;
  border-radius: 3px;
  background: var(--n-line);
  overflow: hidden;
}

.reviews__bar-fill {
  display: block;
  height: 100%;
  background: var(--n-warn);
}

.reviews__bar-count {
  color: var(--n-ink-3);
  text-align: right;
}

.reviews__list {
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.reviews__item {
  padding: 16px 0;
  border-top: 1px solid var(--n-line);
}

.reviews__item-head {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  align-items: center;
}

.reviews__author {
  font-weight: 600;
  font-size: 14px;
}

.reviews__verified {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  font-size: 12px;
  color: var(--n-ok);
}

.reviews__comment {
  margin: 8px 0 0;
  white-space: pre-line;
  color: var(--n-ink-2);
}

.reviews__form {
  display: grid;
  gap: 12px;
  max-width: 560px;
  padding: 20px;
  border: 1px solid var(--n-line);
  border-radius: var(--n-radius);
}

.reviews__form-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.reviews__stars-input {
  display: flex;
  gap: 4px;
  margin: 0;
  padding: 0;
  border: 0;
}

.reviews__star-btn {
  padding: 0 2px;
  border: 0;
  background: transparent;
  color: var(--n-line-2);
  font-size: 28px;
  line-height: 1;
  cursor: pointer;

  &--on {
    color: var(--n-warn);
  }

  &:focus-visible {
    outline: 2px solid var(--n-accent);
    outline-offset: 2px;
    border-radius: var(--n-radius-sm);
  }
}

.reviews__form-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
