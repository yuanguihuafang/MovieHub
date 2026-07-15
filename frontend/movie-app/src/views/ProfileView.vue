<template>
  <div class="profile-page page-mesh">
    <el-card class="hero-card" shadow="never">
      <div class="hero-inner">
        <div>
          <h2>个人中心</h2>
          <p v-if="user" class="hero-meta">
            {{ user.username }}
            <el-tag size="small" :type="user.role === 'admin' ? 'danger' : 'info'" class="role-tag">
              {{ user.role === 'admin' ? '管理员' : '用户' }}
            </el-tag>
          </p>
          <p v-if="user" class="hero-date">注册时间：{{ user.created_at }}</p>
        </div>
      </div>
    </el-card>

    <el-row :gutter="20">
      <el-col :xs="24" :md="12">
        <el-card class="glass" shadow="never">
          <template #header>
            <span>收藏摘要</span>
            <el-button text type="primary" @click="loadFavorites">刷新</el-button>
          </template>
          <el-skeleton v-if="loadingFavorites" :rows="3" animated />
          <el-empty v-else-if="favorites.length === 0" description="暂无收藏" :image-size="64" />
          <ul v-else class="mini-list">
            <li v-for="f in favorites.slice(0, 6)" :key="f.id">
              <span>{{ f.movie_name.replace(/_/g, ' ') }}</span>
              <small>{{ f.genres }}</small>
            </li>
          </ul>
          <el-button v-if="favorites.length" link type="primary" @click="$router.push('/library')">
            管理全部收藏 →
          </el-button>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card class="glass" shadow="never">
          <template #header>
            <span>已看过的片</span>
            <el-button text type="primary" @click="loadWatched">刷新</el-button>
          </template>
          <el-skeleton v-if="loadingWatched" :rows="3" animated />
          <el-empty v-else-if="watched.length === 0" description="暂无" :image-size="64" />
          <ul v-else class="mini-list">
            <li v-for="h in watched.slice(0, 6)" :key="h.id">
              <span>{{ h.movie_name.replace(/_/g, ' ') }}</span>
              <small>{{ h.genres }}</small>
            </li>
          </ul>
          <el-button
            v-if="watched.length"
            link
            type="primary"
            @click="$router.push({ path: '/library', query: { tab: 'watched' } })"
          >
            管理已看过 →
          </el-button>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="logs-card glass" shadow="never">
      <template #header>
        <span>近期推荐记录</span>
        <el-button text type="primary" @click="loadRecommendLogs">刷新</el-button>
      </template>
      <div class="logs-body">
        <el-skeleton v-if="loadingLogs" :rows="2" animated class="logs-skel" />
        <el-empty v-else-if="logs.length === 0" description="暂无" :image-size="64" class="logs-empty" />
        <el-table v-else :data="logs" size="small" class="logs-table">
          <el-table-column type="expand" width="48">
            <template #default="{ row }">
              <div class="log-expand">
                <RecommendSnapshotBody :payload="row?.snapshot_payload || null" embedded simple />
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="170" />
          <el-table-column prop="user_input" label="您的描述（摘要）" show-overflow-tooltip />
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { userApi } from '@/services/api'
import type { User, Favorite } from '@/types'
import RecommendSnapshotBody from '@/components/RecommendSnapshotBody.vue'
import type { RecommendSnapshotPayload } from '@/components/RecommendSnapshotBody.vue'

const router = useRouter()

interface WatchedItem {
  id: number
  movie_name: string
  genres: string
  watched_at: string
}

interface RecommendLogItem {
  id: number
  user_input: string
  created_at: string
  snapshot_payload?: RecommendSnapshotPayload | null
}

const user = ref<User | null>(null)
const favorites = ref<Favorite[]>([])
const loadingFavorites = ref(false)
const watched = ref<WatchedItem[]>([])
const loadingWatched = ref(false)
const logs = ref<RecommendLogItem[]>([])
const loadingLogs = ref(false)

const loadUserProfile = async () => {
  try {
    const res = await userApi.getUserProfile()
    if (res.data.success) {
      user.value = res.data.user
    }
  } catch {
    router.push('/auth')
  }
}

const loadFavorites = async () => {
  loadingFavorites.value = true
  try {
    const res = await userApi.getMyFavorites()
    if (res.data.success) favorites.value = res.data.favorites
  } finally {
    loadingFavorites.value = false
  }
}

const loadWatched = async () => {
  loadingWatched.value = true
  try {
    const res = await userApi.getMyWatched(30)
    if (res.data.success) watched.value = res.data.watched || []
  } finally {
    loadingWatched.value = false
  }
}

const loadRecommendLogs = async () => {
  loadingLogs.value = true
  try {
    const res = await userApi.getMyRecommendLogs(15)
    if (res.data.success) {
      logs.value = (res.data.logs || []).map((r: any) => ({
        id: r.id,
        user_input: (r.user_input || '').slice(0, 200),
        created_at: r.created_at,
        snapshot_payload:
          r.snapshot_payload && typeof r.snapshot_payload === 'object'
            ? (r.snapshot_payload as RecommendSnapshotPayload)
            : null
      }))
    }
  } finally {
    loadingLogs.value = false
  }
}


onMounted(() => {
  loadUserProfile()
  loadFavorites()
  loadWatched()
  loadRecommendLogs()
})
</script>

<style scoped>
.profile-page {
  max-width: 1040px;
  margin: 0 auto;
  padding: 12px 20px 44px;
  position: relative;
}

/* 个人中心两侧氛围背景（只在两侧空白显示，不影响操作） */
.profile-page::before {
  content: '';
  position: fixed;
  inset: 64px 0 0 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.2;
  filter: brightness(1.16) contrast(1.06) saturate(1.08);
  background-image:
    radial-gradient(520px 420px at 18% 18%, rgba(99, 102, 241, 0.16), transparent 60%),
    radial-gradient(520px 420px at 82% 18%, rgba(168, 85, 247, 0.12), transparent 60%),
    url('/api/background/片库2.png'),
    url('/api/background/片库4.jpg'),
    url('/api/background/推荐.png');
  background-repeat: no-repeat;
  background-size: auto, auto, contain, contain, contain;
  background-position: 18% 18%, 82% 18%, -10% 56%, -2% 56%, 110% 56%;
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0.95) 0%,
    rgba(0, 0, 0, 0.95) 18%,
    rgba(0, 0, 0, 0.0) 50%,
    rgba(0, 0, 0, 0.95) 82%,
    rgba(0, 0, 0, 0.95) 100%
  );
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0.95) 0%,
    rgba(0, 0, 0, 0.95) 18%,
    rgba(0, 0, 0, 0.0) 50%,
    rgba(0, 0, 0, 0.95) 82%,
    rgba(0, 0, 0, 0.95) 100%
  );
}

.profile-page > * {
  position: relative;
  z-index: 1;
}

.log-expand {
  padding: 0;
}


.glass {
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  background: rgba(255, 255, 255, 0.06) !important;
  backdrop-filter: blur(18px) saturate(1.12);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.06) inset,
    0 22px 70px rgba(0, 0, 0, 0.28) !important;
}

.glass :deep(.el-card__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(248, 250, 252, 0.94);
  font-weight: 650;
}

.hero-card {
  position: relative;
  overflow: hidden;
  margin-bottom: 22px;
  border-radius: 22px;
  background: linear-gradient(125deg, #4f46e5 0%, #7c3aed 42%, #6366f1 100%);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.08) inset,
    0 24px 56px rgba(79, 70, 229, 0.38);
}

.hero-card::after {
  content: '';
  position: absolute;
  inset: -35%;
  background: radial-gradient(circle at 25% 25%, rgba(255, 255, 255, 0.16), transparent 42%),
    radial-gradient(circle at 85% 15%, rgba(255, 255, 255, 0.08), transparent 40%);
  pointer-events: none;
}

.hero-card :deep(.el-card__body) {
  padding: 24px 28px;
}

.hero-inner {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
}

.hero-card h2 {
  margin: 0 0 10px 0;
  font-size: 1.5rem;
}

.hero-meta {
  margin: 0;
  font-size: 1.1rem;
}

.role-tag {
  margin-left: 8px;
  vertical-align: middle;
}

.hero-date {
  margin: 8px 0 0 0;
  opacity: 0.9;
  font-size: 13px;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-actions .el-button {
  margin: 0;
}

.mini-list {
  list-style: none;
  padding: 0;
  margin: 0 0 12px 0;
}

.mini-list li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
  font-size: 14px;
  color: rgba(248, 250, 252, 0.98);
}

.mini-list li > span:first-of-type {
  flex: 1;
  min-width: 0;
  font-weight: 650;
  color: rgba(248, 250, 252, 0.98);
  letter-spacing: 0.01em;
}

.mini-list small {
  flex-shrink: 0;
  max-width: 48%;
  text-align: right;
  color: rgba(211, 219, 234, 0.95);
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
}

/* 两列摘要卡：正文与空状态不要用浅灰默认色 */
.glass :deep(.el-card__body) {
  color: rgba(248, 250, 252, 0.94);
}

.glass :deep(.el-empty__description p) {
  color: rgba(226, 232, 240, 0.92) !important;
  font-size: 14px;
}

.glass :deep(.el-button.is-link) {
  font-weight: 600;
}

.profile-page .glass :deep(.el-skeleton__item) {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.08) 25%,
    rgba(255, 255, 255, 0.16) 50%,
    rgba(255, 255, 255, 0.08) 75%
  ) !important;
}

.logs-card {
  margin-top: 22px;
  border-radius: 20px !important;
}

.logs-card :deep(.el-card__header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.logs-card :deep(.el-card__body) {
  background: transparent !important;
  padding-top: 16px;
  padding-bottom: 18px;
}

.logs-body {
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(2, 6, 23, 0.35);
}

.logs-skel {
  padding: 16px 18px;
}

.logs-skel :deep(.el-skeleton__item) {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.06) 25%,
    rgba(255, 255, 255, 0.12) 50%,
    rgba(255, 255, 255, 0.06) 75%
  ) !important;
}

.logs-empty {
  padding: 28px 16px 32px;
}

.logs-empty :deep(.el-empty__description p) {
  color: rgba(203, 213, 225, 0.88);
}

.logs-empty :deep(.el-empty__image svg) {
  opacity: 0.55;
  filter: brightness(1.2);
}

.logs-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: rgba(15, 23, 42, 0.92);
  --el-table-row-hover-bg-color: rgba(99, 102, 241, 0.16);
  --el-table-text-color: rgba(226, 232, 240, 0.94);
  --el-table-header-text-color: rgba(248, 250, 252, 0.9);
  --el-table-border-color: rgba(255, 255, 255, 0.08);
  background: transparent !important;
}

.logs-table :deep(.el-table__inner-wrapper::before) {
  display: none;
}

.logs-table :deep(.el-table__header-wrapper),
.logs-table :deep(.el-table__body-wrapper) {
  background: transparent !important;
}

.logs-table :deep(th.el-table__cell) {
  background: rgba(15, 23, 42, 0.92) !important;
  color: rgba(248, 250, 252, 0.9) !important;
  border-color: rgba(255, 255, 255, 0.08) !important;
  font-weight: 650;
}

.logs-table :deep(td.el-table__cell) {
  background: rgba(30, 41, 59, 0.55) !important;
  color: rgba(226, 232, 240, 0.94) !important;
  border-color: rgba(255, 255, 255, 0.06) !important;
}

.logs-table :deep(.el-table__body tr:nth-child(even) > td.el-table__cell) {
  background: rgba(15, 23, 42, 0.42) !important;
}

.logs-table :deep(.el-table__body tr:hover > td.el-table__cell) {
  background: rgba(99, 102, 241, 0.2) !important;
}

.logs-table :deep(.el-table__border-left-patch),
.logs-table :deep(.el-table__border-bottom-patch) {
  background: rgba(255, 255, 255, 0.08) !important;
}

.profile-page :deep(.el-row) {
  margin-bottom: 4px;
}
</style>
