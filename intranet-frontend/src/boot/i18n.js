import { boot } from 'quasar/wrappers'
import { createI18n } from 'vue-i18n'
import { watch } from 'vue'
import messages from 'src/i18n'
import { useAuth } from 'src/services/auth'
import axios from 'axios'

export default boot(async ({ app }) => {
  // Try server-provided default language for unauthenticated pages (login)
  let serverDefault = null
  try {
    const res = await axios.get('/api/public/settings')
    serverDefault = res?.data?.data?.default_user_language || res?.data?.data?.invite_default_language || null
  } catch (e) {
    // ignore network / 404 errors
  }

  // choose initial locale from localStorage, server default, or navigator
  const initial = (typeof localStorage !== 'undefined' && localStorage.getItem('locale')) || serverDefault || (navigator && navigator.language) || 'en-US'
  const locale = messages[initial] ? initial : (initial && initial.startsWith && initial.startsWith('sv') ? 'sv-SE' : 'en-US')

  const i18n = createI18n({
    locale,
    globalInjection: true,
    messages
  })

  // Set i18n instance on app
  app.use(i18n)

  // Dynamically load and apply Quasar language pack to match vue-i18n locale
  const applyQuasarLang = async (loc) => {
    try {
      const code = String(loc || i18n.global.locale.value || 'en-US')
      let mod
      if (/^sv/i.test(code)) {
        mod = await import('quasar/lang/sv')
      } else {
        // default to en-US
        mod = await import('quasar/lang/en-US')
      }
      const quasarLang = mod && (mod.default || mod)
      try {
        const $q = app.config && app.config.globalProperties && app.config.globalProperties.$q
        if ($q && $q.lang && typeof $q.lang.set === 'function') {
          $q.lang.set(quasarLang)
        } else if ($q && $q.lang) {
          $q.lang = quasarLang
        } else {
          // fallback: register Quasar with lang option
          const { Quasar } = await import('quasar')
          app.use(Quasar, { lang: quasarLang })
        }
      } catch (e) {
        // ignore failures setting Quasar lang
      }
    } catch (e) {
      // ignore dynamic import failures
    }
  }

  // watch i18n locale and apply corresponding Quasar lang
  try {
    watch(() => i18n.global.locale.value, (v) => { applyQuasarLang(v) }, { immediate: true })
  } catch (e) {
    // ignore if watch can't be registered
  }

  // Sync i18n locale with the auth.selectedLanguage so changes
  // to the user's language propagate immediately across the app.
  try {
    const auth = useAuth()
    watch(() => auth.selectedLanguage, (v) => {
      if (v) i18n.global.locale.value = v
    })
  } catch (e) {
    // ignore if reactive auth isn't available at boot time
  }
})
