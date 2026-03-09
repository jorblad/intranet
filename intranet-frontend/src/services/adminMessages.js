import axios from 'axios'

function apiBase() {
  try {
    if (typeof window !== 'undefined' && window.__API_PROXY_TARGET__) {
      // ensure no trailing slash
      return String(window.__API_PROXY_TARGET__).replace(/\/$/, '') + '/api'
    }
  } catch (e) {}
  return '/api'
}

export async function fetchAdminMessages(organizationId = null) {
  const params = {}
  // only include organization_id when a non-null id is provided; do not send
  // the literal string 'null' which FastAPI would interpret as a real id
  if (organizationId !== undefined && organizationId !== null) params.organization_id = organizationId
  params.active = true
  const res = await axios.get(`${apiBase()}/admin/messages`, { params })
  return res.data || []
}

export async function createAdminMessage(payload) {
  const res = await axios.post(`${apiBase()}/admin/messages`, payload)
  return res.data
}

export async function updateAdminMessage(id, payload) {
  const res = await axios.patch(`${apiBase()}/admin/messages/${id}`, payload)
  return res.data
}

export async function deleteAdminMessage(id) {
  await axios.delete(`${apiBase()}/admin/messages/${id}`)
}

export default { fetchAdminMessages, createAdminMessage, updateAdminMessage, deleteAdminMessage }
