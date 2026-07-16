import { createConfigForNuxt } from '@nuxt/eslint-config/flat'

export default createConfigForNuxt({
  features: {
    stylistic: false,
    tooling: true,
  },
}).append({
  rules: {
    // Vuetify data tables expose scoped slots such as `item.score`.
    'vue/valid-v-slot': ['error', { allowModifiers: true }],
    // API and graph payloads are incrementally typed; runtime validation remains authoritative.
    '@typescript-eslint/no-explicit-any': 'off',
    // `props` is the conventional Vuetify activator slot binding.
    'vue/no-template-shadow': 'off',
  },
  ignores: [
    '.nuxt/**',
    '.nuxt-*/**',
    '.output/**',
    '.output-*/**',
    'dist/**',
    'node_modules/**',
  ],
})
