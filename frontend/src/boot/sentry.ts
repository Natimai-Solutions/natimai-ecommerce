import { defineBoot } from '#q-app';
import * as Sentry from '@sentry/vue';

/**
 * Error monitoring of the browser side (R8 / U3). Active only when the build
 * carries `VITE_SENTRY_DSN` (deploy: GitHub environment variable); nothing is
 * loaded otherwise. Client only: the SSR process reports through the API's
 * own Sentry. 10 % of the page loads are traced, like the backend.
 */
export default defineBoot(({ app, router }) => {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn || import.meta.env.SSR || typeof window === 'undefined') return;
  Sentry.init({
    app,
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || import.meta.env.MODE,
    release: import.meta.env.VITE_APP_RELEASE || undefined,
    integrations: [Sentry.browserTracingIntegration({ router })],
    tracesSampleRate: 0.1,
  });
});
