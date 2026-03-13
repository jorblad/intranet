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
                  <q-chip :style="{ backgroundColor: getPlacementColor(m.placement), color: '#fff' }" class="text-caption q-ma-none q-pa-xs q-ml-sm">
                    <span style="display:inline-block; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; max-width:120px;">{{ getPlacementLabel(m.placement) }}</span>
                    <q-tooltip anchor="bottom middle">{{ getPlacementLabel(m.placement) }}</q-tooltip>
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

    <AdminMessageDialog v-model="dialogShow" :initial="dialogInitial" defaultPlacement="banner" @created="handleCreated" @updated="handleUpdated" />

    <!-- Editing / creation handled by shared AdminMessageDialog component -->

  </div>
</template>

<script>
import { defineComponent, ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { useAuth, fetchOrganizations } from 'src/services/auth'
import { fetchAdminMessages, deleteAdminMessage } from 'src/services/adminMessages'
import orbitSchedules from 'src/services/orbitSchedules.js'
import AdminMessageDialog from 'src/components/AdminMessageDialog.vue'

export default defineComponent({
  name: 'AdminMessages',
  components: { AdminMessageDialog },
  setup () {
    const auth = useAuth()
    fetchOrganizations()


    const messages = ref([])
    const dialogShow = ref(false)
    const dialogInitial = ref(null)

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
      dialogInitial.value = { title: '', body: '', start: null, end: null, priority: 0, organization_id: determineDefaultOrg(), id: null, icon: null, placement: 'banner' }
      dialogShow.value = true
    }

    // If the org options arrive after the dialog was opened, ensure we set a sensible default
    watch([() => dialogShow.value, orgOptions], ([show]) => {
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

    const { t: i18nT, locale } = useI18n()

    const placementOptions = [
      { label: i18nT('adminMessages.placement_frontpage') || 'Front page', value: 'frontpage' },
      { label: i18nT('adminMessages.placement_banner') || 'Banner', value: 'banner' }
    ]

    const getPlacementLabel = (p) => {
      try {
        const found = placementOptions.find(x => x.value === p)
        if (found) return found.label
        return String(p || '')
      } catch (e) { return String(p || '') }
    }

    const getPlacementColor = (p) => {
      try {
        if (!p) return '#6b6b6b'
        if (p === 'frontpage') return '#1976d2'
        if (p === 'banner') return '#6b6b6b'
        return '#6b6b6b'
      } catch (e) { return '#6b6b6b' }
    }

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

    function handleCreated(created) {
      try {
        if (matchesOrg(created.organization_id)) {
          const idx = messages.value.findIndex(x => String(x.id) === String(created.id))
          if (idx === -1) messages.value.push(created)
          else messages.value.splice(idx, 1, created)
          sortMessages(messages.value)
        }
      } catch (e) {}
    }

    const edit = (m) => {
      // find the matching option object for the message's organization_id so the select shows label
      const opts = orgOptions.value || []
      const orgVal = (m && (m.organization_id === null || m.organization_id === undefined)) ? null : (m && m.organization_id != null ? String(m.organization_id) : null)
      const opt = orgVal == null ? (opts.find(o => o.value === null) || null) : (opts.find(o => String(o.value) === String(orgVal)) || null)
      dialogInitial.value = { ...m, organization_id: opt, icon: (m && m.icon) ? m.icon : null, placement: (m && m.placement) ? m.placement : 'banner' }
      dialogShow.value = true
    }

    function handleUpdated(updated) {
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

    return { messages, showCreate, editing, form, orgOptions, iconOptions, placementOptions, edit, remove, displayRange, openCreate, canChooseGlobal, formOrgValue, isFaIcon, isDark, getOrgLabel, getOrgColor, getOrgInitial, getPlacementLabel, getPlacementColor, dialogShow, dialogInitial, handleCreated, handleUpdated }
  }
})
</script>

<style scoped></style>
