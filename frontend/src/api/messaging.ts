import { api } from '@/boot/api';
import type { components } from '@app/api-types';

export type MessagingInfo = components['schemas']['MessagingInfo'];
export type ConversationSummary = components['schemas']['ConversationSummary'];
export type ConversationDetail = components['schemas']['ConversationDetail'];
export type ConversationCreate = components['schemas']['ConversationCreate'];

/** Canaux, motifs, horaires et délai de réponse affiché (public). */
export async function getMessagingInfo(): Promise<MessagingInfo> {
  const { data } = await api.get<MessagingInfo>('/messaging/info');
  return data;
}

export async function listMyConversations(): Promise<ConversationSummary[]> {
  const { data } = await api.get<ConversationSummary[]>('/me/conversations');
  return data;
}

export async function getMyUnreadCount(): Promise<number> {
  const { data } = await api.get<{ count: number }>('/me/conversations/unread');
  return data.count;
}

export async function openConversation(payload: ConversationCreate): Promise<ConversationDetail> {
  const { data } = await api.post<ConversationDetail>('/me/conversations', payload);
  return data;
}

/** La conversation, ou seulement les messages arrivés après `after`. */
export async function getMyConversation(id: string, after?: string): Promise<ConversationDetail> {
  const { data } = await api.get<ConversationDetail>(`/me/conversations/${id}`, {
    params: after ? { after } : {},
  });
  return data;
}

export async function postMyMessage(id: string, body: string): Promise<ConversationDetail> {
  const { data } = await api.post<ConversationDetail>(`/me/conversations/${id}/messages`, {
    body,
  });
  return data;
}

export async function markConversationRead(id: string): Promise<void> {
  await api.post(`/me/conversations/${id}/read`);
}

export async function resolveMyConversation(id: string): Promise<ConversationSummary> {
  const { data } = await api.post<ConversationSummary>(`/me/conversations/${id}/resolve`);
  return data;
}
