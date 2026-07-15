<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/services/api'
import UserLayout from '@/app/shell/UserLayout.vue'
import AdminLayout from '@/app/shell/AdminLayout.vue'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const userStore = useUserStore()

const layout = computed(() => (route.meta.layout as string) || 'none')

onMounted(async () => {
  const token = localStorage.getItem('token')
  if (!token || userStore.userInfo) return
  try {
    const res = await api.get('/api/user/profile', { timeout: 20000 })
    if (res.data?.success && res.data.user) {
      userStore.setUser(res.data.user)
    }
  } catch {
    /* token 无效或网络错误 */
  }
})
</script>

<template>
  <UserLayout v-if="layout === 'user'" />
  <AdminLayout v-else-if="layout === 'admin'" />
  <router-view v-else />
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background: var(--app-bg-deep, #070b1a);
}

#app {
  width: 100%;
  min-height: 100vh;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: rgba(148, 163, 184, 0.12);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.36);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.52);
}
</style>
