import { api } from '@/boot/api';

interface OkMessage {
  message: string;
}

/**
 * Demander un lien de réinitialisation.
 *
 * Le backend répond la même chose que l'adresse ait un compte ou non — c'est
 * délibéré, sinon l'endpoint devient un test d'existence de compte. L'interface
 * doit donc afficher ce message tel quel, sans chercher à en déduire davantage.
 */
export async function requestPasswordReset(email: string): Promise<string> {
  const { data } = await api.post<OkMessage>('/login/forgot-password', { email });
  return data.message;
}

export async function resetPassword(token: string, password: string): Promise<string> {
  const { data } = await api.post<OkMessage>('/login/reset-password', { token, password });
  return data.message;
}
