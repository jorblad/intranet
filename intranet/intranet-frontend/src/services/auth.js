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
  } catch (err) {
    state.user = null
  }
}

export async function fetchOrganizations() {
  try {
    const res = await axios.get('/api/rbac/organizations')
    state.organizations = res.data || []
  } catch (err) {
    state.organizations = []
  }
}

export function setSelectedOrganization(orgId) {
  state.selectedOrganization = orgId == null ? null : orgId
  try {
    localStorage.setItem('selected_organization', String(orgId))
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
