import { route } from 'quasar/wrappers'
import { createRouter, createMemoryHistory, createWebHistory, createWebHashHistory } from 'vue-router'
import routes from './routes'
import { fetchCurrentUser, useAuth } from 'src/services/auth'


export default route(function (/* { store, ssrContext } */) {
  // If a token is present in the server URL (before the hash), move it into the hash
  // so the hash-based router can pick it up (handles links like /invite/accept?token=...#/profile).
  if (typeof window !== 'undefined') {
    try {
      const loc = window.location
      const hash = String(loc.hash || '')
      const search = String(loc.search || '')
      const pathname = String(loc.pathname || '')
      const hasHashInvite = hash.includes('/invite/accept')
      const pathInvite = pathname.includes('/invite/accept')
      const tokenMatch = search && search.match(/[?&]token=([^&]+)/)
      if (!hasHashInvite && (pathInvite || tokenMatch)) {
        const token = tokenMatch ? decodeURIComponent(tokenMatch[1]) : null
        // Remove token from the search while preserving other params
        let newSearch = ''
        try {
          const params = new URLSearchParams(search ? search.replace(/^\?/, '') : '')
          if (params.has('token')) params.delete('token')
          const s = params.toString()
          if (s) newSearch = `?${s}`
        } catch (e) {}
        const newHash = token ? `#/invite/accept?token=${encodeURIComponent(token)}` : '#/invite/accept'
        try {
          // When normalizing into a hash route, use the app base (root) as the path
          // to avoid duplicating the invite path both before and after the hash.
          const baseForHash = pathInvite ? (process.env.VUE_ROUTER_BASE || '/') : pathname
          history.replaceState(null, '', `${baseForHash}${newSearch}${newHash}`)
        } catch (e) {
          loc.hash = newHash
        }
      }
    } catch (e) {}
  }
  const createHistory = process.env.SERVER
    ? createMemoryHistory
    : (process.env.VUE_ROUTER_MODE === 'history' ? createWebHistory : createWebHashHistory)

  const Router = createRouter({
    scrollBehavior: () => ({ left: 0, top: 0 }),
    routes,

    // Leave this as is and make changes in quasar.conf.js instead!
    // quasar.conf.js -> build -> vueRouterMode
    // quasar.conf.js -> build -> publicPath
    history: createHistory(process.env.VUE_ROUTER_BASE)
  })

  // Global route guard
  Router.beforeEach(async (to, from, next) => {
    // If the route is the public invite accept page, skip auth checks entirely
    try {
      if (to && (to.name === 'invite-accept' || String(to.path || '').startsWith('/invite/accept') || (typeof window !== 'undefined' && String(window.location.hash || '').includes('/invite/accept')))) {
        next()
        return
      }
    } catch (e) {}

    const requiresAuth = !!to.meta.requiresAuth

    if (requiresAuth) {
      let token = null
      if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
        try {
          token = window.localStorage.getItem('access_token')
        } catch (e) {
          token = null
        }
      }
      if (!token) {
        next('/login')
        return
      }

      try {
        // Ensure the current user is valid; fetchCurrentUser will attempt
        // token refresh if necessary via interceptors.
        await fetchCurrentUser()
        const auth = useAuth()
        if (!auth.user) {
          // no valid user -> treat as unauthenticated
          next('/login')
          return
        }
      } catch (err) {
        try {
          if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
            window.localStorage.removeItem('access_token')
            window.localStorage.removeItem('refresh_token')
          }
        } catch (e) {}
        next('/login')
        return
      }
    }

    // If route requires admin, ensure loaded user has admin rights
    if (to.meta.requiresAdmin) {
      try {
        const auth = useAuth()
        const u = auth.user
        const isAdmin = !!(u && (u.attributes?.is_superadmin || (u.attributes?.assignments || []).some(a => a.role && a.role.name === 'org_admin')))
        if (!isAdmin) {
          next('/')
          return
        }
      } catch (err) {
        next('/')
        return
      }
    }

    next()
  });

  return Router
})

function isAuthenticated() {
  // Implement your authentication logic here
  // For example, check if a token is stored in localStorage
  if (typeof window === 'undefined' || typeof window.localStorage === 'undefined') {
    return false;
  }
  try {
    return window.localStorage.getItem('access_token') !== null;
  } catch (e) {
    return false;
  }
}
