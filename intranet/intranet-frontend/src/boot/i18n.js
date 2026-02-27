import { boot } from 'quasar/wrappers'
import { createI18n } from 'vue-i18n'
import { watch } from 'vue'
import messages from 'src/i18n'
import { useAuth } from 'src/services/auth'

export default boot(({ app }) => {
  // choose initial locale from localStorage or navigator
  const initial = (typeof localStorage !== 'undefined' && localStorage.getItem('locale')) || (navigator && navigator.language) || 'en-US'
  const locale = messages[initial] ? initial : (initial.startsWith('sv') ? 'sv-SE' : 'en-US')

  const i18n = createI18n({
    locale,
    globalInjection: true,
    messages
  })

  // Set i18n instance on app
  app.use(i18n)

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
