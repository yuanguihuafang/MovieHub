<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { userApi } from '@/services/api'
import { ElMessage } from 'element-plus'
import { House, Film, Star, ChatDotRound, EditPen, Setting, ArrowDown } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const active = ref('')
const unreadNotifications = ref(0)

router.afterEach((to) => {
  active.value = to.path
  loadUnreadNotifications()
})

async function loadUnreadNotifications() {
  if (!userStore.isLoggedIn) {
    unreadNotifications.value = 0
    return
  }
  try {
    const res = await userApi.getNotificationUnreadCount()
    if (res.data?.success) unreadNotifications.value = Number(res.data.unread || 0)
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  loadUnreadNotifications()
  window.addEventListener('notifications:updated', loadUnreadNotifications)
})

onUnmounted(() => {
  window.removeEventListener('notifications:updated', loadUnreadNotifications)
})

const logout = () => {
  userStore.logout()
  ElMessage.success('已退出登录')
  router.push('/')
}

const onMenu = (cmd: string) => {
  if (cmd === 'logout') logout()
  else if (cmd === 'password') router.push('/change-password')
  else if (cmd === 'profile') router.push('/profile')
  else if (cmd === 'notifications') router.push('/notifications')
}
</script>

<template>
  <div class="user-shell">
    <header class="user-top">
      <div class="inner">
        <router-link to="/" class="brand">
          <span class="brand-mark">MH</span>
          <span class="brand-text">MovieHub</span>
        </router-link>

        <nav class="nav">
          <router-link to="/" class="nav-link" :class="{ active: active === '/' }">
            <el-icon><House /></el-icon>首页
          </router-link>
          <router-link to="/browse" class="nav-link" :class="{ active: active === '/browse' }">
            <el-icon><Film /></el-icon>片库
          </router-link>
          <template v-if="userStore.isLoggedIn">
            <router-link to="/recommend" class="nav-link" :class="{ active: active === '/recommend' }">
              <el-icon><ChatDotRound /></el-icon>推荐
            </router-link>
            <router-link to="/library" class="nav-link" :class="{ active: active === '/library' }">
              <el-icon><Star /></el-icon>片单
            </router-link>
            <router-link to="/reviews" class="nav-link" :class="{ active: active === '/reviews' }">
              <el-icon><EditPen /></el-icon>影评
            </router-link>
          </template>
        </nav>

        <div class="nav-right">
          <router-link v-if="userStore.isLoggedIn && userStore.isAdmin" to="/admin" class="admin-chip">
            <el-icon><Setting /></el-icon>
            管理
          </router-link>
          <template v-if="userStore.isLoggedIn">
            <el-dropdown trigger="click" @command="onMenu">
              <span class="avatar-dd">
                <span class="avatar-circle">{{ userStore.userInfo?.username?.charAt(0) || '?' }}</span>
                <span class="uname">{{ userStore.userInfo?.username }}</span>
                <el-icon><ArrowDown /></el-icon>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="notifications">
                    <span class="dd-msg-row">
                      <span>消息中心</span>
                      <el-badge v-if="unreadNotifications > 0" :max="99" :value="unreadNotifications" class="dd-msg-badge" />
                    </span>
                  </el-dropdown-item>
                  <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                  <el-dropdown-item command="password">修改密码</el-dropdown-item>
                  <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template v-else>
            <router-link class="login-btn" :to="{ path: '/auth', query: { redirect: route.fullPath } }">
              登录 / 注册
            </router-link>
          </template>
        </div>
      </div>
    </header>

    <main class="user-body">
      <router-view />
    </main>

    <footer class="user-foot">
      <div class="inner foot-inner">
        <span class="foot-brand">影荐 · 电影发现与个性化推荐</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* Copied from previous components/UserLayout.vue */
.user-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(1100px 520px at 12% -10%, rgba(99, 102, 241, 0.26), transparent 55%),
    radial-gradient(900px 520px at 90% 0%, rgba(168, 85, 247, 0.18), transparent 52%),
    radial-gradient(900px 520px at 70% 70%, rgba(14, 165, 233, 0.1), transparent 58%),
    #070b1a;
}

.user-top {
  position: sticky;
  top: 0;
  z-index: 50;
  backdrop-filter: blur(16px) saturate(1.2);
  background: linear-gradient(180deg, rgba(7, 11, 26, 0.72), rgba(7, 11, 26, 0.38));
  border-bottom: 1px solid rgba(255, 255, 255, 0.09);
  box-shadow:
    0 1px 0 rgba(129, 140, 248, 0.12) inset,
    0 12px 40px rgba(0, 0, 0, 0.35);
}

.inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 64px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: rgba(255, 255, 255, 0.92);
  font-weight: 800;
  letter-spacing: 0.02em;
}

.brand-mark {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, #6366f1, #a855f7);
  color: #fff;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.12) inset,
    0 10px 28px rgba(99, 102, 241, 0.45);
}

.brand-text {
  font-size: 20px;
}

.nav {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  justify-content: center;
  flex-wrap: wrap;
}

.nav-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 999px;
  text-decoration: none;
  color: rgba(226, 232, 240, 0.84);
  font-size: 14px;
  transition: background 0.2s, color 0.2s;
}

.nav-link:hover {
  background: rgba(99, 102, 241, 0.16);
  color: rgba(255, 255, 255, 0.96);
}

.nav-link.active {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.38), rgba(168, 85, 247, 0.28));
  color: rgba(255, 255, 255, 0.98);
  font-weight: 600;
  box-shadow:
    0 0 0 1px rgba(165, 180, 252, 0.22),
    0 8px 24px rgba(99, 102, 241, 0.2);
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.admin-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(251, 146, 60, 0.14);
  color: rgba(255, 255, 255, 0.92);
  text-decoration: none;
  font-size: 13px;
  border: 1px solid rgba(251, 146, 60, 0.24);
}

.avatar-dd {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: rgba(226, 232, 240, 0.9);
  font-size: 14px;
}

.avatar-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
}

.uname {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.login-btn {
  display: inline-flex;
  align-items: center;
  padding: 8px 18px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  color: #fff;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35);
}

.login-btn:hover {
  filter: brightness(1.05);
}

.user-body {
  flex: 1;
  width: 100%;
}

.user-foot {
  border-top: 1px solid rgba(255, 255, 255, 0.09);
  background: linear-gradient(0deg, rgba(7, 11, 26, 0.85), rgba(7, 11, 26, 0.4));
  backdrop-filter: blur(14px);
  margin-top: auto;
}

.foot-inner {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: rgba(226, 232, 240, 0.7);
}

.foot-brand {
  font-weight: 700;
  letter-spacing: 0.02em;
  color: rgba(241, 245, 249, 0.86);
  text-shadow: 0 8px 30px rgba(99, 102, 241, 0.15);
}

.dd-msg-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

:deep(.dd-msg-badge .el-badge__content) {
  border: none;
}

@media (max-width: 900px) {
  .uname {
    display: none;
  }
  .nav {
    justify-content: flex-end;
  }
}
</style>

