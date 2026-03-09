<template>
  <div class="q-pa-md">
    <div class="row items-center q-col-gutter-sm">
        <div class="col">
          <h5>{{$t('adminMessages.title')}}</h5>
        </div>
        <div class="col-auto">
          <q-btn color="primary" :label="$t('adminMessages.newMessage')" @click="openCreate" />
        </div>
      </div>

    <q-separator class="q-my-sm" />

    <div v-if="messages.length === 0" class="q-pa-sm">{{$t('adminMessages.noActiveMessages')}}</div>
    <div v-else>
      <q-list bordered>
        <q-item v-for="m in messages" :key="m.id" clickable>
          <q-item-section avatar>
              <q-avatar size="40px">
                <template v-if="isFaIcon(m.icon)">
                  <i :class="[m.icon, isDark ? 'text-white' : 'text-black']" />
                </template>
                <template v-else>
                  <q-icon :name="m.icon || 'campaign'" :class="isDark ? 'text-white' : 'text-black'" />
                </template>
              </q-avatar>
            </q-item-section>
          <q-item-section>
            <q-item-label>{{ m.title }}</q-item-label>
            <q-item-label caption>
              <div class="row items-center q-gutter-sm" style="align-items: center;">
                <q-chip :style="{ backgroundColor: getOrgColor(m.organization_id), color: '#fff', maxWidth: '260px' }" class="text-caption q-ma-none q-pa-xs q-mt-xs">
                  <span style="display:inline-block; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; max-width:220px;">{{ getOrgLabel(m.organization_id) }}</span>
                  <q-tooltip anchor="bottom middle">{{ getOrgLabel(m.organization_id) }}</q-tooltip>
                </q-chip>
              </div>
              <div class="text-caption">{{ displayRange(m) }}</div>
            </q-item-label>
            <div style="white-space: pre-wrap; margin-top: 8px">{{ m.body }}</div>
          </q-item-section>
          <q-item-section side class="row items-center q-gutter-sm">
            <q-btn dense flat icon="edit" @click="edit(m)" :title="$t('common.edit')" />
            <q-btn dense flat icon="delete" color="negative" @click="remove(m)" :title="$t('common.delete')" />
          </q-item-section>
        </q-item>
      </q-list>
    </div>

    <q-dialog v-model="showCreate">
      <q-card style="min-width: 500px">
        <q-card-section>
          <div class="text-h6">{{$t('adminMessages.newAdminMessage')}}</div>
        </q-card-section>
        <q-card-section>
          <q-input v-model="form.title" :rules="[v => !!v || $t('adminMessages.title_required')]" :label="$t('adminMessages.title_label')" />
          <q-input v-model="form.body" type="textarea" :label="$t('adminMessages.body_label')" class="q-mt-sm" />
          <DateTimePicker v-model="form.start" :label="$t('adminMessages.start_optional')" class="q-mt-sm" />
          <div class="text-caption q-mt-xs">{{$t('adminMessages.leave_empty_hint')}}</div>
          <DateTimePicker v-model="form.end" :label="$t('adminMessages.end_optional')" class="q-mt-sm" />
          <div class="text-caption q-mt-xs">{{$t('adminMessages.leave_empty_hint')}}</div>
          <q-input v-model.number="form.priority" :label="$t('adminMessages.priority_label')" type="number" class="q-mt-sm" />
          <q-icon-picker v-model="form.icon" class="q-mt-sm" />
          <div class="q-mt-sm">
            <q-select v-model="form.organization_id" :options="orgOptions" option-label="label" option-value="value" :label="$t('adminMessages.organization_label')" />
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat :label="$t('common.cancel')" v-close-popup @click="showCreate=false" />
          <q-btn color="primary" :label="$t('common.create')" @click="create" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="editing">
      <q-card style="min-width: 500px">
        <q-card-section>
          <div class="text-h6">{{$t('adminMessages.editMessage')}}</div>
        </q-card-section>
        <q-card-section>
          <q-input v-model="form.title" :rules="[v => !!v || $t('adminMessages.title_required')]" :label="$t('adminMessages.title_label')" />
          <q-input v-model="form.body" type="textarea" :label="$t('adminMessages.body_label')" class="q-mt-sm" />
          <DateTimePicker v-model="form.start" :label="$t('adminMessages.start_optional')" class="q-mt-sm" />
          <div class="text-caption q-mt-xs">{{$t('adminMessages.leave_empty_hint')}}</div>
          <DateTimePicker v-model="form.end" :label="$t('adminMessages.end_optional')" class="q-mt-sm" />
          <div class="text-caption q-mt-xs">{{$t('adminMessages.leave_empty_hint')}}</div>
          <q-input v-model.number="form.priority" :label="$t('adminMessages.priority_label')" type="number" class="q-mt-sm" />
          <q-icon-picker v-model="form.icon" class="q-mt-sm" />
          <div class="q-mt-sm">
            <template v-if="formOrgValue === null && !canChooseGlobal">
              <q-input :model-value="$t('nav.global') || 'Global'" :label="$t('adminMessages.organization_label')" readonly dense />
            </template>
            <template v-else>
              <q-select v-model="form.organization_id" :options="orgOptions" option-label="label" option-value="value" :label="$t('adminMessages.organization_label')" />
            </template>
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat :label="$t('common.cancel')" v-close-popup @click="editing=false" />
          <q-btn color="primary" :label="$t('common.save')" @click="save" />
        </q-card-actions>
      </q-card>
    </q-dialog>

  </div>
</template>

<script>
import { defineComponent, ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { useAuth, fetchOrganizations } from 'src/services/auth'
import { fetchAdminMessages, createAdminMessage, updateAdminMessage, deleteAdminMessage } from 'src/services/adminMessages'
import orbitSchedules from 'src/services/orbitSchedules.js'
import DateTimePicker from 'src/components/DateTimePicker.vue'
// Use a local QIconPicker component as a lightweight fallback.
import QIconPicker from 'src/components/QIconPicker.vue'

export default defineComponent({
  name: 'AdminMessages',
  components: { DateTimePicker, QIconPicker },
  setup () {
    const auth = useAuth()
    fetchOrganizations()


    const messages = ref([])
    const showCreate = ref(false)
    const editing = ref(false)
    const form = ref({ title: '', body: '', start: null, end: null, priority: 0, organization_id: null, id: null, icon: null })
    const editingOriginalOrg = ref(null)

    const canChooseGlobal = computed(() => {
      try {
        const u = auth.user
        if (!u) return false
        // superadmin flag returned by /api/user/me
        if (u.attributes?.is_superadmin) return true
        const assigns = u.attributes?.assignments || []
        return assigns.some(a => a && a.role && a.role.name === 'org_admin' && a.role.is_global)
      } catch (e) { return false }
    })

    const orgOptions = computed(() => {
      const items = (auth.organizations || []).map(o => ({ label: o.name, value: String(o.id) }))
      if (canChooseGlobal.value) return [{ label: 'Global', value: null }].concat(items)
      return items
    })

    const iconOptions = [
      { label: 'Announcement', value: 'campaign' },
      { label: 'Info', value: 'info' },
      { label: 'Warning', value: 'warning' },
      { label: 'Alert', value: 'report_problem' },
      { label: 'Success', value: 'check_circle' },
    ]

    const $q = useQuasar()
    const isDark = computed(() => $q.dark.isActive)

    const load = async () => {
      try {
        const orgId = auth.selectedOrganization == null ? null : String(auth.selectedOrganization)
        const items = await fetchAdminMessages(orgId)
        messages.value = items || []
      } catch (e) {
        messages.value = []
      }
    }

    const determineDefaultOrg = () => {
      try {
        const opts = orgOptions.value || []
        if (!opts || opts.length === 0) return null
        // if there's only one option, preselect the option object
        if (opts.length === 1) return opts[0]
        // otherwise prefer the currently selected organization in the app
        const sel = auth.selectedOrganization == null ? null : String(auth.selectedOrganization)
        if (sel != null) {
          const found = opts.find(o => String(o.value) === String(sel))
          if (found) return found
        }
        return null
      } catch (e) { return null }
    }

    const openCreate = () => {
      form.value = { title: '', body: '', start: null, end: null, priority: 0, organization_id: determineDefaultOrg(), id: null, icon: null }
      showCreate.value = true
    }

    // If the org options arrive after the dialog was opened, ensure we set a sensible default
    watch([() => showCreate.value, orgOptions], ([show]) => {
      try {
        if (!show) return
        if (form.value && (form.value.organization_id === null || form.value.organization_id === undefined)) {
          form.value.organization_id = determineDefaultOrg()
        }
      } catch (e) {}
    })

    const formOrgValue = computed(() => {
      try {
        const v = form.value.organization_id
        if (v == null) return null
        if (typeof v === 'object' && 'value' in v) return v.value
        return v
      } catch (e) { return null }
    })

    onMounted(load)
    // realtime updates: listen for admin_message events on shared websocket
    let ws = null
    let attached = false
    let poll = null

    const sortMessages = (arr) => {
      try {
        arr.sort((a, b) => {
          const pa = a.priority || 0
          const pb = b.priority || 0
          if (pa !== pb) return pb - pa
          const sa = a.start || ''
          const sb = b.start || ''
          if (sa < sb) return -1
          if (sa > sb) return 1
          return 0
        })
      } catch (e) {}
    }

    const getSelectedOrg = () => (auth.selectedOrganization == null ? null : String(auth.selectedOrganization))
    const matchesOrg = (msgOrg) => {
      const sel = getSelectedOrg()
      if (sel === null) {
        return msgOrg === null || msgOrg === undefined
      }
      if (msgOrg === null || msgOrg === undefined) return true
      try { return String(msgOrg) === String(sel) } catch (e) { return false }
    }

    const onWsMessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (!msg || msg.type !== 'admin_message') return
        const action = msg.action
        const m = msg.message || {}
        if (action === 'delete') {
          try { messages.value = messages.value.filter(x => String(x.id) !== String(m.id)) } catch (e) {}
          return
        }
        if (action === 'create' || action === 'update') {
          try {
            if (!matchesOrg(m.organization_id)) {
              messages.value = messages.value.filter(x => String(x.id) !== String(m.id))
              return
            }
            const incoming = Object.assign({}, m)
            const idx = messages.value.findIndex(x => String(x.id) === String(incoming.id))
            if (idx === -1) messages.value.push(incoming)
            else messages.value.splice(idx, 1, incoming)
            sortMessages(messages.value)
          } catch (e) {}
        }
      } catch (e) {}
    }

    const tryAttach = () => {
      try {
        ws = orbitSchedules && orbitSchedules.ws
        if (ws && typeof ws.addEventListener === 'function' && !attached) {
          ws.addEventListener('message', onWsMessage)
          attached = true
          if (poll) { clearInterval(poll); poll = null }
        }
      } catch (e) {}
    }

    tryAttach()
    if (!attached) poll = setInterval(tryAttach, 500)
    onBeforeUnmount(() => {
      try { if (attached && ws && typeof ws.removeEventListener === 'function') ws.removeEventListener('message', onWsMessage) } catch (e) {}
      try { if (poll) clearInterval(poll) } catch (e) {}
    })

    const { t, locale } = useI18n()

    const formatDate = (iso) => {
      if (!iso) return ''
      try {
        const d = new Date(iso)
        if (isNaN(d.getTime())) return String(iso)
        return new Intl.DateTimeFormat(locale.value || (typeof navigator !== 'undefined' && navigator.language) || 'en-US', { dateStyle: 'short', timeStyle: 'short' }).format(d)
      } catch (e) { return String(iso) }
    }

    const displayRange = (m) => {
      if (!m.start && !m.end) return t('adminMessages.range.always')
      if (m.start && m.end) return `${formatDate(m.start)} → ${formatDate(m.end)}`
      return m.start ? t('adminMessages.range.from', { date: formatDate(m.start) }) : t('adminMessages.range.until', { date: formatDate(m.end) })
    }

    const getOrgLabel = (orgId) => {
      try {
        if (orgId === null || orgId === undefined) return t('nav.global') || 'Global'
        const orgs = auth.organizations || []
        const found = orgs.find(o => String(o.id) === String(orgId))
        if (found) return found.name || found.label || String(orgId)
        if (typeof orgId === 'object') return orgId.name || orgId.label || String(orgId)
        return String(orgId)
      } catch (e) { return '' }
    }

    const stringToColor = (s) => {
      try {
        const str = String(s || '')
        let hash = 0
        for (let i = 0; i < str.length; i++) {
          hash = str.charCodeAt(i) + ((hash << 5) - hash)
          hash = hash & hash
        }
        const h = Math.abs(hash) % 360
        return `hsl(${h}, 70%, 45%)`
      } catch (e) { return 'grey' }
    }

    const getOrgColor = (orgId) => {
      try {
        if (orgId === null || orgId === undefined) return '#6b6b6b'
        const orgs = auth.organizations || []
        const found = orgs.find(o => String(o.id) === String(orgId))
        if (found && found.color) return found.color
        const name = found ? (found.name || found.label) : (typeof orgId === 'object' ? (orgId.name || orgId.label) : String(orgId))
        return stringToColor(name)
      } catch (e) { return '#6b6b6b' }
    }

    const getOrgInitial = (orgId) => {
      try {
        const orgs = auth.organizations || []
        const found = orgs.find(o => String(o.id) === String(orgId))
        const name = found ? (found.name || found.label) : (typeof orgId === 'object' ? (orgId.name || orgId.label) : (orgId || ''))
        if (!name) return ''
        return String(name).trim().charAt(0).toUpperCase()
      } catch (e) { return '' }
    }

    const create = async () => {
      try {
        // validation
        if (!form.value.title || String(form.value.title).trim() === '') {
          $q.notify({ type: 'negative', message: 'Title is required' })
          return
        }

        // sanitize payload: remove empty strings so backend optional datetimes won't 422
        const payload = { title: String(form.value.title).trim() }
        if (form.value.body && String(form.value.body).trim() !== '') payload.body = form.value.body
        if (form.value.start && String(form.value.start).trim() !== '') payload.start = String(form.value.start).trim()
        if (form.value.end && String(form.value.end).trim() !== '') payload.end = String(form.value.end).trim()
        if (form.value.priority !== null && form.value.priority !== undefined && form.value.priority !== '') payload.priority = Number(form.value.priority) || 0
        // normalize organization id (allow null) and support option objects
        const _org = form.value.organization_id
        if (_org === null || _org === 'null') {
          payload.organization_id = null
        } else if (typeof _org === 'object') {
          if (_org && ('value' in _org)) {
            payload.organization_id = (_org.value === null || _org.value === undefined) ? null : String(_org.value)
          } else if (_org && ('id' in _org)) {
            payload.organization_id = (_org.id === null || _org.id === undefined) ? null : String(_org.id)
          } else {
            payload.organization_id = (_org === null || _org === undefined) ? null : String(_org)
          }
        } else if (_org != null) {
          payload.organization_id = String(_org)
        }
        // include selected icon (optional)
        if (form.value.icon && String(form.value.icon).trim() !== '') payload.icon = String(form.value.icon).trim()

        // Prevent non-global admins from creating global messages
        if (!canChooseGlobal.value && (payload.organization_id === null || payload.organization_id === undefined)) {
          $q.notify({ type: 'negative', message: 'Please select an organization' })
          return
        }

        const created = await createAdminMessage(payload)
        // reset form and close
        form.value = { title: '', body: '', start: null, end: null, priority: 0, organization_id: null, id: null, icon: null }
        showCreate.value = false
        $q.notify({ type: 'positive', message: 'Message created' })
        try {
          // update UI in-place if the created message applies to current selection
          if (matchesOrg(created.organization_id)) {
            const idx = messages.value.findIndex(x => String(x.id) === String(created.id))
            if (idx === -1) messages.value.push(created)
            else messages.value.splice(idx, 1, created)
            sortMessages(messages.value)
          }
        } catch (e) {}
        // broadcast to other components/tabs so banners update without reload
        try {
          const evt = { type: 'admin_message', action: 'create', message: created }
          try { window.dispatchEvent(new CustomEvent('admin:message', { detail: evt })) } catch (e) {}
          try { if (typeof localStorage !== 'undefined') localStorage.setItem('admin:message', JSON.stringify({ ts: Date.now(), payload: evt })) } catch (e) {}
        } catch (e) {}
      } catch (e) {
        console.error(e)
        // present clear validation errors from backend
        const msg = e?.response?.data?.detail || (e?.message || 'Failed to create message')
        if (Array.isArray(msg)) {
          $q.notify({ type: 'negative', message: msg.map(m => m.msg || JSON.stringify(m)).join('; ') })
        } else if (typeof msg === 'string') {
          $q.notify({ type: 'negative', message: msg })
        } else {
          $q.notify({ type: 'negative', message: 'Failed to create message' })
        }
      }
    }

    const edit = (m) => {
      // find the matching option object for the message's organization_id so the select shows label
      const opts = orgOptions.value || []
      const orgVal = (m && (m.organization_id === null || m.organization_id === undefined)) ? null : (m && m.organization_id != null ? String(m.organization_id) : null)
      const opt = orgVal == null ? (opts.find(o => o.value === null) || null) : (opts.find(o => String(o.value) === String(orgVal)) || null)
      form.value = { ...m, organization_id: opt, icon: (m && m.icon) ? m.icon : null }
      editingOriginalOrg.value = orgVal
      editing.value = true
    }

    const save = async () => {
      try {
        if (!form.value.title || String(form.value.title).trim() === '') {
          $q.notify({ type: 'negative', message: 'Title is required' })
          return
        }
        const id = form.value.id
        const payload = { title: String(form.value.title).trim() }
        if (form.value.body && String(form.value.body).trim() !== '') payload.body = form.value.body
        if (form.value.start && String(form.value.start).trim() !== '') payload.start = String(form.value.start).trim()
        if (form.value.end && String(form.value.end).trim() !== '') payload.end = String(form.value.end).trim()
        if (form.value.priority !== null && form.value.priority !== undefined && form.value.priority !== '') payload.priority = Number(form.value.priority) || 0
        const _org2 = form.value.organization_id
        if (_org2 === null || _org2 === 'null') {
          payload.organization_id = null
        } else if (typeof _org2 === 'object') {
          if (_org2 && ('value' in _org2)) {
            payload.organization_id = (_org2.value === null || _org2.value === undefined) ? null : String(_org2.value)
          } else if (_org2 && ('id' in _org2)) {
            payload.organization_id = (_org2.id === null || _org2.id === undefined) ? null : String(_org2.id)
          } else {
            payload.organization_id = (_org2 === null || _org2 === undefined) ? null : String(_org2)
          }
        } else if (_org2 != null) {
          payload.organization_id = String(_org2)
        }
        if (form.value.icon && String(form.value.icon).trim() !== '') payload.icon = String(form.value.icon).trim()

        // Prevent non-global admins from turning a message global
        if (!canChooseGlobal.value && (payload.organization_id === null || payload.organization_id === undefined)) {
          $q.notify({ type: 'negative', message: 'Only global admins can set a message as global' })
          return
        }
        // Prevent non-global admins from editing an existing global message
        if (editingOriginalOrg.value === null && !canChooseGlobal.value) {
          $q.notify({ type: 'negative', message: 'You are not allowed to modify global messages' })
          return
        }

        const updated = await updateAdminMessage(id, payload)
        editing.value = false
        form.value = { title: '', body: '', start: null, end: null, priority: 0, organization_id: null, id: null, icon: null }
        $q.notify({ type: 'positive', message: 'Message updated' })
        try {
          const idx = messages.value.findIndex(x => String(x.id) === String(updated.id))
          if (matchesOrg(updated.organization_id)) {
            if (idx === -1) messages.value.push(updated)
            else messages.value.splice(idx, 1, updated)
          } else {
            if (idx !== -1) messages.value.splice(idx, 1)
          }
          sortMessages(messages.value)
        } catch (e) {}
        // broadcast updated message to other components/tabs
        try {
          const evt = { type: 'admin_message', action: 'update', message: updated }
          try { window.dispatchEvent(new CustomEvent('admin:message', { detail: evt })) } catch (e) {}
          try { if (typeof localStorage !== 'undefined') localStorage.setItem('admin:message', JSON.stringify({ ts: Date.now(), payload: evt })) } catch (e) {}
        } catch (e) {}
      } catch (e) {
        console.error(e)
        const msg = e?.response?.data?.detail || (e?.message || 'Failed to update message')
        if (Array.isArray(msg)) {
          $q.notify({ type: 'negative', message: msg.map(m => m.msg || JSON.stringify(m)).join('; ') })
        } else if (typeof msg === 'string') {
          $q.notify({ type: 'negative', message: msg })
        } else {
          $q.notify({ type: 'negative', message: 'Failed to update message' })
        }
      }
    }

    const remove = async (m) => {
      if (!confirm('Delete this message?')) return
      try {
        await deleteAdminMessage(m.id)
        try { messages.value = messages.value.filter(x => String(x.id) !== String(m.id)) } catch (e) {}
        // broadcast deletion to other components/tabs
        try {
          const evt = { type: 'admin_message', action: 'delete', message: { id: m.id, organization_id: m.organization_id } }
          try { window.dispatchEvent(new CustomEvent('admin:message', { detail: evt })) } catch (e) {}
          try { if (typeof localStorage !== 'undefined') localStorage.setItem('admin:message', JSON.stringify({ ts: Date.now(), payload: evt })) } catch (e) {}
        } catch (e) {}
      } catch (e) {
        console.error(e)
      }
    }

    const isFaIcon = (v) => {
      try {
        if (!v || typeof v !== 'string') return false
        return v.includes('fa-') || v.startsWith('fa ') || v.startsWith('fas ') || v.startsWith('far ') || v.startsWith('fab ') || v.startsWith('fa-')
      } catch (e) { return false }
    }

    return { messages, showCreate, editing, form, orgOptions, iconOptions, create, edit, save, remove, displayRange, openCreate, canChooseGlobal, formOrgValue, isFaIcon, isDark, getOrgLabel, getOrgColor, getOrgInitial }
  }
})
</script>

<style scoped></style>
