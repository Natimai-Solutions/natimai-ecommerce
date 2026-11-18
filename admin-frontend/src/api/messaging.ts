import { api } from '@/boot/api';
import type { components } from '@app/api-types';

export type StaffConversation = components['schemas']['StaffConversation'];
export type StaffConversationDetail = components['schemas']['StaffConversationDetail'];
export type ConversationPage = components['schemas']['ConversationPage'];
export type ConversationSummaryCounts = components['schemas']['Summary'];
export type TeamMember = components['schemas']['TeamMember'];
export type ConversationTab = 'todo' | 'mine' | 'pending' | 'resolved' | 'all';

export async function listConversations(params: {
  tab: ConversationTab;
  channel?: string | null;
  q?: string | null;
  skip?: number;
  limit?: number;
}): Promise<ConversationPage> {
  const { data } = await api.get<ConversationPage>('/admin/conversations', { params });
  return data;
}

export async function conversationsSummary(): Promise<ConversationSummaryCounts> {
  const { data } = await api.get<ConversationSummaryCounts>('/admin/conversations/summary');
  return data;
}

/** Who a conversation of ``channel`` can be transferred to. */
export async function conversationTeam(channel?: string): Promise<TeamMember[]> {
  const { data } = await api.get<TeamMember[]>('/admin/conversations/team', {
    params: channel ? { channel } : {},
  });
  return data;
}

export async function getConversation(
  id: string,
  after?: string,
): Promise<StaffConversationDetail> {
  const { data } = await api.get<StaffConversationDetail>(`/admin/conversations/${id}`, {
    params: after ? { after } : {},
  });
  return data;
}

export async function postStaffMessage(
  id: string,
  body: string,
  kind: 'message' | 'note',
): Promise<StaffConversationDetail> {
  const { data } = await api.post<StaffConversationDetail>(`/admin/conversations/${id}/messages`, {
    body,
    kind,
  });
  return data;
}

export async function readConversation(id: string): Promise<void> {
  await api.post(`/admin/conversations/${id}/read`);
}

type Action = 'claim' | 'release' | 'resolve';

export async function conversationAction(
  id: string,
  action: Action,
  force = false,
): Promise<StaffConversationDetail> {
  const { data } = await api.post<StaffConversationDetail>(
    `/admin/conversations/${id}/${action}`,
    null,
    { params: force ? { force: true } : {} },
  );
  return data;
}

export async function transferConversation(
  id: string,
  userId: string,
  force = false,
): Promise<StaffConversationDetail> {
  const { data } = await api.post<StaffConversationDetail>(`/admin/conversations/${id}/transfer`, {
    user_id: userId,
    force,
  });
  return data;
}

export async function moveConversation(
  id: string,
  channel: string,
  topic: string,
): Promise<StaffConversationDetail> {
  const { data } = await api.put<StaffConversationDetail>(`/admin/conversations/${id}/topic`, {
    channel,
    topic,
  });
  return data;
}

/** Channels and their topics, in display order (mirrors the backend). */
export const CHANNEL_TOPICS: Record<string, string[]> = {
  customer_service: ['order_tracking', 'delivery', 'payment_invoice', 'account'],
  technical: ['setup_usage', 'fault', 'warranty_return'],
  sales: ['pre_sale', 'quote', 'volume', 'price_group'],
};

export async function postStaffFile(
  id: string,
  file: File,
  body: string,
  kind: 'message' | 'note',
): Promise<StaffConversationDetail> {
  const form = new FormData();
  form.append('file', file);
  form.append('body', body);
  form.append('kind', kind);
  const { data } = await api.post<StaffConversationDetail>(
    `/admin/conversations/${id}/attachments`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}

export async function downloadStaffFile(
  conversationId: string,
  attachmentId: string,
  filename: string,
): Promise<void> {
  const { data } = await api.get<Blob>(
    `/admin/conversations/${conversationId}/attachments/${attachmentId}`,
    { responseType: 'blob' },
  );
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
