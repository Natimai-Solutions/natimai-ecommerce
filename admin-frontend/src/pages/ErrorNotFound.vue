<template>
  <main class="not-found">
    <div class="app-result">
      <q-icon name="ph:compass" size="44px" class="app-result__icon" />
      <h1>Page introuvable</h1>
      <p>Cette adresse ne correspond à aucun écran de l'administration.</p>
      <div class="app-result__actions">
        <q-btn color="primary" unelevated no-caps label="Tableau de bord" to="/" />
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
