<template>
  <q-page padding>
    <div class="row items-center q-gutter-md">
      <q-input v-model="newName" :label="$t('admin.roles.new_role_name')" @keyup.enter="createRole" />
      <q-checkbox v-model="newIsGlobal" :label="$t('admin.roles.global_role')" />
      <q-btn :label="$t('admin.roles.create')" color="primary" @click="createRole" />
    </div>

    <div class="q-mt-md">
      <q-input dense v-model="search" :label="$t('admin.roles.search_placeholder')" clearable @input="onSearch" />
      <q-table
        :rows="filteredRoles"
        :columns="columns"
        :pagination="pagination"
        row-key="id"
        :no-data-label="$t('admin.roles.no_roles')"
      >
        <template v-slot:body-cell-name="props">
          <q-td :props="props">
            <div v-if="editingId === props.row.id">
              <q-input dense v-model="editName" @keyup.enter="saveEdit(props.row)" />
            </div>
            <div v-else>
              {{ props.row.name }}
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-is_global="props">
          <q-td :props="props">
            <div v-if="editingId === props.row.id">
              <q-checkbox dense v-model="editIsGlobal" :label="$t('admin.roles.global')" />
            </div>
            <div v-else>
              <q-badge :color="props.row.is_global ? 'primary' : 'grey'">{{ props.row.is_global ? $t('common.yes') : $t('common.no') }}</q-badge>
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-actions="props">
          <q-td align="right">
            <q-btn dense flat icon="edit" @click="startEdit(props.row)" />
            <q-btn dense flat icon="key" :label="$t('admin.roles.permissions')" @click="openPermissions(props.row)" />
            <q-btn dense flat color="negative" icon="delete" @click="deleteRole(props.row.id)" :aria-label="$t('admin.roles.delete')" />
          </q-td>
        </template>
      </q-table>
    </div>

    <q-dialog v-model="permsDialog">
      <q-card style="min-width:400px; max-width:720px;">
        <q-card-section>
          <div class="text-h6">{{ $t('admin.roles.edit_permissions_for', { name: currentRole?.name }) }}</div>
        </q-card-section>

        <q-separator />

        <q-card-section>
            <div class="row q-gutter-sm items-center">
              <q-select dense use-input v-model="resourceType" :options="resourceTypeOptions" option-value="value" option-label="label" :label="$t('admin.roles.resource_type')" style="min-width:240px" />
              <div class="text-caption q-ml-sm">{{ $t('admin.roles.choose_resource_type') }}</div>
            </div>

            <div class="row items-center q-gutter-sm q-mt-sm">
              <q-checkbox v-model="scoped" :label="$t('admin.roles.scoped_to_resource')" />
              <div v-if="scoped" class="row q-gutter-sm items-center">
                <q-input dense v-model="resourceId" :label="$t('admin.roles.resource_id_optional')" style="min-width:160px" />
                <q-btn dense :label="$t('admin.roles.load_scoped')" @click="loadScopedPermissions" />
              </div>
            </div>

          <div class="q-gutter-sm q-mt-sm">
            <q-checkbox v-for="p in allPermissions" :key="p.id" v-model="selectedPermissionIds" :val="p.id" :label="p.codename + (p.description ? ' — ' + p.description : '')" dense />
          </div>

          <div v-if="resourceTypeStr === 'activity'" class="q-mt-md">
            <div class="text-subtitle2">{{ $t('admin.roles.quick_presets_activities') }}</div>
            <div class="row q-gutter-sm q-mt-sm">
              <q-btn dense :label="$t('admin.roles.preset_none')" @click="applyResourcePreset('none')" />
              <q-btn dense :label="$t('admin.roles.preset_read')" color="primary" @click="applyResourcePreset('read')" />
              <q-btn dense :label="$t('admin.roles.preset_readwrite')" color="secondary" @click="applyResourcePreset('readwrite')" />
              <q-btn dense :label="$t('admin.roles.preset_admin')" color="accent" @click="applyResourcePreset('admin')" />
              <q-space />
              <q-btn dense outline :label="$t('admin.roles.set_default_for_all_activities')" @click="applyPresetAsDefault('read')" />
              <q-btn dense outline :label="$t('admin.roles.apply_to_all_activities')" color="warning" @click="applyPresetToAllResources('read')" />
            </div>
            <div class="text-caption q-mt-sm">{{ $t('admin.roles.presets_map_activity') }}</div>
          </div>

          <div v-if="resourceTypeStr === 'activity'" class="q-mt-md">
            <div class="text-subtitle2">{{ $t('admin.roles.apply_to_specific_activities') }}</div>
            <div class="row items-center q-gutter-sm q-mt-sm">
              <q-select dense multiple v-model="selectedActivityIds" :options="activityOptions" option-value="value" option-label="label" :label="$t('admin.roles.select_activities')" style="min-width:320px" use-chips />
              <q-btn dense :label="$t('admin.roles.apply_to_selected_activities')" color="primary" @click="applyPresetToSelectedActivities('read')" />
            </div>
            <div class="text-caption q-mt-sm">{{ $t('admin.roles.pick_activities_caption') }}</div>
          </div>

          <div v-if="resourceTypeStr === 'schedule'" class="q-mt-md">
            <div class="text-subtitle2">{{ $t('admin.roles.quick_presets_schedules') }}</div>
            <div class="row q-gutter-sm q-mt-sm">
              <q-btn dense :label="$t('admin.roles.preset_none')" @click="applyResourcePreset('none')" />
              <q-btn dense :label="$t('admin.roles.preset_read')" color="primary" @click="applyResourcePreset('read')" />
              <q-btn dense :label="$t('admin.roles.preset_readwrite')" color="secondary" @click="applyResourcePreset('readwrite')" />
              <q-btn dense :label="$t('admin.roles.preset_admin')" color="accent" @click="applyResourcePreset('admin')" />
              <q-space />
              <q-btn dense outline :label="$t('admin.roles.set_default_for_all_schedules')" @click="applyPresetAsDefault('read')" />
              <q-btn dense outline :label="$t('admin.roles.apply_to_all_schedules')" color="warning" @click="applyPresetToAllResources('read')" />
            </div>
            <div class="text-caption q-mt-sm">{{ $t('admin.roles.presets_map_schedule') }}</div>
          </div>

          <div v-if="resourceTypeStr === 'schedule'" class="q-mt-md">
            <div class="text-subtitle2">{{ $t('admin.roles.apply_to_specific_schedules') }}</div>
            <div class="row items-center q-gutter-sm q-mt-sm">
              <q-select dense multiple v-model="selectedScheduleIds" :options="scheduleOptions" option-value="value" option-label="label" :label="$t('admin.roles.select_schedules')" style="min-width:320px" use-chips />
              <q-btn dense :label="$t('admin.roles.apply_to_selected_schedules')" color="primary" @click="applyPresetToSelectedSchedules('read')" />
            </div>
            <div class="text-caption q-mt-sm">{{ $t('admin.roles.pick_schedules_caption') }}</div>
          </div>

          <q-separator class="q-mt-md" />
          <div class="q-mt-sm">
            <div class="text-subtitle2">{{ $t('admin.roles.scoped_permission_entries') }}</div>
            <q-table
              :rows="roleResources"
              :columns="roleResourceColumns"
              row-key="resource_type"
              :no-data-label="$t('admin.roles.no_scoped_entries')"
            >
              <template v-slot:body-cell-actions="props">
                <q-td align="right">
                  <q-btn dense flat :label="$t('common.edit')" @click="editResource(props.row)" />
                  <q-btn dense flat color="negative" :label="$t('common.delete')" @click="deleteResource(props.row)" />
                </q-td>
              </template>
            </q-table>
          </div>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn flat :label="$t('common.cancel')" v-close-popup @click="closePermissions" />
          <q-btn color="primary" :label="$t('common.save')" @click="savePermissions" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useQuasar } from 'quasar'
import axios from 'axios'
import { useAuth } from 'src/services/auth'
import { useI18n } from 'vue-i18n'

const auth = useAuth()

// reactively reload activities/schedules when selected organization changes
watch(
  () => auth.selectedOrganization,
  async () => {
    try {
      // Clear selectors and scoped state to avoid leaking data between orgs
      selectedActivityIds.value = []
      selectedScheduleIds.value = []
      activities.value = []
      schedules.value = []
      resourceType.value = ''
      resourceId.value = ''
      selectedPermissionIds.value = []
      roleResources.value = []

      await loadActivities()
      await loadSchedules()
    } catch (e) {
      // ignore
    }
  }
)
const $q = useQuasar()
const { t } = useI18n()

const roles = ref([])
const newName = ref('')
const newIsGlobal = ref(false)

const search = ref('')
const columns = [
  { name: 'name', label: t('admin.roles.col_name'), field: 'name', align: 'left' },
  { name: 'is_global', label: t('admin.roles.col_global'), field: 'is_global', align: 'center' },
  { name: 'actions', label: '', field: 'actions', sortable: false }
]
const pagination = ref({ page: 1, rowsPerPage: 10 })

const editingId = ref(null)
const editName = ref('')
const editIsGlobal = ref(false)

const filteredRoles = computed(() => {
  if (!search.value) return roles.value
  const q = search.value.toLowerCase()
  return roles.value.filter(r => (r.name || '').toLowerCase().includes(q))
})

const permsDialog = ref(false)
const allPermissions = ref([])
const selectedPermissionIds = ref([])
const currentRole = ref(null)
const scoped = ref(false)
const resourceType = ref('')
const resourceId = ref('')
const resourceTypeOptions = [
  { value: 'activity', label: t('resources.activity') },
  { value: 'schedule', label: t('resources.schedule') },
]
const activities = ref([])
const activityOptions = computed(() => activities.value.map(p => ({ value: p.id, label: p.name })))
const selectedActivityIds = ref([])
const schedules = ref([])
const scheduleOptions = computed(() => schedules.value.map(s => ({ value: s.id, label: s.name || s.id })))
const selectedScheduleIds = ref([])
const roleResources = ref([])
const resourceTypeStr = computed(() => {
  const v = resourceType.value
  if (!v) return ''
  if (typeof v === 'object') return v.value || v.label || ''
  return v
})
const roleResourceColumns = [
  { name: 'resource_type', label: t('admin.roles.col_resource'), field: 'resource_type', align: 'left' },
  { name: 'resource_id', label: t('admin.roles.col_resource_id'), field: 'resource_id', align: 'left' },
  { name: 'permission_count', label: t('admin.roles.col_permissions'), field: row => (row.permission_ids || []).length, align: 'center' },
  { name: 'actions', label: '', field: 'actions', sortable: false }
]

async function openPermissions(row) {
  currentRole.value = row
  try {
    const [allRes, assignedRes] = await Promise.all([
      axios.get('/api/rbac/permissions'),
      axios.get(`/api/rbac/roles/${row.id}/permissions`),
    ])
    allPermissions.value = allRes.data
    selectedPermissionIds.value = assignedRes.data.permission_ids || []
    // load existing scoped resources for this role
    try {
      const rr = await axios.get(`/api/rbac/roles/${row.id}/permission-resources`)
      roleResources.value = rr.data || []
    } catch (e) {
      roleResources.value = []
    }
    // preload activities and schedules for multi-select when opening dialog
    await Promise.all([loadActivities(), loadSchedules()])
    // debug: log resourceType values so we can diagnose missing presets
    console.log('openPermissions: resourceType=', resourceType.value, 'resourceTypeStr=', resourceTypeStr.value, 'activities=', activities.value, 'schedules=', schedules.value)
    permsDialog.value = true
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_load_permissions') })
  }
}

function closePermissions() {
  permsDialog.value = false
  currentRole.value = null
  selectedPermissionIds.value = []
}

async function savePermissions() {
  if (!currentRole.value) return
  try {
    const params = {}
    if (scoped.value && resourceTypeStr.value) {
      params.resource_type = resourceTypeStr.value
      if (resourceId.value) params.resource_id = resourceId.value
    }
    await axios.put(`/api/rbac/roles/${currentRole.value.id}/permissions`, { permission_ids: selectedPermissionIds.value }, { params })
    $q.notify({ type: 'positive', message: t('admin.roles.permissions_updated') })
    closePermissions()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_save_permissions') })
  }
}

async function loadScopedPermissions() {
  if (!currentRole.value) return
  if (!resourceTypeStr.value) {
    $q.notify({ type: 'warning', message: t('admin.roles.set_resource_type_first') })
    return
  }
  try {
    const params = { resource_type: resourceTypeStr.value }
    if (resourceId.value) params.resource_id = resourceId.value
    const res = await axios.get(`/api/rbac/roles/${currentRole.value.id}/permissions`, { params })
    selectedPermissionIds.value = res.data.permission_ids || []
    // ensure allPermissions are loaded
    const allRes = await axios.get('/api/rbac/permissions')
    allPermissions.value = allRes.data
    $q.notify({ type: 'info', message: t('admin.roles.scoped_permissions_loaded') })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_load_scoped_permissions') })
  }
}

async function loadActivities() {
  try {
    const auth = useAuth()
    const params = {}
    if (auth.selectedOrganization != null) params.organization_id = auth.selectedOrganization
    const res = await axios.get('/api/activities', { params })
    // API returns JSON: { data: [ { id, type, attributes: { name } } ] }
    const list = (res.data && res.data.data) || []
    activities.value = list.map(p => ({ id: p.id, name: p.attributes?.name || '' }))
  } catch (err) {
    activities.value = []
  }
}

async function loadSchedules() {
  try {
    const auth = useAuth()
    const params = {}
    if (auth.selectedOrganization != null) params.organization_id = auth.selectedOrganization
    const res = await axios.get('/api/schedules', { params })
    // handle both JSONAPI-like { data: [...] } and plain arrays
    const list = (res.data && (res.data.data || res.data)) || []
    schedules.value = list.map(s => ({ id: s.id || s.pk || s.identifier, name: s.attributes?.name || s.name || (`Schedule ${s.id || s.pk || ''}`) }))
  } catch (err) {
    schedules.value = []
  }
}

async function applyPresetToSelectedActivities(preset) {
  if (!currentRole.value) return
  if (!selectedActivityIds.value || !selectedActivityIds.value.length) {
    $q.notify({ type: 'warning', message: t('admin.roles.select_at_least_one_activity') })
    return
  }
    await applyResourcePreset(preset)
  try {
    await axios.post(`/api/rbac/roles/${currentRole.value.id}/apply-program-preset`, { preset, resource_ids: selectedActivityIds.value, resource_type: 'activity' })
    $q.notify({ type: 'positive', message: t('admin.roles.applied_preset_to_selected_activities') })
    const rr = await axios.get(`/api/rbac/roles/${currentRole.value.id}/permission-resources`)
    roleResources.value = rr.data || []
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_apply_preset_selected_activities') })
  }
}

async function applyPresetToSelectedSchedules(preset) {
  if (!currentRole.value) return
  if (!selectedScheduleIds.value || !selectedScheduleIds.value.length) {
    $q.notify({ type: 'warning', message: t('admin.roles.select_at_least_one_schedule') })
    return
  }
  await applyResourcePreset(preset)
  try {
    await axios.post(`/api/rbac/roles/${currentRole.value.id}/apply-program-preset`, { preset, resource_ids: selectedScheduleIds.value, resource_type: 'schedule' })
    $q.notify({ type: 'positive', message: t('admin.roles.applied_preset_to_selected_schedules') })
    const rr = await axios.get(`/api/rbac/roles/${currentRole.value.id}/permission-resources`)
    roleResources.value = rr.data || []
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_apply_preset_selected_schedules') })
  }
}

async function editResource(row) {
  scoped.value = true
  resourceType.value = row.resource_type
  resourceId.value = row.resource_id || ''
  // load permissions for this scope
  await loadScopedPermissions()
}

async function deleteResource(row) {
  try {
    const params = { resource_type: row.resource_type }
    if (row.resource_id) params.resource_id = row.resource_id
    await axios.delete(`/api/rbac/roles/${currentRole.value.id}/permission-resources`, { params })
    $q.notify({ type: 'positive', message: t('admin.roles.scoped_permissions_removed') })
    // refresh list
    const rr = await axios.get(`/api/rbac/roles/${currentRole.value.id}/permission-resources`)
    roleResources.value = rr.data || []
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_delete_scoped_permissions') })
  }
}

function findPermissionIdsByCodenames(codenames) {
  const ids = []
  for (const code of codenames) {
    const p = allPermissions.value.find(x => x.codename === code)
    if (p) ids.push(p.id)
  }
  return ids
}

async function applyResourcePreset(preset) {
  // presets: none, read, readwrite, admin — operate based on selected resourceTypeStr
  const prefix = resourceTypeStr.value || 'activity'
  if (!allPermissions.value.length) {
    const allRes = await axios.get('/api/rbac/permissions')
    allPermissions.value = allRes.data
  }
  if (preset === 'none') {
    selectedPermissionIds.value = []
    return
  }
  if (preset === 'read') {
    selectedPermissionIds.value = findPermissionIdsByCodenames([`${prefix}.read`])
    return
  }
  if (preset === 'readwrite') {
    selectedPermissionIds.value = findPermissionIdsByCodenames([`${prefix}.read`,`${prefix}.write`])
    return
  }
  if (preset === 'admin') {
    // take any permission that starts with the resource prefix
    selectedPermissionIds.value = allPermissions.value.filter(p => p.codename && p.codename.startsWith(`${prefix}.`)).map(p => p.id)
    return
  }
}

async function applyPresetAsDefault(preset) {
  if (!currentRole.value) return
  await applyResourcePreset(preset)
  try {
    const params = { resource_type: resourceTypeStr.value || 'activity' }
    await axios.put(`/api/rbac/roles/${currentRole.value.id}/permissions`, { permission_ids: selectedPermissionIds.value }, { params })
    $q.notify({ type: 'positive', message: t('admin.roles.default_permissions_set', { resource: params.resource_type }) })
    // refresh list
    const rr = await axios.get(`/api/rbac/roles/${currentRole.value.id}/permission-resources`)
    roleResources.value = rr.data || []
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_set_default_permissions') })
  }
}

async function applyPresetToAllResources(preset) {
  if (!currentRole.value) return
  const rType = resourceTypeStr.value || 'activity'
  // show confirmation dialog; some environments may not have $q.dialog available
  let ok = false
  if ($q && typeof $q.dialog === 'function') {
    try {
      ok = await new Promise((resolve) => {
        const d = $q.dialog({ title: t('admin.roles.apply_to_all_title', { resource: rType }), message: t('admin.roles.apply_to_all_message', { resource: rType }), cancel: true })
        d.onOk(() => resolve(true))
        d.onCancel(() => resolve(false))
        d.onDismiss(() => resolve(false))
      })
    } catch (e) {
      ok = false
    }
  } else {
    ok = window.confirm(t('admin.roles.apply_to_all_confirm', { resource: rType }))
  }
  if (!ok) return

  try {
    // call backend batch endpoint which creates missing <resource>.* permissions and applies to all resources
    await axios.post(`/api/rbac/roles/${currentRole.value.id}/apply-program-preset`, { preset, apply_to_existing: true, resource_type: rType })
    $q.notify({ type: 'positive', message: t('admin.roles.applied_preset_to_all', { resource: rType }) })
    const rr = await axios.get(`/api/rbac/roles/${currentRole.value.id}/permission-resources`)
    roleResources.value = rr.data || []
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_apply_preset_to_all', { resource: rType }) })
  }
}

async function load() {
  try {
    const res = await axios.get('/api/rbac/roles')
    roles.value = res.data
  } catch (err) {
    $q.notify({ type: 'negative', message: t('admin.roles.failed_load_roles') })
  }
}

async function createRole() {
  if (!newName.value || !newName.value.trim()) {
    $q.notify({ type: 'warning', message: t('admin.roles.role_name_empty') })
    return
  }
  try {
    await axios.post('/api/rbac/roles', { name: newName.value.trim(), is_global: newIsGlobal.value })
    newName.value = ''
    newIsGlobal.value = false
    await load()
    $q.notify({ type: 'positive', message: t('admin.roles.role_created') })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_create_role') })
  }
}

function onSearch() {
  pagination.value.page = 1
}

function startEdit(row) {
  editingId.value = row.id
  editName.value = row.name
  editIsGlobal.value = !!row.is_global
}

function cancelEdit() {
  editingId.value = null
  editName.value = ''
  editIsGlobal.value = false
}

async function saveEdit(row) {
  if (!editName.value || !editName.value.trim()) {
    $q.notify({ type: 'warning', message: t('admin.roles.name_cannot_be_empty') })
    return
  }
  try {
    await axios.patch(`/api/rbac/roles/${row.id}`, { name: editName.value.trim(), is_global: editIsGlobal.value })
    await load()
    $q.notify({ type: 'positive', message: t('admin.roles.role_updated') })
    cancelEdit()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_update_role') })
  }
}

async function deleteRole(id) {
  try {
    await axios.delete(`/api/rbac/roles/${id}`)
    await load()
    $q.notify({ type: 'positive', message: t('admin.roles.role_deleted') })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || t('admin.roles.failed_delete_role') })
  }
}

onMounted(load)
</script>

<style scoped>
</style>
