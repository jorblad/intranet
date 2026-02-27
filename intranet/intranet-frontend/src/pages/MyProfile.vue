<template>
  <q-page padding>
    <div class="row items-center q-col-gutter-md">
      <div class="col-12 col-md-6">
        <div class="text-h6 q-mb-md">{{ t('profile.title') }}</div>

        <q-form id="profileForm" autocomplete="on" @submit.prevent="saveProfile" ref="formRef">
          <q-input v-model="username" :label="t('profile.username')" dense :error="!!errors.username" :error-message="errors.username" :input-attrs="{ autocomplete: 'username', name: 'username' }" />
          <q-input v-model="displayName" :label="t('profile.display_name')" dense class="q-mt-sm" :error="!!errors.displayName" :error-message="errors.displayName" :input-attrs="{ autocomplete: 'name', name: 'display_name' }" />

          <q-input v-model="password" :label="t('profile.password')" dense type="password" class="q-mt-sm" :error="!!errors.password" :error-message="errors.password" :input-attrs="{ autocomplete: 'new-password', name: 'new-password' }" />
          <div class="text-caption q-mt-xs">{{ t('profile.password_helper') }}</div>
          <q-input v-model="passwordConfirm" :label="t('profile.password_confirm')" dense type="password" class="q-mt-sm" :error="!!errors.passwordConfirm" :error-message="errors.passwordConfirm" :input-attrs="{ autocomplete: 'new-password', name: 'new-password-confirm' }" />

          <q-select v-model="language" :options="languageOptions" class="q-mt-sm" :label="t('profile.language')" emit-value map-options option-label="label" option-value="value" />

          <div class="row q-mt-md">
            <q-btn color="primary" :label="t('profile.save')" type="submit" />
            <q-btn flat :label="t('profile.reset')" class="q-ml-sm" @click="resetForm" />
          </div>
          <div class="q-mt-lg">
            <div class="text-subtitle2 q-mb-sm">{{ t('profile.calendar_links') }}</div>
            <div class="row items-center q-col-gutter-sm">
              <div class="col">
                <q-input readonly dense :value="personalCalendarUrl" label="Personal calendar (shareable)" />
              </div>
              <div class="col-auto">
                <q-btn flat icon="content_copy" @click="copyPersonalUrl" />
                <q-btn flat icon="refresh" @click="regenerateToken" :title="t('profile.regenerate_token')" />
              </div>
            </div>
          </div>
        </q-form>
      </div>
    </div>
  </q-page>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'
import { useQuasar } from 'quasar'
import { useAuth, fetchCurrentUser, setSelectedLanguage } from 'src/services/auth'
import { useI18n } from 'vue-i18n'
import { ref as ref2 } from 'vue'

const { t } = useI18n()
const $q = useQuasar()
const auth = useAuth()

const username = ref('')
const displayName = ref('')
const password = ref('')
const passwordConfirm = ref('')
const language = ref(null)
const errors = ref({ username: '', displayName: '', password: '', passwordConfirm: '' })
const formRef = ref(null)
const personalCalendarUrl = ref2('')

const languageOptions = [
  { label: 'English', value: 'en-US' },
  { label: 'Svenska', value: 'sv-SE' }
]

function populateFromAuth() {
  const u = auth.user
  if (!u) return
  username.value = u.attributes?.username || ''
  displayName.value = u.attributes?.display_name || ''
  // normalize stored language: accept either primitive or option object
  const stored = u.attributes?.language
  if (!stored) {
    language.value = auth.selectedLanguage || 'en-US'
  } else if (typeof stored === 'string') {
    language.value = stored
  } else if (typeof stored === 'object') {
    // try common keys for locale
    language.value = stored.value || stored.code || stored.locale || stored.language || stored.name || stored.label || auth.selectedLanguage || 'en-US'
  } else {
    language.value = auth.selectedLanguage || 'en-US'
  }

  // final coercion: if language is still an object, pick its common fields
  if (language.value && typeof language.value === 'object') {
    const s = language.value
    language.value = s.value || s.code || s.locale || s.language || s.name || s.label || auth.selectedLanguage || 'en-US'
  }

  // ensure the selected language matches one of our options; fallback to en-US
  if (!languageOptions.find(o => o.value === language.value)) {
    language.value = auth.selectedLanguage || 'en-US'
  }
}

onMounted(() => {
  populateFromAuth()
  // ensure password inputs have native autocomplete attributes (some browsers
  // warn if not present even when `input-attrs` is used). Use DOM selection
  // so any rendered native inputs receive the attribute.
  ensurePasswordAutocomplete()
  updatePersonalUrl()
})

// when auth.user is populated/updated elsewhere (e.g. after fetchCurrentUser),
// repopulate the form so the page shows current data without navigation.
watch(() => auth.user, (v) => {
  if (v) populateFromAuth()
  updatePersonalUrl()
})

function updatePersonalUrl() {
  const u = auth.user
  const token = u?.attributes?.calendar_token
  if (token) {
    personalCalendarUrl.value = `${window.location.origin}/api/calendars/personal/${token}.ics`
  } else {
    personalCalendarUrl.value = ''
  }
}

async function regenerateToken() {
  try {
    await axios.post('/api/user/me/calendar_token/regenerate')
    await fetchCurrentUser()
    updatePersonalUrl()
    $q.notify({ type: 'positive', message: t('profile.token_regenerated') })
  } catch (e) {
    $q.notify({ type: 'negative', message: t('failed') })
  }
}

function copyPersonalUrl() {
  if (!personalCalendarUrl.value) return
  navigator.clipboard.writeText(personalCalendarUrl.value)
  $q.notify({ type: 'positive', message: t('profile.link_copied') })
}

function resetForm() {
  populateFromAuth()
  password.value = ''
  passwordConfirm.value = ''
  errors.value = { username: '', displayName: '', password: '', passwordConfirm: '' }
}

function ensurePasswordAutocomplete() {
  try {
    const form = document.getElementById('profileForm')
    if (!form) return
    const inputs = form.querySelectorAll('input')
    inputs.forEach(i => {
      try {
        const type = (i.getAttribute('type') || '').toLowerCase()
        const label = (i.getAttribute('aria-label') || '').toLowerCase()
        if (type === 'password') {
          if (!i.getAttribute('autocomplete')) i.setAttribute('autocomplete', 'new-password')
        } else {
          // heuristics: map aria-labels to sensible autocomplete values
          if (!i.getAttribute('autocomplete')) {
            if (label.includes('användarnamn') || label.includes('username')) {
              i.setAttribute('autocomplete', 'username')
            } else if (label.includes('visningsnamn') || label.includes('display')) {
              i.setAttribute('autocomplete', 'name')
            } else if (label.includes('email') || label.includes('epost') || label.includes('e-post')) {
              i.setAttribute('autocomplete', 'email')
            }
          }
        }
      } catch (e) {}
    })
  } catch (e) {}
}

function validate() {
  let ok = true
  errors.value = { username: '', displayName: '', password: '', passwordConfirm: '' }
  if (!username.value || !username.value.trim()) {
    errors.value.username = 'Användarnamn krävs'
    ok = false
  }
  if (!displayName.value || !displayName.value.trim()) {
    errors.value.displayName = 'Visningsnamn krävs'
    ok = false
  }
  if (password.value) {
    if (password.value.length < 8) {
      errors.value.password = 'Lösenord måste vara minst 8 tecken'
      ok = false
    }
    if (password.value !== passwordConfirm.value) {
      errors.value.passwordConfirm = 'Lösenorden matchar inte'
      ok = false
    }
  }
  return ok
}

async function saveProfile() {
  if (!validate()) return
  const payload = {}
  if (username.value) payload.username = username.value.trim()
  if (displayName.value) payload.display_name = displayName.value.trim()
  if (password.value) payload.password = password.value
  if (language.value) payload.language = language.value

  try {
    const res = await axios.patch('/api/user/me', payload)
    await fetchCurrentUser()
    // refresh local form values from the updated auth state
    populateFromAuth()
    // ensure native inputs have autocomplete set after re-render
    ensurePasswordAutocomplete()
    // update client language immediately
    try {
      const id = language.value || auth.selectedLanguage || 'en-US'
      const { locale } = useI18n()
      locale.value = id
    } catch (e) {}
    setSelectedLanguage(language.value)
    $q.notify({ type: 'positive', message: t('profile.updated') })
    // clear sensitive fields
    password.value = ''
    passwordConfirm.value = ''
  } catch (err) {
    const msg = err.response?.data?.detail || err.response?.data || err.message
    if (err.response && err.response.status === 400 && typeof msg === 'string' && msg.toLowerCase().includes('username')) {
      errors.value.username = 'Användarnamnet är redan taget'
      return
    }
    $q.notify({ type: 'negative', message: t('failed') })
  }
}
</script>

<style scoped>
</style>
