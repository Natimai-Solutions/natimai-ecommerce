// Variables d'environnement exposées au code client (préfixe `VITE_`, voir
// quasar.config.ts > build > env.clientPrefix). Les constantes propres à Quasar
// (import.meta.env.QUASAR_DEV, QUASAR_SERVER…) sont typées par @quasar/app-vite.
interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  /** Sentry DSN of this front; empty = no monitoring (R8 / U3). */
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_SENTRY_ENVIRONMENT?: string;
  readonly VITE_APP_RELEASE?: string;
}

// Feuille de style d'icônes sans déclaration de types (import pour effet de bord).
declare module '@phosphor-icons/web/light';
