<template>
  <q-page padding>
    <q-card>
      <q-card-section>
        <div class="text-h6">{{ t('adminSettings.title') }}</div>
      </q-card-section>
      <q-card-section>
        <div class="q-gutter-md">
          <q-input
            v-model="form.mailjet_api_key"
            :label="t('adminSettings.mailjet_api_key')"
            dense
            :disabled="!isSuper"
          />

          <div v-if="isSuper" class="row items-center">
            <div class="col">
              <q-input
                v-model="form.mailjet_api_secret"
                :label="t('adminSettings.mailjet_api_secret')"
                dense
                :type="showSecret ? 'text' : 'password'"
              />
            </div>
            <div class="col-auto">
              <q-btn dense flat :icon="showSecret ? 'visibility_off' : 'visibility'" @click="showSecret = !showSecret" :title="showSecret ? t('adminSettings.hide_secret') : t('adminSettings.reveal_secret')" />
            </div>
          </div>
          <div v-else>
            <div v-if="hasSecretConfigured" class="row items-center q-gutter-sm">
              <q-chip dense color="grey">{{ t('adminSettings.configured') }}</q-chip>
              <div class="text-caption q-ml-sm">{{ t('adminSettings.secret_hidden') }}</div>
            </div>
          </div>

          <q-input
            v-model="form.mailjet_sender"
            :label="t('adminSettings.mailjet_sender')"
            dense
            :disabled="!isSuper"
            :rules="[v => !v || emailRegex.test(v) || t('adminSettings.invalid_email')]"
          />

          <q-select
            v-model="form.default_user_language"
            emit-value
            :options="langOptions"
            option-label="label"
            option-value="value"
            :label="t('adminSettings.default_user_language')"
            dense
            :disabled="!isSuper"
          />

          <div class="q-separator q-my-md" />

          <div class="q-gutter-md">
            <q-input v-model="frontendBaseUrl" :label="t('adminSettings.frontend_base_url')" dense :disabled="!isSuper" placeholder="https://example.com" />

              <div class="text-caption q-mt-sm">{{ t('adminSettings.frontend_base_help') }}</div>

            <div class="row items-center q-mt-sm">
              <div class="col-12 col-md-4">
                <q-select v-model="selectedInviteLang" :options="langOptions" emit-value option-label="label" option-value="value" :label="t('adminSettings.invite_language_select')" dense :disabled="!isSuper" />
              </div>
            </div>

            <q-input v-model="inviteSubject" :label="t('adminSettings.invite_subject')" dense :disabled="!isSuper" />
            <q-input type="textarea" autogrow v-model="inviteHtml" :label="t('adminSettings.invite_html')" dense :disabled="!isSuper" />
            <q-input type="textarea" autogrow v-model="inviteText" :label="t('adminSettings.invite_text')" dense :disabled="!isSuper" />

            <div class="text-caption q-mt-sm">{{ t('adminSettings.invite_help') }}</div>
          </div>

          <div class="q-separator q-my-md" />

          <div class="q-gutter-md">
            <div class="row items-center q-mt-sm">
              <div class="col-12 col-md-4">
                <q-select v-model="selectedResetLang" :options="langOptions" emit-value option-label="label" option-value="value" :label="t('adminSettings.password_reset_language_select')" dense :disabled="!isSuper" />
              </div>
            </div>

            <q-input v-model="resetSubject" :label="t('adminSettings.password_reset_subject')" dense :disabled="!isSuper" />
            <q-input type="textarea" autogrow v-model="resetHtml" :label="t('adminSettings.password_reset_html')" dense :disabled="!isSuper" />
            <q-input type="textarea" autogrow v-model="resetText" :label="t('adminSettings.password_reset_text')" dense :disabled="!isSuper" />

            <div class="text-caption q-mt-sm">{{ t('adminSettings.password_reset_help') }}</div>
          </div>

          <div v-if="isSuper" class="row items-center q-pt-md">
            <div class="col">
              <q-input v-model="testEmail" :label="t('adminSettings.test_email_label')" dense :placeholder="t('adminSettings.test_email_placeholder')" />
            </div>
            <div class="col-auto">
              <div class="row items-center">
                <q-btn color="primary" class="q-mr-sm" :label="t('adminSettings.test_send')" @click="sendTestEmail" :loading="sendingTest" />
                <q-btn color="secondary" :label="t('adminSettings.test_send_reset')" @click="sendTestResetEmail" :loading="sendingTestReset" />
              </div>
            </div>
          </div>

          <div v-if="!isSuper" class="text-caption q-mt-sm">{{ t('adminSettings.edit_super_only') }}</div>
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat :label="t('common.cancel')" @click="load" />
        <q-btn color="primary" :label="t('common.save')" @click="save" :disabled="!isSuper || saving" :loading="saving" />
      </q-card-actions>
    </q-card>
  </q-page>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import axios from 'axios'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import i18nMessages from 'src/i18n'

const $q = useQuasar()
const { t } = useI18n()

const form = ref({
  mailjet_api_key: '',
  mailjet_api_secret: '',
  mailjet_sender: '',
  default_user_language: '',
})
const isSuper = ref(false)
const showSecret = ref(false)
const hasSecretConfigured = ref(false)
const saving = ref(false)
const testEmail = ref('')
const sendingTest = ref(false)
  const sendingTestReset = ref(false)

const frontendBaseUrl = ref('')
const selectedInviteLang = ref('')
const inviteSubject = ref('')
const inviteHtml = ref('')
const inviteText = ref('')
const selectedResetLang = ref('')
const resetSubject = ref('')
const resetHtml = ref('')
const resetText = ref('')
const settingsData = ref({})

// Default invite templates (used when no setting is present)
const DEFAULT_INVITE_SUBJECT = "You're invited to the Intranet (username: {username})"
const DEFAULT_INVITE_HTML = '<p>Hello {display} ({username}),</p><p>You were invited to the intranet. Click <a href="{link}">this link</a> to set your password and sign in.</p><p>Your username is <strong>{username}</strong>.</p>'
const DEFAULT_INVITE_TEXT = 'Hello {display} ({username}),\n\nOpen the following link to set your password: {link}\n\nYour username: {username}\n'

// Swedish defaults for invite
const DEFAULT_INVITE_SUBJECT_SV = 'Du är inbjuden till Intranätet (användarnamn: {username})'
const DEFAULT_INVITE_HTML_SV = '<p>Hej {display} ({username}),</p><p>Du har blivit inbjuden till intranätet. Klicka <a href="{link}">här</a> för att ange ditt lösenord och logga in.</p><p>Ditt användarnamn är <strong>{username}</strong>.</p>'
const DEFAULT_INVITE_TEXT_SV = 'Hej {display} ({username}),\n\nÖppna följande länk för att ange ditt lösenord: {link}\n\nDitt användarnamn: {username}\n'

// Default password reset templates
const DEFAULT_PASSWORD_RESET_SUBJECT = 'Reset your password'
const DEFAULT_PASSWORD_RESET_HTML = '<p>Hello {display},</p><p>Click <a href="{link}">this link</a> to reset your password.</p>'
const DEFAULT_PASSWORD_RESET_TEXT = 'Hello {display},\n\nOpen the following link to reset your password: {link}\n'

// Swedish defaults for password reset
const DEFAULT_PASSWORD_RESET_SUBJECT_SV = 'Återställ ditt lösenord'
const DEFAULT_PASSWORD_RESET_HTML_SV = '<p>Hej {display},</p><p>Klicka <a href="{link}">här</a> för att återställa ditt lösenord.</p>'
const DEFAULT_PASSWORD_RESET_TEXT_SV = 'Hej {display},\n\nÖppna följande länk för att återställa ditt lösenord: {link}\n'

const pickDefaultInviteSubject = (lang) => (lang && String(lang).toLowerCase().startsWith('sv') ? DEFAULT_INVITE_SUBJECT_SV : DEFAULT_INVITE_SUBJECT)
const pickDefaultInviteHtml = (lang) => (lang && String(lang).toLowerCase().startsWith('sv') ? DEFAULT_INVITE_HTML_SV : DEFAULT_INVITE_HTML)
const pickDefaultInviteText = (lang) => (lang && String(lang).toLowerCase().startsWith('sv') ? DEFAULT_INVITE_TEXT_SV : DEFAULT_INVITE_TEXT)

const pickDefaultResetSubject = (lang) => (lang && String(lang).toLowerCase().startsWith('sv') ? DEFAULT_PASSWORD_RESET_SUBJECT_SV : DEFAULT_PASSWORD_RESET_SUBJECT)
const pickDefaultResetHtml = (lang) => (lang && String(lang).toLowerCase().startsWith('sv') ? DEFAULT_PASSWORD_RESET_HTML_SV : DEFAULT_PASSWORD_RESET_HTML)
const pickDefaultResetText = (lang) => (lang && String(lang).toLowerCase().startsWith('sv') ? DEFAULT_PASSWORD_RESET_TEXT_SV : DEFAULT_PASSWORD_RESET_TEXT)

const emailRegex = /^\S+@\S+\.\S+$/

const langOptions = computed(() => {
  try {
    const keys = Object.keys(i18nMessages || {})
    // Prefer full locale codes (e.g. en-US) over short (en) and dedupe by base language
    keys.sort((a, b) => {
      const aFull = a.includes('-')
      const bFull = b.includes('-')
      if (aFull && !bFull) return -1
      if (!aFull && bFull) return 1
      return 0
    })
    const seen = new Set()
    const opts = []
    for (const k of keys) {
      const base = (k || '').split('-')[0]
      if (seen.has(base)) continue
      seen.add(base)
      const label = t(`languages.${k}`) || t(`languages.${base}`) || k
      opts.push({ value: k, label })
    }
    return opts
  } catch (e) {
    return []
  }
})

async function loadUser() {
  try {
    const res = await axios.get('/api/user/me')
    isSuper.value = !!res.data?.data?.attributes?.is_superadmin
  } catch (e) {
    isSuper.value = false
  }
}

async function load() {
  try {
    await loadUser()
    const res = await axios.get('/api/admin/settings')
    const data = res.data?.data || {}
    form.value.mailjet_api_key = data.mailjet_api_key || ''
    // only show secret to superadmins
    if (isSuper.value) form.value.mailjet_api_secret = data.mailjet_api_secret || ''
    hasSecretConfigured.value = !!data.mailjet_api_secret
    form.value.mailjet_sender = data.mailjet_sender || ''
    form.value.default_user_language = data.default_user_language || ''
    // frontend base url and invite templates
    settingsData.value = data || {}
    frontendBaseUrl.value = data.frontend_base_url || ''
    // initialize selected invite language
    selectedInviteLang.value = form.value.default_user_language || (langOptions.value.length ? langOptions.value[0].value : '')
    // load invite templates for selected language
    loadInviteTemplates()
    // initialize selected reset language (default to same as invite/default)
    selectedResetLang.value = form.value.default_user_language || selectedInviteLang.value || (langOptions.value.length ? langOptions.value[0].value : '')
    // load reset templates
    loadResetTemplates()
  } catch (e) {
    console.error('load settings', e)
    $q.notify({ type: 'negative', message: t('adminSettings.load_failed') })
  }
}

function loadInviteTemplates() {
  const data = settingsData.value || {}
  const lang = selectedInviteLang.value || ''
  inviteSubject.value = data[`invite_subject_${lang}`] || data.invite_subject || pickDefaultInviteSubject(lang)
  inviteHtml.value = data[`invite_html_${lang}`] || data.invite_html || pickDefaultInviteHtml(lang)
  inviteText.value = data[`invite_text_${lang}`] || data.invite_text || pickDefaultInviteText(lang)
}

function loadResetTemplates() {
  const data = settingsData.value || {}
  const lang = selectedResetLang.value || ''
  resetSubject.value = data[`password_reset_subject_${lang}`] || data.password_reset_subject || pickDefaultResetSubject(lang)
  resetHtml.value = data[`password_reset_html_${lang}`] || data.password_reset_html || pickDefaultResetHtml(lang)
  resetText.value = data[`password_reset_text_${lang}`] || data.password_reset_text || pickDefaultResetText(lang)
}

watch(selectedInviteLang, () => {
  loadInviteTemplates()
})

watch(selectedResetLang, () => {
  loadResetTemplates()
})

function validateBeforeSave() {
  // if any Mailjet field provided, require all three
  const k = form.value.mailjet_api_key
  const s = form.value.mailjet_api_secret
  const e = form.value.mailjet_sender
  if (k || s || e) {
    if (!(k && s && e)) {
      $q.notify({ type: 'negative', message: t('adminSettings.mailjet_require_all') })
      return false
    }
    if (!emailRegex.test(e)) {
      $q.notify({ type: 'negative', message: t('adminSettings.invalid_email') })
      return false
    }
  }
  // default language must be one of available keys
  if (form.value.default_user_language) {
    const available = langOptions.value.map(o => o.value)
    if (!available.includes(form.value.default_user_language)) {
      $q.notify({ type: 'negative', message: t('adminSettings.invalid_language') })
      return false
    }
  }
  return true
}

async function save() {
  if (!isSuper.value) {
    $q.notify({ type: 'negative', message: t('adminSettings.edit_super_only') })
    return
  }
  if (!validateBeforeSave()) return
  saving.value = true
  try {
    const payload = {
      mailjet_api_key: form.value.mailjet_api_key || '',
      mailjet_api_secret: form.value.mailjet_api_secret || '',
      mailjet_sender: form.value.mailjet_sender || '',
      default_user_language: form.value.default_user_language || '',
      frontend_base_url: frontendBaseUrl.value || '',
    }
    // include current invite templates for selected language
    const lang = selectedInviteLang.value || form.value.default_user_language || ''
    if (lang) {
      payload[`invite_subject_${lang}`] = inviteSubject.value || ''
      payload[`invite_html_${lang}`] = inviteHtml.value || ''
      payload[`invite_text_${lang}`] = inviteText.value || ''
    }
    // include current password reset templates for selected reset language
    const rlang = selectedResetLang.value || form.value.default_user_language || ''
    if (rlang) {
      payload[`password_reset_subject_${rlang}`] = resetSubject.value || ''
      payload[`password_reset_html_${rlang}`] = resetHtml.value || ''
      payload[`password_reset_text_${rlang}`] = resetText.value || ''
    }
    // remember which language admins used for editing invite templates
    if (selectedInviteLang.value) payload.invite_default_language = selectedInviteLang.value
    if (selectedResetLang.value) payload.password_reset_default_language = selectedResetLang.value
    await axios.patch('/api/admin/settings', payload)
    $q.notify({ type: 'positive', message: t('adminSettings.save_success') })
    await load()
  } catch (err) {
    console.error('save settings', err)
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminSettings.save_failed') })
  } finally {
    saving.value = false
  }
}

async function sendTestEmail() {
  if (!isSuper.value) {
    $q.notify({ type: 'negative', message: t('adminSettings.edit_super_only') })
    return
  }
  if (!testEmail.value || !emailRegex.test(testEmail.value)) {
    $q.notify({ type: 'negative', message: t('adminSettings.invalid_email') })
    return
  }
  sendingTest.value = true
  try {
    await axios.post('/api/admin/settings/test_send', { to_email: testEmail.value })
    $q.notify({ type: 'positive', message: t('adminSettings.test_send_success') })
  } catch (err) {
    console.error('test send', err)
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminSettings.test_send_failed') })
  } finally {
    sendingTest.value = false
  }
}

async function sendTestResetEmail() {
  if (!isSuper.value) {
    $q.notify({ type: 'negative', message: t('adminSettings.edit_super_only') })
    return
  }
  if (!testEmail.value || !emailRegex.test(testEmail.value)) {
    $q.notify({ type: 'negative', message: t('adminSettings.invalid_email') })
    return
  }
  sendingTestReset.value = true
  try {
    const payload = { to_email: testEmail.value, language: selectedResetLang.value }
    await axios.post('/api/admin/settings/test_send_reset', payload)
    $q.notify({ type: 'positive', message: t('adminSettings.test_send_reset_success') })
  } catch (err) {
    console.error('test reset send', err)
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminSettings.test_send_reset_failed') })
  } finally {
    sendingTestReset.value = false
  }
}

onMounted(() => {
  load()
})
</script>

<style scoped>
</style>
