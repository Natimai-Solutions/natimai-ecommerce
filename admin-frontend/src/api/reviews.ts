import type { components } from '@app/api-types';
import { api } from '@/boot/api';

export type ReviewToModerate = components['schemas']['ReviewToModerate'];
export type ReviewStatus = 'pending' | 'approved' | 'rejected';

/** Reviews by moderation status, pending ones first-come first-served. */
export async function listReviews(
  status: ReviewStatus,
  options: { skip?: number; limit?: number } = {},
): Promise<{ data: ReviewToModerate[]; count: number }> {
  const { data } = await api.get<{ data?: ReviewToModerate[]; count?: number }>('/reviews/admin', {
    params: { status, skip: options.skip ?? 0, limit: options.limit ?? 50 },
  });
  return { data: data.data ?? [], count: data.count ?? 0 };
}

/** Publish (approve) or reject a review; the note is kept for the shop. */
export async function moderateReview(
  id: string,
  decision: 'approve' | 'reject',
  note?: string | null,
): Promise<ReviewToModerate> {
  const { data } = await api.post<ReviewToModerate>(`/reviews/admin/${id}/moderate`, {
    decision,
    note: note ?? null,
  });
  return data;
}
