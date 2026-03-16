<template>
  <q-card flat bordered class="admin-messages-card">
    <q-card-section class="row items-center justify-between">
      <div class="text-h6">{{ $t('adminMessages.title') }}</div>
      <div v-if="canCreate">
        <q-btn dense color="primary" :label="$t('adminMessages.newMessage')" @click="openCreate" />
      </div>
    </q-card-section>

    <q-separator />

    <q-card-section>
      <div v-if="messages.length === 0" class="text-caption">{{ $t('adminMessages.noActiveMessages') }}</div>
      <div v-else>
        <div v-for="m in messages" :key="m.id" class="admin-message q-mb-sm">
          <div class="row items-start no-wrap">
            <div class="q-mr-sm">
              <q-avatar size="40px">
                <template v-if="isFaIcon(m.icon)">
                  <i :class="[m.icon, isDark ? 'text-white' : 'text-black']" />
                </template>
                <template v-else>
                  <q-icon :name="m.icon || 'campaign'" :class="isDark ? 'text-white' : 'text-black'" />
                </template>
              </q-avatar>
            </div>

            <div class="col">
              <div style="font-weight:600">{{ m.title }}</div>

              <div class="row items-center q-gutter-sm q-mt-xs">
                <q-chip :style="{ backgroundColor: getOrgColor(m.organization_id), color: '#fff', maxWidth: '260px' }" class="text-caption q-ma-none q-pa-xs">
                  <span style="display:inline-block; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; max-width:220px;">{{ getOrgLabel(m.organization_id) }}</span>
                  <q-tooltip anchor="bottom middle">{{ getOrgLabel(m.organization_id) }}</q-tooltip>
                </q-chip>
                <div v-if="canCreate" class="q-ml-sm">
                  <q-btn dense flat icon="edit" @click.stop.prevent="openEdit(m)" :title="$t('common.edit')" />
                </div>
              </div>

                  <div class="md-preview md-render q-mt-sm"
                    :ref="el => setPreviewRef(el, m.id)"
                    :class="{ expanded: !!expanded[m.id], 'has-overlay': needsTruncate[m.id], dark: isDark }"
                    v-html="renderedHtml[m.id] || ''"></div>

              <div v-if="(needsTruncate[m.id] || expanded[m.id] || forceShowToggle[m.id])" class="text-caption q-mt-xs">
                <q-btn outline dense size="sm" class="pill-btn" @click="toggleExpand(m.id)" :label="expanded[m.id] ? ($te('common.readLess') ? $t('common.readLess') : 'Read less') : ($te('common.readMore') ? $t('common.readMore') : 'Read more')" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </q-card-section>

    <AdminMessageDialog v-model="dialogShow" :initial="dialogInitial" defaultPlacement="frontpage" @created="onDialogCreated" @updated="onDialogUpdated" />
  </q-card>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { useAuth, fetchOrganizations } from 'src/services/auth'
import { fetchAdminMessages, createAdminMessage } from 'src/services/adminMessages'
import orbitSchedules from 'src/services/orbitSchedules.js'
import DateTimePicker from 'src/components/DateTimePicker.vue'
import QIconPicker from 'src/components/QIconPicker.vue'
import AdminMessageDialog from 'src/components/AdminMessageDialog.vue'

// Lightweight fallback markdown renderer to avoid depending on external
// packages during early development / when npm deps aren't installed.
function escapeHtml(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function simpleMarkdownToHtml(md) {
  if (!md) return ''
  let s = String(md)
  // Escape input first to avoid raw HTML injection
  s = escapeHtml(s)

  // Code blocks ```lang\n...\n``` -> <pre><code>...</code></pre>
  s = s.replace(/```(?:([^\n]*?)\n)?([\s\S]*?)```/g, (_, _lang, code) => `<pre><code>${code.replace(/</g,'&lt;')}</code></pre>`)

  // Inline code `code`
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')

  // Bold **text**
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // Italic *text*
  s = s.replace(/\*(?!\*)(.+?)\*/g, '<em>$1</em>')

  // Links [text](url)
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')

  // Unordered lists: lines starting with - or *
  s = s.replace(/(^|\n)[ \t]*([-*])[ \t]+(.+)(?=\n|$)/g, (m, pre, _dash, content) => `${pre}<li>${content}</li>`)
  // Wrap adjacent <li> items into <ul>
  s = s.replace(/(?:<li>.*?<\/li>\s*)+/gs, m => `<ul>${m.replace(/\s+/g,'')}</ul>`)

  // Paragraphs: split on two or more newlines
  const parts = s.split(/\n{2,}/).map(p => `<p>${p.replace(/\n/g, '<br/>')}</p>`)
  return parts.join('')
}

const { t, locale } = useI18n()
const $q = useQuasar()
const auth = useAuth()

const messages = ref([])
const renderedHtml = ref({})
const plainLengths = ref({})
const expanded = ref({})
const previews = ref({})
const needsTruncate = ref({})
const forceShowToggle = ref({})
let collapseTimers = {}
// dialog state shared for create/edit on the frontpage card
const dialogShow = ref(false)
const dialogInitial = ref(null)

const TRUNCATE_LENGTH = 300

const isDark = computed(() => $q.dark.isActive)

const canCreate = computed(() => {
  try {
    const u = auth.user
    if (!u) return false
    if (u.attributes?.is_superadmin) return true
    const assigns = u.attributes?.assignments || []
    return assigns.some(a => a && a.role && a.role.name === 'org_admin')
  } catch (e) { return false }
})

const canChooseGlobal = computed(() => {
  try {
    const u = auth.user
    if (!u) return false
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

const isFaIcon = (v) => {
  try { if (!v || typeof v !== 'string') return false; return v.includes('fa-') || v.startsWith('fa ') || v.startsWith('fas ') || v.startsWith('far ') || v.startsWith('fab ') } catch (e) { return false }
}

const placementOptions = [
  { label: t('adminMessages.placement_frontpage') || 'Front page', value: 'frontpage' },
  { label: t('adminMessages.placement_banner') || 'Banner', value: 'banner' }
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

// Organization label/color helpers (mirrors AdminMessages page)
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

const load = async () => {
  try {
    const orgId = auth.selectedOrganization == null ? null : String(auth.selectedOrganization)
    const items = await fetchAdminMessages(orgId, 'frontpage')
    messages.value = items || []
    processRendered()
  } catch (e) {
    messages.value = []
  }
}

const determineDefaultOrg = () => {
  try {
    const opts = orgOptions.value || []
    if (!opts || opts.length === 0) return null
    // prefer currently selected organization
    const sel = auth.selectedOrganization == null ? null : String(auth.selectedOrganization)
    if (sel != null) {
      const found = opts.find(o => String(o.value) === String(sel))
      if (found) return found
    }
    // otherwise if there's only one option return it
    if (opts.length === 1) return opts[0]
    return null
  } catch (e) { return null }
}

function openCreate() {
  try {
    dialogInitial.value = { title: '', body: '', start: null, end: null, priority: 0, organization_id: determineDefaultOrg(), id: null, icon: null, placement: 'frontpage' }
    dialogShow.value = true
  } catch (e) { dialogShow.value = true }
}

function openEdit(m) {
  try {
    const opts = orgOptions.value || []
    const orgVal = (m && (m.organization_id === null || m.organization_id === undefined)) ? null : (m && m.organization_id != null ? String(m.organization_id) : null)
    const opt = orgVal == null ? (opts.find(o => o.value === null) || null) : (opts.find(o => String(o.value) === String(orgVal)) || null)
    dialogInitial.value = { ...m, organization_id: opt, icon: (m && m.icon) ? m.icon : null, placement: (m && m.placement) ? m.placement : 'frontpage' }
    dialogShow.value = true
  } catch (e) { dialogShow.value = true }
}

function textFromHtml(html) {
  try {
    const d = document.createElement('div')
    d.innerHTML = html || ''
    return d.textContent || d.innerText || ''
  } catch (e) { return String(html || '') }
}

function setPreviewRef(el, id) {
  try {
    if (el) previews.value[id] = el
    else delete previews.value[id]
  } catch (e) {}
}

async function checkOverflow() {
  try {
    await nextTick()
    messages.value.forEach(m => {
      try {
        const el = previews.value[m.id]
        if (!el) {
          // fallback to length-based check
          needsTruncate.value[m.id] = (plainLengths.value[m.id] || 0) > TRUNCATE_LENGTH
        } else {
          // consider overflow when scrollHeight exceeds clientHeight
          const overflow = el.scrollHeight > (el.clientHeight + 1)
          needsTruncate.value[m.id] = !!overflow
          if (!overflow && expanded.value[m.id]) expanded.value[m.id] = false
        }
      } catch (e) { needsTruncate.value[m.id] = false }
    })
  } catch (e) {}
}

async function renderToHtml(md) {
  if (!md) return ''
  try {
    const markedMod = await import('marked')
    const domMod = await import('dompurify')
    const markedFn = markedMod && (markedMod.default || markedMod.marked || markedMod)
    const dompurify = domMod && (domMod.default || domMod.sanitize || domMod)
    let raw = ''
    if (typeof markedFn === 'function') raw = markedFn(md)
    else if (markedFn && typeof markedFn.parse === 'function') raw = markedFn.parse(md)
    else raw = String(md)
    try {
      if (dompurify && typeof dompurify.sanitize === 'function') return dompurify.sanitize(raw)
      if (dompurify && typeof dompurify === 'function') return dompurify(raw)
      return raw
    } catch (e) {
      return raw
    }
  } catch (e) {
    return simpleMarkdownToHtml(md)
  }
}

async function processRendered() {
  try {
    renderedHtml.value = {}
    plainLengths.value = {}
    for (const m of messages.value) {
      try {
        const md = m.body || ''
        let html = ''
        try { html = await renderToHtml(md) } catch (err) { html = simpleMarkdownToHtml(md) }
        renderedHtml.value[m.id] = html
        plainLengths.value[m.id] = (textFromHtml(html) || '').length
      } catch (e) { renderedHtml.value[m.id] = ''; plainLengths.value[m.id] = 0 }
    }
    // measure after DOM update
    checkOverflow()
  } catch (e) {}
}

const expandedSet = expanded
function isTruncated(id) {
  try { return !!needsTruncate.value[id] && !expandedSet.value[id] } catch (e) { return false }
}

async function toggleExpand(id) {
  try {
    const wasExpanded = !!expandedSet.value[id]
    if (wasExpanded) {
      // collapsing: force the toggle visible immediately and re-check after a short delay
      try { forceShowToggle.value[id] = true } catch (e) {}
      if (collapseTimers[id]) { clearTimeout(collapseTimers[id]); delete collapseTimers[id] }
      collapseTimers[id] = setTimeout(async () => {
        try { forceShowToggle.value[id] = false } catch (e) {}
        try { await checkOverflow() } catch (e) {}
        delete collapseTimers[id]
      }, 300)
    }
    expandedSet.value[id] = !wasExpanded
    await nextTick()
    await checkOverflow()
  } catch (e) {}
}

// realtime websocket handling (reuse orbitSchedules pattern)
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
  const sel = auth.selectedOrganization == null ? null : String(auth.selectedOrganization)
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
      try {
        // always remove deleted messages from this view
        messages.value = messages.value.filter(x => String(x.id) !== String(m.id)); processRendered()
      } catch (e) {}
      return
    }
    if (action === 'create' || action === 'update') {
      try {
        // if placement is provided and not frontpage, remove on update (and ignore on create)
        if (m && (m.placement !== undefined && m.placement !== null) && m.placement !== 'frontpage') {
          if (action === 'update') {
            messages.value = messages.value.filter(x => String(x.id) !== String(m.id))
            processRendered()
          }
          return
        }
        if (!matchesOrg(m.organization_id)) {
          messages.value = messages.value.filter(x => String(x.id) !== String(m.id)); processRendered(); return
        }
        const incoming = Object.assign({}, m)
        const idx = messages.value.findIndex(x => String(x.id) === String(incoming.id))
        if (idx === -1) messages.value.push(incoming)
        else messages.value.splice(idx, 1, incoming)
        sortMessages(messages.value)
        processRendered()
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
  try { window.removeEventListener('resize', checkOverflow) } catch (e) {}
  try { Object.keys(collapseTimers || {}).forEach(k => { clearTimeout(collapseTimers[k]) }) } catch (e) {}
})

onMounted(() => {
  fetchOrganizations().catch(() => {})
  load()
  try { window.addEventListener('resize', checkOverflow) } catch (e) {}
})

watch(() => auth.selectedOrganization, () => load())

const displayRange = (m) => {
  try {
    if (!m.start && !m.end) return t('adminMessages.range.always')
    const loc = locale && locale.value ? locale.value : undefined
    const format = (iso) => {
      if (!iso) return ''
      try { const d = new Date(iso); if (isNaN(d.getTime())) return String(iso); return new Intl.DateTimeFormat(loc || undefined, { dateStyle: 'short', timeStyle: 'short' }).format(d) } catch (e) { return String(iso) }
    }
    if (m.start && m.end) return `${format(m.start)} → ${format(m.end)}`
    return m.start ? t('adminMessages.range.from', { date: format(m.start) }) : t('adminMessages.range.until', { date: format(m.end) })
  } catch (e) { return '' }
}



function onDialogCreated(created) {
  try {
    if (matchesOrg(created.organization_id)) {
      const idx = messages.value.findIndex(x => String(x.id) === String(created.id))
      if (idx === -1) messages.value.push(created)
      else messages.value.splice(idx, 1, created)
      sortMessages(messages.value)
      processRendered()
    }
  } catch (e) {}
}

function onDialogUpdated(updated) {
  try {
    const idx = messages.value.findIndex(x => String(x.id) === String(updated.id))
    if (matchesOrg(updated.organization_id)) {
      if (idx === -1) messages.value.push(updated)
      else messages.value.splice(idx, 1, updated)
    } else {
      if (idx !== -1) messages.value.splice(idx, 1)
    }
    sortMessages(messages.value)
    processRendered()
  } catch (e) {}
}

</script>

<style scoped>
.admin-messages-card { max-width: 100%; }
.md-preview { max-height: 8.5em; overflow: hidden; transition: max-height .18s ease; position: relative; font-size: 0.95rem; color: inherit; }
.md-preview.expanded { max-height: 2000px; }
.md-preview.has-overlay::after { content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 2.6em; pointer-events: none; background: linear-gradient(transparent, white); }
.md-preview.has-overlay.dark::after { background: linear-gradient(transparent, rgba(0,0,0,0.6)); }
.md-preview.expanded::after { display: none; }

/* Tame markdown header sizes so headings inside messages aren't gigantic.
  Use ::v-deep because the markup is injected with `v-html` and thus
  won't receive the component's scoped attribute. */
.md-preview ::v-deep h1, .md-preview ::v-deep h2, .md-preview ::v-deep h3, .md-preview ::v-deep h4 { margin: 0.15em 0 0.35em; font-weight: 600; line-height: 1.15; color: inherit; }
.md-preview ::v-deep h1 { font-size: 1.5rem; }
.md-preview ::v-deep h2 { font-size: 1.20rem; }
.md-preview ::v-deep h3 { font-size: 1.0rem; }
.md-preview ::v-deep h4 { font-size: 0.90rem; }
.md-preview.dark ::v-deep h1, .md-preview.dark ::v-deep h2, .md-preview.dark ::v-deep h3 { color: #ffffff; }

.md-preview p { margin: 0 0 0.4em; line-height: 1.3; }
.md-preview ul { margin: 0.2em 0 0.6em 1.2em; }
.md-preview li { margin-bottom: 0.2em; }
.md-preview code { background: #f5f5f5; color: #111; padding: 0.06em 0.28em; border-radius: 3px; font-family: monospace; font-size: .95em; }
.md-preview pre { background: #f5f5f5; padding: .6em; border-radius: 4px; overflow: auto; font-family: monospace; }
.md-preview.dark code, .md-preview.dark pre { background: #1e1e1e; color: #eaeaea; }
</style>
