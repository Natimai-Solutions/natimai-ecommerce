import { api } from '@/boot/api';

/** Origine de la valeur en vigueur. */
export type SettingSource = 'db' | 'env' | 'default';
export type SettingType = 'bool' | 'int' | 'float' | 'decimal' | 'str' | 'text' | 'list';

/** Un réglage déclaré dans le registre (R5), résolu. */
export interface RuntimeSetting {
  key: string;
  category: string;
  label: string;
  description: string;
  type: SettingType;
  /** Valeur en vigueur, en texte (masquée pour un secret). */
  value: string;
  source: SettingSource;
  /** Ce qui s'applique sans valeur saisie (environnement ou défaut). */
  fallback: string;
  env_var: string | null;
  stored_invalid: boolean;
  public: boolean;
  secret: boolean;
  restart_required: boolean;
  reprices: boolean;
  choices: string[] | null;
  minimum: string | number | null;
  maximum: string | number | null;
  below: string | number | null;
  max_length: number | null;
  unit: string | null;
  order: number;
  updated_at: string | null;
  updated_by_email: string | null;
}

export interface SettingCategory {
  key: string;
  label: string;
  hint: string;
}

/** Valeur renvoyée à la place d'un secret : la renvoyer ne change rien. */
export const SECRET_MASK = '••••••';

export async function listSystemSettings(): Promise<RuntimeSetting[]> {
  const { data } = await api.get<RuntimeSetting[]>('/admin/system-settings');
  return data;
}

export async function listSettingCategories(): Promise<SettingCategory[]> {
  const { data } = await api.get<SettingCategory[]>('/admin/system-settings/categories');
  return data;
}

/** Enregistrer une valeur (vide : retour à l'environnement / au défaut). */
export async function updateSystemSetting(
  key: string,
  payload: { value: string },
): Promise<RuntimeSetting> {
  const { data } = await api.put<RuntimeSetting>(`/admin/system-settings/${key}`, payload);
  return data;
}

/** Oublier la valeur saisie : l'environnement ou le défaut s'applique. */
export async function resetSystemSetting(key: string): Promise<RuntimeSetting> {
  const { data } = await api.delete<RuntimeSetting>(`/admin/system-settings/${key}`);
  return data;
}
