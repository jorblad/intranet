<template>
  <q-page padding>
    <!-- Anti-autofill trap: off-screen inputs to capture browser password/autofill behavior (Edge workaround) -->
    <div style="position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden;" aria-hidden="true">
      <input autocomplete="username" tabindex="-1" />
      <input type="password" autocomplete="current-password" tabindex="-1" />
    </div>
    <div class="row items-center q-gutter-md">
      <q-input v-model="form.username" :label="$t('adminUsers.username')" />
      <q-input v-model="form.display_name" :label="$t('adminUsers.display_name')" />
      <q-input v-model="form.password" type="password" :label="$t('adminUsers.password')" :input-attrs="{ autocomplete: 'new-password' }" />
      <q-btn :label="$t('adminUsers.create')" color="primary" @click="createUser" />
    </div>

    <div class="q-mt-md">
      <q-input dense v-model="search" :label="$t('adminUsers.search')" clearable @input="onSearch" :input-attrs="{ autocomplete: 'off', spellcheck: false, name: searchInputName }" />
      <q-table
        :rows="filteredUsers"
        :columns="columns"
        :pagination="pagination"
        row-key="id"
        :no-data-label="$t('adminUsers.no_users')"
      >
        <template v-slot:body-cell-user="props">
          <q-td :props="props">
            <div v-if="editingId === props.row.id">
              <q-input dense v-model="editUsername" label="Username" class="q-mb-xs" />
              <q-input dense v-model="editDisplayName" @keyup.enter="saveEdit(props.row)" />
              <q-btn dense flat icon="check" @click="saveEdit(props.row)" />
              <q-btn dense flat icon="close" color="negative" @click="cancelEdit" />
            </div>
            <div v-else>
              {{ props.row.attributes.display_name }} ({{ props.row.attributes.username }})
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-actions="props">
          <q-td align="right">
            <q-btn dense flat icon="edit" @click="startEdit(props.row)" />
            <q-btn dense flat color="secondary" icon="vpn_key" @click="resetPassword(props.row)" :title="t('adminUsers.reset_password')" />
            <q-btn dense flat color="negative" icon="delete" @click="deleteUser(props.row.id)" />
          </q-td>
        </template>
      </q-table>
      <!-- Reset password result dialog -->
      <q-dialog v-model="resetDialogVisible">
        <q-card>
          <q-card-section>
            <div class="text-h6">{{ t('adminUsers.reset_password') }}</div>
            <div class="text-subtitle2">{{ resetPasswordUser?.attributes?.display_name }} ({{ resetPasswordUser?.attributes?.username }})</div>
          </q-card-section>
          <q-card-section>
            <div class="q-mb-md">{{ t('adminUsers.reset_success', { pw: resetPasswordValue }) }}</div>
            <div class="row items-center">
              <div class="col"> <code style="font-size:1.1rem">{{ resetPasswordValue }}</code> </div>
              <!-- copy button moved to dialog actions as 'Copy & Close' -->
            </div>
          </q-card-section>
          <q-card-actions>
            <q-space />
            <q-btn flat icon="content_copy" :label="t('adminUsers.copy_close')" color="primary" @click="copyAndClose" />
          </q-card-actions>
        </q-card>
      </q-dialog>
      <!-- Inline confirmation dialog to avoid depending on $q.dialog -->
      <q-dialog v-model="confirmDialogVisible">
        <q-card>
          <q-card-section>
            <div class="text-h6">{{ t('adminUsers.reset_password') }}</div>
            <div class="text-body1">{{ confirmMessage }}</div>
          </q-card-section>
          <q-card-actions>
            <q-btn flat :label="t('common.cancel')" color="secondary" v-close-popup @click="confirmDialogVisible = false" />
            <q-space />
            <q-btn flat :label="t('adminUsers.reset_password')" color="primary" @click="confirmProceed" />
          </q-card-actions>
        </q-card>
      </q-dialog>
    </div>
  </q-page>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useQuasar } from 'quasar'
import axios from 'axios'
const $q = useQuasar()

import { useI18n } from 'vue-i18n'
const { t } = useI18n()

const users = ref([])
const form = ref({ username: '', display_name: '', password: '' })

const search = ref('')
// randomize input name to avoid browser autofill matching stored field names on reload
const searchInputName = ref(`admin-users-search-${Date.now()}`)
const columns = [
  { name: 'user', label: t('adminUsers.user'), field: 'attributes.display_name', align: 'left' },
  { name: 'actions', label: '', field: 'actions', sortable: false }
]
const pagination = ref({ page: 1, rowsPerPage: 10 })

const editingId = ref(null)
const editDisplayName = ref('')
const editUsername = ref('')
const resetDialogVisible = ref(false)
const resetPasswordValue = ref('')
const resetPasswordUser = ref(null)
const confirmDialogVisible = ref(false)
const confirmMessage = ref('')
const confirmTargetUser = ref(null)

const filteredUsers = computed(() => {
  if (!search.value) return users.value
  const q = search.value.toLowerCase()
  return users.value.filter(u => {
    const dn = (u.attributes.display_name || '').toLowerCase()
    const un = (u.attributes.username || '').toLowerCase()
    return dn.includes(q) || un.includes(q)
  })
})

async function load() {
  try {
    const res = await axios.get('/api/user/user')
    users.value = res.data.data
    // ensure search is cleared after loading to avoid any autofill-preserved text
    try { search.value = '' } catch (e) {}
  } catch (err) {
    $q.notify({ type: 'negative', message: t('adminUsers.load_failed') })
  }
}

async function createUser() {
    if (!form.value.username || !form.value.password) {
    $q.notify({ type: 'warning', message: t('adminUsers.username_password_required') })
    return
  }
  try {
    await axios.post('/api/user/user', form.value)
    form.value = { username: '', display_name: '', password: '' }
    await load()
    $q.notify({ type: 'positive', message: t('adminUsers.created') })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminUsers.create_failed') })
  }
}

function onSearch() {
  pagination.value.page = 1
}

function startEdit(row) {
  editingId.value = row.id
  editDisplayName.value = row.attributes.display_name
  editUsername.value = row.attributes.username || ''
}

function cancelEdit() {
  editingId.value = null
  editDisplayName.value = ''
}

async function saveEdit(row) {
  if (!editDisplayName.value || !editDisplayName.value.trim()) {
    $q.notify({ type: 'warning', message: t('adminUsers.display_name_empty') })
    return
  }
  try {
    const payload = { display_name: editDisplayName.value.trim() }
    if (editUsername.value && editUsername.value.trim()) payload.username = editUsername.value.trim()
    await axios.patch(`/api/user/user/${row.id}`, payload)
    await load()
    $q.notify({ type: 'positive', message: t('adminUsers.updated') })
    cancelEdit()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminUsers.update_failed') })
  }
}

async function resetPassword(row) {
  // Show inline confirmation dialog and call performReset on confirm
  try {
    console.debug('resetPassword called for', row && row.id)
    confirmMessage.value = t('adminUsers.reset_confirm', { name: row.attributes.display_name || row.attributes.username })
    confirmTargetUser.value = row
    confirmDialogVisible.value = true
  } catch (e) {
    console.error('resetPassword error', e)
    // fallback to native confirm on error
    try { if (window.confirm(t('adminUsers.reset_confirm', { name: row.attributes.display_name || row.attributes.username }))) performReset(row) } catch (e) {}
  }
}

function confirmProceed() {
  if (!confirmTargetUser.value) return
  confirmDialogVisible.value = false
  // call performReset asynchronously to avoid blocking UI thread
  setTimeout(() => { try { performReset(confirmTargetUser.value) } catch (e) { console.error(e) } }, 50)
}

async function performReset(row) {
  try {
    // blur any focused element to avoid browser autofill/autocomplete populating inputs
    try { if (document && document.activeElement) document.activeElement.blur() } catch (e) {}
    const res = await axios.post(`/api/user/user/${row.id}/reset_password`)
    const newPw = res.data?.data?.new_password
    resetPasswordValue.value = newPw || ''
    resetPasswordUser.value = row
    resetDialogVisible.value = true
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminUsers.reset_failed') })
  }
}

async function copyResetPassword() {
  try {
    if (navigator && navigator.clipboard && resetPasswordValue.value) {
      await navigator.clipboard.writeText(resetPasswordValue.value)
      $q.notify({ type: 'positive', message: t('adminUsers.copy_success') })
    }
  } catch (e) {
    $q.notify({ type: 'negative', message: t('failed') })
  }
}

async function copyAndClose() {
  try {
    if (navigator && navigator.clipboard && resetPasswordValue.value) {
      await navigator.clipboard.writeText(resetPasswordValue.value)
      $q.notify({ type: 'positive', message: t('adminUsers.copy_success') })
    }
  } catch (e) {
    $q.notify({ type: 'negative', message: t('failed') })
  } finally {
    resetDialogVisible.value = false
  }
}

async function deleteUser(id) {
  try {
    await load()
    await axios.delete(`/api/user/user/${id}`)
    await load()
    $q.notify({ type: 'positive', message: t('adminUsers.deleted') })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminUsers.delete_failed') })
  }
}

onMounted(() => {
  // Clear and briefly protect the search input to avoid Edge autofill restoring values on reload.
  try {
    search.value = ''
    // mark readonly briefly so some autofill engines skip it, then remove readonly
    const name = searchInputName.value
    const el = document.getElementsByName(name)[0]
    if (el) {
      el.setAttribute('readonly', 'true')
      setTimeout(() => { try { el.removeAttribute('readonly') } catch (e) {} }, 50)
    }
    // Ensure on back/forward or reload pageshow we clear the field again
    const pageshowHandler = () => { setTimeout(() => { try { search.value = '' } catch (e) {} }, 50) }
    window.addEventListener('pageshow', pageshowHandler)
    // remove listener on unmount
    onBeforeUnmount(() => { try { window.removeEventListener('pageshow', pageshowHandler) } catch (e) {} })
  } catch (e) {}

  load()
})
</script>

<style scoped>
</style>
