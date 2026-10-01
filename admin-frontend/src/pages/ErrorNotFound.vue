<template>
  <main class="not-found">
    <div class="app-result">
      <q-icon name="ph:compass" size="44px" class="app-result__icon" />
      <h1>{{ $t('not_found.title') }}</h1>
      <p>{{ $t('not_found.hint') }}</p>
      <div class="app-result__actions">
        <q-btn color="primary" unelevated no-caps :label="$t('not_found.dashboard')" to="/" />
      </div>
    </div>
  </main>
</template>

<style scoped>
.not-found {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--n-bg);
}
</style>
