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
        <div v-if="m.body" style="white-space:pre-wrap">{{ m.body }}</div>
      </div>
    </q-banner>
  </div>
</template>

<script>
import { defineComponent, ref, watch, onMounted, onBeforeUnmount, computed } from 'vue'
import { useQuasar } from 'quasar'
import { fetchAdminMessages } from 'src/services/adminMessages'
import orbitSchedules from 'src/services/orbitSchedules.js'
import ensureFontAwesomeLoaded from 'src/plugins/fa-loader'

export default defineComponent({
  name: 'AdminBanners',
  props: {
    organizationId: { type: [String, null], default: null },
  },
  setup (props) {
    const messages = ref([])

    const load = async () => {
      try {
        const items = await fetchAdminMessages(props.organizationId)
        messages.value = items || []
      } catch (e) {
        messages.value = []
      }
    }

    onMounted(() => {
      ensureFontAwesomeLoaded().catch(() => {})
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
        if (action === 'delete') {
          try {
            messages.value = messages.value.filter(x => String(x.id) !== String(m.id))
          } catch (e) {}
          return
        }
        if (action === 'create' || action === 'update') {
          try {
            if (!matchesOrg(m.organization_id)) {
              // if message no longer applies to this view, remove it
              messages.value = messages.value.filter(x => String(x.id) !== String(m.id))
              return
            }
            // ensure we have canonical shape similar to loader
            const incoming = Object.assign({}, m)
            // try to find existing
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
    // try immediately and poll until orbit attaches the socket
    tryAttach()
    if (!attached) poll = setInterval(tryAttach, 500)

    // Periodic fallback refresh for environments without cross-process pubsub
    let refreshTimer = null
    const REFRESH_MS = 5000
    try {
      refreshTimer = setInterval(() => {
        try { load().catch(() => {}) } catch (e) {}
      }, REFRESH_MS)
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

    return { messages, isFaIcon, isDark }
  }
})
</script>

<style scoped>
.admin-banners {
  max-width: 100%;
}
</style>
