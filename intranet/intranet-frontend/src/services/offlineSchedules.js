// Simple prototype offline store + WebSocket sync for TermSchedules
// This is a minimal local-first implementation for prototyping only.

const PREFIX = 'offline:termschedules:'
let store = {} // map scheduleId -> rows array
let listeners = []
let ws = null
let wsConnected = false
let pendingOps = []
let subscribedSchedule = null

function _key(scheduleId) {
  return PREFIX + String(scheduleId)
}

function loadFromStorage(scheduleId) {
  try {
    const raw = localStorage.getItem(_key(scheduleId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch (e) { return [] }
}

function saveToStorage(scheduleId) {
  try {
    localStorage.setItem(_key(scheduleId), JSON.stringify(store[scheduleId] || []))
  } catch (e) {}
}

function applyOpLocally(scheduleId, op) {
  // op: { type: 'create'|'update'|'delete', entry }
  if (!store[scheduleId]) store[scheduleId] = loadFromStorage(scheduleId)
  if (op.type === 'create') {
    // ensure id
    if (!op.entry.id) op.entry.id = `local-${Date.now()}-${Math.random().toString(36).slice(2,8)}`
    store[scheduleId].push(op.entry)
  } else if (op.type === 'update') {
    store[scheduleId] = store[scheduleId].map(e => e.id === op.entry.id ? Object.assign({}, e, op.entry) : e)
  } else if (op.type === 'delete') {
    store[scheduleId] = store[scheduleId].filter(e => e.id !== op.entry.id)
  }
  saveToStorage(scheduleId)
  _notify(scheduleId)
}

function _notify(scheduleId) {
  const rows = (store[scheduleId] || []).slice()
  listeners.forEach(fn => {
    try { fn(scheduleId, rows) } catch (e) {}
  })
}

function init() {
  // no-op for now
}

function subscribe(scheduleId, cb) {
  if (!listeners.includes(cb)) listeners.push(cb)
  if (!store[scheduleId]) store[scheduleId] = loadFromStorage(scheduleId)
  cb(scheduleId, (store[scheduleId] || []).slice())
  // ensure ws subscription
  if (wsConnected && subscribedSchedule !== scheduleId) {
    // simple subscribe message
    try { ws.send(JSON.stringify({ type: 'subscribe', scheduleId })) } catch(e){}
    subscribedSchedule = scheduleId
  }
}

function unsubscribe(cb) {
  listeners = listeners.filter(f => f !== cb)
}

function connectWebsocket() {
  if (ws) return
  try {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    // backend expects /api/ws per FastAPI route
    const token = localStorage.getItem('access_token')
    const url = `${proto}://${location.host}/api/ws${token ? `?token=${token}` : ''}`
    ws = new WebSocket(url)
    ws.addEventListener('open', () => {
      wsConnected = true
      // flush pending ops
      while (pendingOps.length) {
        const m = pendingOps.shift()
        try { ws.send(JSON.stringify(m)) } catch(e) { pendingOps.unshift(m); break }
      }
    })
    ws.addEventListener('message', (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        // expected msg: { type: 'op', scheduleId, op }
        if (msg && msg.type === 'op' && msg.scheduleId) {
          applyOpLocally(msg.scheduleId, msg.op)
        }
      } catch (e) {}
    })
    ws.addEventListener('close', () => { wsConnected = false; ws = null })
    ws.addEventListener('error', () => { wsConnected = false; ws = null })
  } catch (e) {
    ws = null
    wsConnected = false
  }
}

function sendOp(scheduleId, op) {
  const msg = { type: 'op', scheduleId, op }
  if (wsConnected && ws) {
    try { ws.send(JSON.stringify(msg)) } catch (e) { pendingOps.push(msg) }
  } else {
    pendingOps.push(msg)
    // try to connect
    connectWebsocket()
  }
}

async function getEntries(scheduleId) {
  if (!store[scheduleId]) store[scheduleId] = loadFromStorage(scheduleId)
  return (store[scheduleId] || []).slice()
}

async function createEntry(scheduleId, entry) {
  const op = { type: 'create', entry }
  applyOpLocally(scheduleId, op)
  sendOp(scheduleId, op)
  return entry
}

async function updateEntry(scheduleId, entry) {
  const op = { type: 'update', entry }
  applyOpLocally(scheduleId, op)
  sendOp(scheduleId, op)
  return entry
}

async function deleteEntry(scheduleId, entryId) {
  const op = { type: 'delete', entry: { id: entryId } }
  applyOpLocally(scheduleId, op)
  sendOp(scheduleId, op)
  return true
}

export default {
  init,
  subscribe,
  unsubscribe,
  connectWebsocket,
  getEntries,
  createEntry,
  updateEntry,
  deleteEntry,
}
