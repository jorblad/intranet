import { reactive } from 'vue'
import axios from 'axios'
import { setupInterceptors } from './http'

const state = reactive({
  user: null,
  organizations: [],
  // selected organization id (string) or null for Global
  selectedOrganization: null,
  // selected UI language (locale string)
  selectedLanguage: null,
})

// install interceptors on module load
setupInterceptors({ refreshEndpoint: '/oauth/token' })

export async function fetchCurrentUser() {
  try {
    const res = await axios.get('/api/user/me')
    state.user = res.data.data
    // initialize selectedLanguage from server or localStorage
    try {
      let serverLang = res.data.data?.attributes?.language
      if (serverLang) {
        // normalize possible object shapes to primitive locale
        if (typeof serverLang === 'object') {
          serverLang = serverLang.value || serverLang.code || serverLang.locale || serverLang.language || serverLang.name || serverLang.label || null
        }
        state.selectedLanguage = serverLang
      } else {
        const sl = localStorage.getItem('locale')
        state.selectedLanguage = sl || null
      }
    } catch (e) {
      state.selectedLanguage = null
    }
    // initialize selectedOrganization from localStorage if present
    try {
      const sid = localStorage.getItem('selected_organization')
      state.selectedOrganization = sid === 'null' ? null : sid
    } catch (e) {
      state.selectedOrganization = null
    }
    // If no selected organization in localStorage, and user has exactly one org assignment,
    // default to that organization so mobile users immediately see scoped data in selects.
    try {
      if (state.selectedOrganization == null) {
        const assignments = res.data.data?.attributes?.assignments || []
        // find the first non-global assignment
        const nonGlobal = assignments.find(a => a && a.role && !a.role.is_global)
        if (assignments.length === 1 && nonGlobal && nonGlobal.organization_id) {
          state.selectedOrganization = String(nonGlobal.organization_id)
          try { localStorage.setItem('selected_organization', String(state.selectedOrganization)) } catch (e) {}
        }
      }
    } catch (e) {}
  } catch (err) {
    state.user = null
    try {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    } catch (e) {}
  }
}

export async function fetchOrganizations() {
  try {
    const res = await axios.get('/api/rbac/organizations')
    state.organizations = res.data?.data || res.data || []
    // Ensure selectedOrganization is valid for this user; clear if it's not present
    try {
      const sid = state.selectedOrganization
      if (sid != null) {
        const ok = state.organizations.some(o => String(o.id) === String(sid))
        if (!ok) {
          state.selectedOrganization = null
          try { localStorage.removeItem('selected_organization') } catch (e) {}
        }
      }
    } catch (e) {}
  } catch (err) {
    state.organizations = []
  }
}

export function setSelectedOrganization(orgId) {
  // Validate orgId against known organizations; if invalid, clear selection
  let normalized = orgId == null ? null : String(orgId)
  try {
    if (normalized != null) {
      const ok = (state.organizations || []).some(o => String(o.id) === String(normalized))
      if (!ok) normalized = null
    }
  } catch (e) { normalized = null }

  state.selectedOrganization = normalized
  try {
    if (normalized == null) {
      localStorage.removeItem('selected_organization')
    } else {
      localStorage.setItem('selected_organization', normalized)
    }
  } catch (e) {
    // ignore
  }
}

export function setSelectedLanguage(locale) {
  state.selectedLanguage = locale
  try { localStorage.setItem('locale', locale) } catch (e) {}
}

export function useAuth() {
  return state
}

export default { fetchCurrentUser, useAuth }
