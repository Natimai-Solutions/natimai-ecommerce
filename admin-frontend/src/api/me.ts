import { api } from '@/boot/api';

/** `GET /users/me` — identité de la personne connectée (en-tête de l'admin). */
export interface Me {
  id: string;
  email: string;
  full_name: string | null;
  /** Accès du back-office (lot ROLE). */
  is_superuser?: boolean;
  staff_role?: string | null;
}

export async function getMe(): Promise<Me> {
  const { data } = await api.get<Me>('/users/me');
  return data;
}
