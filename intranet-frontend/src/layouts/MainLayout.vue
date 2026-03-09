<template>
  <q-layout view="lHh Lpr lFf">
    <q-header elevated>
      <q-toolbar>
        <q-btn
          flat
          dense
          round
          icon="menu"
          aria-label="Menu"
          @click="toggleLeftDrawer"
        />

        <q-toolbar-title>
          {{$t('app.title')}}
        </q-toolbar-title>

        <div>Quasar v{{ $q.version }}</div>
        <div style="margin-left: 12px">
          <q-chip dense :color="syncStatus.color" text-color="white" outline>
            {{ syncStatus.label }}
          </q-chip>
        </div>
        <q-btn
          flat
          round
          :icon="$q.dark.isActive ? 'light_mode' : 'dark_mode'"
          @click="$q.dark.toggle()"
        />
        <q-btn
          flat
          round
          icon="logout"
          :aria-label="$t('nav.logout')"
          @click="logout"
        />
      </q-toolbar>
    </q-header>

    <q-drawer
      v-model="leftDrawerOpen"
      show-if-above
      bordered
    >
      <q-list>
        <q-item-label header>
          {{$t('nav.navigation')}}
        </q-item-label>

        <q-item>
          <q-item-section>
            <q-select
              dense
              outlined
              :options="orgOptions"
              v-model="selectedOrgObj"
              option-label="label"
              option-value="value"
              :label="$t('nav.org') || 'Organization'"
            />
          </q-item-section>
        </q-item>


        <router-link :to="{ name: 'index' }" class="custom-router-link">
          <q-item clickable v-ripple class="q-list-padding">
            <q-item-section avatar>
              <q-icon name='home' />
            </q-item-section>

            <q-item-section>
              <q-item-label>{{$t('nav.home')}}</q-item-label>
              <q-item-label caption></q-item-label>
            </q-item-section>
          </q-item>
        </router-link>
        <router-link :to="{ name: 'profile' }" class="custom-router-link">
          <q-item clickable v-ripple>
            <q-item-section avatar>
              <q-icon name="person" />
            </q-item-section>

            <q-item-section>
              <q-item-label>{{$t('nav.profile')}}</q-item-label>
              <q-item-label caption>{{$t('nav.profile_caption')}}</q-item-label>
            </q-item-section>
          </q-item>
        </router-link>
        <router-link :to="{ name: 'schedules' }" class="custom-router-link">
          <q-item clickable v-ripple>
            <q-item-section avatar>
              <q-icon name="event" />
            </q-item-section>

            <q-item-section>
              <q-item-label>{{$t('nav.activity')}}</q-item-label>
              <q-item-label caption>{{$t('nav.activity_caption')}}</q-item-label>
            </q-item-section>
          </q-item>
        </router-link>

        <q-item-label header class="q-mt-md">{{$t('nav.admin')}}</q-item-label>
        <router-link v-if="isAdminVisible" :to="{ name: 'admin-orgs' }" class="custom-router-link">
          <q-item clickable v-ripple class="q-list-padding">
            <q-item-section avatar>
              <q-icon name='groups' />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{$t('nav.orgs')}}</q-item-label>
            </q-item-section>
          </q-item>
        </router-link>
        <router-link v-if="isAdminVisible" :to="{ name: 'admin-users' }" class="custom-router-link">
          <q-item clickable v-ripple>
            <q-item-section avatar>
              <q-icon name='person' />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{$t('nav.users')}}</q-item-label>
            </q-item-section>
          </q-item>
        </router-link>
        <router-link v-if="isAdminVisible" :to="{ name: 'admin-assignments' }" class="custom-router-link">
          <q-item clickable v-ripple>
            <q-item-section avatar>
              <q-icon name='admin_panel_settings' />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{$t('nav.assignments')}}</q-item-label>
            </q-item-section>
          </q-item>
        </router-link>
        <router-link v-if="isAdminVisible" :to="{ name: 'admin-messages' }" class="custom-router-link">
          <q-item clickable v-ripple>
            <q-item-section avatar>
              <q-icon name='announcement' />
            </q-item-section>
            <q-item-section>
              <q-item-label>Messages</q-item-label>
            </q-item-section>
          </q-item>
        </router-link>
        <router-link v-if="isAdminVisible" :to="{ name: 'admin-roles' }" class="custom-router-link">
          <q-item clickable v-ripple>
            <q-item-section avatar>
              <q-icon name='badge' />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{$t('nav.roles')}}</q-item-label>
            </q-item-section>
          </q-item>
        </router-link>
        <router-link v-if="isAdminVisible" :to="{ name: 'admin-activities' }" class="custom-router-link">
          <q-item clickable v-ripple>
            <q-item-section avatar>
              <q-icon name='list' />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{$t('nav.activities')}}</q-item-label>
            </q-item-section>
          </q-item>
        </router-link>
        <router-link v-if="isAdminVisible" :to="{ name: 'admin-permissions' }" class="custom-router-link">
          <q-item clickable v-ripple>
            <q-item-section avatar>
              <q-icon name='vpn_key' />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{$t('nav.permissions')}}</q-item-label>
            </q-item-section>
          </q-item>
        </router-link>
      <q-expansion-item icon="sync" label="Sync Debug" :dense="true" class="q-my-sm">
          <div class="q-pa-sm">
            <div class="row items-center q-col-gutter-sm">
              <div class="col">
                <div>Pending transforms: <strong>{{ pendingCount }}</strong></div>
                <div style="font-size: 0.85em; color: var(--q-color-grey-6)">Last error: {{ lastErrorDisplay }}</div>
              </div>
              <div class="col-auto">
                <q-btn dense color="primary" label="Reload" @click="reloadPending" />
              </div>
            </div>
            <div class="q-mt-sm">
              <q-btn dense color="positive" label="Flush Pending" @click="flushPending" class="q-mr-sm"/>
              <q-btn dense color="negative" flat label="Clear Pending" @click="clearPending" />
            </div>
            <div class="q-mt-sm">
              <div>Prefetch progress: <strong>{{ syncProgress.done }}</strong> / <strong>{{ syncProgress.total }}</strong></div>
              <div class="q-mt-xs">
                <q-linear-progress :value="syncProgress.total ? syncProgress.done / syncProgress.total : 0" color="primary" />
              </div>
            </div>
            <div class="q-mt-sm" style="max-height:200px; overflow:auto; font-size:0.85em">
              <pre v-if="pendingList.length === 0">(no queued transforms)</pre>
              <pre v-else>{{ pendingList }}</pre>
            </div>
          </div>
        </q-expansion-item>
      </q-list>
    </q-drawer>

    <q-page-container>
      <AdminBanners :organizationId="selectedOrg" />
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<style scoped>
.custom-router-link {
  text-decoration: none;
  color: inherit;
}

</style>

<script>
import { defineComponent, ref, computed, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router' // Import the router instance
import { useQuasar } from 'quasar'
import { useAuth, fetchCurrentUser, fetchOrganizations, setSelectedOrganization } from '../services/auth.js'
import { useI18n } from 'vue-i18n'
import orbitSchedules from 'src/services/orbitSchedules.js'
import AdminBanners from 'src/components/AdminBanners.vue'



export default defineComponent({
  components: { AdminBanners },
  name: 'MainLayout',

    setup () {
    const leftDrawerOpen = ref(false)

    // Import the router instance
    const router = useRouter()
    const $q = useQuasar()

    // fetch current user and orgs
    const auth = useAuth()
    fetchCurrentUser()
    fetchOrganizations()

    const { t } = useI18n()

    const orgOptions = computed(() => {
      const base = [{ label: t('nav.global'), value: null }]
      const items = (auth.organizations || []).map(o => ({ label: o.name, value: String(o.id) }))
      return base.concat(items)
    })

    const selectedOrg = computed({
      get () {
        return auth.selectedOrganization == null ? null : String(auth.selectedOrganization)
      },
      set (v) {
        // normalize null/undefined and handle option objects
        let id = null
        if (v == null) id = null
        else if (typeof v === 'object' && 'value' in v) id = v.value
        else id = v
        setSelectedOrganization(id == null ? null : String(id))
      }
    })

    const selectedOrgObj = computed({
      get () {
        const cur = auth.selectedOrganization == null ? null : String(auth.selectedOrganization)
        if (cur == null) return orgOptions.value.find(o => o.value === null) || null
        return orgOptions.value.find(o => String(o.value) === String(cur)) || null
      },
      set (v) {
        let id = null
        if (v == null) id = null
        else if (typeof v === 'object' && 'value' in v) id = v.value
        else id = v
        setSelectedOrganization(id == null ? null : String(id))
      }
    })

    // expose auth for quick console inspection and add debug logging
    try {
      // make available in browser console: window.__AUTH__
      if (typeof window !== 'undefined') window.__AUTH__ = auth
    } catch (e) {
      // ignore in non-browser environments
    }

    // Sync status indicator
    const syncStatus = ref({ color: 'grey', label: 'Sync: unknown' })
    let _pollInterval = null
    const updateSync = () => {
      try {
        if (!orbitSchedules) {
          syncStatus.value = { color: 'grey', label: 'Sync: disabled' }
          return
        }
        const s = orbitSchedules.getSyncStatus ? orbitSchedules.getSyncStatus() : {}
        const now = Date.now()
        // consider org-level sync: if current org was recently bootstrapped into Orbit
        let orgSynced = false
        try {
          const curOrg = auth.selectedOrganization == null ? null : String(auth.selectedOrganization)
          if (curOrg && s.syncedOrgs && s.syncedOrgs[curOrg]) {
            const ts = parseInt(s.syncedOrgs[curOrg], 10)
            if (!isNaN(ts) && (now - ts) < 5 * 60 * 1000) orgSynced = true
          }
        } catch (e) {}
        const connected = !!s.connected || !!s.crossTabConnected || orgSynced
        const pending = s.pendingOps || 0
        const last = s.lastReceivedTs || s.lastSentTs || 0
        const age = last ? (now - last) / 1000 : Infinity
        if (!connected) {
          syncStatus.value = { color: 'negative', label: 'Sync: offline' }
        } else if (pending > 0 || age > 30) {
          syncStatus.value = { color: 'warning', label: `Sync: ${pending} pending` }
        } else {
          syncStatus.value = { color: 'positive', label: 'Sync: OK' }
        }
      } catch (e) {
        syncStatus.value = { color: 'grey', label: 'Sync: error' }
      }
    }
    // poll every 2s
    _pollInterval = setInterval(updateSync, 2000)
    updateSync()

    onUnmounted(() => { if (_pollInterval) clearInterval(_pollInterval); try { if (typeof _reloadInterval !== 'undefined' && _reloadInterval) clearInterval(_reloadInterval) } catch (e) {} })

    // Debug panel state
    const pendingList = ref([])
    const pendingCount = ref(0)
    const lastErrorDisplay = ref('')
    const syncProgress = ref({ total: 0, done: 0 })

    const reloadPending = async () => {
      try {
        const q = await orbitSchedules.getPendingQueue()
        pendingList.value = q.length ? JSON.stringify(q, null, 2) : []
        pendingCount.value = q.length
        lastErrorDisplay.value = orbitSchedules.getSyncStatus().lastError || ''
        // also refresh sync progress for prefetch
        try {
          const p = orbitSchedules.getSyncProgress ? orbitSchedules.getSyncProgress() : null
          if (p) syncProgress.value = { total: p.total || 0, done: p.done || 0 }
        } catch (e) {}
      } catch (e) {
        pendingList.value = []
        pendingCount.value = 0
        lastErrorDisplay.value = String(e)
      }
    }

    const flushPending = async () => {
      try {
        await orbitSchedules.flushPending()
        await reloadPending()
        // immediately update sync status chip
        updateSync()
        $q.notify({ type: 'positive', message: 'Flush attempted' })
      } catch (e) {
        $q.notify({ type: 'negative', message: 'Flush failed: ' + String(e) })
        lastErrorDisplay.value = String(e)
      }
    }

    const clearPending = async () => {
      try {
        await orbitSchedules.clearPending()
        await reloadPending()
        $q.notify({ type: 'info', message: 'Pending queue cleared' })
      } catch (e) {
        $q.notify({ type: 'negative', message: 'Clear failed: ' + String(e) })
      }
    }

    // expose orbitSchedules for easy console inspection (dev helper)
    try {
      if (typeof window !== 'undefined') window.__ORBIT__ = orbitSchedules
    } catch (e) {}

    // initial load for debug panel
    reloadPending()
    // poll sync progress periodically
    const _reloadInterval = setInterval(() => {
      try { reloadPending() } catch (e) {}
    }, 2000)

    const isAdminVisible = computed(() => {
      const u = auth.user
      if (!u) return false
      if (u.attributes?.is_superadmin) return true
      // check assignments for org_admin
      const assigns = u.attributes?.assignments || []
      return assigns.some(a => a.role && a.role.name === 'org_admin')
    })

    const logout = async () => {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      $q.notify({ type: 'info', message: t('nav.logged_out') })
      router.push('/login')
    }


    return {
      leftDrawerOpen,
      toggleLeftDrawer () {
        leftDrawerOpen.value = !leftDrawerOpen.value
      },
      logout,
      isAdminVisible,
      orgOptions,
      selectedOrg,
      selectedOrgObj,
      syncStatus,
      // debug panel bindings
      pendingList,
      pendingCount,
      syncProgress,
      lastErrorDisplay,
      reloadPending,
      flushPending,
      clearPending,
    }
  }
})
</script>
