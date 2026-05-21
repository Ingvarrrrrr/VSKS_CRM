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
    VTextField: { rounded: 'lg' },
    VSelect: { rounded: 'lg' },
    VAutocomplete: { rounded: 'lg' },
    VCombobox: { rounded: 'lg' },
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
          primary: '#1976D2',
          secondary: '#424242',
          accent: '#82B1FF',
          error: '#FF5252',
          info: '#2196F3',
          success: '#4CAF50',
          warning: '#FFC107',
        },
      },
      dark: {
        dark: true,
        colors: {
          primary: '#42A5F5',
          secondary: '#78909C',
          accent: '#82B1FF',
          error: '#FF5252',
          info: '#29B6F6',
          success: '#66BB6A',
          warning: '#FFA726',
          background: '#0F172A',
          surface: '#1E293B',
        },
      },
    },
  },
})