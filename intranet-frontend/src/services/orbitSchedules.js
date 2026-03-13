/*
Orbit.js prototype service for TermSchedules

This file provides a minimal Orbit client + WebSocket adapter scaffold.
It expects the following packages to be installed in the frontend:

  npm install @orbit/core @orbit/data @orbit/indexeddb @orbit/transform @orbit/serializers

NOTE: Orbit has several packages and different adapters/serializers depending
on how you want to use it (JSON:API, REST, etc). This scaffold focuses on
creating an in-memory + IndexedDB source and wiring a very small WebSocket
adapter that translates orbit transforms to socket messages and applies
incoming transforms to the local store.

This is a prototype: adapt schemas and serializers to your project's
JSON shape before using in production.
*/

import axios from 'axios'

let orbit = { initialized: false }
let connected = false
// share subscribers across HMR/module instances as early as possible
let subs = []
try {
  if (typeof window !== 'undefined') {
    if (!window.__ORBIT_SUBS) window.__ORBIT_SUBS = []
    subs = window.__ORBIT_SUBS
  }
} catch (e) {
  subs = []
}
let memoryStore = {} // scheduleId -> [rows]
// sync telemetry
let lastSentTs = null
let lastReceivedTs = null
let pendingOps = 0
let lastError = null
let _reconnectIntervalId = null
const _reconnectIntervalMs = 5000

// lightweight API client used for reconciliation when flushing pending creates
function apiClient() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
  try {
    return axios.create({ baseURL: '/api/', headers: { Authorization: token ? `Bearer ${token}` : '' } })
  } catch (e) { return null }
}

// Simple IndexedDB helper: object store 'orbitSchedules' with key = scheduleId
function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('orbitSchedulesDB')
    req.onerror = () => reject(req.error)
    req.onsuccess = () => {
      const db = req.result
      // if any required store is missing, reopen with a bumped version to create them
      const needsOrbit = !db.objectStoreNames.contains('orbitSchedules')
      const needsPending = !db.objectStoreNames.contains('orbitPending')
      if (!needsOrbit && !needsPending) {
        resolve(db)
        return
      }
      const newVersion = db.version + 1
      db.close()
      const req2 = indexedDB.open('orbitSchedulesDB', newVersion)
      req2.onupgradeneeded = (ev) => {
        const db2 = ev.target.result
        if (!db2.objectStoreNames.contains('orbitSchedules')) db2.createObjectStore('orbitSchedules')
        if (!db2.objectStoreNames.contains('orbitPending')) db2.createObjectStore('orbitPending')
      }
      req2.onsuccess = () => resolve(req2.result)
      req2.onerror = () => reject(req2.error)
    }
    // also create stores on first-time open
    req.onupgradeneeded = (ev) => {
      const db = ev.target.result
      if (!db.objectStoreNames.contains('orbitSchedules')) db.createObjectStore('orbitSchedules')
      if (!db.objectStoreNames.contains('orbitPending')) db.createObjectStore('orbitPending')
    }
  })
}

// fallback persistence for quick unloads/reloads: localStorage is synchronous
function persistPendingFallback(items) {
  try {
    if (typeof localStorage !== 'undefined') {
      try {
        const raw = JSON.stringify(items || [])
        localStorage.setItem('orbit:pending_fallback', raw)
        try { console.debug('persistPendingFallback: wrote fallback pending length', Array.isArray(items) ? items.length : null) } catch (e) {}
      } catch (e) { console.warn('persistPendingFallback: localStorage write failed', e) }
    }
  } catch (e) {}
}
// Helper: generate client-side transform id
function generateTransformId() {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  } catch (e) {}
  return `ct-${Date.now()}-${Math.random().toString(36).slice(2,8)}`
}

// Ensure a pending transform item has deterministic metadata: transformId and lastModified
function ensureTransformMetadata(item) {
  try {
    if (!item || typeof item !== 'object') return item
    const t = item.transform || (item.item && item.item.transform) || item
    if (!t || typeof t !== 'object') return item
    if (!t.transformId) t.transformId = generateTransformId()
    if (t.entry && typeof t.entry === 'object') {
      if (!t.entry.lastModified || Number(t.entry.lastModified) === 0) t.entry.lastModified = Date.now()
    } else {
      if (!t.lastModified) t.lastModified = Date.now()
    }
  } catch (e) {}
  return item
}

// Attempt a short best-effort flush of persisted pending items over websocket.
async function attemptFlushPendingShort(timeoutMs = 800) {
  try {
    if (!orbit || !orbit.ws || orbit.ws.readyState !== WebSocket.OPEN) return
    const q = (await safeIdbGetPending()) || []
    if (!Array.isArray(q) || q.length === 0) return
    for (const item of q) {
      try { ensureTransformMetadata(item) } catch (e) {}
      try { orbit.ws.send(JSON.stringify(item)); lastSentTs = Date.now() } catch (e) {}
    }
  } catch (e) {}
}
async function idbGet(scheduleId) {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction('orbitSchedules', 'readonly')
      const store = tx.objectStore('orbitSchedules')
      const r = store.get(String(scheduleId))
      r.onsuccess = () => resolve(r.result || [])
      r.onerror = () => reject(r.error)
    })
  } catch (e) { return [] }
}

async function idbSet(scheduleId, rows) {
  try {
    const db = await openDb()
    // Ensure the value is structured-cloneable. Use native structuredClone when available,
    // otherwise fall back to JSON serialization. If both fail, attempt a shallow copy as last resort.
    let toStore = rows
    try {
      if (typeof structuredClone === 'function') toStore = structuredClone(rows)
      else toStore = JSON.parse(JSON.stringify(rows))
    } catch (cloneErr) {
      console.warn('idbSet: failed to clone rows for IndexedDB, attempting deep sanitize', cloneErr)
      // Deep sanitize: recursively copy plain objects/arrays and drop functions, symbols, and non-enumerable props
      const sanitize = (v) => {
        if (v === null || v === undefined) return v
        const t = typeof v
        if (t === 'string' || t === 'number' || t === 'boolean') return v
        if (Array.isArray(v)) return v.map(sanitize)
        if (t === 'object') {
          const out = {}
          try {
            Object.keys(v).forEach(k => {
              try {
                const val = v[k]
                const vt = typeof val
                if (vt === 'function' || vt === 'symbol') return
                out[k] = sanitize(val)
              } catch (e) {}
            })
          } catch (e) {}
          return out
        }
        // fallback: stringify if possible
        try { return JSON.parse(JSON.stringify(v)) } catch (e) { return String(v) }
      }
      try {
        toStore = Array.isArray(rows) ? rows.map(r => sanitize(r)) : sanitize(rows)
      } catch (sanErr) {
        console.warn('idbSet: deep sanitize failed, falling back to shallow copy', sanErr)
        try { toStore = Array.isArray(rows) ? rows.map(r => Object.assign({}, r)) : Object.assign({}, rows) } catch (shallowErr) { console.warn('idbSet: shallow copy also failed, storing original (may error)', shallowErr); toStore = rows }
      }
    }
    return new Promise((resolve, reject) => {
      const tx = db.transaction('orbitSchedules', 'readwrite')
      const store = tx.objectStore('orbitSchedules')
        const r = store.put(toStore, String(scheduleId))
      r.onsuccess = () => resolve(true)
      r.onerror = () => reject(r.error)
    })
  } catch (e) { console.warn('idbSet failed', e); return false }
}

async function init() {
  // Initialize our lightweight in-memory + IndexedDB store.
  try {
    // warm memory store from IndexedDB (do not load every schedule yet)
    orbit.initialized = true
    // share subscriber list across module instances (helps during HMR/dev reloads)
    try {
      if (typeof window !== 'undefined') {
        if (!window.__ORBIT_SUBS) window.__ORBIT_SUBS = []
        subs = window.__ORBIT_SUBS
      }
    } catch (e) {}
    // load pending queue (use safe wrapper to log issues)
    pendingQueue = (await safeIdbGetPending()) || []
    pendingOps = pendingQueue.length
    // start reconnect loop to try opening websocket when offline
    try {
      if (!_reconnectIntervalId) {
        _reconnectIntervalId = setInterval(() => {
          try { if (!connected) connectWebsocket() } catch (e) { console.warn('reconnect attempt failed', e) }
        }, _reconnectIntervalMs)
      }
    } catch (e) { console.warn('failed to start reconnect loop', e) }
    // expose a small global helper and attach cross-tab storage listener for fallback realtime delivery
    try {
      if (typeof window !== 'undefined') {
        try { window.__ORBIT_INTERNAL = orbit } catch (e) {}
        try { if (!window.__ORBIT) window.__ORBIT = {} } catch (e) {}
      }
    } catch (e) {}
    // cross-tab storage listener for fallback realtime delivery
    try {
      if (typeof window !== 'undefined' && typeof window.addEventListener === 'function' && !orbit._storageHandlerAttached) {
        orbit._storageHandlerAttached = true
        window.addEventListener('storage', (ev) => {
          try {
            if (!ev || !ev.key) return
            if (ev.key !== 'orbit:transform') return
/** storage listener attached above **/
            if (!ev.newValue) return
            let obj = null
            try { obj = JSON.parse(ev.newValue) } catch (e) { console.warn('orbit storage: invalid JSON', e); return }
            if (!obj || !obj.item) return
            const item = obj.item
            if (item && item.type === 'transform' && item.transform) {
              // apply transform locally (other tabs will receive this)
              try {
                console.debug('orbit storage event: applying transform', item.transform && (item.transform.op || item.transform), 'scheduleId', item.transform.scheduleId || item.transform.schedule_id)
                applyRemoteTransform(item.transform)
              } catch (e) { console.warn('applyRemoteTransform failed from storage event', e) }
            }
          } catch (e) { console.warn('orbit storage handler error', e) }
        })
      }
    } catch (e) { console.warn('failed to attach storage listener', e) }
    // BroadcastChannel fallback (more reliable cross-tab messaging)
    try {
      if (typeof window !== 'undefined' && typeof BroadcastChannel !== 'undefined' && !orbit._bc) {
        try {
          orbit._bc = new BroadcastChannel('orbit:transform')
          orbit._bc.onmessage = (ev) => {
            try {
              const obj = ev && ev.data
              if (!obj || !obj.item) return
              const item = obj.item
              if (item && item.type === 'transform' && item.transform) {
                console.debug('orbit bc message: applying transform', item.transform && (item.transform.op || item.transform), 'scheduleId', item.transform.scheduleId || item.transform.schedule_id)
                applyRemoteTransform(item.transform)
              }
            } catch (e) { console.warn('orbit bc handler error', e) }
          }
        } catch (e) { console.warn('failed to create BroadcastChannel', e) }
      }
    } catch (e) { console.warn('BroadcastChannel setup failed', e) }
      // ensure pending queue is saved to synchronous fallback on unload/reload
      try {
        if (typeof window !== 'undefined' && typeof window.addEventListener === 'function' && !orbit._beforeUnloadAttached) {
          orbit._beforeUnloadAttached = true
          window.addEventListener('beforeunload', () => {
            try { persistPendingFallback(pendingQueue) } catch (e) {}
          })
        }
      } catch (e) {}
    // attach small runtime helpers onto window.__ORBIT
    try {
      if (typeof window !== 'undefined' && window.__ORBIT) {
        window.__ORBIT.getSyncStatus = () => {
          const now = Date.now()
          let crossTab = false
          try {
            const v = typeof localStorage !== 'undefined' ? localStorage.getItem('orbit:connected') : null
            if (v) {
              const ts = parseInt(v, 10)
              if (!isNaN(ts) && (now - ts) < 15000) crossTab = true
            }
          } catch (e) { crossTab = false }
          const syncedOrgs = (orbit && orbit.syncedOrgs) ? Object.assign({}, orbit.syncedOrgs) : {}
          const syncProgress = (orbit && orbit.syncProgress) ? Object.assign({}, orbit.syncProgress) : { total: 0, done: 0 }
          return { connected, crossTabConnected: crossTab, lastSentTs, lastReceivedTs, pendingOps, lastError, syncedOrgs, syncProgress }
        }
        window.__ORBIT.getPendingQueue = async () => {
          try {
            const persisted = await safeIdbGetPending().catch(() => []) || []
            const mem = Array.isArray(pendingQueue) ? pendingQueue.slice() : []
            const out = []
            const seen = new Set()
            const extractId = (p) => {
              try {
                const t = p && (p.transform || (p.item && p.item.transform) || p)
                if (!t) return null
                if (t.transformId) return String(t.transformId)
                if (t.entry && t.entry.id) return String(t.entry.id)
              } catch (e) {}
              try { return JSON.stringify(p) } catch (e) { return null }
            }
            for (const p of persisted) {
              const id = extractId(p)
              if (id) seen.add(id)
              out.push(p)
            }
            for (const p of mem) {
              const id = extractId(p)
              if (!id || !seen.has(id)) {
                out.push(p)
                if (id) seen.add(id)
              }
            }
            return out
          } catch (e) { return pendingQueue.slice() }
        }
        window.__ORBIT.ws = () => (orbit && orbit.ws)
        window.__ORBIT.__orbit = orbit
        window.__ORBIT.dumpMemory = () => {
          try {
            const out = {}
            Object.keys(memoryStore).forEach(k => { out[k] = Array.isArray(memoryStore[k]) ? memoryStore[k].slice() : [] })
            try { console.debug('orbit dumpMemory', out) } catch (e) {}
            return out
          } catch (e) { return {} }
        }
          window.__ORBIT.listSubscribers = () => {
            try { return { count: Array.isArray(subs) ? subs.length : 0 } } catch (e) { return { count: 0 } }
          }
      }
    } catch (e) {}
    return orbit
  } catch (e) {
    console.warn('Orbit init failed', e)
    orbit.initialized = false
    return orbit
  }
}

function ensureInitialized() {
  if (!orbit || !orbit.initialized) throw new Error('Orbit not initialized. Call init() first.')
}

async function connectWebsocket() {
  // This adapter is intentionally minimal: it opens WebSocket to /api/ws
  // and expects/produces simple messages: { type: 'transform', transform }
  // where `transform` is a serializable representation of an Orbit transform.
  ensureInitialized()
  if (connected) return
  const token = localStorage.getItem('access_token')
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  // Determine the websocket host/URL.
  // Priority:
  // 1. If the page has a runtime global `window.__API_PROXY_TARGET__`, use that (portable).
  // 2. If frontend is served on :9000 (dev), prefer backend on :8000 to avoid connecting to the dev server.
  // 3. Otherwise use the current origin.
  let url
  try {
    const proxy = (typeof window !== 'undefined' && window.__API_PROXY_TARGET__) || null
    if (proxy) {
      // build ws URL from proxy (may include scheme and host)
      try {
        const base = new URL(proxy)
        const wsProto = base.protocol === 'https:' ? 'wss' : 'ws'
        url = `${wsProto}://${base.host}/api/ws${token ? `?token=${token}` : ''}`
      } catch (e) {
        // if proxy is a host:port string, fallback
        const host = proxy
        url = `${proto}://${host}/api/ws${token ? `?token=${token}` : ''}`
      }
    } else {
      let host = location.host
      // when running the frontend dev server on port 9000 (dev), prefer the
      // backend on host port 8200 (dev compose maps host:8200 -> container:8000)
      if (location.port === '9000') {
        host = `${location.hostname}:8200`
      }
      url = `${proto}://${host}/api/ws${token ? `?token=${token}` : ''}`
    }
  } catch (e) {
    url = `${proto}://${location.host}/api/ws${token ? `?token=${token}` : ''}`
  }
  const ws = new WebSocket(url)
  console.info('Orbit WS connecting to', url)

  ws.onopen = function (ev) {
    try {
      connected = true
      try { if (typeof window !== 'undefined') window.__ORBIT_WS = ws } catch (e) {}
      try { if (typeof window !== 'undefined') window.__ORBIT_INTERNAL = orbit } catch (e) {}
      const _flushPendingOnOpen = async () => {
        console.log('Orbit WS onopen debug:', { typeof_safeIdbGetPending: typeof safeIdbGetPending, typeof_safeIdbSetPending: typeof safeIdbSetPending, typeof_ws_send: typeof ws.send })
        try {
          if (typeof safeIdbGetPending !== 'function') {
            console.error('safeIdbGetPending is not a function:', typeof safeIdbGetPending)
            return
          }
          // Load persisted pending items and merge with in-memory queue (avoid duplicates)
          const persisted = await safeIdbGetPending() || []
          try {
            if (!Array.isArray(pendingQueue) || pendingQueue.length === 0) {
              pendingQueue = Array.isArray(persisted) ? persisted.slice() : []
            } else {
              const existingIds = new Set()
              for (const p of pendingQueue) {
                const t = p && (p.transform || (p.item && p.item.transform))
                const id = (t && t.entry && t.entry.id) || (t && t.transformId) || null
                if (id) existingIds.add(String(id))
              }
              for (const p of (Array.isArray(persisted) ? persisted : [])) {
                const t = p && (p.transform || (p.item && p.item.transform))
                const id = (t && t.entry && t.entry.id) || (t && t.transformId) || null
                if (!id || !existingIds.has(String(id))) pendingQueue.push(p)
              }
            }
          } catch (e) {}
          console.log('Orbit WS flush pendingQueue value:', typeof pendingQueue, Array.isArray(pendingQueue) ? pendingQueue.length : null)
          if (!Array.isArray(pendingQueue) || pendingQueue.length === 0) return
          // Ensure all pending items have deterministic metadata before sending
          try {
            let persistModified = false
            for (let i = 0; i < pendingQueue.length; i++) {
              try {
                const p = pendingQueue[i]
                const t = p && (p.transform || (p.item && p.item.transform) || p)
                const hadId = Boolean(t && t.transformId)
                const hadLm = Boolean(t && t.entry && t.entry.lastModified)
                ensureTransformMetadata(p)
                const t2 = p && (p.transform || (p.item && p.item.transform) || p)
                const hasId = Boolean(t2 && t2.transformId)
                const hasLm = Boolean(t2 && t2.entry && t2.entry.lastModified)
                if ((!hadId && hasId) || (!hadLm && hasLm)) persistModified = true
              } catch (e) {}
            }
            if (persistModified) {
              try { await safeIdbSetPending(pendingQueue) } catch (e) { console.warn('flushOnOpen: failed to persist metadata-updated pending', e) }
            }
          } catch (e) {}
          for (const item of pendingQueue) {
            try {
              console.log('About to send pending item, types:', { typeof_ws_send: typeof ws.send, typeof_JSON_stringify: typeof JSON.stringify })
              if (typeof ws.send !== 'function') {
                console.error('ws.send is not a function:', typeof ws.send)
                break
              }
              let payload
              try {
                payload = JSON.stringify(item)
              } catch (err) {
                console.error('JSON.stringify failed for pending item', err, item)
                continue
              }
              try {
                ws.send(payload)
              } catch (err) {
                console.error('ws.send threw', err)
                throw err
              }
              lastSentTs = Date.now()
            } catch (err) {
              console.warn('Failed to flush pending transform', err)
            }
          }
          // Do NOT clear persisted pending queue here; wait for server ACKs to remove items individually.
          pendingOps = Array.isArray(pendingQueue) ? pendingQueue.length : 0
        } catch (e) {
          console.warn('Error flushing pending transforms', e)
        }
      }

      try {
        const maybeFn = _flushPendingOnOpen
        console.log('flushPendingOnOpen typeof', typeof maybeFn)
        if (typeof maybeFn === 'function') {
          maybeFn().catch(err => console.warn('flushPendingOnOpen caught', err))
        } else {
          console.error('flushPendingOnOpen is not callable', maybeFn)
        }
      } catch (err) {
        console.error('Error invoking flushPendingOnOpen', err)
      }
      // mark cross-tab connectivity for other tabs
      try { if (typeof localStorage !== 'undefined') localStorage.setItem('orbit:connected', String(Date.now())) } catch (e) {}
    } catch (err) {
      console.error('Orbit WS onopen handler error', err)
    }
  }

  ws.onmessage = async (ev) => {
    try {
      try {
        try { console.debug('Orbit WS raw frame (truncated):', typeof ev.data === 'string' ? ev.data.slice(0,500) : ev.data) } catch (e) {}
      } catch (e) {}
      let msg = null
      try { msg = JSON.parse(ev.data) } catch (e) { console.warn('Orbit WS: failed to parse incoming frame', e); return }
      if (!msg) return
      console.debug('Orbit WS incoming frame type=', msg.type)
      // capture server/process info sent by backend on accept
      if (msg.type === 'server_info') {
        lastReceivedTs = Date.now()
        try {
          orbit.serverInfo = msg
          if (typeof window !== 'undefined' && window.__ORBIT_INTERNAL) window.__ORBIT_INTERNAL.serverInfo = msg
        } catch (e) {}
        return
      }
      // update lastReceivedTs for any incoming control/ack/heartbeat
      if (msg.type === 'heartbeat') {
        lastReceivedTs = Date.now()
        return
      }
      if (msg.type === 'ack') {
        lastReceivedTs = Date.now()
        try {
          const transformId = msg.transformId || (msg.transform && msg.transform.transformId)
          if (transformId) {
            await removePendingByTransformId(transformId)
          } else {
            if (pendingOps > 0) pendingOps = Math.max(0, pendingOps - 1)
          }
        } catch (e) { console.warn('ack handling failed', e) }
        return
      }
      if (msg.type === 'transform' && msg.transform) {
        // apply transform to local memory + IDB with merge semantics
        lastReceivedTs = Date.now()
        const t = msg.transform
        try { console.debug('Orbit WS transform received', t && (t.op || t)) } catch (e) {}
        await applyRemoteTransform(t)
      }
    } catch (e) { console.warn('Orbit WS message handling error', e) }
  }

  ws.onclose = (ev) => {
    connected = false
    lastError = `ws close ${ev && ev.code ? ev.code : ''}`
    console.warn('Orbit WS closed', ev)
    try { if (typeof localStorage !== 'undefined') localStorage.removeItem('orbit:connected') } catch (e) {}
  }
  ws.onerror = (ev) => {
    connected = false
    lastError = 'ws error'
    console.error('Orbit WS error', ev)
    try { if (typeof localStorage !== 'undefined') localStorage.removeItem('orbit:connected') } catch (e) {}
  }
  orbit.ws = ws
}

// pending transforms persistence helpers
let pendingQueue = []
async function idbGetPending() {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction('orbitPending', 'readonly')
      const store = tx.objectStore('orbitPending')
      const r = store.get('pending')
      r.onsuccess = () => {
        try { console.debug('idbGetPending: loaded pending value type=', typeof r.result, 'isArray=', Array.isArray(r.result), 'len=', Array.isArray(r.result) ? r.result.length : null) } catch (e) {}
        resolve(r.result || [])
      }
      r.onerror = () => reject(r.error)
    })
  } catch (e) { return [] }
}
async function idbSetPending(items) {
  try {
    const db = await openDb()
    // Clone pending items to ensure compatibility with IndexedDB structured clone algorithm
    let toStore = items
    try {
      if (typeof structuredClone === 'function') toStore = structuredClone(items)
      else toStore = JSON.parse(JSON.stringify(items))
    } catch (cloneErr) {
      console.warn('idbSetPending: failed to clone pending items, attempting deep sanitize', cloneErr)
      const sanitize = (v) => {
        if (v === null || v === undefined) return v
        const t = typeof v
        if (t === 'string' || t === 'number' || t === 'boolean') return v
        if (Array.isArray(v)) return v.map(sanitize)
        if (t === 'object') {
          const out = {}
          try {
            Object.keys(v).forEach(k => {
              try {
                const val = v[k]
                const vt = typeof val
                if (vt === 'function' || vt === 'symbol') return
                out[k] = sanitize(val)
              } catch (e) {}
            })
          } catch (e) {}
          return out
        }
        try { return JSON.parse(JSON.stringify(v)) } catch (e) { return String(v) }
      }
      try {
        toStore = Array.isArray(items) ? items.map(i => sanitize(i)) : sanitize(items)
      } catch (sanErr) {
        console.warn('idbSetPending: deep sanitize failed, falling back to shallow copy', sanErr)
        try { toStore = Array.isArray(items) ? items.map(i => Object.assign({}, i)) : Object.assign({}, items) } catch (shallowErr) { console.warn('idbSetPending: shallow copy failed', shallowErr); toStore = items }
      }
    }
    return new Promise((resolve, reject) => {
      const tx = db.transaction('orbitPending', 'readwrite')
      const store = tx.objectStore('orbitPending')
      const r = store.put(toStore, 'pending')
      r.onsuccess = () => {
        try { console.debug('idbSetPending: persisted pending queue length', Array.isArray(toStore) ? toStore.length : null) } catch (e) {}
        try {
          // If queue is empty, remove the synchronous fallback to avoid replaying empty arrays
          if (Array.isArray(toStore) && toStore.length === 0) {
            try { if (typeof localStorage !== 'undefined') { localStorage.removeItem('orbit:pending_fallback'); try { console.debug('idbSetPending: removed orbit:pending_fallback') } catch (e) {} } } catch (e) { console.warn('idbSetPending: failed to remove pending_fallback', e) }
          } else {
            try { persistPendingFallback(toStore) } catch (e) {}
          }
        } catch (e) {}
        resolve(true)
      }
      r.onerror = () => {
        try { console.warn('idbSetPending: idb put error', r.error) } catch (e) {}
        try { persistPendingFallback(toStore) } catch (e) {}
        reject(r.error)
      }
    })
  } catch (e) { console.warn('idbSetPending failed', e); return false }
}

// Safe wrappers that log issues when IndexedDB operations fail
async function safeIdbGetPending() {
  try {
    const fromIdb = await idbGetPending()
    if (Array.isArray(fromIdb) && fromIdb.length > 0) return fromIdb
    // fallback: check synchronous localStorage copy (helps when a reload interrupted IDB write)
    try {
      if (typeof localStorage !== 'undefined') {
        const raw = localStorage.getItem('orbit:pending_fallback')
        if (raw) {
          try {
            const parsed = JSON.parse(raw)
            if (Array.isArray(parsed) && parsed.length > 0) {
              console.debug('safeIdbGetPending: recovered pending queue from localStorage fallback', parsed.length)
              return parsed
            }
          } catch (e) { /* ignore parse errors */ }
        }
      }
    } catch (e) {}
    return fromIdb || []
  } catch (e) {
    console.warn('safeIdbGetPending failed', e)
    // try localStorage fallback when IDB access fails
    try {
      if (typeof localStorage !== 'undefined') {
        const raw = localStorage.getItem('orbit:pending_fallback')
        if (raw) {
          try { return JSON.parse(raw) } catch (e) { return [] }
        }
      }
    } catch (e) {}
    return []
  }
}
async function safeIdbSetPending(items) {
  try {
    const ok = await idbSetPending(items)
    if (!ok) console.warn('safeIdbSetPending: idbSetPending returned false')
    return ok
  } catch (e) {
    console.warn('safeIdbSetPending failed', e)
    return false
  }
}

// Remove pending item(s) whose transform references `transformId`.
async function removePendingByTransformId(transformId) {
  try {
    if (!transformId) return false
    const prev = Array.isArray(pendingQueue) ? pendingQueue.slice() : []
    const filtered = prev.filter(p => {
      const t = p && (p.transform || (p.item && p.item.transform) || p)
      if (!t) return true
      const ids = []
      try {
        if (t.entry && t.entry.id) ids.push(String(t.entry.id))
      } catch (e) {}
      try {
        if (t.transformId) ids.push(String(t.transformId))
      } catch (e) {}
      try {
        if (t.transform && t.transform.entry && t.transform.entry.id) ids.push(String(t.transform.entry.id))
      } catch (e) {}
      if (ids.some(id => id === String(transformId))) return false
      return true
    })
    if (filtered.length !== prev.length) {
      pendingQueue = filtered
      pendingOps = pendingQueue.length
      try { await safeIdbSetPending(pendingQueue) } catch (e) { console.warn('removePendingByTransformId: failed to persist pending', e) }
      return true
    } else {
      if (pendingOps > 0) pendingOps = Math.max(0, pendingOps - 1)
      return false
    }
  } catch (e) {
    console.warn('removePendingByTransformId failed', e)
    return false
  }
}

async function applyRemoteTransform(transform) {
  // transform: { op: 'create'|'update'|'delete', scheduleId, entry, lastModified }
  if (!transform || typeof transform !== 'object') return
  try { console.debug('applyRemoteTransform: received transform', transform && (transform.op || transform)) } catch (e) {}
  // normalize incoming transform shapes to a canonical form so consumers can rely on structure
  function normalizeTransform(t) {
    if (!t || typeof t !== 'object') return null
    const out = {}
    out.op = t.op || t.operation || t.type || null
    out.scheduleId = t.scheduleId || t.schedule_id || (t.transform && (t.transform.scheduleId || t.transform.schedule_id)) || null
    out.entry = t.entry || t.data || t.payload || (t.transform && (t.transform.entry || t.transform.data)) || null
    // support bulk rows payloads: { rows: { scheduleId: [ ... ] } } or { rows: [...] , scheduleId }
    if (t.rows && typeof t.rows === 'object' && !Array.isArray(t.rows)) {
      // rows is mapping scheduleId -> array
      out.rows = t.rows
    } else if (t.rows && Array.isArray(t.rows)) {
      out.rows = {}
      const sid = out.scheduleId || (Object.keys(out.rows)[0])
      out.rows[out.scheduleId || String(Date.now())] = t.rows.slice()
    }
    // sometimes server sends { scheduleId: [ ...rows... ] }
    if (!out.rows) {
      for (const k in t) {
        if (Object.prototype.hasOwnProperty.call(t, k) && Array.isArray(t[k]) && k.match(/^[0-9a-fA-F\-]{8,}$/)) {
          out.rows = out.rows || {}
          out.rows[k] = t[k].slice()
        }
      }
    }
    return out
  }

  const norm = normalizeTransform(transform)
  if (!norm) return
  const { op, scheduleId, entry, rows } = norm
  // normalize entry assignment arrays to canonical keys so UI mapping works
  if (entry && typeof entry === 'object') {
    try {
      // Prefer the canonical *_ids arrays when present (server may send both empty arrays and *_ids)
      if (Array.isArray(entry.responsible_ids)) {
        entry.responsible = entry.responsible_ids.slice()
        try { console.debug('applyRemoteTransform: normalized responsible_ids -> responsible', entry.responsible.length) } catch (e) {}
      } else if (!Array.isArray(entry.responsible) && Array.isArray(entry.responsible_ids)) {
        entry.responsible = entry.responsible_ids.slice()
        try { console.debug('applyRemoteTransform: normalized responsible_ids -> responsible (fallback)', entry.responsible.length) } catch (e) {}
      }
      if (Array.isArray(entry.devotional_ids)) {
        entry.devotional = entry.devotional_ids.slice()
        try { console.debug('applyRemoteTransform: normalized devotional_ids -> devotional', entry.devotional.length) } catch (e) {}
      } else if (!Array.isArray(entry.devotional) && Array.isArray(entry.devotional_ids)) {
        entry.devotional = entry.devotional_ids.slice()
        try { console.debug('applyRemoteTransform: normalized devotional_ids -> devotional (fallback)', entry.devotional.length) } catch (e) {}
      }
      if (Array.isArray(entry.cant_come_ids)) {
        entry.cant_come = entry.cant_come_ids.slice()
        try { console.debug('applyRemoteTransform: normalized cant_come_ids -> cant_come', entry.cant_come.length) } catch (e) {}
      } else if (!Array.isArray(entry.cant_come) && Array.isArray(entry.cant_come_ids)) {
        entry.cant_come = entry.cant_come_ids.slice()
        try { console.debug('applyRemoteTransform: normalized cant_come_ids -> cant_come (fallback)', entry.cant_come.length) } catch (e) {}
      }
      // normalize start/end datetime fields from legacy `date` when present
      try {
        if (!entry.start && Array.isArray(entry.start) === false) {
          if (entry.start_date) entry.start = entry.start_date
          else if (entry.date) entry.start = `${entry.date}T00:00`
        }
        if (!entry.end && Array.isArray(entry.end) === false) {
          if (entry.end_date) entry.end = entry.end_date
          else if (entry.date) entry.end = `${entry.date}T23:59`
        }
      } catch (e) {}
    } catch (e) { console.warn('applyRemoteTransform: failed to normalize entry assignment fields', e) }
  }
  // if transform contained bulk rows, delegate to setLocalEntries for proper normalization/persist
  if (rows && typeof rows === 'object') {
    try {
      for (const sid of Object.keys(rows)) {
        const prepared = Array.isArray(rows[sid]) ? rows[sid].map(r => {
          return Object.assign({}, r, {
            responsible: Array.isArray(r.responsible_ids) ? r.responsible_ids.slice() : (Array.isArray(r.responsible) ? r.responsible : []),
            devotional: Array.isArray(r.devotional_ids) ? r.devotional_ids.slice() : (Array.isArray(r.devotional) ? r.devotional : []),
            cant_come: Array.isArray(r.cant_come_ids) ? r.cant_come_ids.slice() : (Array.isArray(r.cant_come) ? r.cant_come : []),
          })
        }) : []
        // normalize start/end datetimes for prepared rows
        const preparedWithDates = prepared.map(p => Object.assign({}, p, {
          start: p.start || p.start_date || (p.date ? `${p.date}T00:00` : null),
          end: p.end || p.end_date || (p.date ? `${p.date}T23:59` : null),
          date: p.date || (p.start ? String(p.start).split('T')[0] : null),
        }))
        try {
          try { console.debug('applyRemoteTransform: bulk rows prepared (showing id,start,end,date):', preparedWithDates.map(x => ({ id: x.id, start: x.start, end: x.end, date: x.date }))) } catch (e) {}
        } catch (e) {}
        await setLocalEntries(sid, preparedWithDates)
      }
    } catch (e) { console.warn('applyRemoteTransform: failed to apply bulk rows', e) }
    return
  }
  if (!scheduleId) return
  try {
    // load current rows into memory (or from IDB)
    if (!memoryStore[scheduleId]) {
      const fromIdb = await idbGet(scheduleId)
      memoryStore[scheduleId] = Array.isArray(fromIdb) ? fromIdb : []
    }
    const rows = memoryStore[scheduleId]
      if (op === 'create') {
        // avoid duplicates by id (string-safe comparison)
        if (!rows.find(r => String(r.id) === String(entry.id))) rows.push(entry)
    } else if (op === 'update') {
      const idx = rows.findIndex(r => String(r.id) === String(entry.id))
      if (idx === -1) {
        rows.push(entry)
      } else {
        // merge using lastModified when available; be conservative when incoming lacks timestamps
        const existing = rows[idx]
        const existingTs = (existing && existing.lastModified) ? Number(existing.lastModified) || 0 : 0
        const incomingTs = (entry && entry.lastModified) ? Number(entry.lastModified) || 0 : 0
        try {
          if (incomingTs === 0 && existingTs > 0) {
            // incoming has no timestamp but we have a local edit -> prefer local, but merge authoritative assignment arrays if present
            const updated = Object.assign({}, existing)
            try {
              if (Array.isArray(entry.responsible_ids)) updated.responsible = entry.responsible_ids.slice()
              if (Array.isArray(entry.devotional_ids)) updated.devotional = entry.devotional_ids.slice()
              if (Array.isArray(entry.cant_come_ids)) updated.cant_come = entry.cant_come_ids.slice()
            } catch (e) {}
            rows[idx] = updated
          } else if (incomingTs >= existingTs) {
            // incoming is newer (or both zero) -> apply shallow merge with incoming taking precedence
            rows[idx] = Object.assign({}, existing, entry)
          } else {
            // existing is newer -> ignore incoming update
          }
        } catch (e) {
          // fallback to shallow merge on unexpected errors
          rows[idx] = Object.assign({}, existing, entry)
        }
      }
    } else if (op === 'delete') {
      memoryStore[scheduleId] = rows.filter(r => String(r.id) !== String(entry.id))
    }
    // persist merged state
    await idbSet(scheduleId, memoryStore[scheduleId])
    try { console.debug('applyRemoteTransform: applied', op, 'for schedule', scheduleId, 'entry', entry && entry.id, 'rows', (memoryStore[scheduleId] || []).length) } catch (e) {}
    try {
      // dump the updated entry for deeper inspection (including start/end/date)
      const updated = (memoryStore[scheduleId] || []).find(r => r && String(r.id) === String(entry && entry.id))
      if (updated) {
        try { console.debug('applyRemoteTransform: updated entry after apply', { id: updated.id, start: updated.start, end: updated.end, date: updated.date, responsible: updated.responsible, responsible_ids: updated.responsible_ids, devotional: updated.devotional, devotional_ids: updated.devotional_ids, cant_come: updated.cant_come, cant_come_ids: updated.cant_come_ids }) } catch (e) {}
      }
    } catch (e) {}
    // notify subscribers (log each invocation to help trace cross-tab delivery)
    subs.forEach((s, i) => {
      try {
        try { console.debug('applyRemoteTransform: invoking subscriber', i, 'schedule', scheduleId, 'rows', (memoryStore[scheduleId] || []).length) } catch (e) {}
        s(scheduleId, (memoryStore[scheduleId] || []).slice())
      } catch (e) {
        console.warn('applyRemoteTransform: subscriber callback threw', e)
      }
    })
    // emit a DOM event so UI components can listen reliably
    try {
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
        const detail = { scheduleId, rows: (memoryStore[scheduleId] || []).slice(), transform }
        window.dispatchEvent(new CustomEvent('orbit:transform', { detail }))
      }
    } catch (e) {}
  } catch (e) {
    console.warn('applyRemoteTransform failed', e)
  }
}

async function getEntries(scheduleId) {
  ensureInitialized()
  if (memoryStore[scheduleId]) return memoryStore[scheduleId].slice()
  const fromIdb = await idbGet(scheduleId)
  const rows = Array.isArray(fromIdb) ? fromIdb : []
  memoryStore[scheduleId] = rows.slice()
  return rows
}

// Set local entries without broadcasting transforms (bootstrap from server)
async function setLocalEntries(scheduleId, entries) {
  ensureInitialized()
  try {
    const serverRows = Array.isArray(entries) ? entries.slice() : []
    // preserve any locally-created unsynced entries (ids starting with 'local-')
    let existing = memoryStore[scheduleId]
    if (!existing) {
      try { existing = await idbGet(scheduleId) } catch (e) { existing = [] }
    }
    // Also preserve any entries that have pending transforms (updates/creates)
    // so that a subsequent bootstrap from server rows doesn't clobber local edits
    const pendingEntryIds = new Set()
    try {
      // include persisted pending transforms from IDB (or fallback)
      const persistedPending = await safeIdbGetPending().catch(() => [])
      for (const p of (persistedPending || [])) {
        try {
          const t = (p && p.transform) ? p.transform : (p && p.item && p.item.transform ? p.item.transform : null)
          if (t && String(t.scheduleId) === String(scheduleId) && t.entry && t.entry.id) pendingEntryIds.add(String(t.entry.id))
        } catch (e) {}
      }
      // include any in-memory queued pending transforms
      for (const p of (pendingQueue || [])) {
        try {
          const t = (p && p.transform) ? p.transform : (p && p.item && p.item.transform ? p.item.transform : null)
          if (t && String(t.scheduleId) === String(scheduleId) && t.entry && t.entry.id) pendingEntryIds.add(String(t.entry.id))
        } catch (e) {}
      }
    } catch (e) {}

    // Merge server rows with local memory carefully:
    // - If a local entry has a newer `lastModified` than the server-provided row, prefer local.
    // - Always preserve locally-created `local-*` rows and any rows with pending transforms.
    const mergedMap = new Map()
    // First, add server rows but allow local to override when newer
    for (const sr of serverRows) {
      try {
        const id = String(sr && sr.id)
        let chosen = sr
        const local = Array.isArray(existing) ? existing.find(r => r && String(r.id) === id) : null
        if (local && local.lastModified) {
          const localTs = Number(local.lastModified) || 0
          const serverTs = (sr && sr.lastModified) ? Number(sr.lastModified) || 0 : 0
          if (localTs > serverTs) chosen = Object.assign({}, local)
        }
        mergedMap.set(id, chosen)
      } catch (e) { try { mergedMap.set(String((sr && sr.id) || Date.now()), sr) } catch (er) {} }
    }

    // Then, ensure any existing local-only entries are preserved (local- ids, pending, or locally-modified)
    for (const local of (Array.isArray(existing) ? existing : [])) {
      try {
        const id = String(local && local.id)
        if (!mergedMap.has(id)) {
          if (id.startsWith('local-') || pendingEntryIds.has(id) || (local.lastModified && Number(local.lastModified) > 0)) {
            mergedMap.set(id, Object.assign({}, local))
          }
        }
      } catch (e) {}
    }

    const merged = Array.from(mergedMap.values())
    memoryStore[scheduleId] = merged.slice()
    await idbSet(scheduleId, memoryStore[scheduleId])
    try { console.debug('setLocalEntries: persisted merged rows (id,start,end,date):', (memoryStore[scheduleId] || []).map(r => ({ id: r.id, start: r.start, end: r.end, date: r.date }))) } catch (e) {}
    // notify subscribers (log each invocation)
    subs.forEach((s, i) => {
      try {
        try { console.debug('setLocalEntries: invoking subscriber', i, 'schedule', scheduleId, 'rows', (memoryStore[scheduleId] || []).length) } catch (e) {}
        s(scheduleId, memoryStore[scheduleId].slice())
      } catch (e) {
        console.warn('setLocalEntries: subscriber callback threw', e)
      }
    })
    // emit a DOM event for consistency with applyRemoteTransform
    try {
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
        const detail = { scheduleId, rows: (memoryStore[scheduleId] || []).slice(), source: 'bootstrap' }
        window.dispatchEvent(new CustomEvent('orbit:transform', { detail }))
      }
    } catch (e) {}
    return true
  } catch (e) {
    console.warn('setLocalEntries failed', e)
    return false
  }
}

// Bootstrap/prefetch all schedules+entries for an organization into local store
async function syncOrganization(orgId) {
  ensureInitialized()
  if (!orgId) return false
  try {
    // Short wait or best-effort flush to avoid race where we immediately
    // bootstrap server rows that overwrite local pending edits. If there
    // are pending transforms, try a short flush when WS is open, otherwise
    // wait briefly to give reconnect loop a chance to run.
    try {
      const hasPending = (pendingOps > 0) || (Array.isArray(pendingQueue) && pendingQueue.length > 0)
      if (hasPending) {
        if (orbit && orbit.ws && orbit.ws.readyState === WebSocket.OPEN) {
          try {
            await Promise.race([attemptFlushPendingShort(800), new Promise(r => setTimeout(r, 800))])
            // allow a small grace for ack processing
            await new Promise(r => setTimeout(r, 300))
          } catch (e) {}
        } else {
          // not connected: small grace period for reconnect attempts
          await new Promise(r => setTimeout(r, 600))
        }
      }
    } catch (e) {}
    const api = apiClient()
    if (!api) return false
    // fetch schedules for org
    const resp = await api.get('schedules', { params: { organization_id: orgId } })
    const schedules = (resp && resp.data && resp.data.data) || []
      // parallelize fetching entries with limited concurrency and support cancellation
      const concurrency = 3
      // abort any previous in-progress sync
      try { if (orbit._syncController && typeof orbit._syncController.abort === 'function') orbit._syncController.abort() } catch (e) {}
      const controller = (typeof AbortController !== 'undefined') ? new AbortController() : null
      orbit._syncController = controller
      if (!orbit.syncProgress) orbit.syncProgress = { total: schedules.length, done: 0 }
      else orbit.syncProgress.total = schedules.length
      if (!orbit.syncedSchedules) orbit.syncedSchedules = {}
      if (!orbit.syncErrors) orbit.syncErrors = {}
      const queue = schedules.slice()
      const workers = []
      const doWork = async () => {
        while (queue.length) {
          const s = queue.shift()
          const sid = s && s.id
          if (!sid) {
            try { orbit.syncProgress.done = (orbit.syncProgress.done || 0) + 1 } catch (e) {}
            continue
          }
          // skip if recently synced
          try {
            const prev = orbit.syncedSchedules[sid]
            if (prev && (Date.now() - prev) < 5 * 60 * 1000) {
              orbit.syncProgress.done = (orbit.syncProgress.done || 0) + 1
              continue
            }
          } catch (e) {}
          try {
            const opt = controller ? { signal: controller.signal } : {}
            const entriesResp = await api.get(`schedules/${sid}/entries`, opt)
            const serverRows = (entriesResp && entriesResp.data && entriesResp.data.data) ? entriesResp.data.data.map(entry => ({
              id: entry.id,
              date: entry.date,
              start: entry.start || (entry.date ? `${entry.date}T00:00` : null),
              end: entry.end || (entry.date ? `${entry.date}T23:59` : null),
              name: entry.name,
              description: entry.description,
              responsible: Array.isArray(entry.responsible_ids) ? entry.responsible_ids : [],
              devotional: Array.isArray(entry.devotional_ids) ? entry.devotional_ids : [],
              cant_come: Array.isArray(entry.cant_come_ids) ? entry.cant_come_ids : [],
              notes: entry.notes,
              public_event: entry.public_event,
            })) : []
            await setLocalEntries(sid, serverRows)
            orbit.syncedSchedules[sid] = Date.now()
          } catch (e) {
            // record error but avoid flooding console
            try { orbit.syncErrors[sid] = (e && e.message) ? e.message : String(e) } catch (er) {}
            console.debug('syncOrganization: failed to fetch entries for schedule', sid)
          }
          try { orbit.syncProgress.done = (orbit.syncProgress.done || 0) + 1 } catch (e) {}
        }
      }
      for (let i = 0; i < concurrency; i++) workers.push(doWork())
      try { await Promise.all(workers) } catch (e) { /* swallow to avoid noisy logs */ }
      // clear controller when done
      try { if (orbit._syncController === controller) orbit._syncController = null } catch (e) {}
    // mark org as synced
    try {
      if (!orbit.syncedOrgs) orbit.syncedOrgs = {}
      orbit.syncedOrgs[String(orgId)] = Date.now()
      // also publish syncProgress timestamp under orbit for consumers
      try { orbit.syncProgress = orbit.syncProgress || { total: schedules.length, done: schedules.length } } catch (e) {}
    } catch (e) {}
    return true
  } catch (e) {
    console.warn('syncOrganization failed', e)
    return false
  }
}

function getSyncProgress() {
  try {
    const sp = orbit.syncProgress || { total: 0, done: 0 }
    return { total: sp.total || 0, done: sp.done || 0 }
  } catch (e) { return { total: 0, done: 0 } }
}

async function createEntry(scheduleId, entry) {
  ensureInitialized()
  const toCreate = Object.assign({}, entry)
  if (!toCreate.id) toCreate.id = `local-${Date.now()}-${Math.random().toString(36).slice(2,8)}`
  toCreate.lastModified = Date.now()
  const rows = await getEntries(scheduleId)
  rows.push(toCreate)
  memoryStore[scheduleId] = rows.slice()
  await idbSet(scheduleId, memoryStore[scheduleId])
  // broadcast transform
  if (orbit && orbit.ws && orbit.ws.readyState === WebSocket.OPEN) {
    const payload = { type: 'transform', transform: { op: 'create', scheduleId, entry: toCreate } }
    try {
      ensureTransformMetadata(payload)
      console.debug('Orbit WS sending create transform', scheduleId, toCreate && toCreate.id, 'transformId', payload.transform && payload.transform.transformId)
      orbit.ws.send(JSON.stringify(payload))
      lastSentTs = Date.now()
      pendingOps = pendingOps + 1
    } catch (e) {
      console.warn('Orbit WS send failed, queuing', e)
      const msg = payload
      // ensure metadata on queued copy as well
      try { ensureTransformMetadata(msg) } catch (er) {}
      pendingQueue.push(msg)
      pendingOps = pendingQueue.length
      const ok1b = await safeIdbSetPending(pendingQueue)
      if (!ok1b) console.warn('createEntry: failed to persist pending queue after send failure')
    }
  } else {
    // queue transform for later delivery
    const msg = { type: 'transform', transform: { op: 'create', scheduleId, entry: toCreate } }
    try { ensureTransformMetadata(msg) } catch (e) {}
    pendingQueue.push(msg)
    pendingOps = pendingQueue.length
    try { persistPendingFallback(pendingQueue) } catch (e) {}
    console.debug('createEntry: queued pending transform', scheduleId, toCreate && toCreate.id, 'transformId', msg.transform && msg.transform.transformId)
    const ok1 = await safeIdbSetPending(pendingQueue)
    if (!ok1) console.warn('createEntry: failed to persist pending queue')
  }
  // broadcast to other tabs via localStorage as a fast-fallback
  try {
    if (typeof localStorage !== 'undefined') {
      const payload = { ts: Date.now(), item: { type: 'transform', transform: { op: 'create', scheduleId, entry: toCreate } } }
      console.debug('createEntry: broadcasting orbit:transform via localStorage', payload.item.transform && payload.item.transform.scheduleId)
      localStorage.setItem('orbit:transform', JSON.stringify(payload))
    }
  } catch (e) { console.warn('createEntry: failed to broadcast via localStorage', e) }
  subs.forEach(s => { try { s(scheduleId, memoryStore[scheduleId].slice()) } catch (e) {} })
  return toCreate
}

async function updateEntry(scheduleId, entry) {
  ensureInitialized()
  const rows = await getEntries(scheduleId)
  const idx = rows.findIndex(r => r.id === entry.id)
  const now = Date.now()
  const toUpdate = Object.assign({}, rows[idx] || {}, entry, { lastModified: now })
  // If the caller explicitly provided canonical id arrays (even empty),
  // prefer those over any stale `responsible`/`devotional` values from memoryStore.
  try {
    if (entry && Object.prototype.hasOwnProperty.call(entry, 'responsible_ids')) {
      toUpdate.responsible = Array.isArray(entry.responsible_ids) ? entry.responsible_ids.slice() : []
      try { console.debug('updateEntry: overriding responsible from entry.responsible_ids', toUpdate.responsible.length) } catch (e) {}
    }
    if (entry && Object.prototype.hasOwnProperty.call(entry, 'devotional_ids')) {
      toUpdate.devotional = Array.isArray(entry.devotional_ids) ? entry.devotional_ids.slice() : []
      try { console.debug('updateEntry: overriding devotional from entry.devotional_ids', toUpdate.devotional.length) } catch (e) {}
    }
    if (entry && Object.prototype.hasOwnProperty.call(entry, 'cant_come_ids')) {
      toUpdate.cant_come = Array.isArray(entry.cant_come_ids) ? entry.cant_come_ids.slice() : []
      try { console.debug('updateEntry: overriding cant_come from entry.cant_come_ids', toUpdate.cant_come.length) } catch (e) {}
    }
  } catch (e) {}
    if (idx === -1) {
      rows.push(toUpdate)
      console.debug('updateEntry: queued pending transform', scheduleId, toUpdate && toUpdate.id)
      const ok1 = await safeIdbSetPending(pendingQueue)
      if (!ok1) console.warn('updateEntry: failed to persist pending queue')
    }
  else rows[idx] = toUpdate
  memoryStore[scheduleId] = rows.slice()
  await idbSet(scheduleId, memoryStore[scheduleId])
  // Persist update to server via REST when possible (ensures assignments are saved)
  try {
    const api = apiClient()
    if (api && toUpdate && typeof toUpdate.id === 'string' && !toUpdate.id.startsWith('local-')) {
      const extractIdsFromArr = (arr) => {
        if (!Array.isArray(arr)) return []
        return arr.map(a => (a && (a.value || a.id)) || a).filter(Boolean)
      }

      // Prefer explicit fields from the caller `entry` argument.
      // If the caller provided `responsible_ids` (even an empty array), honor it and
      // use that for the REST payload. Fallback order:
      // 1. entry.responsible_ids (own property)
      // 2. entry.responsible (own property)
      // 3. toUpdate.responsible (merged memory)
      // 4. toUpdate.responsible_ids
      const pickIds = (fieldBase) => {
        const idsKey = `${fieldBase}_ids`
        try {
          if (entry && Object.prototype.hasOwnProperty.call(entry, idsKey)) return extractIdsFromArr(entry[idsKey])
          if (entry && Object.prototype.hasOwnProperty.call(entry, fieldBase)) return extractIdsFromArr(entry[fieldBase])
          if (toUpdate && Array.isArray(toUpdate[fieldBase]) && toUpdate[fieldBase].length > 0) return extractIdsFromArr(toUpdate[fieldBase])
          return extractIdsFromArr(toUpdate[idsKey])
        } catch (e) { return [] }
      }

      const responsible_ids = pickIds('responsible')
      const devotional_ids = pickIds('devotional')
      const cant_come_ids = pickIds('cant_come')

      // ensure toUpdate carries the canonical id-arrays so WS transforms include them too
      try { toUpdate.responsible_ids = responsible_ids } catch (e) {}
      try { toUpdate.devotional_ids = devotional_ids } catch (e) {}
      try { toUpdate.cant_come_ids = cant_come_ids } catch (e) {}

      const payload = {
        // include start/end datetimes when available; keep legacy `date` for fallback
        start: toUpdate.start || toUpdate.start_date || (toUpdate.date ? `${toUpdate.date}T00:00` : null),
        end: toUpdate.end || toUpdate.end_date || (toUpdate.date ? `${toUpdate.date}T23:59` : null),
        date: toUpdate.date || (toUpdate.start ? String(toUpdate.start).split('T')[0] : null),
        name: toUpdate.name,
        description: toUpdate.description || '',
        notes: toUpdate.notes || '',
        public_event: !!toUpdate.public_event,
        responsible_ids: responsible_ids,
        devotional_ids: devotional_ids,
        cant_come_ids: cant_come_ids,
      }
      try {
        console.debug('updateEntry: REST PATCH payload', payload, 'entryId', toUpdate.id)
        const resp = await api.patch(`entries/${toUpdate.id}`, payload)
        console.debug('updateEntry: REST PATCH resp', resp && resp.data)
        // If server returned authoritative assignment arrays, merge them into local store
        try {
          const serverEntry = resp && resp.data && resp.data.data ? resp.data.data : null
          if (serverEntry) {
            // update the toUpdate object with authoritative arrays when available
            if (Array.isArray(serverEntry.responsible_ids)) {
              toUpdate.responsible_ids = serverEntry.responsible_ids.slice()
              toUpdate.responsible = serverEntry.responsible_ids.slice()
            }
            if (Array.isArray(serverEntry.devotional_ids)) {
              toUpdate.devotional_ids = serverEntry.devotional_ids.slice()
              toUpdate.devotional = serverEntry.devotional_ids.slice()
            }
            if (Array.isArray(serverEntry.cant_come_ids)) {
              toUpdate.cant_come_ids = serverEntry.cant_come_ids.slice()
              toUpdate.cant_come = serverEntry.cant_come_ids.slice()
            }
            // persist merged state and notify subscribers so UI updates immediately
            try {
              if (memoryStore[scheduleId]) {
                const idx = memoryStore[scheduleId].findIndex(r => r && String(r.id) === String(toUpdate.id))
                if (idx !== -1) memoryStore[scheduleId][idx] = Object.assign({}, memoryStore[scheduleId][idx], toUpdate)
                else memoryStore[scheduleId].push(toUpdate)
                await idbSet(scheduleId, memoryStore[scheduleId])
                try { console.debug('updateEntry: merged server response into memoryStore for', toUpdate.id) } catch (e) {}
                // notify subscribers and emit orbit:transform event
                subs.forEach((s) => { try { s(scheduleId, memoryStore[scheduleId].slice()) } catch (e) {} })
                try { if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') window.dispatchEvent(new CustomEvent('orbit:transform', { detail: { scheduleId, rows: memoryStore[scheduleId].slice(), source: 'server-patch' } })) } catch (e) {}
              }
            } catch (e) { console.warn('updateEntry: failed to persist server-merged entry', e) }
          }
        } catch (e) { console.warn('updateEntry: error merging server response', e) }
      } catch (e) {
        // server update failed; leave transform/queue handling to WS/flushPending
        console.debug('updateEntry: server PATCH failed, will rely on WS/flushPending', e)
      }
    }
  } catch (e) {}
  try {
    try { console.debug('updateEntry: toUpdate preview', { id: toUpdate.id, responsible: toUpdate.responsible, responsible_ids: toUpdate.responsible_ids, devotional: toUpdate.devotional, devotional_ids: toUpdate.devotional_ids, cant_come: toUpdate.cant_come, cant_come_ids: toUpdate.cant_come_ids }) } catch (e) {}
  } catch (e) {}
  if (orbit && orbit.ws && orbit.ws.readyState === WebSocket.OPEN) {
    const payload = { type: 'transform', transform: { op: 'update', scheduleId, entry: toUpdate } }
    try {
      ensureTransformMetadata(payload)
      console.debug('Orbit WS sending update transform', scheduleId, toUpdate && toUpdate.id, 'transformId', payload.transform && payload.transform.transformId)
      orbit.ws.send(JSON.stringify(payload))
      lastSentTs = Date.now()
      pendingOps = pendingOps + 1
    } catch (e) {
      console.warn('Orbit WS send failed for update, queuing', e)
      const msg = payload
      try { ensureTransformMetadata(msg) } catch (er) {}
      pendingQueue.push(msg)
      pendingOps = pendingQueue.length
      const ok2b = await safeIdbSetPending(pendingQueue)
      if (!ok2b) console.warn('updateEntry: failed to persist pending queue after send failure')
    }
  } else {
    const msg = { type: 'transform', transform: { op: 'update', scheduleId, entry: toUpdate } }
    try { ensureTransformMetadata(msg) } catch (e) {}
    pendingQueue.push(msg)
    pendingOps = pendingQueue.length
    try { persistPendingFallback(pendingQueue) } catch (e) {}
    console.debug('updateEntry: queued pending transform', scheduleId, toUpdate && toUpdate.id, 'transformId', msg.transform && msg.transform.transformId)
    const ok2 = await safeIdbSetPending(pendingQueue)
    if (!ok2) console.warn('updateEntry: failed to persist pending queue')
  }
  try {
    if (typeof localStorage !== 'undefined') {
      const payload = { ts: Date.now(), item: { type: 'transform', transform: { op: 'update', scheduleId, entry: toUpdate } } }
      console.debug('updateEntry: broadcasting orbit:transform via localStorage', payload.item.transform && payload.item.transform.scheduleId)
      localStorage.setItem('orbit:transform', JSON.stringify(payload))
    }
  } catch (e) { console.warn('updateEntry: failed to broadcast via localStorage', e) }
  subs.forEach(s => { try { s(scheduleId, memoryStore[scheduleId].slice()) } catch (e) {} })
  return toUpdate
}

async function deleteEntry(scheduleId, entryId) {
  ensureInitialized()
  const rows = await getEntries(scheduleId)
  const updated = rows.filter(r => r.id !== entryId)
  memoryStore[scheduleId] = updated.slice()
  await idbSet(scheduleId, memoryStore[scheduleId])
  // Attempt to remove from server via REST as a best-effort fallback so deleted
  // items aren't reintroduced when bootstrapping from server rows.
  try {
    const api = apiClient()
    if (api && entryId && typeof entryId === 'string' && !entryId.startsWith('local-')) {
      try {
        await api.delete(`entries/${entryId}`)
        try { console.debug('deleteEntry: REST DELETE succeeded for', entryId) } catch (e) {}
      } catch (e) {
        console.warn('deleteEntry: REST DELETE failed for', entryId, e)
      }
    }
  } catch (e) { console.warn('deleteEntry: apiClient check failed', e) }
  if (orbit && orbit.ws && orbit.ws.readyState === WebSocket.OPEN) {
    const payload = { type: 'transform', transform: { op: 'delete', scheduleId, entry: { id: entryId } } }
    try {
          // broadcast to other tabs via localStorage and BroadcastChannel as fast-fallback
          try {
            const payload = { ts: Date.now(), item: { type: 'transform', transform: { op: 'update', scheduleId, entry: toUpdate } } }
            if (typeof localStorage !== 'undefined') localStorage.setItem('orbit:transform', JSON.stringify(payload))
            if (typeof window !== 'undefined' && orbit && orbit._bc && typeof orbit._bc.postMessage === 'function') {
              try { orbit._bc.postMessage(payload) } catch (e) { console.warn('BroadcastChannel postMessage failed', e) }
            }
          } catch (e) {}
      try { ensureTransformMetadata(payload) } catch (e) {}
      console.debug('Orbit WS sending delete transform', scheduleId, entryId, 'transformId', payload.transform && payload.transform.transformId)
      orbit.ws.send(JSON.stringify(payload))
      lastSentTs = Date.now()
      pendingOps = pendingOps + 1
    } catch (e) {
      console.warn('Orbit WS send failed for delete, queuing', e)
      try { ensureTransformMetadata(payload) } catch (er) {}
      pendingQueue.push(payload)
      pendingOps = pendingQueue.length
      const ok3b = await safeIdbSetPending(pendingQueue)
      if (!ok3b) console.warn('deleteEntry: failed to persist pending queue after send failure')
    }
  } else {
    const msg = { type: 'transform', transform: { op: 'delete', scheduleId, entry: { id: entryId } } }
    try { ensureTransformMetadata(msg) } catch (e) {}
    pendingQueue.push(msg)
    pendingOps = pendingQueue.length
    try { persistPendingFallback(pendingQueue) } catch (e) {}
    console.debug('deleteEntry: queued pending transform', scheduleId, entryId, 'transformId', msg.transform && msg.transform.transformId)
    const ok3 = await safeIdbSetPending(pendingQueue)
    if (!ok3) console.warn('deleteEntry: failed to persist pending queue')
  }
  try {
    if (typeof localStorage !== 'undefined') {
      const payload = { ts: Date.now(), item: { type: 'transform', transform: { op: 'delete', scheduleId, entry: { id: entryId } } } }
      console.debug('deleteEntry: broadcasting orbit:transform via localStorage', payload.item.transform && payload.item.transform.scheduleId)
      localStorage.setItem('orbit:transform', JSON.stringify(payload))
    }
  } catch (e) { console.warn('deleteEntry: failed to broadcast via localStorage', e) }
  subs.forEach(s => { try { s(scheduleId, memoryStore[scheduleId].slice()) } catch (e) {} })
  return true
}

function subscribe(scheduleId, cb) {
  try {
    if (!subs.includes(cb)) {
      subs.push(cb)
      try { console.debug('subscribe: added subscriber, total:', subs.length) } catch (e) {}
    } else {
      try { console.debug('subscribe: subscriber already present') } catch (e) {}
    }
  } catch (e) {}
  // immediately call with current data and log the immediate invocation
  getEntries(scheduleId).then(rows => {
    try { console.debug('subscribe: invoking immediate callback for schedule', scheduleId, 'rows', (rows || []).length) } catch (e) {}
    try { cb(scheduleId, rows.slice()) } catch (e) { console.warn('subscribe: immediate callback threw', e) }
  }).catch(() => {
    try { console.debug('subscribe: immediate callback failed, calling with empty array') } catch (e) {}
    try { cb(scheduleId, []) } catch (e) { console.warn('subscribe: immediate callback threw on error path', e) }
  })
}

function unsubscribe(cb) {
  subs = subs.filter(s => s !== cb)
}

// Developer helper: return local in-memory + persisted entries for a schedule
async function getLocalEntries(scheduleId) {
  try {
    const mem = memoryStore[scheduleId] ? memoryStore[scheduleId].slice() : []
    const persisted = await idbGet(scheduleId)
    return { memory: mem, persisted: Array.isArray(persisted) ? persisted : [] }
  } catch (e) {
    console.warn('getLocalEntries failed', e)
    return { memory: memoryStore[scheduleId] || [], persisted: [] }
  }
}

export default {
  init,
  connectWebsocket,
  getEntries,
  setLocalEntries,
  syncOrganization,
  getSyncProgress,
  createEntry,
  updateEntry,
  deleteEntry,
  subscribe,
  unsubscribe,
  // telemetry
  getSyncStatus: () => {
    const now = Date.now()
    let crossTab = false
    try {
      const v = typeof localStorage !== 'undefined' ? localStorage.getItem('orbit:connected') : null
      if (v) {
        const ts = parseInt(v, 10)
        if (!isNaN(ts) && (now - ts) < 15000) crossTab = true
      }
    } catch (e) {
      crossTab = false
    }
    // include any tracked org sync timestamps and progress
    const syncedOrgs = (orbit && orbit.syncedOrgs) ? Object.assign({}, orbit.syncedOrgs) : {}
    const syncProgress = (orbit && orbit.syncProgress) ? Object.assign({}, orbit.syncProgress) : { total: 0, done: 0 }
    return { connected, crossTabConnected: crossTab, lastSentTs, lastReceivedTs, pendingOps, lastError, syncedOrgs, syncProgress }
  },
  // developer helpers for pending queue
  getPendingQueue: async () => {
    try {
      const persisted = await safeIdbGetPending().catch(() => []) || []
      const mem = Array.isArray(pendingQueue) ? pendingQueue.slice() : []
      const out = []
      const seen = new Set()
      const extractId = (p) => {
        try {
          const t = p && (p.transform || (p.item && p.item.transform) || p)
          if (!t) return null
          if (t.transformId) return String(t.transformId)
          if (t.entry && t.entry.id) return String(t.entry.id)
        } catch (e) {}
        try { return JSON.stringify(p) } catch (e) { return null }
      }
      for (const p of persisted) {
        const id = extractId(p)
        if (id) seen.add(id)
        out.push(p)
      }
      for (const p of mem) {
        const id = extractId(p)
        if (!id || !seen.has(id)) {
          out.push(p)
          if (id) seen.add(id)
        }
      }
      return out
    } catch (e) { return pendingQueue.slice() }
  },
  flushPending: async () => {
    // attempt to send persisted pending queue via websocket; returns remaining count
    try {
      if (!orbit || !orbit.ws || orbit.ws.readyState !== WebSocket.OPEN) throw new Error('Websocket not open')
      const q = (await safeIdbGetPending()) || []
      // Ensure persisted pending items have transformId/lastModified metadata
      try {
        let metaModified = false
        for (let i = 0; i < q.length; i++) {
          try {
            const item = q[i]
            const t = item && (item.transform || (item.item && item.item.transform) || item)
            const hadId = Boolean(t && t.transformId)
            const hadLm = Boolean(t && t.entry && t.entry.lastModified)
            ensureTransformMetadata(item)
            const t2 = item && (item.transform || (item.item && item.item.transform) || item)
            const hasId = Boolean(t2 && t2.transformId)
            const hasLm = Boolean(t2 && t2.entry && t2.entry.lastModified)
            if ((!hadId && hasId) || (!hadLm && hasLm)) metaModified = true
          } catch (e) {}
        }
        if (metaModified) {
          try { await safeIdbSetPending(q) } catch (e) { console.warn('flushPending: failed to persist metadata-updated queue', e) }
        }
      } catch (e) {}
      // reconciliation step: POST any create ops with local-* ids to the server to get canonical ids
      let modified = false
      try {
        const api = apiClient()
        const extractIds = (arr) => {
          if (!Array.isArray(arr)) return []
          return arr.map(a => (a && (a.value || a.id)) || a).filter(Boolean)
        }
        for (let i = 0; i < q.length; i++) {
          const item = q[i]
          try {
            if (item && item.type === 'transform' && item.transform && item.transform.op === 'create') {
              const t = item.transform
              const scheduleId = t.scheduleId || t.schedule_id || (t.entry && t.entry.scheduleId)
              const entry = t.entry || {}
              if (entry && typeof entry.id === 'string' && entry.id.startsWith('local-') && scheduleId) {
                // build server payload
                const payload = {
                  date: entry.date,
                  name: entry.name,
                  description: entry.description || '',
                  notes: entry.notes || '',
                  public_event: !!entry.public_event,
                  responsible_ids: extractIds(entry.responsible || entry.responsible_ids),
                  devotional_ids: extractIds(entry.devotional || entry.devotional_ids),
                  cant_come_ids: extractIds(entry.cant_come || entry.cant_come_ids),
                }
                try {
                  const resp = await api.post(`schedules/${scheduleId}/entries`, payload)
                  const serverEntry = resp && resp.data && resp.data.data ? resp.data.data : null
                  if (serverEntry && serverEntry.id) {
                    const oldId = entry.id
                    const newId = serverEntry.id
                    // update memoryStore
                    if (memoryStore && memoryStore[scheduleId]) {
                      for (let j = 0; j < memoryStore[scheduleId].length; j++) {
                        if (memoryStore[scheduleId][j] && String(memoryStore[scheduleId][j].id) === String(oldId)) {
                          memoryStore[scheduleId][j] = Object.assign({}, memoryStore[scheduleId][j], { id: newId })
                        }
                      }
                      try { await idbSet(scheduleId, memoryStore[scheduleId]) } catch (e) { console.warn('idbSet after reconciliation failed', e) }
                    }
                    // replace ids in pending queue entries
                    for (let k = 0; k < q.length; k++) {
                      const qi = q[k]
                      try {
                        if (qi && qi.type === 'transform' && qi.transform && qi.transform.entry) {
                          const ent = qi.transform.entry
                          if (ent.id === oldId) {
                            ent.id = newId
                            modified = true
                          }
                        }
                      } catch (e) {}
                    }
                    modified = true
                  }
                } catch (e) {
                  // if server create fails, skip and leave item queued
                  console.warn('Reconciliation POST failed for local entry', entry.id, e)
                }
              }
            } else if (item && item.type === 'transform' && item.transform && item.transform.rows && typeof item.transform.rows === 'object') {
              // Handle bulk transforms that include a rows mapping: scheduleId -> [entries]
              try {
                const rowsMap = item.transform.rows
                for (const sid of Object.keys(rowsMap)) {
                  const rowArr = Array.isArray(rowsMap[sid]) ? rowsMap[sid] : []
                  for (const entry of rowArr) {
                    try {
                      if (entry && typeof entry.id === 'string' && entry.id.startsWith('local-')) {
                        // build server payload
                        const payload = {
                          date: entry.date,
                          name: entry.name,
                          description: entry.description || '',
                          notes: entry.notes || '',
                          public_event: !!entry.public_event,
                          responsible_ids: extractIds(entry.responsible || entry.responsible_ids),
                          devotional_ids: extractIds(entry.devotional || entry.devotional_ids),
                          cant_come_ids: extractIds(entry.cant_come || entry.cant_come_ids),
                        }
                        try {
                          const resp = await api.post(`schedules/${sid}/entries`, payload)
                          const serverEntry = resp && resp.data && resp.data.data ? resp.data.data : null
                          if (serverEntry && serverEntry.id) {
                            const oldId = entry.id
                            const newId = serverEntry.id
                            // update memoryStore
                            if (memoryStore && memoryStore[sid]) {
                              for (let j = 0; j < memoryStore[sid].length; j++) {
                                if (memoryStore[sid][j] && String(memoryStore[sid][j].id) === String(oldId)) {
                                  memoryStore[sid][j] = Object.assign({}, memoryStore[sid][j], { id: newId })
                                }
                              }
                              try { await idbSet(sid, memoryStore[sid]) } catch (e) { console.warn('idbSet after reconciliation failed', e) }
                            }
                            // replace ids in pending queue entries
                            for (let k = 0; k < q.length; k++) {
                              const qi = q[k]
                              try {
                                if (qi && qi.type === 'transform' && qi.transform) {
                                  // replace occurrences in single-entry transforms
                                  if (qi.transform.entry && qi.transform.entry.id === oldId) {
                                    qi.transform.entry.id = newId
                                    modified = true
                                  }
                                  // replace occurrences in bulk rows transforms
                                  if (qi.transform.rows && typeof qi.transform.rows === 'object') {
                                    try {
                                      for (const rSid of Object.keys(qi.transform.rows)) {
                                        const arr = qi.transform.rows[rSid]
                                        if (!Array.isArray(arr)) continue
                                        for (const ent of arr) {
                                          if (ent && ent.id === oldId) {
                                            ent.id = newId
                                            modified = true
                                          }
                                        }
                                      }
                                    } catch (e) {}
                                  }
                                }
                              } catch (e) {}
                            }
                          }
                        } catch (e) {
                          console.warn('Reconciliation POST failed for bulk local entry', entry.id, e)
                        }
                      }
                    } catch (e) {}
                  }
                }
              } catch (e) { console.warn('flushPending: bulk rows reconciliation failed', e) }
            }
          } catch (e) {}
        }
        if (modified) {
          try { await safeIdbSetPending(q) } catch (e) { console.warn('Failed to persist modified pending queue', e) }
        }
      } catch (e) {
        console.warn('Reconciliation step failed', e)
      }

      const remaining = []
      for (const item of q) {
        try {
          try {
            console.debug('flushPending: sending item', item && item.type)
            orbit.ws.send(JSON.stringify(item))
            lastSentTs = Date.now()
          } catch (err) {
            console.warn('flushPending: send failed for item', err)
            remaining.push(item)
          }
        } catch (err) {
          remaining.push(item)
        }
      }
      pendingQueue = remaining.slice()
      pendingOps = pendingQueue.length
      await safeIdbSetPending(pendingQueue)
      return pendingOps
    } catch (e) {
      lastError = e
      throw e
    }
  },
  clearPending: async () => {
    pendingQueue = []
    pendingOps = 0
    try { await safeIdbSetPending([]) } catch (e) {}
    return true
  }
  ,getLocalEntries,
  // debug helper: expose the internal WebSocket (read-only getter)
  get ws() { return orbit && orbit.ws },
  // debug helper: expose internal orbit state (for debugging only)
  get __orbit() { return orbit },
  // debug helper: send a raw transform (or other control message) from console
  sendTransform: async (payload) => {
    try {
      if (!payload) throw new Error('sendTransform: missing payload')
      try { ensureTransformMetadata(payload) } catch (e) {}
      if (orbit && orbit.ws && orbit.ws.readyState === WebSocket.OPEN) {
        try { console.debug('sendTransform: sending payload transformId', payload && payload.transform && payload.transform.transformId) } catch (e) {}
        orbit.ws.send(JSON.stringify(payload))
        lastSentTs = Date.now()
        pendingOps = pendingOps + 1
        return true
      }
      // persist to pending queue when offline
      pendingQueue.push(payload)
      pendingOps = pendingQueue.length
      try { console.debug('sendTransform: persisting fallback pending length', pendingQueue.length) } catch (e) {}
      try { persistPendingFallback(pendingQueue) } catch (e) { console.warn('sendTransform: persistPendingFallback failed', e) }
      try {
        const ok = await safeIdbSetPending(pendingQueue)
        try { console.debug('sendTransform: safeIdbSetPending result', ok) } catch (e) {}
      } catch (e) { console.warn('sendTransform: failed to persist pending', e) }
      // also broadcast to other tabs so they can update optimistically
      try { if (typeof localStorage !== 'undefined') { console.debug('sendTransform: broadcasting to other tabs'); localStorage.setItem('orbit:transform', JSON.stringify({ ts: Date.now(), item: payload })) } } catch (e) {}
      return false
    } catch (e) {
      console.warn('sendTransform failed', e)
      throw e
    }
  },
}

// Auto-initialize so storage listener and helpers are available immediately in each tab.
try { if (typeof window !== 'undefined') { init().catch(() => {}) } } catch (e) {}
