<template>
  <ul class="brand-strip" data-testid="home-brands">
    <li v-for="brand in brands" :key="brand.id">
      <router-link :to="`/marque/${brand.slug}`" class="brand-strip__item" :title="brand.name">
        <img
          :src="brand.logo"
          :srcset="brand.logo_srcset ?? undefined"
          sizes="120px"
          :alt="brand.name"
          loading="lazy"
        />
      </router-link>
    </li>
  </ul>
</template>

<script setup lang="ts">
import type { components } from '@app/api-types';

type Brand = components['schemas']['HomepageBrandTile'];

defineProps<{ brands: Brand[] }>();
</script>

<style scoped lang="scss">
.brand-strip {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
}

.brand-strip__item {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 80px;
  padding: 12px 16px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
  // Logos are drawn for a light background: a light tile in both themes.
  background: var(--n-paper);

  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }

  &:hover {
    border-color: var(--n-line-2);
  }
}

@media (max-width: 599px) {
  .brand-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .brand-strip__item {
    height: 64px;
    padding: 8px;
  }
}
</style>
