// https://nuxt.com/docs/api/configuration/nuxt-config
import { ru } from 'vuetify/locale'

const buildDir = process.env.NUXT_BUILD_DIR || '.nuxt'
const nitroOutputDir = process.env.NITRO_OUTPUT_DIR || '.output'

export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  buildDir,
  devtools: { enabled: process.env.NODE_ENV !== 'production' },
  modules: ['vuetify-nuxt-module', '@pinia/nuxt'],
  // Resolve components by filename regardless of subfolder, so short names like
  // <NodePalette>, <ConstructorHeader>, <BenchmarkOverviewTab>, <MetricCard> used
  // across the feature/widget folders auto-import correctly.
  components: [{ path: '~/components', pathPrefix: false }],
  css: ['~/assets/css/a11y.css'],
  app: {
    baseURL: '/medical/',
    head: {
      title: 'MedConstructor',
      meta: [
        { name: 'application-name', content: 'MedConstructor' },
        { name: 'apple-mobile-web-app-title', content: 'MedConstructor' },
        { name: 'theme-color', content: '#ffffff' },
        { property: 'og:title', content: 'MedConstructor' },
        { property: 'og:type', content: 'website' },
        { property: 'og:image', content: '/medical/brand/logo-podpis.png' }
      ],
      link: [
        { rel: 'icon', href: '/medical/favicon.ico', sizes: 'any' },
        { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/medical/favicon-32x32.png' },
        { rel: 'icon', type: 'image/png', sizes: '16x16', href: '/medical/favicon-16x16.png' },
        { rel: 'apple-touch-icon', sizes: '180x180', href: '/medical/apple-touch-icon.png' },
        { rel: 'manifest', href: '/medical/site.webmanifest' },
      ]
    }
  },
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/medical-api',
      internalApiBase: process.env.NUXT_INTERNAL_API_BASE || 'http://127.0.0.1:8012',
      showDemoCredentials: process.env.NUXT_PUBLIC_SHOW_DEMO_CREDENTIALS === 'true',
    },
  },
  experimental: {
    viewTransition: true
  },
  nitro: {
    compressPublicAssets: true,
    output: {
      dir: nitroOutputDir
    }
  },
  routeRules: {
    '/_nuxt/**': {
      headers: { 'cache-control': 'public, max-age=31536000, immutable' }
    },
    '/android-chrome-192x192.png': {
      headers: { 'cache-control': 'public, max-age=31536000, immutable' }
    },
    '/medical/android-chrome-192x192.png': {
      headers: { 'cache-control': 'public, max-age=31536000, immutable' }
    },
    '/android-chrome-512x512.png': {
      headers: { 'cache-control': 'public, max-age=31536000, immutable' }
    },
    '/medical/android-chrome-512x512.png': {
      headers: { 'cache-control': 'public, max-age=31536000, immutable' }
    },
    '/brand/**': {
      headers: { 'cache-control': 'public, max-age=31536000, immutable' }
    },
    '/medical/brand/**': {
      headers: { 'cache-control': 'public, max-age=31536000, immutable' }
    }
  },
  vuetify: {
    vuetifyOptions: {
      locale: {
        locale: 'ru',
        fallback: 'en',
        messages: { ru },
      },
      theme: {
        defaultTheme: 'light',
        themes: {
          light: {
            dark: false,
            colors: {
              primary: '#2563eb',
              secondary: '#0891b2',
              accent: '#7c3aed',
              surface: '#ffffff',
              'surface-variant': '#f8fafc',
              background: '#f1f5f9',
              error: '#dc2626',
              info: '#2563eb',
              success: '#059669',
              warning: '#d97706',
              'on-surface': '#000000',
              'on-background': '#000000',
            },
          },
          dark: {
            dark: true,
            colors: {
              primary: '#6b8afc',
              secondary: '#18c4d9',
              accent: '#8b5cf6',
              surface: '#121212',
              'surface-variant': '#1e1e1e',
              background: '#0a0a0a',
              error: '#ef4444',
              info: '#3b82f6',
              success: '#10b981',
              warning: '#f59e0b',
            },
          },
        },
      },
      defaults: {
        global: {
          ripple: false,
        },
        VCard: {
          rounded: 'xl',
        },
        VBtn: {
          rounded: 'lg',
        }
      }
    },
  },
})
