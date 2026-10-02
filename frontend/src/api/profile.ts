import { api } from '@/boot/api';

/** Identité du client connecté (`GET /users/me`). */
export interface MyProfile {
  id: string;
  email: string;
  full_name: string | null;
  phone: string | null;
  is_verified: boolean;
  created_at: string | null;
}

export interface MyProfileUpdate {
  full_name?: string | null;
  phone?: string | null;
}

export async function getMyProfile(): Promise<MyProfile> {
  const { data } = await api.get<MyProfile>('/users/me');
  return data;
}

export async function updateMyProfile(payload: MyProfileUpdate): Promise<MyProfile> {
  const { data } = await api.patch<MyProfile>('/users/me', payload);
  return data;
}

/**
 * Change le mot de passe. Toutes les sessions sont fermées ensuite, celle-ci
 * comprise : l'appelant reconduit le client vers la connexion.
 */
export async function changeMyPassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await api.post('/users/me/password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

/**
 * Download everything the shop holds about me as a JSON file (R8 / U8). The
 * file travels as a blob so the bearer token goes with the request.
 */
export async function downloadMyData(): Promise<void> {
  const response = await api.get<Blob>('/users/me/export', { responseType: 'blob' });
  const disposition = String(response.headers['content-disposition'] ?? '');
  const match = /filename="([^"]+)"/.exec(disposition);
  const url = URL.createObjectURL(response.data);
  try {
    const link = document.createElement('a');
    link.href = url;
    link.download = match?.[1] ?? 'mes-donnees.json';
    document.body.appendChild(link);
    link.click();
    link.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Erase my account (R8 / U8): the e-mail typed back, and the password when
 * the account has one. Every session is closed afterwards.
 */
export async function deleteMyAccount(confirmation: string, password: string): Promise<void> {
  await api.post('/users/me/delete', {
    confirmation,
    password: password || null,
  });
}
