import type { components } from '@app/api-types';
import { api } from '@/boot/api';

export type ProductReviewsResponse = components['schemas']['ProductReviewsResponse'];
export type PublishedReview = components['schemas']['PublishedReview'];
export type MyReviewState = components['schemas']['MyReviewState'];

/** Approved reviews of a product, newest first, with their summary. */
export async function getProductReviews(
  productId: string,
  options: { skip?: number; limit?: number } = {},
): Promise<ProductReviewsResponse> {
  const { data } = await api.get<ProductReviewsResponse>(`/reviews/product/${productId}`, {
    params: { skip: options.skip ?? 0, limit: options.limit ?? 10 },
  });
  return data;
}

/** May the signed-in customer review this product, and their review if any. */
export async function getMyReview(productId: string): Promise<MyReviewState> {
  const { data } = await api.get<MyReviewState>(`/reviews/product/${productId}/mine`);
  return data;
}

/** Write or edit the review; it waits for the shop's moderation. */
export async function putMyReview(
  productId: string,
  payload: { rating: number; comment: string | null },
): Promise<MyReviewState> {
  const { data } = await api.put<MyReviewState>(`/reviews/product/${productId}/mine`, payload);
  return data;
}

export async function deleteMyReview(productId: string): Promise<void> {
  await api.delete(`/reviews/product/${productId}/mine`);
}
