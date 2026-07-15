import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import type { RouteRecordRaw } from 'vue-router'

const routes: Array<RouteRecordRaw> = [
  {
    path: '/auth',
    name: 'Auth',
    component: () => import('@/views/AuthView.vue'),
    meta: { requiresAuth: false, layout: 'none' }
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { requiresAuth: false, layout: 'user' }
  },
  {
    path: '/browse',
    name: 'Browse',
    component: () => import('@/views/BrowseView.vue'),
    meta: { requiresAuth: false, layout: 'user' }
  },
  {
    path: '/library',
    name: 'Library',
    component: () => import('@/views/LibraryView.vue'),
    meta: { requiresAuth: true, layout: 'user' }
  },
  {
    path: '/favorites',
    redirect: (to) => ({ path: '/library', query: { ...to.query, tab: 'favorites' } })
  },
  {
    path: '/history',
    redirect: (to) => ({ path: '/library', query: { ...to.query, tab: 'watched' } })
  },
  {
    path: '/recommend',
    name: 'Recommend',
    component: () => import('@/views/RecommendView.vue'),
    meta: { requiresAuth: true, layout: 'user' }
  },
  {
    path: '/reviews',
    name: 'Reviews',
    component: () => import('@/views/ReviewsView.vue'),
    meta: { requiresAuth: false, layout: 'user' }
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('@/views/ProfileView.vue'),
    meta: { requiresAuth: true, layout: 'user' }
  },
  {
    path: '/notifications',
    name: 'Notifications',
    component: () => import('@/views/NotificationsView.vue'),
    meta: { requiresAuth: true, layout: 'user' }
  },
  {
    path: '/change-password',
    name: 'ChangePassword',
    component: () => import('@/views/ChangePasswordView.vue'),
    meta: { requiresAuth: true, layout: 'user' }
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/AdminView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true, layout: 'admin' }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  const userStore = useUserStore()

  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    next({ path: '/auth', query: { redirect: to.fullPath } })
  } else if (to.meta.requiresAdmin && !userStore.isAdmin) {
    next('/')
  } else {
    next()
  }
})

export default router

