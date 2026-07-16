<template>
  <v-app class="app-root">
    <v-main class="auth-main">
      <slot />
    </v-main>
  </v-app>
</template>

<style>
.app-root {
  min-height: 100vh;
  background: radial-gradient(1000px 600px at 20% -10%, rgba(37, 99, 235, 0.05), transparent),
    radial-gradient(800px 500px at 100% 0%, rgba(8, 145, 178, 0.04), transparent),
    rgb(var(--v-theme-background));
  background-attachment: fixed;
}

.auth-main {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100dvh;
  padding: max(1rem, env(safe-area-inset-top))
    max(1rem, env(safe-area-inset-right))
    max(1rem, env(safe-area-inset-bottom))
    max(1rem, env(safe-area-inset-left));
  overflow-y: auto;
}
</style>
