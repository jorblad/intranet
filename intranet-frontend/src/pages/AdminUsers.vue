<template>
  <q-page padding>
    <!-- Anti-autofill trap: off-screen inputs to capture browser password/autofill behavior (Edge workaround) -->
    <div style="position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden;" aria-hidden="true">
      <input autocomplete="username" tabindex="-1" />
      <input type="password" autocomplete="current-password" tabindex="-1" />
    </div>
    <div class="row q-col-gutter-md items-start">
      <div class="col">
        <q-card flat bordered class="q-pa-sm">
          <q-card-section>
            <div class="row q-gutter-sm">
              <div class="col-12">
                <div class="row items-center q-gutter-sm">
                  <div class="col-12 col-sm-4 col-md-3">
                    <q-input dense stack-label v-model="form.username" :label="$t('adminUsers.username')" />
                  </div>
                  <div class="col-12 col-sm-4 col-md-3">
                    <q-input dense stack-label v-model="form.display_name" :label="$t('adminUsers.display_name')" />
                  </div>
                  <div class="col-12 col-sm-4 col-md-3">
                    <q-input dense stack-label v-model="form.email" :label="$t('adminUsers.email')" />
                  </div>
                </div>
                <div class="row items-center q-gutter-sm q-mt-sm">
                  <div class="col-12 col-sm-4 col-md-2">
                    <q-input dense stack-label v-model="form.password" type="password" :label="$t('adminUsers.password')" :input-attrs="{ autocomplete: 'new-password' }" />
                  </div>
                  <div class="col-12 col-sm-4 col-md-2">
                    <q-select dense stack-label emit-value v-model="form.language" :options="langOptions" option-label="label" option-value="value" :label="$t('adminUsers.language')" clearable :display-value="getLangLabel(form.language)" />
                  </div>
                  <div class="col-auto">
                    <div class="row items-center no-wrap q-gutter-sm">
                      <q-btn dense color="primary" :label="$t('adminUsers.create')" @click="createUser" />
                      <q-btn dense color="secondary" :label="$t('adminUsers.invite_user')" @click="openInviteDialog" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>
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
            <div>
              {{ props.row.attributes.display_name }} ({{ props.row.attributes.username }}) <span v-if="props.row.attributes.email">&lt;{{ props.row.attributes.email }}&gt;</span>
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-actions="props">
          <q-td align="right">
            <q-btn dense flat icon="edit" @click="startEdit(props.row)" />
            <q-btn dense flat color="secondary" icon="vpn_key" @click="resetPassword(props.row)" :title="t('adminUsers.reset_password')" />
            <q-btn dense flat color="negative" icon="delete" @click="askDeleteUser(props.row)" />
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
      <!-- Edit user dialog -->
      <q-dialog v-model="editDialogVisible">
        <q-card style="min-width:320px; max-width:70vw;">
          <q-card-section>
            <div class="text-h6">{{ t('common.edit') }}</div>
            <div class="text-subtitle2">{{ editDisplayName }}</div>
          </q-card-section>
          <q-card-section>
            <q-input v-model="editUsername" :label="t('adminUsers.username')" />
            <q-input v-model="editDisplayName" :label="t('adminUsers.display_name')" />
            <q-input v-model="editEmail" :label="t('adminUsers.email')" />
            <q-select stack-label emit-value v-model="editLanguage" :options="langOptions" option-label="label" option-value="value" :label="t('adminUsers.language')" dense clearable style="min-width:160px; max-width:220px" :display-value="getLangLabel(editLanguage)" />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat :label="t('common.cancel')" color="secondary" @click="cancelEdit" />
            <q-btn color="primary" :label="t('common.save')" @click="saveEditDialog" />
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
            <q-btn flat :label="t('adminUsers.send_reset_link')" color="primary" @click="confirmSendResetLink" />
            <q-btn flat :label="t('adminUsers.reset_password')" color="primary" @click="confirmProceed" />
          </q-card-actions>
        </q-card>
      </q-dialog>
      <!-- Delete user confirmation dialog -->
      <q-dialog v-model="deleteDialogVisible">
        <q-card>
          <q-card-section>
            <div class="text-h6">{{ t('common.delete') }}</div>
            <div class="text-body1">{{ t('adminUsers.delete_confirm', { name: deleteTargetUserName }) }}</div>
          </q-card-section>
          <q-card-actions>
            <q-btn flat :label="t('common.cancel')" color="secondary" @click="cancelDeleteUser" />
            <q-space />
            <q-btn flat :label="t('common.delete')" color="negative" @click="confirmDeleteUser" />
          </q-card-actions>
        </q-card>
      </q-dialog>
      <!-- Invite user dialog -->
      <q-dialog v-model="inviteDialogVisible">
        <q-card style="min-width:320px; max-width:70vw;">
          <q-card-section>
            <div class="text-h6">{{ t('adminUsers.invite_user') }}</div>
          </q-card-section>
          <q-card-section>
            <q-input v-model="inviteForm.username" :label="t('adminUsers.username')" />
            <q-input v-model="inviteForm.display_name" :label="t('adminUsers.display_name')" />
            <q-input v-model="inviteForm.email" :label="t('adminUsers.email')" />
            <q-select stack-label emit-value v-model="inviteForm.language" :options="langOptions" option-label="label" option-value="value" :label="t('adminUsers.language')" dense clearable style="min-width:160px; max-width:220px" :display-value="getLangLabel(inviteForm.language)" />
            <div class="q-mt-sm">
              <div v-for="(a, idx) in inviteForm.assignments" :key="idx" class="row items-center q-gutter-sm q-mb-sm">
                <q-select stack-label v-model="inviteForm.assignments[idx].organization_id" :options="orgOptions" :label="t('adminUsers.organization')" emit-value option-value="value" option-label="label" clearable style="min-width:160px; max-width:220px" :display-value="getOrgLabel(inviteForm.assignments[idx].organization_id)" />
                <q-select stack-label v-model="inviteForm.assignments[idx].role_id" :options="roleOptions" :label="t('adminUsers.role')" emit-value option-value="value" option-label="label" clearable style="min-width:140px; max-width:200px" :display-value="getRoleLabel(inviteForm.assignments[idx].role_id)" />
                <q-btn flat icon="remove_circle_outline" color="negative" @click="removeAssignment(idx)" />
              </div>
              <q-btn flat dense color="primary" @click="addAssignment" :label="t('adminUsers.add_assignment')" />
            </div>
            <q-toggle v-model="inviteForm.send_email" :label="t('adminUsers.send_email')" class="q-mt-md" />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat :label="t('common.cancel')" color="secondary" @click="inviteDialogVisible=false" />
            <q-btn color="primary" :label="t('adminUsers.invite_user')" @click="sendInvite" />
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
import i18nMessages from 'src/i18n'
const $q = useQuasar()

import { useI18n } from 'vue-i18n'
const { t } = useI18n()

const users = ref([])
const form = ref({ username: '', display_name: '', password: '', language: '', email: '' })

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
const editEmail = ref('')
const editLanguage = ref('')
const editDialogVisible = ref(false)
const editUserId = ref(null)
const resetDialogVisible = ref(false)
const resetPasswordValue = ref('')
const resetPasswordUser = ref(null)
const confirmDialogVisible = ref(false)
const confirmMessage = ref('')
const confirmTargetUser = ref(null)
const deleteDialogVisible = ref(false)
const deleteTargetUserId = ref(null)
const deleteTargetUserName = ref('')

const filteredUsers = computed(() => {
  if (!search.value) return users.value
  const q = search.value.toLowerCase()
  return users.value.filter(u => {
    const dn = (u.attributes.display_name || '').toLowerCase()
    const un = (u.attributes.username || '').toLowerCase()
    return dn.includes(q) || un.includes(q)
  })
})

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

const emailRegex = /^\S+@\S+\.\S+$/

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
    const payload = { username: form.value.username, display_name: form.value.display_name, password: form.value.password }
    if (form.value.email) {
      if (!emailRegex.test(form.value.email)) {
        $q.notify({ type: 'negative', message: t('adminUsers.invalid_email') })
        return
      }
      payload.email = form.value.email
    }
    if (form.value.language) payload.language = form.value.language
    await axios.post('/api/user/user', payload)
    form.value = { username: '', display_name: '', password: '', language: '', email: '' }
    await load()
    $q.notify({ type: 'positive', message: t('adminUsers.created') })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminUsers.create_failed') })
  }
}

const inviteDialogVisible = ref(false)
const inviteForm = ref({ username: '', display_name: '', email: '', language: '', assignments: [], send_email: true })
const orgOptions = ref([])
const roleOptions = ref([])

// Helpers to ensure q-select shows the label for a given stored value
function getLangLabel(val) {
  try {
    if (!val && val !== '') return ''
    const opts = langOptions.value || []
    const found = opts.find(o => String(o.value) === String(val))
    return found ? found.label : (val || '')
  } catch (e) {
    return val || ''
  }
}

function getOrgLabel(val) {
  try {
    if (!val && val !== '') return ''
    const opts = orgOptions.value || []
    const found = opts.find(o => String(o.value) === String(val))
    return found ? found.label : (val || '')
  } catch (e) {
    return val || ''
  }
}

function getRoleLabel(val) {
  try {
    if (!val && val !== '') return ''
    const opts = roleOptions.value || []
    const found = opts.find(o => String(o.value) === String(val))
    return found ? found.label : (val || '')
  } catch (e) {
    return val || ''
  }
}

async function openInviteDialog() {
  try {
    inviteDialogVisible.value = true
    // fetch organizations and roles for assignment pickers
    const [orgRes, roleRes, settingsRes] = await Promise.all([
      axios.get('/api/rbac/organizations').catch(() => ({ data: [] })),
      axios.get('/api/rbac/roles').catch(() => ({ data: [] })),
      axios.get('/api/admin/settings').catch(() => ({ data: {} })),
    ])
    // Normalize response shapes: backend may return { data: [...] } or [...]
    const orgList = orgRes?.data?.data || orgRes?.data || []
    const roleList = roleRes?.data?.data || roleRes?.data || []
    console.debug('openInviteDialog orgList', orgList)
    console.debug('openInviteDialog roleList', roleList)
    const settingsData = settingsRes?.data?.data || settingsRes?.data || {}
    // default invite language: prefer explicit invite_default_language, then server default
    try {
      inviteForm.value.language = inviteForm.value.language || settingsData.invite_default_language || settingsData.default_user_language || ''
    } catch (e) {
      console.error('failed setting invite default language', e)
    }

    orgOptions.value = (Array.isArray(orgList) ? orgList : []).map(o => ({
      label: o.attributes?.name || o.name || o.fields?.name || o.pk || '',
      value: o.id != null ? String(o.id) : (o.attributes && o.attributes.id != null ? String(o.attributes.id) : (o.pk != null ? String(o.pk) : null)),
    }))
    roleOptions.value = (Array.isArray(roleList) ? roleList : []).map(r => ({
      label: r.attributes?.name || r.name || r.fields?.name || r.pk || '',
      value: r.id != null ? String(r.id) : (r.attributes && r.attributes.id != null ? String(r.attributes.id) : (r.pk != null ? String(r.pk) : null)),
    }))
    console.debug('openInviteDialog orgOptions', orgOptions.value)
    console.debug('openInviteDialog roleOptions', roleOptions.value)
  } catch (e) {
    console.error('openInviteDialog error', e)
  }
}

function addAssignment() {
  inviteForm.value.assignments.push({ organization_id: null, role_id: null })
}

function removeAssignment(idx) {
  inviteForm.value.assignments.splice(idx, 1)
}

async function sendInvite() {
  try {
    const payload = { username: inviteForm.value.username, display_name: inviteForm.value.display_name, language: inviteForm.value.language, assignments: inviteForm.value.assignments, send_email: inviteForm.value.send_email }
    if (inviteForm.value.email) {
      if (!emailRegex.test(inviteForm.value.email)) {
        $q.notify({ type: 'negative', message: t('adminUsers.invalid_email') })
        return
      }
      payload.email = inviteForm.value.email
    }
    if (inviteForm.value.send_email && !inviteForm.value.email) {
      $q.notify({ type: 'negative', message: t('adminUsers.invalid_email') })
      return
    }
    const res = await axios.post('/api/user/invite', payload)
    const emailSent = !!(res?.data?.data?.email_sent)
    if (payload.send_email) {
      if (!emailSent) {
        $q.notify({ type: 'warning', message: t('adminUsers.invite_failed') })
      } else {
        $q.notify({ type: 'positive', message: t('adminUsers.invite_sent') })
      }
    } else {
      $q.notify({ type: 'positive', message: t('adminUsers.invite_sent') })
    }
    inviteDialogVisible.value = false
    inviteForm.value = { username: '', display_name: '', email: '', language: '', assignments: [], send_email: true }
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminUsers.invite_failed') })
  }
}

function onSearch() {
  pagination.value.page = 1
}

function startEdit(row) {
  // open edit dialog instead of inline editing
  editUserId.value = row.id
  editDisplayName.value = row.attributes.display_name || ''
  editUsername.value = row.attributes.username || ''
  editLanguage.value = row.attributes.language || ''
  editEmail.value = row.attributes.email || ''
  editDialogVisible.value = true
}

function cancelEdit() {
  editDialogVisible.value = false
  editUserId.value = null
  editDisplayName.value = ''
  editUsername.value = ''
  editLanguage.value = ''
  editEmail.value = ''
}

async function saveEditDialog() {
  if (!editDisplayName.value || !editDisplayName.value.trim()) {
    $q.notify({ type: 'warning', message: t('adminUsers.display_name_empty') })
    return
  }
  try {
    const payload = { display_name: editDisplayName.value.trim() }
    if (editUsername.value && editUsername.value.trim()) payload.username = editUsername.value.trim()
    if (editLanguage.value) payload.language = editLanguage.value
    if (editEmail.value) payload.email = editEmail.value
    await axios.patch(`/api/user/user/${editUserId.value}`, payload)
    await load()
    $q.notify({ type: 'positive', message: t('adminUsers.updated') })
    cancelEdit()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminUsers.update_failed') })
  }
}

async function saveEdit(row) {
  if (!editDisplayName.value || !editDisplayName.value.trim()) {
    $q.notify({ type: 'warning', message: t('adminUsers.display_name_empty') })
    return
  }
  try {
    const payload = { display_name: editDisplayName.value.trim() }
    if (editUsername.value && editUsername.value.trim()) payload.username = editUsername.value.trim()
    if (editLanguage.value) payload.language = editLanguage.value
    if (editEmail.value) payload.email = editEmail.value
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

function confirmSendResetLink() {
  if (!confirmTargetUser.value) return
  confirmDialogVisible.value = false
  setTimeout(() => { try { performSendResetLink(confirmTargetUser.value) } catch (e) { console.error(e) } }, 50)
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

async function performSendResetLink(row) {
  try {
    try { if (document && document.activeElement) document.activeElement.blur() } catch (e) {}
    const res = await axios.post(`/api/user/user/${row.id}/send_reset_link`)
    const sent = !!(res?.data?.data?.email_sent)
    if (sent) {
      $q.notify({ type: 'positive', message: t('adminUsers.reset_link_sent') })
    } else {
      $q.notify({ type: 'warning', message: t('adminUsers.reset_link_failed') })
    }
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminUsers.reset_link_failed') })
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

function askDeleteUser(row) {
  deleteTargetUserId.value = row?.id || null
  deleteTargetUserName.value = row?.attributes?.display_name || row?.attributes?.username || ''
  deleteDialogVisible.value = true
}

function cancelDeleteUser() {
  deleteDialogVisible.value = false
  deleteTargetUserId.value = null
  deleteTargetUserName.value = ''
}

async function confirmDeleteUser() {
  const id = deleteTargetUserId.value
  cancelDeleteUser()
  if (!id) return
  await deleteUser(id)
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
