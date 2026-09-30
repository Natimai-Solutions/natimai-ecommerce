import { api } from '@/boot/api';

/** `GET /admin/modules` — un module activable, son interrupteur et son état réel. */
export interface ModuleState {
  key: string;
  label: string;
  description: string;
  group: string;
  /** Ce que l'admin a choisi. */
  switched_on: boolean;
  /** Ce que la boutique fait réellement (interrupteur ET configuration serveur). */
  enabled: boolean;
  /** Valeur d'une installation neuve dans le mode actuel (simple / complet). */
  preset: boolean;
  /** Variable d'environnement qui garde le module éteint quel que soit l'interrupteur. */
  blocked_by_env: string | null;
}

export async function listModules(): Promise<ModuleState[]> {
  const { data } = await api.get<ModuleState[]>('/admin/modules');
  return data;
}

export async function setModuleEnabled(key: string, enabled: boolean): Promise<ModuleState> {
  const { data } = await api.put<ModuleState>(`/admin/modules/${key}`, { enabled });
  return data;
}
