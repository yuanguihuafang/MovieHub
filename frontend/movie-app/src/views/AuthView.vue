<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { User, Lock } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const activeTab = ref('login')
const loginForm = ref({
  username: '',
  password: ''
})
const registerForm = ref({
  username: '',
  password: '',
  confirmPassword: ''
})
const loginLoading = ref(false)
const registerLoading = ref(false)

const onLogin = async () => {
  if (!loginForm.value.username || !loginForm.value.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  
  loginLoading.value = true
  try {
    await userStore.login(loginForm.value.username, loginForm.value.password)
    ElMessage.success({ message: '登录成功', duration: 1600 })
    const redir = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    if (redir && redir.startsWith('/')) router.push(redir)
    else router.push('/')
  } catch (error: any) {
    ElMessage.error(error.message || '登录失败')
  } finally {
    loginLoading.value = false
  }
}

const onRegister = async () => {
  if (!registerForm.value.username || !registerForm.value.password) {
    ElMessage.warning('请填写完整信息')
    return
  }
  if (registerForm.value.password !== registerForm.value.confirmPassword) {
    ElMessage.error('两次密码不一致')
    return
  }
  if (registerForm.value.password.length < 6) {
    ElMessage.error('密码至少6位')
    return
  }
  
  registerLoading.value = true
  try {
    await userStore.register(
      registerForm.value.username,
      registerForm.value.password,
      registerForm.value.confirmPassword
    )
    ElMessage.success({ message: '注册成功', duration: 1600 })
    const redir = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    if (redir && redir.startsWith('/')) router.push(redir)
    else router.push('/')
    registerForm.value = { username: '', password: '', confirmPassword: '' }
  } catch (error: any) {
    ElMessage.error(error.message || '注册失败')
  } finally {
    registerLoading.value = false
  }
}
</script>

<template>
  <div class="auth-container">
    <div class="auth-glow" aria-hidden="true" />
    <el-card class="auth-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div class="auth-logo">
            <span class="auth-logo-mark">MH</span>
          </div>
          <h2>MovieHub</h2>
          <p class="subtitle">登录后浏览片库、收藏影片并获取个性化推荐</p>
        </div>
      </template>

      <el-tabs v-model="activeTab" class="auth-tabs">
        <!-- 登录 -->
        <el-tab-pane label="登录" name="login">
          <el-form @submit.prevent="onLogin">
            <el-form-item>
              <el-input
                v-model="loginForm.username"
                placeholder="用户名"
                size="large"
                :prefix-icon="User"
              />
            </el-form-item>
            <el-form-item>
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="密码"
                size="large"
                :prefix-icon="Lock"
                @keyup.enter="onLogin"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                size="large"
                :loading="loginLoading"
                style="width: 100%"
                @click="onLogin"
              >
                登录
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- 注册 -->
        <el-tab-pane label="注册" name="register">
          <el-form @submit.prevent="onRegister">
            <el-form-item>
              <el-input
                v-model="registerForm.username"
                placeholder="用户名"
                size="large"
                :prefix-icon="User"
              />
            </el-form-item>
            <el-form-item>
              <el-input
                v-model="registerForm.password"
                type="password"
                placeholder="密码（至少6位）"
                size="large"
                :prefix-icon="Lock"
              />
            </el-form-item>
            <el-form-item>
              <el-input
                v-model="registerForm.confirmPassword"
                type="password"
                placeholder="确认密码"
                size="large"
                :prefix-icon="Lock"
                @keyup.enter="onRegister"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                size="large"
                plain
                :loading="registerLoading"
                style="width: 100%"
                @click="onRegister"
              >
                注册
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>
      <p class="auth-foot">
        <router-link to="/">返回首页</router-link>
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.auth-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  padding: 24px;
  background-color: #070b1a;
  background-image:
    radial-gradient(1000px 520px at 15% -5%, rgba(99, 102, 241, 0.35), transparent 55%),
    radial-gradient(900px 480px at 95% 10%, rgba(168, 85, 247, 0.22), transparent 52%),
    radial-gradient(800px 400px at 50% 100%, rgba(14, 165, 233, 0.12), transparent 50%),
    linear-gradient(180deg, rgba(7, 11, 26, 0.42), rgba(7, 11, 26, 0.58)),
    url('/api/background/海报/老头.png'),
    url('/api/background/海报/inception.png'),
    url('/api/background/海报/bill.png');
  background-repeat: no-repeat;
  background-size:
    auto,
    auto,
    auto,
    100% 100%,
    calc(100% / 3) 100%,
    calc(100% / 3) 100%,
    calc(100% / 3) 100%;
  background-position:
    center,
    center,
    center,
    center,
    left center,
    center center,
    right center;
}

.auth-glow {
  position: absolute;
  inset: -20%;
  background: radial-gradient(circle at 50% 50%, rgba(99, 102, 241, 0.08), transparent 45%);
  pointer-events: none;
}

.auth-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 420px;
  border-radius: 22px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.08) inset,
    0 28px 80px rgba(0, 0, 0, 0.45);
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(20px) saturate(1.15);
  --el-card-bg-color: transparent;
}

.auth-card :deep(.el-card__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 22px 22px 18px;
}

.auth-card :deep(.el-card__body) {
  padding: 8px 22px 22px;
}

.card-header {
  text-align: center;
}

.auth-logo {
  display: flex;
  justify-content: center;
  margin-bottom: 14px;
}

.auth-logo-mark {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0.04em;
  color: #fff;
  background: linear-gradient(135deg, #6366f1, #a855f7);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.15) inset,
    0 12px 32px rgba(99, 102, 241, 0.45);
}

.card-header h2 {
  margin: 0 0 8px;
  font-size: 1.45rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: rgba(248, 250, 252, 0.96);
}

.subtitle {
  margin: 0;
  color: rgba(203, 213, 225, 0.82);
  font-size: 13px;
  line-height: 1.55;
}

.auth-tabs {
  margin-top: 4px;
}

.auth-tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}

.auth-tabs :deep(.el-tabs__nav-wrap::after) {
  background-color: rgba(255, 255, 255, 0.08);
}

.auth-tabs :deep(.el-tabs__item) {
  color: rgba(148, 163, 184, 0.95);
  font-weight: 600;
}

.auth-tabs :deep(.el-tabs__item.is-active) {
  color: #e0e7ff;
}

.auth-tabs :deep(.el-tabs__active-bar) {
  background: linear-gradient(90deg, #6366f1, #a855f7);
  height: 3px;
  border-radius: 3px;
}

.auth-tabs :deep(.el-input__wrapper) {
  background: rgba(2, 6, 23, 0.45);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
}

.auth-tabs :deep(.el-input__inner) {
  color: rgba(248, 250, 252, 0.95);
}

.auth-tabs :deep(.el-input__inner::placeholder) {
  color: rgba(148, 163, 184, 0.75);
}

.auth-foot {
  text-align: center;
  margin: 18px 0 0;
  font-size: 13px;
}

.auth-foot a {
  color: #c7d2fe;
  text-decoration: none;
  font-weight: 600;
}

.auth-foot a:hover {
  color: #fff;
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
