<template>
  <div class="pwd-page page-mesh">
    <el-card class="pwd-card glass" shadow="never">
      <template #header>
        <div class="head">
          <h2>修改密码</h2>
          <p>验证旧密码后设置新密码</p>
        </div>
      </template>

      <el-form :model="form" label-position="top" @submit.prevent="onSubmit">
        <el-form-item label="当前密码">
          <el-input v-model="form.oldPassword" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-form-item label="新密码（至少 6 位）">
          <el-input v-model="form.newPassword" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="form.confirmPassword" type="password" show-password autocomplete="new-password" />
        </el-form-item>

        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="mb" />
        <el-alert v-if="success" :title="success" type="success" show-icon :closable="false" class="mb" />

        <div class="actions">
          <el-button @click="goBack">返回</el-button>
          <el-button type="primary" :loading="loading" native-type="submit">确认修改</el-button>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { userApi } from '@/services/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()

const form = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})
const loading = ref(false)
const error = ref('')
const success = ref('')

const onSubmit = async () => {
  error.value = ''
  success.value = ''
  if (!form.value.oldPassword || !form.value.newPassword) {
    error.value = '请填写完整信息'
    return
  }
  if (form.value.newPassword !== form.value.confirmPassword) {
    error.value = '两次新密码不一致'
    return
  }
  if (form.value.newPassword.length < 6) {
    error.value = '新密码至少 6 位'
    return
  }
  loading.value = true
  try {
    await userApi.updatePassword(form.value.oldPassword, form.value.newPassword)
    success.value = '密码已更新，请重新登录'
    ElMessage.success('修改成功')
    setTimeout(() => {
      userStore.logout()
      router.push('/auth')
    }, 1200)
  } catch (err: any) {
    error.value = err.response?.data?.detail || '修改失败'
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  router.push('/profile')
}
</script>

<style scoped>
.pwd-page {
  max-width: 480px;
  margin: 0 auto;
  padding: 28px 20px 52px;
}

.glass {
  border-radius: 22px !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  background: rgba(15, 23, 42, 0.52) !important;
  backdrop-filter: blur(20px) saturate(1.12);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.08) inset,
    0 28px 80px rgba(0, 0, 0, 0.38) !important;
  --el-card-bg-color: transparent;
}

.pwd-card :deep(.el-card__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 20px 22px 16px;
}

.pwd-card :deep(.el-card__body) {
  padding: 12px 22px 24px;
}

.head h2 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: rgba(255, 255, 255, 0.96);
}

.head p {
  margin: 6px 0 0;
  font-size: 13px;
  color: rgba(203, 213, 225, 0.82);
  line-height: 1.5;
}

.pwd-card :deep(.el-form-item__label) {
  color: rgba(226, 232, 240, 0.88) !important;
  font-weight: 600;
}

.pwd-card :deep(.el-input__wrapper) {
  background: rgba(2, 6, 23, 0.45);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
}

.pwd-card :deep(.el-input__inner) {
  color: rgba(248, 250, 252, 0.95);
}

.pwd-card :deep(.el-input__inner::placeholder) {
  color: rgba(148, 163, 184, 0.75);
}

.mb {
  margin-bottom: 16px;
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.actions .el-button {
  flex: 1;
}
</style>
