<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const drawer = ref(false)
const route = useRoute()
const appBase = useRuntimeConfig().app.baseURL
const brandLogoSrc = `${appBase}android-chrome-192x192.png`

// Static items never depend on auth.user, so they render identically on SSR
// and client and are safe to render during SSR (no hydration mismatch).
const baseNavItems = [
  { title: 'Панель', to: '/dashboard', icon: 'mdi-view-dashboard-outline' },
  { title: 'Конструктор', to: '/', icon: 'mdi-graph' },
  { title: 'Протоколы', to: '/protocols', icon: 'mdi-book-open-page-variant-outline' },
  { title: 'RAG Чат', to: '/rag', icon: 'mdi-brain' },
]

// Role-dependent items rely on auth.user, which is not reliably resolved during
// SSR (the JWT lives in the mc_access cookie and fetchMe is async). Rendering
// them only on the client (via <ClientOnly>) keeps SSR/hydration in sync.
const roleNavItems = computed(() => {
  const items = []
  if (auth.user?.role === 'teacher' || auth.user?.role === 'admin') {
    items.push({ title: 'Генератор задач', to: '/teacher/generator', icon: 'mdi-auto-fix' })
    items.push({ title: 'Проверка', to: '/teacher/review', icon: 'mdi-clipboard-check-outline' })
    items.push({ title: 'Метрики', to: '/teacher/benchmarks', icon: 'mdi-chart-box-outline' })
  }
  if (auth.user?.role === 'expert' || auth.user?.role === 'admin') {
    items.push({ title: 'Экспертная оценка', to: '/expert/review', icon: 'mdi-stethoscope' })
    items.push({ title: 'Слепая валидация', to: '/expert/validation', icon: 'mdi-clipboard-pulse-outline' })
  }
  if (auth.user?.role === 'admin') {
    items.push({ title: 'Администрирование', to: '/admin', icon: 'mdi-shield-account-outline' })
  }
  return items
})
</script>

<template>
  <v-app class="app-root">
    <v-navigation-drawer v-model="drawer" temporary color="surface">
      <v-list nav>
        <v-list-item
          v-for="item in baseNavItems"
          :key="item.to"
          :to="item.to"
          :prepend-icon="item.icon"
          :title="item.title"
          color="primary"
          rounded="lg"
        />
        <ClientOnly>
          <v-list-item
            v-for="item in roleNavItems"
            :key="item.to"
            :to="item.to"
            :prepend-icon="item.icon"
            :title="item.title"
            color="primary"
            rounded="lg"
          />
        </ClientOnly>
      </v-list>
    </v-navigation-drawer>

    <v-app-bar flat :elevation="0" class="glass-header border-b">
      <v-app-bar-nav-icon class="d-lg-none" @click="drawer = !drawer" />

      <v-app-bar-title class="app-brand-title">
        <NuxtLink to="/" class="brand-link" aria-label="MedConstructor">
          <img
            :src="brandLogoSrc"
            alt=""
            class="brand-logo-mark"
            width="36"
            height="36"
            decoding="async"
            fetchpriority="high"
          >
          <span class="brand-name">MedConstructor</span>
        </NuxtLink>
      </v-app-bar-title>

      <div class="d-none d-lg-flex align-center ml-6 gap-2">
        <v-btn
          v-for="item in baseNavItems"
          :key="item.to"
          :to="item.to"
          variant="text"
          class="text-none font-weight-medium px-3"
          :active="route.path === item.to || (item.to !== '/' && route.path.startsWith(item.to))"
          color="primary"
          rounded="pill"
        >
          <v-icon :icon="item.icon" start size="small" class="mr-2" />
          {{ item.title }}
        </v-btn>
        <ClientOnly>
          <v-btn
            v-for="item in roleNavItems"
            :key="item.to"
            :to="item.to"
            variant="text"
            class="text-none font-weight-medium px-3"
            :active="route.path === item.to || (item.to !== '/' && route.path.startsWith(item.to))"
            color="primary"
            rounded="pill"
          >
            <v-icon :icon="item.icon" start size="small" class="mr-2" />
            {{ item.title }}
          </v-btn>
        </ClientOnly>
      </div>

      <v-spacer />

      <HelpDialog class="mr-1" />

      <ClientOnly>
        <template v-if="auth.user">
          <v-chip size="small" variant="outlined" class="mr-2 d-none d-lg-flex">
            {{ auth.user.email }}
          </v-chip>
          <v-btn variant="text" size="small" rounded="pill" @click="auth.logout()">Выйти</v-btn>
        </template>
        <v-btn v-else to="/login" variant="flat" size="small" color="primary" rounded="pill">Войти</v-btn>
      </ClientOnly>
    </v-app-bar>

    <v-main class="app-main">
      <slot />
    </v-main>
  </v-app>
</template>

<style>
:root {
  --app-font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  --serif-font-family: Georgia, 'Times New Roman', serif;
  --v-medium-emphasis-opacity: 0.85 !important;
  --v-high-emphasis-opacity: 1 !important;
  color-scheme: light dark;
}

html {
  scrollbar-width: thin;
  scrollbar-color: #94a3b8 transparent;
}

html,
body,
#__nuxt {
  height: 100%;
  font-family: var(--app-font-family);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Modern Web Guidance: Typography Layout */
h1, h2, h3, h4, h5, h6, .text-h1, .text-h2, .text-h3, .text-h4, .text-h5, .text-h6, .v-card-title {
  text-wrap: balance;
}

p, .text-body-1, .text-body-2, .text-subtitle-1, .text-subtitle-2 {
  text-wrap: pretty;
}

/* Modern Web Guidance: Auto-sizing inputs */
.field-auto-size textarea, .field-auto-size input {
  field-sizing: content;
}

/* Modern Web Guidance: Accessibility */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}

.v-application {
  font-family: var(--app-font-family) !important;
}

.app-root {
  min-height: 100vh;
  background: radial-gradient(1000px 600px at 20% -10%, rgba(37, 99, 235, 0.05), transparent),
    radial-gradient(800px 500px at 100% 0%, rgba(8, 145, 178, 0.04), transparent),
    rgb(var(--v-theme-background));
  background-attachment: fixed;
}

.glass-header {
  background: rgba(var(--v-theme-surface), 0.8) !important;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(var(--v-border-color), 0.1) !important;
}

.gap-2 {
  gap: 0.5rem;
}

.app-brand-title {
  min-width: 0;
  flex: 0 0 auto;
}

.brand-link {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  min-width: 0;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
}

.brand-logo-mark {
  width: 2.25rem;
  height: 2.25rem;
  object-fit: contain;
  flex: 0 0 auto;
}

.brand-name {
  overflow: hidden;
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 420px) {
  .brand-logo-mark {
    width: 2rem;
    height: 2rem;
  }

  .brand-name {
    max-width: 9.5rem;
    font-size: 0.95rem;
  }
}

.app-main {
  min-height: calc(100dvh - 64px);
  /* Reserve the fixed 64px app-bar height from the very first paint. Vuetify's
     .v-main sets `padding: var(--v-layout-top) …`, and --v-layout-top is 0
     until the app-bar registers with the layout on the client — which drops the
     whole page (and the constructor sidebar) down 64px on hydration, a large
     layout shift. `!important` beats Vuetify's padding shorthand; the value
     matches the app-bar height so there is no double gap once it registers.
     The default layout always has the 64px app-bar, so this is safe. */
  padding-top: 64px !important;
}

.smooth-scroll {
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}
</style>
