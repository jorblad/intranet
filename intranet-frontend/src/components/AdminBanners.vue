<template>
  <div v-if="messages.length > 0" class="admin-banners q-pa-sm">
    <q-banner v-for="m in messages" :key="m.id" class="q-mb-sm q-pa-sm">
      <template v-slot:avatar>
        <q-avatar size="40px">
          <template v-if="isFaIcon(m.icon)">
            <i :class="[m.icon, isDark ? 'text-white' : 'text-black']" />
          </template>
          <template v-else>
            <q-icon :name="m.icon || 'campaign'" :class="isDark ? 'text-white' : 'text-black'" />
          </template>
        </q-avatar>
      </template>
      <div>
        <div style="font-weight:600">{{ m.title }}</div>
        <div class="row items-center q-gutter-sm q-mt-xs">
          <q-chip :style="{ backgroundColor: getOrgColor(m.organization_id), color: '#fff', maxWidth: '260px' }" class="text-caption q-ma-none q-pa-xs">
            <span style="display:inline-block; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; max-width:220px;">{{ getOrgLabel(m.organization_id) }}</span>
            <q-tooltip anchor="bottom middle">{{ getOrgLabel(m.organization_id) }}</q-tooltip>
          </q-chip>
        </div>
        <div v-if="bannerBodies[m.id]" class="banner-body md-render" v-html="bannerBodies[m.id]"></div>
      </div>
    </q-banner>
  </div>
</template>

<script>
import { defineComponent, ref, watch, onMounted, onBeforeUnmount, computed } from 'vue'
import { useQuasar } from 'quasar'
import { useAuth, fetchOrganizations } from 'src/services/auth'
import { useI18n } from 'vue-i18n'
import { fetchAdminMessages } from 'src/services/adminMessages'
import orbitSchedules from 'src/services/orbitSchedules.js'
import ensureFontAwesomeLoaded from 'src/plugins/fa-loader'
import { renderToHtml } from 'src/utils/markdown'
import DOMPurify from 'dompurify'

export default defineComponent({
  name: 'AdminBanners',
  props: {
    organizationId: { type: [String, null], default: null },
  },
  methods: {
  },
  setup (props) {
    const messages = ref([])
    const renderedHtml = ref({})
    const bannerBodies = ref({})
    const auth = useAuth()
    const { t } = useI18n()

    const processBannerBodies = async () => {
      const bodies = {}
      for (const m of messages.value) {
        if (m && m.id != null && m.body) {
          const rawHtml = await renderToHtml(m.body)
          bodies[m.id] = DOMPurify.sanitize(rawHtml)
        }
      }
      bannerBodies.value = bodies
    }

    const load = async () => {
      try {
        const items = await fetchAdminMessages(props.organizationId, 'banner')
        messages.value = items || []
        await processBannerBodies()
        processRendered().catch(() => {})
      } catch (e) {
        messages.value = []
        bannerBodies.value = {}
      }
    }

    onMounted(() => {
      ensureFontAwesomeLoaded().catch(() => {})
      fetchOrganizations().catch(() => {})
      load()
    })
    watch(() => props.organizationId, load)
    // attach to existing orbit websocket (if available) to receive realtime admin_message events
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

    const matchesOrg = (msgOrg) => {
      const sel = props.organizationId === null ? null : (props.organizationId === undefined ? null : String(props.organizationId))
      if (sel === null) {
        // when no org selected show only global messages
        return msgOrg === null || msgOrg === undefined
      }
      // selected org -> include org-specific messages for that org and global
      if (msgOrg === null || msgOrg === undefined) return true
      try { return String(msgOrg) === String(sel) } catch (e) { return false }
    }

    const onWsMessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (!msg || msg.type !== 'admin_message') return
        const action = msg.action
        const m = msg.message || {}
        // ignore events for other placements
        if (m.placement !== undefined && m.placement !== 'banner') return
        if (action === 'delete') {
          try {
            messages.value = messages.value.filter(x => String(x.id) !== String(m.id))
            processRendered().catch(() => {})
          } catch (e) {}
          return
        }
        if (action === 'create' || action === 'update') {
          try {
            if (!matchesOrg(m.organization_id)) {
              // if message no longer applies to this view, remove it
              messages.value = messages.value.filter(x => String(x.id) !== String(m.id))
              processRendered().catch(() => {})
              return
            }
            // ensure we have canonical shape similar to loader
            const incoming = Object.assign({}, m)
            // try to find existing
            const idx = messages.value.findIndex(x => String(x.id) === String(incoming.id))
            if (idx === -1) messages.value.push(incoming)
            else messages.value.splice(idx, 1, incoming)
            sortMessages(messages.value)
            processRendered().catch(() => {})
          } catch (e) {}
        }
      } catch (e) {}
    }

    async function processRendered() {
      try {
        renderedHtml.value = {}
        for (const m of messages.value) {
          try {
            renderedHtml.value[m.id] = await renderToHtml(m.body || '')
          } catch (e) { renderedHtml.value[m.id] = '' }
        }
      } catch (e) {}
    }
    let refreshTimer = null
    const tryAttach = () => {
      try {
        ws = orbitSchedules && orbitSchedules.ws
        if (ws && typeof ws.addEventListener === 'function' && !attached) {
          ws.addEventListener('message', onWsMessage)
          attached = true
          if (poll) { clearInterval(poll); poll = null }
          if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
        }
      } catch (e) {}
    }
    // try immediately and poll until orbit attaches the socket
    tryAttach()
    if (!attached) poll = setInterval(tryAttach, 500)

    // Periodic fallback refresh for environments without cross-process pubsub
    const REFRESH_MS = 5000
    try {
      if (!attached) {
        refreshTimer = setInterval(() => {
          try { load().catch(() => {}) } catch (e) {}
        }, REFRESH_MS)
      }
    } catch (e) {}

    // listen for in-tab broadcasts (CustomEvent) and cross-tab broadcasts (storage)
    const handleLocalBroadcast = (ev) => {
      try {
        const payload = ev && ev.detail ? ev.detail : null
        if (!payload) return
        // reuse websocket handling logic
        const fake = { data: JSON.stringify(payload) }
        onWsMessage(fake)
      } catch (e) {}
    }
    const handleStorage = (ev) => {
      try {
        if (!ev || ev.key !== 'admin:message') return
        if (!ev.newValue) return
        let obj = null
        try { obj = JSON.parse(ev.newValue) } catch (e) { return }
        if (!obj || !obj.payload) return
        const payload = obj.payload
        const fake = { data: JSON.stringify(payload) }
        onWsMessage(fake)
      } catch (e) {}
    }

    try { window.addEventListener('admin:message', handleLocalBroadcast) } catch (e) {}
    try { window.addEventListener('storage', handleStorage) } catch (e) {}

    onBeforeUnmount(() => {
      try { if (attached && ws && typeof ws.removeEventListener === 'function') ws.removeEventListener('message', onWsMessage) } catch (e) {}
      try { if (poll) clearInterval(poll) } catch (e) {}
      try { if (refreshTimer) clearInterval(refreshTimer) } catch (e) {}
      try { window.removeEventListener('admin:message', handleLocalBroadcast) } catch (e) {}
      try { window.removeEventListener('storage', handleStorage) } catch (e) {}
    })

    const $q = useQuasar()
    const isDark = computed(() => $q.dark.isActive)

    const isFaIcon = (v) => {
      try {
        if (!v || typeof v !== 'string') return false
        return v.includes('fa-') || v.startsWith('fa ') || v.startsWith('fas ') || v.startsWith('far ') || v.startsWith('fab ')
      } catch (e) { return false }
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

    return { messages, isFaIcon, isDark, getOrgLabel, getOrgColor, renderedHtml }
  }
})
</script>

<style scoped>
.admin-banners {
  max-width: 100%;
}
.banner-body { font-size: 0.98rem; color: inherit; }
.banner-body p { margin: 0 0 0.4em; line-height: 1.3 }
.banner-body code { background: #f5f5f5; color: #111; padding: 0.06em 0.28em; border-radius: 3px; font-family: monospace; font-size: .95em; }
.banner-body pre { background: #f5f5f5; padding: .6em; border-radius: 4px; overflow: auto; font-family: monospace; }
.banner-body ::v-deep h1, .banner-body ::v-deep h2, .banner-body ::v-deep h3 { margin: 0.15em 0 0.35em; font-weight: 600; line-height: 1.15; color: inherit; }
.banner-body ::v-deep h1 { font-size: 1.25rem; }
.banner-body ::v-deep h2 { font-size: 1.0rem; }
.banner-body ::v-deep h3 { font-size: 0.95rem; }
</style>
