declare namespace NodeJS {
  interface ProcessEnv {
    NODE_ENV: string;
    VUE_ROUTER_MODE: 'hash' | 'history' | 'abstract' | undefined;
    VUE_ROUTER_BASE: string | undefined;
    VITE_API_URL: string;
    VITE_PUBLIC_SITE_URL: string | undefined;
    VITE_OAUTH_ENABLED: string | undefined;
  }
}

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_PUBLIC_SITE_URL: string | undefined;
  readonly VITE_OAUTH_ENABLED: string | undefined;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
  readonly hot?: {
    readonly data: Record<string, unknown>;
    accept(): void;
    accept(cb: (mod: unknown) => void): void;
    dispose(cb: (data: Record<string, unknown>) => void): void;
    decline(): void;
    invalidate(): void;
  };
}

// Feuille de style de la police d'icônes Phosphor (import pour effet de bord).
declare module '@phosphor-icons/web/light';
