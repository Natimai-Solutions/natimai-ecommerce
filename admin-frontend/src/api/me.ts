import { api } from '@/boot/api';

/** `GET /users/me` — identité de la personne connectée (en-tête de l'admin). */
export interface Me {
  id: string;
  email: string;
  full_name: string | null;
}

export async function getMe(): Promise<Me> {
  const { data } = await api.get<Me>('/users/me');
  return data;
}
