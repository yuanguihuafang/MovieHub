import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import type { User } from '@/types'
import { useRecommendStore } from '@/stores/recommend'

const API_BASE = ''

const axiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export const useUserStore = defineStore('user', () => {
  const userInfo = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('token'))

  const isLoggedIn = computed(() => !!userInfo.value)
  const isAdmin = computed(() => userInfo.value?.role === 'admin')

  // 登录
  const login = async (username: string, password: string) => {
    const response = await axiosInstance.post('/api/auth/login', {
      username,
      password
    })
    if (response.data.success) {
      useRecommendStore().resetForNewUser()
      userInfo.value = response.data.user
      const newToken = `user_${response.data.user.id}`
      token.value = newToken
      localStorage.setItem('token', newToken)
      return response.data
    }
    throw new Error('登录失败')
  }

  // 注册
  const register = async (username: string, password: string, confirmPassword: string) => {
    const response = await axiosInstance.post('/api/auth/register', {
      username,
      password,
      confirm_password: confirmPassword
    })
    if (response.data.success) {
      // 注册即登录：与 login() 保持一致的 token 写入逻辑
      if (response.data.user?.id) {
        useRecommendStore().resetForNewUser()
        userInfo.value = response.data.user
        const newToken = `user_${response.data.user.id}`
        token.value = newToken
        localStorage.setItem('token', newToken)
      }
      return response.data
    }
    throw new Error('注册失败')
  }

  // 登出
  const logout = () => {
    useRecommendStore().resetForNewUser()
    userInfo.value = null
    token.value = null
    localStorage.removeItem('token')
  }

  // 设置用户信息（用于保持登录状态）
  const setUser = (user: User) => {
    userInfo.value = user
  }

  return {
    userInfo,
    token,
    isLoggedIn,
    isAdmin,
    login,
    register,
    logout,
    setUser
  }
})
