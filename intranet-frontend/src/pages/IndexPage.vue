<template>
  <q-page padding class="index-page">
    <div class="row q-col-gutter-md">
      <div class="col-12 col-md-8">
        <q-card flat bordered>
          <q-card-section class="row items-center justify-between">
            <div>
              <div class="text-h6">{{ $t('index.title') }}</div>
              <div class="text-subtitle2 q-mt-xs">{{ currentMonthLabel }}</div>
            </div>
            <div>
              <q-btn dense flat round icon="chevron_left" @click="prevMonth" />
              <q-btn dense flat round icon="today" @click="goToday" />
              <q-btn dense flat round icon="chevron_right" @click="nextMonth" />
            </div>
          </q-card-section>

          <q-separator />

          <q-card-section>
            <div class="calendar-grid">
              <div class="calendar-weekday" v-for="d in weekdays" :key="d">{{ d }}</div>
              <div v-for="cell in calendarCells" :key="cell.key" class="calendar-cell" :class="{ 'today': cell.isToday }">
                <div class="date-number">{{ cell.day }}</div>
                <div class="events">
                  <q-chip v-for="ev in cell.events" :key="ev.id" dense class="q-mt-xs" clickable @click="openEntry(ev)">
                    <span class="event-time" v-if="ev._startDt">{{ formatTimeFromDate(ev._startDt) }}</span>
                    <span class="event-emoji" v-if="isUserResponsible(ev) || isUserDevotional(ev)">{{ emojiForEntry(ev) }}</span>
                    <span class="event-name">{{ ev.name }}</span>
                  </q-chip>
                </div>
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-4">
        <AdminMessagesCard class="q-mb-md" />
        <q-card flat bordered>
          <q-card-section class="row items-center justify-between">
            <div class="text-h6">{{ upcoming.length }} {{ $t('termschedules.upcoming') }}</div>
          </q-card-section>
          <q-separator />
          <q-card-section>
            <q-list bordered padding>
              <q-item v-for="item in upcoming" :key="item.id" clickable @click="openEntry(item)">
                <q-item-section side>
                  <div class="item-time-range">{{ formatUpcomingRange(item) }}</div>
                </q-item-section>
                <q-item-section>
                  <div class="text-subtitle2">{{ item.name }}</div>
                  <div class="text-caption">
                    <span v-if="item.organization_name">{{ item.organization_name }}</span>
                    <span v-if="item.activity_name"> • {{ item.activity_name }}</span>
                    <span v-if="isUserResponsible(item)" class="status-badge"> • 👤 {{ $t('termschedules.responsible_label') }}</span>
                    <span v-if="isUserDevotional(item)" class="status-badge"> • 🙏 {{ $t('termschedules.devotional_label') }}</span>
                  </div>
                  <div class="text-body2 q-mt-sm" v-if="item.description">{{ item.description }}</div>
                </q-item-section>
                <q-item-section side top>
                  <q-btn dense flat icon="open_in_new" @click.stop="openSchedule(item.schedule_id)" />
                </q-item-section>
              </q-item>
              <q-item v-if="upcoming.length === 0">
                <q-item-section>
                  <div class="text-caption">No upcoming items</div>
                </q-item-section>
              </q-item>
            </q-list>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import { useRouter } from 'vue-router'
import { useAuth, fetchCurrentUser } from 'src/services/auth'
import { useI18n } from 'vue-i18n'
import AdminMessagesCard from 'src/components/AdminMessagesCard.vue'

const { t, locale } = useI18n()
const router = useRouter()
const auth = useAuth()

const today = ref(new Date())
const viewYear = ref(today.value.getFullYear())
const viewMonth = ref(today.value.getMonth()) // 0-based

// Localized weekdays starting Monday
const weekdays = computed(() => {
  try {
    const loc = (locale && locale.value) ? locale.value : undefined
    // find a Monday to start from (walk forward from Jan 1 of a stable year)
    let base = new Date(2021, 0, 1)
    while (base.getDay() !== 1) base.setDate(base.getDate() + 1)
    const dtf = new Intl.DateTimeFormat(loc, { weekday: 'short' })
    const names = []
    for (let i = 0; i < 7; i++) {
      const d = new Date(base.getFullYear(), base.getMonth(), base.getDate() + i)
      names.push(dtf.format(d))
    }
    return names
  } catch (e) {
    return ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
  }
})

const currentMonthLabel = computed(() => {
  try {
    const loc = (locale && locale.value) ? locale.value : undefined
    const dt = new Date(viewYear.value, viewMonth.value, 1)
    return new Intl.DateTimeFormat(loc, { month: 'long', year: 'numeric' }).format(dt)
  } catch (e) {
    return `${viewYear.value}-${String(viewMonth.value+1).padStart(2,'0')}`
  }
})

const schedules = ref([])
const schedulesMap = ref({})
const activities = ref([])
const activitiesMap = ref({})
const entries = ref([])

const upcoming = computed(() => {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  return entries.value
    .filter(e => {
      const d = e._startDt || parseDateTime(e.date, e.start)
      // only include future-or-today entries
      if (d) {
        if (d < startOfToday) return false
      }
      // do not show entries the user explicitly can't come to
      try {
        if (userCantCome(e)) return false
      } catch (err) {}
      return true
    })
    .sort((a,b) => {
      const da = a._startDt || parseDateTime(a.date, a.start) || new Date(0)
      const db = b._startDt || parseDateTime(b.date, b.start) || new Date(0)
      return da - db
    })
    .slice(0, 10)
})

function formatDate(d) {
  try { const dt = new Date(d); return dt.toLocaleDateString() } catch (e) { return d }
}

function parseLocalDateTime(dateStr, timeStr) {
  if (!dateStr) return null
  const dateOnly = String(dateStr).split('T')[0]
  const parts = dateOnly.split('-').map(n => parseInt(n, 10))
  if (parts.length < 3) return null
  const [y, m, d] = parts
  if (!timeStr) return new Date(y, m - 1, d)
  const tparts = String(timeStr).split(':').map(n => parseInt(n, 10))
  const hh = tparts[0] || 0
  const mm = tparts[1] || 0
  const ss = tparts[2] || 0
  return new Date(y, m - 1, d, hh, mm, ss)
}

function parseDateTime(dateStr, timeStr) {
  // Robust parsing for combinations of: full ISO timestamps, date + time-only, or separate fields
  const rawDate = dateStr || ''
  const rawTime = timeStr || ''

  const t = String(rawTime)
  const d = String(rawDate)

  // If timeStr already looks like a full ISO timestamp or contains timezone info, use Date directly
  if (t.includes('T') || t.includes('Z') || /[+-]\d{2}:?\d{2}/.test(t)) {
    try { return new Date(t) } catch (e) {}
  }

  // If dateStr contains time information or timezone, let Date parse it
  if (d.includes('T') || d.includes('Z') || /[+-]\d{2}:?\d{2}/.test(d)) {
    try { return new Date(d) } catch (e) {}
  }

  // Otherwise combine date + time as local time
  try { return parseLocalDateTime(d, t) } catch (e) { return null }
}

function formatTimeFromDate(dt) {
  if (!dt) return ''
  try {
    const opts = { hour: '2-digit', minute: '2-digit' }
    return new Intl.DateTimeFormat(undefined, opts).format(dt)
  } catch (e) { return '' }
}

function formatUpcomingRange(item) {
  const start = item._startDt || parseDateTime(item.date || (item.attributes && item.attributes.date), item.start || (item.attributes && item.attributes.start))
  if (!start) return ''
  const YYYY = start.getFullYear()
  const MM = String(start.getMonth() + 1).padStart(2, '0')
  const DD = String(start.getDate()).padStart(2, '0')
  const pad2 = n => String(n).padStart(2, '0')
  const startHM = `${pad2(start.getHours())}:${pad2(start.getMinutes())}`
  const end = item._endDt || parseDateTime(item.date || (item.attributes && item.attributes.date), item.end || (item.attributes && item.attributes.end))
  if (end) {
    const endHM = `${pad2(end.getHours())}:${pad2(end.getMinutes())}`
    return `${YYYY}-${MM}-${DD} ${startHM} → ${endHM}`
  }
  return `${YYYY}-${MM}-${DD} ${startHM}`
}

function formatTime(timeStr, dateStr) {
  if (!timeStr) return ''
  try {
    const dt = parseLocalDateTime(dateStr, timeStr) || new Date()
    const opts = { hour: '2-digit', minute: '2-digit' }
    return new Intl.DateTimeFormat(undefined, opts).format(dt)
  } catch (e) {
    try { const parts = timeStr.split(':'); return `${parts[0].padStart(2,'0')}:${parts[1].padStart(2,'0')}` } catch (ee) { return timeStr }
  }
}

function getUserIdSet() {
  const s = new Set()
  const u = auth.user
  if (!u) return s
  const candidates = []
  try {
    candidates.push(u.id)
    candidates.push(u.sub)
    candidates.push(u.attributes && u.attributes.id)
    candidates.push(u.attributes && u.attributes.user_id)
    candidates.push(u.attributes && u.attributes.person_id)
    candidates.push(u.attributes && u.attributes.account_id)
    candidates.push(u.attributes && u.attributes.person && u.attributes.person.id)
    if (u.relationships && u.relationships.person && u.relationships.person.data) candidates.push(u.relationships.person.data.id)
  } catch (e) {}
  const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  candidates.forEach(c => {
    if (!c && c !== 0) return
    const str = String(c)
    if (uuidRe.test(str)) s.add(str)
  })
  return s
}

function isUserResponsible(entry) {
  const ids = getUserIdSet()
  if (!ids || ids.size === 0) return false
  if (entry.responsible_user_id && ids.has(String(entry.responsible_user_id))) return true
  if (entry.responsible && Array.isArray(entry.responsible) && entry.responsible.some(r => ids.has(String(r)))) return true
  if (entry.responsibles && Array.isArray(entry.responsibles)) {
    if (entry.responsibles.some(r => ids.has(String(r.id || r.user_id || r)))) return true
  }
  if (entry.responsible_ids && Array.isArray(entry.responsible_ids) && entry.responsible_ids.some(rid => ids.has(String(rid)))) return true
  if (entry.attributes && entry.attributes.responsibles && Array.isArray(entry.attributes.responsibles)) {
    if (entry.attributes.responsibles.some(r => ids.has(String(r.id || r.user_id || r)))) return true
  }
  if (entry.attributes && entry.attributes.responsible_ids && Array.isArray(entry.attributes.responsible_ids) && entry.attributes.responsible_ids.some(rid => ids.has(String(rid)))) return true
  return false
}

function isUserDevotional(entry) {
  const ids = getUserIdSet()
  if (!ids || ids.size === 0) return false
  if (entry.devotional_user_id && ids.has(String(entry.devotional_user_id))) return true
  if (entry.devotional && Array.isArray(entry.devotional) && entry.devotional.some(r => ids.has(String(r)))) return true
  if (entry.devotionals && Array.isArray(entry.devotionals)) {
    if (entry.devotionals.some(r => ids.has(String(r.id || r.user_id || r)))) return true
  }
  if (entry.devotional_ids && Array.isArray(entry.devotional_ids) && entry.devotional_ids.some(rid => ids.has(String(rid)))) return true
  if (entry.attributes && entry.attributes.devotionals && Array.isArray(entry.attributes.devotionals)) {
    if (entry.attributes.devotionals.some(r => ids.has(String(r.id || r.user_id || r)))) return true
  }
  if (entry.attributes && entry.attributes.devotional_ids && Array.isArray(entry.attributes.devotional_ids) && entry.attributes.devotional_ids.some(rid => ids.has(String(rid)))) return true
  return false
}

function userCanAttend(entry) {
  const ids = getUserIdSet()
  if (entry.current_user_can_come !== undefined) return !!entry.current_user_can_come
  if (entry.user_can_come !== undefined) return !!entry.user_can_come
  if (entry.can_come !== undefined) return !!entry.can_come
  if (entry.attending !== undefined) return !!entry.attending

  // If the API provides cant_come_ids and the user is in it, user cannot attend
  if (ids && ids.size > 0) {
    if (Array.isArray(entry.cant_come_ids) && entry.cant_come_ids.some(id => ids.has(String(id)))) return false
    if (entry.cant_come && Array.isArray(entry.cant_come) && entry.cant_come.some(id => ids.has(String(id)))) return false
  }

  const list = entry.attendees || (entry.attributes && entry.attributes.attendees)
  if (Array.isArray(list) && ids && ids.size > 0) {
    const found = list.find(a => ids.has(String(a.user_id || a.id || a.person_id || a.person)))
    if (found) {
      if (found.can_come !== undefined) return !!found.can_come
      if (found.status !== undefined) {
        const s = String(found.status).toLowerCase()
        return s === 'accepted' || s === 'going' || s === 'present' || s === 'yes'
      }
      return true
    }
  }

  return true
}

function userCantCome(entry) {
  const ids = getUserIdSet()
  if (!ids || ids.size === 0) return false
  if (Array.isArray(entry.cant_come_ids) && entry.cant_come_ids.some(id => ids.has(String(id)))) return true
  if (entry.cant_come && Array.isArray(entry.cant_come) && entry.cant_come.some(id => ids.has(String(id)))) return true
  if (entry.attributes && Array.isArray(entry.attributes.cant_come_ids) && entry.attributes.cant_come_ids.some(id => ids.has(String(id)))) return true
  return false
}

function showEntryForUser(entry) {
  // Show if responsible or devotional regardless of attendees, otherwise hide if user explicitly can't come
  if (isUserResponsible(entry) || isUserDevotional(entry)) return true
  if (userCantCome(entry)) return false
  return userCanAttend(entry)
}

function emojiForEntry(entry) {
  const parts = []
  if (isUserResponsible(entry)) parts.push('👤')
  if (isUserDevotional(entry)) parts.push('🙏')
  return parts.join(' ')
}

function formatStartEnd(item) {
  try {
    const opts = { hour: '2-digit', minute: '2-digit' }
    const fmt = new Intl.DateTimeFormat(undefined, opts)
    const date = item.date || (item.attributes && item.attributes.date)
    const start = item.start ? parseLocalDateTime(date, item.start) : null
    const end = item.end ? parseLocalDateTime(date, item.end) : null
    if (start && end) return `${fmt.format(start)} - ${fmt.format(end)}`
    if (start) return fmt.format(start)
    return ''
  } catch (e) { return item.start ? item.start + (item.end ? (' - ' + item.end) : '') : '' }
}

function buildCalendarCells() {
  const year = viewYear.value
  const month = viewMonth.value
  const first = new Date(year, month, 1)
  const startDay = (first.getDay() + 6) % 7 // make Monday=0
  const daysInMonth = new Date(year, month+1, 0).getDate()
  const cells = []
  // leading blanks
  for (let i=0;i<startDay;i++) {
    cells.push({ key: `b-${i}`, day: '', events: [], isToday: false })
  }
  for (let d=1; d<=daysInMonth; d++) {
    const monthStr = String(month+1).padStart(2,'0')
    const dayStr = String(d).padStart(2,'0')
    const dateStr = `${year}-${monthStr}-${dayStr}`
    const dayEvents = entries.value.filter(e => e._dateOnly === dateStr && showEntryForUser(e))
    const now = new Date()
    const todayStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`
    const isToday = (todayStr === dateStr)
    cells.push({ key: `${year}-${month}-${d}`, day: d, events: dayEvents, isToday, dateStr })
  }
  // trailing blanks to complete grid
  while (cells.length % 7 !== 0) cells.push({ key: `t-${cells.length}`, day: '', events: [], isToday: false })
  return cells
}

const calendarCells = computed(() => buildCalendarCells())

function prevMonth() {
  if (viewMonth.value === 0) { viewMonth.value = 11; viewYear.value -= 1 } else { viewMonth.value -= 1 }
}
function nextMonth() { if (viewMonth.value === 11) { viewMonth.value = 0; viewYear.value += 1 } else { viewMonth.value += 1 } }
function goToday() { const d = new Date(); viewYear.value = d.getFullYear(); viewMonth.value = d.getMonth() }

function openEntry(ev) {
  // navigate to schedules and set saved activity/schedule in localStorage so TermSchedules opens relevant context
  try { localStorage.setItem('termschedules:activity', ev.activity_id ? String(ev.activity_id) : 'null') } catch (e) {}
  try { localStorage.setItem('termschedules:term', ev.term_id ? String(ev.term_id) : 'null') } catch (e) {}
  router.push('/schedules')
}

function openSchedule(scheduleId) {
  const s = schedulesMap.value[String(scheduleId)]
  if (s) {
    try { localStorage.setItem('termschedules:activity', s.activity_id ? String(s.activity_id) : 'null') } catch (e) {}
    try { localStorage.setItem('termschedules:term', s.term_id ? String(s.term_id) : 'null') } catch (e) {}
  }
  router.push('/schedules')
}

async function loadData() {
  try {
    // Ensure user is loaded
    if (!auth.user) await fetchCurrentUser()
    // fetch activities and build map
    const actsResp = await axios.get('/api/activities')
    activities.value = actsResp.data?.data || actsResp.data || []
    activitiesMap.value = {}
    activities.value.forEach(a => { activitiesMap.value[String(a.id)] = a.attributes?.name || a.attributes?.name })

    // fetch schedules accessible to user
    const schedResp = await axios.get('/api/schedules')
    schedules.value = schedResp.data?.data || schedResp.data || []
    schedulesMap.value = {}
    schedules.value.forEach(s => { schedulesMap.value[String(s.id)] = s })

    // fetch organizations so we can show organization names in the dashboard
    let orgMapLocal = {}
    try {
      const orgResp = await axios.get('/api/rbac/organizations')
      const orgs = orgResp.data?.data || orgResp.data || []
      orgs.forEach(o => {
        try {
          orgMapLocal[String(o.id)] = o.attributes?.name || o.name || ''
        } catch (err) {
          orgMapLocal[String(o.id)] = ''
        }
      })
    } catch (err) {
      // fallback to auth.organizations if available
      try {
        const authOrgs = auth.organizations || []
        authOrgs.forEach(o => {
          try { orgMapLocal[String(o.id)] = o.attributes?.name || o.name || '' } catch (e) { orgMapLocal[String(o.id)] = '' }
        })
      } catch (e) {
        orgMapLocal = {}
      }
    }

    // determine which activities to include (persisted selection in user profile)
    const sel = auth.user?.attributes?.personal_calendar_activity_ids || []
    const selSet = Array.isArray(sel) && sel.length > 0 ? new Set(sel.map(String)) : null

    // filter schedules by selected activities if selection present
    const filteredSchedules = selSet ? schedules.value.filter(s => selSet.has(String(s.activity_id))) : schedules.value

    // load entries for these schedules
    const entryPromises = filteredSchedules.map(s => axios.get(`/api/schedules/${s.id}/entries`).then(r => ({ schedule: s, entries: r.data?.data || [] })).catch(() => ({ schedule: s, entries: [] })))
    const res = await Promise.all(entryPromises)
    const all = []
    res.forEach(r => {
      const s = r.schedule
      r.entries.forEach(e => {
        const desc = e.description || (e.attributes && e.attributes.description) || e.note || ''
        const orgName = s.organization_name || orgMapLocal[String(s.organization_id)] || (s.organization && (s.organization.name || (s.organization.attributes && s.organization.attributes.name))) || (s.attributes && (s.attributes.organization_name || (s.attributes.organization && s.attributes.organization.attributes && s.attributes.organization.attributes.name))) || ''

        // Normalize common date/time fields into local Date objects when possible
        const rawDate = e.date || (e.attributes && (e.attributes.date || (e.attributes.start && String(e.attributes.start).split('T')[0]))) || ''
        const rawStart = e.start || (e.attributes && (e.attributes.start || e.attributes.start_time || e.attributes.time)) || ''
        const rawEnd = e.end || (e.attributes && (e.attributes.end || e.attributes.end_time)) || ''
        const startDt = parseDateTime(rawDate, rawStart)
        const endDt = parseDateTime(rawDate, rawEnd)
        let dateOnly = ''
        if (startDt) {
          dateOnly = `${startDt.getFullYear()}-${String(startDt.getMonth()+1).padStart(2,'0')}-${String(startDt.getDate()).padStart(2,'0')}`
        } else if (rawDate) {
          dateOnly = String(rawDate).split('T')[0]
        }

        all.push({
          ...e,
          schedule_id: s.id,
          schedule_name: s.name,
          organization_name: orgName,
          activity_id: s.activity_id,
          activity_name: activitiesMap.value[String(s.activity_id)] || '',
          description: desc,
          _startDt: startDt,
          _endDt: endDt,
          _dateOnly: dateOnly
        })
      })
    })

    // filter entries according to whether the current user can see/attend them
    const filtered = all.filter(e => showEntryForUser(e))

    // keep entries sorted by date and time
    entries.value = filtered.sort((a,b) => {
      const da = new Date((a.date || (a.attributes && a.attributes.date)) + (a.start ? 'T' + a.start : ''))
      const db = new Date((b.date || (b.attributes && b.attributes.date)) + (b.start ? 'T' + b.start : ''))
      return da - db
    })
  } catch (e) {
    console.warn('Failed to load dashboard data', e)
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}
.calendar-weekday { font-weight: 600; text-align: center; padding: 6px 0 }
.calendar-cell { min-height: 90px; border-radius: 6px; padding: 6px; background: var(--q-color-grey-2); }
.calendar-cell.today { border: 2px solid var(--q-color-primary); background: var(--q-color-grey-1); }
.date-number { font-weight: 600; opacity: 0.85 }
.events { margin-top: 6px; display:flex; flex-direction:column; gap:4px }
.item-date { font-weight:600 }
.item-time { font-size: .85em; color: var(--q-color-dark) }
.event-time { margin-right: 8px; font-weight:600 }
.item-time-range { font-weight:600; font-size: .95em }
.event-emoji { margin: 0 6px; }
.status-badge { margin-left: 6px; font-weight: 600 }
</style>
