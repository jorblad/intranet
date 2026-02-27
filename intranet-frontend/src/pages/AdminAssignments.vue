<template>
  <q-page padding>
    <div class="row q-gutter-md items-center">
      <q-select v-model="form.user_id" :options="userOptions" label="User" option-label="label" option-value="value" dense style="min-width:240px; max-width:520px;" />
      <q-select v-model="form.role_id" :options="roleOptions" label="Role" option-label="label" option-value="value" dense style="min-width:240px; max-width:520px;" />
      <q-select v-model="form.organization_id" :options="orgOptions" label="Organization (optional)" option-label="label" option-value="value" dense style="min-width:240px; max-width:520px;" />
      <q-btn label="Assign" color="primary" @click="assign" />
    </div>

    <div class="q-mt-md">
      <q-input dense v-model="search" label="Search assignments" clearable @input="onSearch" />
      <q-table
        :rows="filteredAssigns"
        :columns="columns"
        :pagination="pagination"
        row-key="id"
        no-data-label="No assignments"
      >
        <template v-slot:body-cell-user="props">
          <q-td :props="props">
            {{ userLabel(props.row.user_id) }}
          </q-td>
        </template>

        <template v-slot:body-cell-role="props">
          <q-td :props="props">
            <div v-if="editingId === props.row.id">
              <q-select dense :options="roleOptions" v-model="editRoleId" option-label="label" option-value="value" />
            </div>
            <div v-else>
              {{ roleLabel(props.row.role_id) }}
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-organization="props">
          <q-td :props="props">
            <div v-if="editingId === props.row.id">
              <q-select dense :options="orgOptions" v-model="editOrgId" option-label="label" option-value="value" />
            </div>
            <div v-else>
              {{ orgLabel(props.row.organization_id) }}
            </div>
          </q-td>
        </template>

        <template v-slot:body-cell-actions="props">
          <q-td align="right">
            <q-btn dense flat icon="edit" @click="startEdit(props.row)" />
            <q-btn dense flat color="negative" icon="delete" @click="remove(props.row.id)" />
            <q-btn v-if="editingId === props.row.id" dense flat icon="check" @click="saveEdit(props.row)" />
            <q-btn v-if="editingId === props.row.id" dense flat icon="close" color="negative" @click="cancelEdit" />
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
import { fetchCurrentUser, useAuth } from 'src/services/auth'
const $q = useQuasar()
const assigns = ref([])
const users = ref([])
const roles = ref([])
const orgs = ref([])
const form = ref({ user_id: null, role_id: null, organization_id: null })
const showAll = ref(false)

const userOptions = computed(() => users.value.map(u => ({ label: u.attributes.display_name, value: String(u.id) })))
const roleOptions = computed(() => roles.value.map(r => ({ label: r.name, value: String(r.id) })))
const orgOptions = computed(() => [{ label: 'Global', value: null }, ...orgs.value.map(o => ({ label: o.name, value: String(o.id) }))])

const search = ref('')
const columns = [
  { name: 'user', label: 'User', field: 'user_id' },
  { name: 'role', label: 'Role', field: 'role_id' },
  { name: 'organization', label: 'Organization', field: 'organization_id' },
  { name: 'actions', label: '', field: 'actions', sortable: false }
]
const pagination = ref({ page: 1, rowsPerPage: 10 })

const editingId = ref(null)
const editRoleId = ref(null)
const editOrgId = ref(null)

const filteredAssigns = computed(() => {
  if (!search.value) return assigns.value
  const q = search.value.toLowerCase()
  return assigns.value.filter(a => {
    const un = userLabel(a.user_id).toLowerCase()
    const rn = roleLabel(a.role_id).toLowerCase()
    const on = orgLabel(a.organization_id).toLowerCase()
    return un.includes(q) || rn.includes(q) || on.includes(q)
  })
})

async function load() {
  try {
    // fetch current user and lists
    await fetchCurrentUser()
    const auth = useAuth()

    const [uRes, rRes, oRes] = await Promise.all([
      axios.get('/api/user/user'),
      axios.get('/api/rbac/roles'),
      axios.get('/api/rbac/organizations'),
    ])
    users.value = uRes.data.data
    roles.value = rRes.data
    orgs.value = oRes.data

    // don't preselect a user; showAll for superadmin or org_admin
    form.value.user_id = null

    const u = auth.user
    if (u && u.attributes?.is_superadmin) {
      showAll.value = true
      await loadAllAssignments()
      return
    }

    // if org_admin for any org, load assignments for those orgs
    const managedOrgs = (u?.attributes?.assignments || [])
      .filter(a => a.role && a.role.name === 'org_admin')
      .map(a => a.organization_id)
      .filter(Boolean)
    if (managedOrgs.length) {
      showAll.value = true
      // fetch per-org and merge
      let items = []
      for (const oid of managedOrgs) {
        const res = await axios.get('/api/rbac/assignments', { params: { organization_id: oid } })
        items = items.concat(res.data || [])
      }
      assigns.value = (items || []).map(a => ({
        ...a,
        user_id: a.user_id != null ? String(a.user_id) : a.user_id,
        role_id: a.role_id != null ? String(a.role_id) : a.role_id,
        organization_id: a.organization_id == null ? null : String(a.organization_id),
        user_label: userLabel(a.user_id),
        role_label: roleLabel(a.role_id),
        org_label: orgLabel(a.organization_id)
      }))
      return
    }

    // otherwise, no assignments shown until a user is selected
  } catch (err) {
    $q.notify({ type: 'negative', message: 'Failed to load assignments data' })
  }
}

async function loadAllAssignments() {
  try {
    const res = await axios.get('/api/rbac/assignments')
    assigns.value = (res.data || []).map(a => ({
      ...a,
      user_id: a.user_id != null ? String(a.user_id) : a.user_id,
      role_id: a.role_id != null ? String(a.role_id) : a.role_id,
      organization_id: a.organization_id == null ? null : String(a.organization_id),
      user_label: userLabel(a.user_id),
      role_label: roleLabel(a.role_id),
      org_label: orgLabel(a.organization_id)
    }))
  } catch (err) {
    $q.notify({ type: 'negative', message: 'Failed to load assignments' })
  }
}

async function loadAssignmentsFor(uid) {
  try {
    const aRes = await axios.get(`/api/rbac/users/${uid}/assignments`)
    // enrich with resolved labels for immediate display
    assigns.value = (aRes.data || []).map(a => ({
      ...a,
      user_id: a.user_id != null ? String(a.user_id) : a.user_id,
      role_id: a.role_id != null ? String(a.role_id) : a.role_id,
      organization_id: a.organization_id == null ? null : String(a.organization_id),
      user_label: userLabel(a.user_id),
      role_label: roleLabel(a.role_id),
      org_label: orgLabel(a.organization_id),
    }))
  } catch (err) {
    $q.notify({ type: 'negative', message: 'Failed to load assignments' })
  }
}

async function assign() {
  if (!form.value.user_id || !form.value.role_id) {
    $q.notify({ type: 'warning', message: 'User and role are required' })
    return
  }
  try {
    // ensure we send primitive ids, not option objects
    const payload = {
      user_id: typeof form.value.user_id === 'object' ? form.value.user_id.value : form.value.user_id,
      role_id: typeof form.value.role_id === 'object' ? form.value.role_id.value : form.value.role_id,
      organization_id: form.value.organization_id == null ? null : (typeof form.value.organization_id === 'object' ? form.value.organization_id.value : form.value.organization_id),
    }
    console.debug('Assign payload:', payload)
    await axios.post('/api/rbac/assignments', payload)
    if (showAll.value) {
      await loadAllAssignments()
    } else {
      await loadAssignmentsFor(form.value.user_id)
    }
    $q.notify({ type: 'positive', message: 'Assigned role' })
  } catch (err) {
    console.error('Assign error:', err.response?.data || err)
    const detail = err.response?.data?.detail
    let msg = 'Failed to assign role'
    if (Array.isArray(detail)) {
      msg = detail.map(d => {
        if (typeof d === 'string') return d
        if (d?.msg) return d.msg
        return JSON.stringify(d)
      }).join('; ')
    } else if (typeof detail === 'string') {
      msg = detail
    }
    $q.notify({ type: 'negative', message: msg })
  }
}

async function remove(id) {
  try {
    await axios.delete(`/api/rbac/assignments/${id}`)
    if (showAll.value) {
      await loadAllAssignments()
    } else if (form.value.user_id) {
      await loadAssignmentsFor(form.value.user_id)
    }
    $q.notify({ type: 'positive', message: 'Assignment removed' })
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || 'Failed to remove assignment' })
  }
}

function userLabel(uid) {
  const u = users.value.find(x => String(x.id) === String(uid))
  return u ? `${u.attributes.display_name} (${u.attributes.username})` : String(uid)
}

function roleLabel(rid) {
  const r = roles.value.find(x => String(x.id) === String(rid))
  return r ? r.name : String(rid)
}

function orgLabel(oid) {
  if (!oid) return 'global'
  const o = orgs.value.find(x => String(x.id) === String(oid))
  return o ? o.name : String(oid)
}

function onSearch() {
  pagination.value.page = 1
}

function startEdit(row) {
  editingId.value = row.id
  // coerce to string so it matches the option `value` types
  editRoleId.value = row.role_id == null ? row.role_id : String(row.role_id)
  editOrgId.value = row.organization_id == null ? null : String(row.organization_id)
}

function cancelEdit() {
  editingId.value = null
  editRoleId.value = null
  editOrgId.value = null
}

async function saveEdit(row) {
  try {
    const payload = {
      role_id: typeof editRoleId.value === 'object' ? editRoleId.value.value : editRoleId.value,
      organization_id: editOrgId.value == null ? null : (typeof editOrgId.value === 'object' ? editOrgId.value.value : editOrgId.value),
    }
    await axios.patch(`/api/rbac/assignments/${row.id}`, payload)
    if (showAll.value) {
      await loadAllAssignments()
    } else if (form.value.user_id) {
      await loadAssignmentsFor(form.value.user_id)
    }
    $q.notify({ type: 'positive', message: 'Assignment updated' })
    cancelEdit()
  } catch (err) {
    $q.notify({ type: 'negative', message: err.response?.data?.detail || 'Failed to update assignment' })
  }
}

onMounted(load)
</script>

<style scoped>
</style>
