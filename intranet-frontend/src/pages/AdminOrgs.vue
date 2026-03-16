<template>
  <q-page padding>
    <div class="row items-center q-gutter-md">
      <q-input v-model="newOrg" :label="$t('orgs.new_placeholder')" @keyup.enter="createOrg" />
      <q-select
        v-model="newOrgLang"
        :options="languageOptions"
        :label="$t('orgs.language')"
        dense
        style="min-width: 160px"
        emit-value
        map-options
        option-label="label"
        option-value="value"
      />
      <q-btn :label="$t('orgs.create')" color="primary" @click="createOrg" />
    </div>

    <div class="q-mt-md">
      <q-input dense v-model="search" :label="$t('orgs.search')" clearable @input="onSearch" />
      <q-table
        :rows="filteredOrgs"
        :columns="columns"
        :pagination="pagination"
        row-key="id"
        :no-data-label="$t('orgs.no_data')"
      >
        <template v-slot:body-cell-name="props">
          <q-td :props="props">
            <div v-if="editingId === props.row.id">
              <q-input dense v-model="editName" @keyup.enter="saveEdit(props.row)" />
              <q-btn dense flat icon="check" @click="saveEdit(props.row)" />
              <q-btn dense flat icon="close" color="negative" @click="cancelEdit" />
            </div>
            <div v-else>
              {{ props.row.name }}
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-language="props">
          <q-td :props="props">
            <div v-if="editingId === props.row.id">
              <q-select dense v-model="editLang" :options="languageOptions" emit-value map-options style="min-width: 160px" />
            </div>
            <div v-else>
              {{ (languageOptions.find(o => o.value === props.row.language)?.label) || props.row.language || '-' }}
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-actions="props">
            <q-td align="right">
            <q-btn dense flat icon="edit" @click="startEdit(props.row)" />
            <q-btn dense flat color="negative" icon="delete" @click="deleteOrg(props.row.id)" />
          </q-td>
        </template>
      </q-table>
    </div>
  </q-page>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useQuasar } from 'quasar'
import { useI18n } from 'vue-i18n'
import axios from 'axios'
const $q = useQuasar()
const { t } = useI18n()

const orgs = ref([])
const newOrg = ref('')

const search = ref('')
const columns = [
  { name: 'name', label: t('orgs.name'), field: 'name', align: 'left' },
  { name: 'language', label: t('orgs.language'), field: 'language', align: 'left' },
  { name: 'actions', label: '', field: 'actions', sortable: false }
]
const pagination = ref({ page: 1, rowsPerPage: 10 })

const editingId = ref(null)
const editName = ref('')
const editLang = ref(null)

const newOrgLang = ref(null)

const languageOptions = [
  { label: 'English', value: 'en-US' },
  { label: 'Svenska', value: 'sv-SE' }
]

const filteredOrgs = computed(() => {
  if (!search.value) return orgs.value
  const q = search.value.toLowerCase()
  return orgs.value.filter(o => (o.name || '').toLowerCase().includes(q))
})

async function load() {
  try {
    const res = await axios.get('/api/rbac/organizations')
    orgs.value = res.data?.data || res.data || []
  } catch (err) {
    $q.notify({ type: 'negative', message: t('orgs.create_failed') || 'Failed to load organizations' })
  }
}

async function createOrg() {
    if (!newOrg.value || !newOrg.value.trim()) {
    $q.notify({ type: 'warning', message: t('orgs.name_empty') })
    return
  }
  try {
    await axios.post('/api/rbac/organizations', { name: newOrg.value.trim(), language: newOrgLang.value || null })
    newOrg.value = ''
    newOrgLang.value = null
    await load()
    $q.notify({ type: 'positive', message: t('orgs.created') })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('orgs.create_failed') })
  }
}

function onSearch() {
  pagination.value.page = 1
}

function startEdit(row) {
  editingId.value = row.id
  editName.value = row.name
  editLang.value = row.language || null
}

function cancelEdit() {
  editingId.value = null
  editName.value = ''
  editLang.value = null
}

async function saveEdit(row) {
  if (!editName.value || !editName.value.trim()) {
    $q.notify({ type: 'warning', message: t('orgs.name_empty') })
    return
  }
  try {
    await axios.patch(`/api/rbac/organizations/${row.id}`, { name: editName.value.trim(), language: editLang.value || null })
    await load()
    $q.notify({ type: 'positive', message: t('orgs.updated') })
    cancelEdit()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('orgs.update_failed') })
  }
}

async function deleteOrg(id) {
  try {
    await axios.delete(`/api/rbac/organizations/${id}`)
    await load()
    $q.notify({ type: 'positive', message: t('orgs.deleted') })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('orgs.delete_failed') })
  }
}

onMounted(load)
</script>

<style scoped>
</style>
