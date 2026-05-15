export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  devtools: { enabled: false },
  modules: ['@nuxtjs/tailwindcss', '@pinia/nuxt'],
  ssr: true,
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api',
      demoUsername: process.env.NUXT_PUBLIC_DEMO_USERNAME || '',
      demoPassword: process.env.NUXT_PUBLIC_DEMO_PASSWORD || '',
    },
  },
  app: {
    head: {
      title: 'Private Audio Intelligence',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      ],
    },
  },
  nitro: {
    preset: 'node-server',
  },
})
