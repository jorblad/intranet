import { route } from 'quasar/wrappers'
import { createRouter, createMemoryHistory, createWebHistory, createWebHashHistory } from 'vue-router'
import routes from './routes'
import { fetchCurrentUser, useAuth } from 'src/services/auth'


export default route(function (/* { store, ssrContext } */) {
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
    if (to.meta.requiresAuth && !isAuthenticated()) {
      next('/login');
      return
    }

    // If route requires admin, ensure current user is loaded and has admin rights
    if (to.meta.requiresAdmin) {
      try {
        await fetchCurrentUser()
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
  return localStorage.getItem('access_token') !== null;
}
