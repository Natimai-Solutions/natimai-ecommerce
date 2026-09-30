// Variables d'environnement exposées au code client (préfixe `VITE_`, voir
// quasar.config.ts > build > env.clientPrefix). Les constantes propres à Quasar
// (import.meta.env.QUASAR_DEV, QUASAR_SERVER…) sont typées par @quasar/app-vite.
interface ImportMetaEnv {
  readonly VITE_API_URL: string;
}
