import Login from 'pages/LoginPage.vue'; // Import your Login component
import { fetchCurrentUser, useAuth } from 'src/services/auth'

const routes = [
  {
    path: '/',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/IndexPage.vue'), name: 'index' }
    ],
    meta: { requiresAuth: true } // Set up meta field for route guarding
  },
  {
    path: '/admin/orgs',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/AdminOrgs.vue'), name: 'admin-orgs' }
    ],
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/activities',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/AdminActivities.vue'), name: 'admin-activities' }
    ],
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/users',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/AdminUsers.vue'), name: 'admin-users' }
    ],
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/roles',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/AdminRoles.vue'), name: 'admin-roles' }
    ],
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/permissions',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/AdminPermissions.vue'), name: 'admin-permissions' }
    ],
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/assignments',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/AdminAssignments.vue'), name: 'admin-assignments' }
    ],
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/messages',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/AdminMessages.vue'), name: 'admin-messages' }
    ],
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/settings',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/AdminSettings.vue'), name: 'admin-settings' }
    ],
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/schedules',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/TermSchedules.vue'), name: 'schedules' }
    ],
    meta: { requiresAuth: true } // Set up meta field for route guarding
  },
  {
    path: '/profile',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/MyProfile.vue'), name: 'profile' }
    ],
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    component: Login // Use your Login component
  },
  {
    path: '/invite/accept',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('pages/InviteAccept.vue'), name: 'invite-accept' }
    ]
  },
  // Always leave this as last one,
  // but you can also remove it
  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue')
  }
];

export default routes;

