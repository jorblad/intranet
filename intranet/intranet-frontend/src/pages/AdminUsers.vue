<template>
  <q-page padding>
    <div class="row items-center q-gutter-md">
      <q-input v-model="form.username" :label="$t('adminUsers.username')" />
      <q-input v-model="form.display_name" :label="$t('adminUsers.display_name')" />
      <q-input v-model="form.password" type="password" :label="$t('adminUsers.password')" :input-attrs="{ autocomplete: 'new-password' }" />
      <q-btn :label="$t('adminUsers.create')" color="primary" @click="createUser" />
    </div>

    <div class="q-mt-md">
      <q-input dense v-model="search" :label="$t('adminUsers.search')" clearable @input="onSearch" />
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
            <q-btn dense flat color="negative" icon="delete" @click="deleteUser(props.row.id)" />
          </q-td>
        </template>
      </q-table>
    </div>
  </q-page>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useQuasar } from 'quasar'
import axios from 'axios'
const $q = useQuasar()

import { useI18n } from 'vue-i18n'
const { t } = useI18n()

const users = ref([])
const form = ref({ username: '', display_name: '', password: '' })

const search = ref('')
const columns = [
  { name: 'user', label: t('adminUsers.user'), field: 'attributes.display_name', align: 'left' },
  { name: 'actions', label: '', field: 'actions', sortable: false }
]
const pagination = ref({ page: 1, rowsPerPage: 10 })

const editingId = ref(null)
const editDisplayName = ref('')

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
    await axios.patch(`/api/user/user/${row.id}`, { display_name: editDisplayName.value.trim() })
    await load()
    $q.notify({ type: 'positive', message: t('adminUsers.updated') })
    cancelEdit()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminUsers.update_failed') })
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

onMounted(load)
</script>

<style scoped>
</style>
