// Styles
// @ts-ignore
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

// Vuetify
import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

export default createVuetify({
  components,
  directives,
  defaults: {
    VCard: { rounded: 'lg' },
    VBtn: { rounded: 'lg' },
    // autocomplete="off" + случайный name отключают browser autofill
    // (Chrome/Edge игнорируют off без name — поэтому "nope")
    VTextField: { rounded: 'lg', autocomplete: 'off' },
    VSelect: { rounded: 'lg', autocomplete: 'off' },
    VAutocomplete: { rounded: 'lg', autocomplete: 'off' },
    VCombobox: { rounded: 'lg', autocomplete: 'off' },
    VTextarea: { autocomplete: 'off' },
    VFileInput: { autocomplete: 'off' },
    VDialog: { rounded: 'lg' },
    VSheet: { rounded: 'lg' },
    VAlert: { rounded: 'lg' },
    VChip: { rounded: 'lg' },
    VBtnToggle: { rounded: 'lg' },
  },
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: {
      mdi,
    },
  },
  theme: {
    defaultTheme: (typeof localStorage !== 'undefined' ? localStorage.getItem('theme') : null) || 'light',
    themes: {
      light: {
        colors: {
          primary: '#c2620a',
          secondary: '#5a5448',
          error: '#ef4444',
          info: '#2563eb',
          success: '#16a34a',
          warning: '#d97706',
          background: '#f5f3ef',
          surface: '#ffffff',
        },
      },
      dark: {
        dark: true,
        colors: {
          primary: '#fb923c',
          secondary: '#9a9080',
          error: '#ef4444',
          info: '#93c5fd',
          success: '#86efac',
          warning: '#fde68a',
          background: '#0f0e0c',
          surface: '#1c1916',
        },
      },
    },
  },
})