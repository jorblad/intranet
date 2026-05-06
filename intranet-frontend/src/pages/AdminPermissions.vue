<template>
  <q-page padding>
    <div class="q-mt-md">
      <q-input dense v-model="search" :label="$t('adminPermissions.search')" clearable @input="onSearch" />
      <q-table
        :rows="filteredPermissions"
        :columns="columns"
        :pagination="pagination"
        row-key="id"
        :no-data-label="$t('adminPermissions.no_permissions')"
      >
        <template v-slot:body-cell-codename="props">
          <q-td :props="props">
            <div v-if="editingId === props.row.id">
              <q-input dense v-model="editCodename" @keyup.enter="saveEdit(props.row)" />
            </div>
            <div v-else>
              {{ props.row.codename }}
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-description="props">
          <q-td :props="props">
            <div v-if="editingId === props.row.id">
              <q-input dense v-model="editDescription" @keyup.enter="saveEdit(props.row)" />
            </div>
            <div v-else>
              {{ props.row.description || '-' }}
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-actions="props">
          <q-td align="right">
            <q-btn dense flat icon="edit" @click="startEdit(props.row)" />
            <q-btn dense flat color="negative" icon="delete" @click="deletePermission(props.row.id)" />
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

const permissions = ref([])

const search = ref('')
const columns = [
  { name: 'codename', label: t('adminPermissions.codename'), field: 'codename', align: 'left' },
  { name: 'description', label: t('adminPermissions.description'), field: 'description', align: 'left' },
  { name: 'actions', label: '', field: 'actions', sortable: false }
]
const pagination = ref({ page: 1, rowsPerPage: 10 })

const editingId = ref(null)
const editCodename = ref('')
const editDescription = ref('')

const filteredPermissions = computed(() => {
  if (!search.value) return permissions.value
  const q = search.value.toLowerCase()
  return permissions.value.filter(p => (p.codename || '').toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q))
})

async function load() {
  try {
    const res = await axios.get('/api/rbac/permissions')
    permissions.value = res.data
  } catch (err) {
    $q.notify({ type: 'negative', message: t('adminPermissions.load_failed') })
  }
}

function onSearch() {
  pagination.value.page = 1
}

function startEdit(row) {
  editingId.value = row.id
  editCodename.value = row.codename
  editDescription.value = row.description || ''
}

function cancelEdit() {
  editingId.value = null
  editCodename.value = ''
  editDescription.value = ''
}

async function saveEdit(row) {
  if (!editCodename.value || !editCodename.value.trim()) {
    $q.notify({ type: 'warning', message: t('adminPermissions.codename_empty') })
    return
  }
  try {
    await axios.patch(`/api/rbac/permissions/${row.id}`, { codename: editCodename.value.trim(), description: editDescription.value?.trim() })
    await load()
    $q.notify({ type: 'positive', message: t('adminPermissions.updated') })
    cancelEdit()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminPermissions.update_failed') })
  }
}

async function deletePermission(id) {
  try {
    await load()
    await axios.delete(`/api/rbac/permissions/${id}`)
    await load()
    $q.notify({ type: 'positive', message: t('adminPermissions.deleted') })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('adminPermissions.delete_failed') })
  }
}

onMounted(load)
</script>

<style scoped>
</style>
