<template>
  <div class="row items-center justify-center" style="min-height: 80vh;">
    <q-card style="width: 420px; max-width: 95%;">
            <q-card-section class="row items-center q-gutter-sm">
              <q-avatar square size="48px" class="bg-primary text-white">
                <q-icon name="home" />
              </q-avatar>
              <div style="flex: 1 1 auto;">
                <div class="text-h6">{{ $t('app.title') }}</div>
                <div class="text-caption">{{ $t('login.sign_in') }}</div>
              </div>
              <div style="min-width:140px;">
                <q-select dense outlined hide-dropdown-icon :options="localeOptions" v-model="selectedLocale" @update:model-value="onLocaleChange" emit-value option-value="value" option-label="label" :display-value="selectedLocaleLabel" />
              </div>
            </q-card-section>

      <q-separator />

      <q-card-section>
        <div v-if="isAuthenticated()">
          <p>{{ $t('login.already_logged_in') }}</p>
          <q-btn :label="$t('login.logout')" color="negative" @click="logout" />
        </div>
        <div v-else>
          <q-form @submit.prevent="login" autocomplete="on">
            <q-input dense v-model="username" :label="$t('login.username')" :input-attrs="{ autocomplete: 'username', name: 'username' }" autofocus />
            <q-input dense v-model="password" type="password" :label="$t('login.password')" :input-attrs="{ autocomplete: 'current-password', name: 'password' }" class="q-mt-sm" />

            <div v-if="errorMessage" class="text-negative q-mt-sm">{{ errorMessage }}</div>

            <div class="row items-center justify-between q-mt-md">
              <q-btn type="submit" color="primary" :label="$t('login.submit')" />
              <q-btn flat @click="forgotDialogVisible = true" :label="$t('login.forgot_password')" />
            </div>
          </q-form>
        </div>
      </q-card-section>
    </q-card>

    <q-dialog v-model="forgotDialogVisible">
      <q-card style="min-width:320px; max-width:420px;">
        <q-card-section>
          <div class="text-h6">{{ $t('login.forgot_title') }}</div>
          <div class="text-caption">{{ $t('login.forgot_help') }}</div>
        </q-card-section>
        <q-card-section>
          <q-input v-model="resetIdentifier" :label="$t('login.username') + ' / ' + $t('adminUsers.email')" dense autofocus :input-attrs="{ autocomplete: 'username', name: 'identifier' }" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat :label="$t('common.cancel')" @click="forgotDialogVisible=false" />
          <q-btn color="primary" :label="$t('login.forgot_password')" :loading="sendingReset" @click="sendResetRequest" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script>
import axios from 'axios'
import i18nMessages from 'src/i18n'

const LANG_LABELS = { 'en-US': 'English (US)', 'sv-SE': 'Svenska' }

export default {
  data() {
    return {
      username: '',
      password: '',
      errorMessage: '',
      forgotDialogVisible: false,
      resetIdentifier: '',
      sendingReset: false,
      selectedLocale: '',
    }
  },
  computed: {
    localeOptions() {
      try {
        const keys = Object.keys(i18nMessages).filter(k => k.indexOf('-') !== -1)
        return keys.map(k => ({ label: LANG_LABELS[k] || k, value: k }))
      } catch (e) {
        return []
      }
    }
    ,
    selectedLocaleLabel() {
      try {
        const opts = this.localeOptions || []
        const found = opts.find(o => o && (o.value === this.selectedLocale))
        if (found && found.label) return found.label
      } catch (e) {}
      return LANG_LABELS[this.selectedLocale] || this.selectedLocale || ''
    }
  },
  mounted() {
    try {
      const canonical = (id) => {
        if (!id) return null
        // if it's already a full locale (contains -) and exists in messages, return it
        if (i18nMessages[id] && id.indexOf('-') !== -1) return id
        // map short codes to a full variant present in messages
        const keys = Object.keys(i18nMessages).filter(k => k.indexOf('-') !== -1)
        const base = String(id).split('-')[0]
        const found = keys.find(k => k.toLowerCase().startsWith(base.toLowerCase()))
        return found || keys[0] || id
      }

      let cur = null
      if (this.$i18n && this.$i18n.global && this.$i18n.global.locale) {
        cur = this.$i18n.global.locale.value
      } else if (this.$i18n && this.$i18n.locale) {
        cur = this.$i18n.locale
      } else if (typeof navigator !== 'undefined') {
        cur = (navigator.language && navigator.language.startsWith('sv') ? 'sv-SE' : 'en-US')
      }
      this.selectedLocale = canonical(cur)
    } catch (e) {}
  },
  methods: {
    onLocaleChange(v) { this.setLocale(v) },
    setLocale(id) {
      if (!id) return
      const canonical = (id2) => {
        if (!id2) return null
        if (i18nMessages[id2] && id2.indexOf('-') !== -1) return id2
        const keys = Object.keys(i18nMessages).filter(k => k.indexOf('-') !== -1)
        const base = String(id2).split('-')[0]
        const found = keys.find(k => k.toLowerCase().startsWith(base.toLowerCase()))
        return found || keys[0] || id2
      }
      const final = canonical(id)
      try {
        if (this.$i18n && this.$i18n.global && this.$i18n.global.locale) {
          this.$i18n.global.locale.value = final
        } else if (this.$i18n && this.$i18n.locale !== undefined) {
          this.$i18n.locale = final
        }
      } catch (e) {}
      try {
        if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
          window.localStorage.setItem('locale', final)
        }
      } catch (e) {}
      this.selectedLocale = final
    },
    async login() {
      try {
        const params = new URLSearchParams()
        params.append('username', this.username)
        params.append('password', this.password)
        params.append('grant_type', 'password')
        params.append('client_id', 'frontend')

        const response = await axios.post('/oauth/token', params, {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        })
        const access_token = response.data.access_token
        const refresh_token = response.data.refresh_token
        try {
          if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
            window.localStorage.setItem('access_token', access_token)
            window.localStorage.setItem('refresh_token', refresh_token)
          }
        } catch (e) {}
        this.errorMessage = ''
      } catch (error) {
        console.error('Login request failed:', error)
        this.errorMessage = this.$t('login.bad_credentials') || 'Invalid username or password'
        return
      }
      try {
        await this.$router.push({ name: 'index' })
      } catch (navErr) {
        console.warn('Navigation after login failed, falling back to path:', navErr)
        try { await this.$router.push('/') } catch (e) { console.warn('Fallback navigation also failed', e) }
      }
    },
    isAuthenticated() {
      try {
        if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
          return window.localStorage.getItem('access_token') !== null
        }
      } catch (e) {}
      return false
    },
    logout() {
      try {
        if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
          window.localStorage.removeItem('access_token')
          window.localStorage.removeItem('refresh_token')
        }
      } catch (e) {}
      this.$router.push('/login').catch(() => {})
    },
    async sendResetRequest() {
      if (!this.resetIdentifier || !String(this.resetIdentifier).trim()) {
        this.$q.notify({ type: 'warning', message: this.$t('login.forgot_help') || 'Please enter a username or email' })
        return
      }
      this.sendingReset = true
      try {
        await axios.post('/api/user/password_reset', { identifier: this.resetIdentifier.trim() })
        this.$q.notify({ type: 'positive', message: this.$t('login.reset_sent_notice') || 'If an account exists we will send a password reset email.' })
        this.forgotDialogVisible = false
        this.resetIdentifier = ''
      } catch (err) {
        console.error('password reset request failed', err)
        this.$q.notify({ type: 'negative', message: err.response?.data?.detail || this.$t('failed') || 'Failed to request password reset' })
      } finally {
        this.sendingReset = false
      }
    }
  }
}
</script>
