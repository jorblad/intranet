<template>
  <q-page class="row items-center justify-center">
    <form @submit.prevent="submit">
      <q-card style="min-width:320px; max-width:420px;">
        <q-card-section>
          <div class="text-h6">{{ $t('inviteAccept.setPasswordTitle') }}</div>
        </q-card-section>
        <q-card-section>
          <div v-if="loading" class="text-caption">{{ $t('inviteAccept.loadingInvite') }}</div>
          <div v-else>
            <div v-if="!tokenValid" class="q-mb-sm text-negative">
              <div class="text-subtitle2">{{ $t('inviteAccept.invalidOrExpiredToken') }}</div>
              <pre v-if="debugInfo && process.env.DEV" style="margin-top:8px; white-space:pre-wrap; color:var(--q-color-grey-4)">{{ JSON.stringify(debugInfo, null, 2) }}</pre>
            </div>
            <div v-else class="q-mb-sm">
              <div class="text-subtitle2">{{ $t('inviteAccept.username') }} <strong>{{ username }}</strong></div>
              <div v-if="displayName" class="text-caption">{{ $t('inviteAccept.displayName') }} {{ displayName }}</div>
              <q-input v-model="password" type="password" :label="$t('inviteAccept.password')" dense />
              <q-input v-model="confirm" type="password" :label="$t('inviteAccept.confirmPassword')" dense class="q-mt-sm" />
            </div>
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat type="button" :label="$t('common.cancel')" @click="goLogin" />
          <q-btn color="primary" type="submit" :label="$t('common.save')" />
        </q-card-actions>
      </q-card>
    </form>
  </q-page>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'

const route = useRoute()
const router = useRouter()
const $q = useQuasar()
const { t } = useI18n()

const token = ref('')
const password = ref('')
const confirm = ref('')
const username = ref('')
const displayName = ref('')
const loading = ref(false)
const tokenValid = ref(true)
const debugInfo = ref(null)

onMounted(() => {
  token.value = route.query.token || ''
  // fallback: if router query is empty (hash-mode routing or normalization issues),
  // try to read token from the URL hash manually
  if (!token.value && typeof window !== 'undefined') {
    try {
      const h = String(window.location.hash || '')
      const m = h.match(/[?&]token=([^&]+)/)
      if (m) token.value = decodeURIComponent(m[1])
    } catch (e) {}
  }
  if (token.value) {
    loading.value = true
    axios.get('/api/user/invite', { params: { token: token.value } }).then(res => {
      const d = res.data?.data || {}
      debugInfo.value = d
      if (d && d.user && d.user.username) {
        username.value = d.user.username || ''
        displayName.value = d.user.display_name || ''
        tokenValid.value = true
      } else {
        tokenValid.value = false
      }
    }).catch(err => {
      debugInfo.value = err.response?.data || null
      tokenValid.value = false
    }).finally(() => { loading.value = false })
  } else {
    // no token in query -> mark invalid so user cannot submit
    tokenValid.value = false
  }
})

function goLogin() {
  router.push({ name: 'index' })
}

async function submit() {
  if (!token.value) {
    $q.notify({ type: 'negative', message: 'Missing invite token' })
    return
  }
  if (!password.value) {
    $q.notify({ type: 'warning', message: 'Please provide a password' })
    return
  }
  if (password.value !== confirm.value) {
    $q.notify({ type: 'warning', message: 'Passwords do not match' })
    return
  }

  try {
    if (!tokenValid.value) {
      $q.notify({ type: 'negative', message: 'Missing or invalid invite token' })
      return
    }
    // Backend expects token and password as query params for this POST
    await axios.post('/api/user/invite/accept', null, { params: { token: token.value, password: password.value } })
    $q.notify({ type: 'positive', message: 'Password set — you may now log in' })
    router.push({ path: '/login' })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || 'Failed to accept invite' })
  }
}
</script>

<style scoped>
</style>
