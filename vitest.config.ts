import { defineConfig } from 'vitest/config'

// Unit tests + coverage for the shared engine (@app/utils: currency / pricing /
// date helpers shared by the storefront and admin apps). The Quasar apps are
// covered by typecheck + lint in CI; this is the "frontend" coverage badge.
export default defineConfig({
  test: {
    // Le moteur partagé, plus les tests unitaires purement TS de la vitrine
    // (config légale…) : il n'existait aucun point d'entrée pour eux.
    include: ['shared/**/src/**/*.test.ts', 'frontend/src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary', 'json'],
      reportsDirectory: './coverage',
      include: ['shared/utils/src/**/*.ts'],
      exclude: ['**/*.test.ts', '**/index.ts', 'shared/utils/src/i18n/**'],
    },
  },
})
