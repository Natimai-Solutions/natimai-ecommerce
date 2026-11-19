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

/** « Garder un an de plus » : repousse la suppression d'un an. */
export async function keepMyConversation(id: string): Promise<string> {
  const { data } = await api.post<{ retain_until: string }>(`/me/conversations/${id}/keep`);
  return data.retain_until;
}

/** La conversation en texte (messages seulement), téléchargée par le navigateur. */
export async function downloadMyConversation(id: string, number: string): Promise<void> {
  const { data } = await api.get<Blob>(`/me/conversations/${id}/export`, {
    responseType: 'blob',
  });
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${number}.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

/** Envoie un fichier (photo, PDF) avec un texte facultatif. */
export async function postMyFile(id: string, file: File, body = ''): Promise<ConversationDetail> {
  const form = new FormData();
  form.append('file', file);
  form.append('body', body);
  const { data } = await api.post<ConversationDetail>(`/me/conversations/${id}/attachments`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

/** Télécharge un fichier de la conversation. */
export async function downloadMyFile(
  conversationId: string,
  attachmentId: string,
  filename: string,
): Promise<void> {
  const { data } = await api.get<Blob>(
    `/me/conversations/${conversationId}/attachments/${attachmentId}`,
    { responseType: 'blob' },
  );
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export type ContactRequest = components['schemas']['ContactRequest'];
export type ContinueInfo = components['schemas']['ContinueInfo'];

/** Formulaire de contact public : réponse identique quoi qu'il arrive. */
export async function sendContact(
  payload: ContactRequest,
  headers: Record<string, string>,
): Promise<void> {
  await api.post('/contact', payload, { headers });
}

/** Ce qu'ouvre le lien d'une réponse de l'équipe. */
export async function getContinueInfo(token: string): Promise<ContinueInfo> {
  const { data } = await api.get<ContinueInfo>(`/contact/continue/${token}`);
  return data;
}

/** Crée le compte de l'adresse du lien et ouvre la session (jeton d'accès). */
export async function continueWithSignup(
  token: string,
  password: string,
  fullName: string | null,
): Promise<string> {
  const { data } = await api.post<{ access_token: string }>(`/contact/continue/${token}/signup`, {
    password,
    full_name: fullName,
  });
  return data.access_token;
}

/** Connecté avec le compte de cette adresse : rattache les conversations. */
export async function continueSignedIn(token: string): Promise<string> {
  const { data } = await api.post<{ conversation_id: string }>(`/contact/continue/${token}/claim`);
  return data.conversation_id;
}
