<template>
  <div class="notifications-page page-mesh">
    <el-card class="hero-card" shadow="never">
      <div class="hero-inner">
        <div>
          <h2>消息中心</h2>
          <p class="hero-meta">你的操作与互动提醒会出现在这里</p>
        </div>
        <div class="hero-actions">
          <el-button round :loading="loading" @click="load">刷新</el-button>
          <el-button type="primary" round :disabled="!items.length || allRead" @click="markAll">
            全部已读
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card class="glass list-card" shadow="never">
      <el-skeleton v-if="loading" :rows="6" animated />
      <el-empty v-else-if="!items.length" description="暂无消息" :image-size="72" />
      <ul v-else class="msg-list">
        <li
          v-for="row in items"
          :key="row.id"
          :class="['msg-row', { unread: !row.is_read, clickable: isClickable(row) }]"
          @click="onRowClick(row)"
        >
          <span class="dot" :class="{ on: !row.is_read }" aria-hidden="true" />
          <div class="msg-body">
            <div class="msg-title">{{ row.title }}</div>
            <p v-if="row.detail" class="msg-detail">{{ row.detail }}</p>
            <div class="msg-meta">
              <el-tag size="small" effect="plain" round class="kind-tag">{{ kindLabel(row.kind) }}</el-tag>
              <span class="time">{{ row.created_at }}</span>
            </div>
          </div>
          <el-icon v-if="isClickable(row)" class="chev"><ArrowRight /></el-icon>
        </li>
      </ul>
    </el-card>

    <RecommendSnapshotDialog
      v-model="snapshotOpen"
      :payload="snapshotPayload"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { userApi } from '@/services/api'
import { ElMessage } from 'element-plus'
import { ArrowRight } from '@element-plus/icons-vue'
import RecommendSnapshotDialog from '@/components/RecommendSnapshotDialog.vue'
import type { RecommendSnapshotPayload } from '@/components/RecommendSnapshotDialog.vue'

const router = useRouter()
const loading = ref(false)
const items = ref<any[]>([])
const snapshotOpen = ref(false)
const snapshotPayload = ref<RecommendSnapshotPayload | null>(null)

const allRead = computed(() => items.value.length > 0 && items.value.every((x) => x.is_read))

const KIND_LABELS: Record<string, string> = {
  favorite_add: '收藏',
  feedback_like: '喜欢',
  watched_add: '已看过',
  review_create: '影评',
  review_update: '影评',
  playlist_create: '片单',
  playlist_add_item: '片单',
  playlist_bulk_add: '片单',
  playlist_remove_item: '片单',
  playlist_rename: '片单',
  playlist_update: '片单',
  playlist_delete: '片单',
  review_comment: '评论',
  review_reply: '回复',
  review_like: '点赞',
  password_change: '账号',
  review_mute: '禁言',
  review_unmute: '禁言解除',
  recommend_done: '推荐'
}

function kindLabel(k: string) {
  return KIND_LABELS[k] || '通知'
}

function isClickable(row: any) {
  const p = row.payload || {}
  if (row.kind === 'recommend_done' && (p.snapshot_version === 1 || (p.final_movies && p.recommend_text)))
    return true
  if (Number(p.review_id || 0)) return true
  if (Number(p.playlist_id || 0)) return true
  return false
}

async function load() {
  loading.value = true
  try {
    const res = await userApi.getNotifications(80, 0)
    if (res.data?.success) items.value = res.data.notifications || []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function notifyUnreadChanged() {
  try {
    window.dispatchEvent(new Event('notifications:updated'))
  } catch {
    /* ignore */
  }
}

async function markRead(ids: number[]) {
  if (!ids.length) return
  try {
    await userApi.markNotificationsRead({ ids })
    for (const r of items.value) {
      if (ids.includes(Number(r.id))) r.is_read = true
    }
    notifyUnreadChanged()
  } catch {
    /* ignore */
  }
}

async function markAll() {
  try {
    await userApi.markNotificationsRead({ mark_all: true })
    await load()
    ElMessage.success('已全部标为已读')
    notifyUnreadChanged()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

function onRowClick(row: any) {
  const p = row.payload || {}
  if (row.kind === 'recommend_done') {
    if (!row.is_read) markRead([Number(row.id)])
    snapshotPayload.value = (p && typeof p === 'object' ? p : null) as RecommendSnapshotPayload | null
    snapshotOpen.value = true
    return
  }
  const rid = Number(p.review_id || 0)
  const pl = Number(p.playlist_id || 0)
  if (!row.is_read) markRead([Number(row.id)])
  if (rid) {
    router.push({ path: '/reviews', query: { review: String(rid) } })
    return
  }
  if (pl) {
    router.push({ path: '/library', query: { tab: 'playlists', playlist: String(pl) } })
  }
}

onMounted(() => {
  load()
})
</script>

<style scoped>
.notifications-page {
  padding: 8px 20px 44px;
  max-width: 860px;
  margin: 0 auto;
  position: relative;
}

/* 消息中心两侧氛围背景（只在两侧空白显示，不影响操作） */
.notifications-page::before {
  content: '';
  position: fixed;
  inset: 64px 0 0 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.2;
  filter: brightness(1.14) contrast(1.06) saturate(1.06);
  background-image:
    radial-gradient(520px 420px at 18% 18%, rgba(99, 102, 241, 0.16), transparent 60%),
    radial-gradient(520px 420px at 82% 18%, rgba(168, 85, 247, 0.12), transparent 60%),
    url('/api/background/4.jpg'),
    url('/api/background/4.jpg');
  background-repeat: no-repeat;
  background-size: auto, auto, contain, contain;
  background-position: 13% 18%, 82% 18%, -10% 56%, 150% 56%;
}

.notifications-page > * {
  position: relative;
  z-index: 1;
}

.hero-card {
  margin-bottom: 20px;
  border-radius: 20px;
  background: linear-gradient(135deg, #1e1b4b, #2e1065);
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.hero-inner {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.hero-inner h2 {
  margin: 0 0 6px;
  font-size: 22px;
  color: rgba(248, 250, 252, 0.96);
}

.hero-meta {
  margin: 0;
  font-size: 13px;
  color: rgba(226, 232, 240, 0.72);
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.list-card {
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: #0b1220;
}

.msg-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.msg-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: rgba(226, 232, 240, 0.92);
}

.msg-row:last-child {
  border-bottom: none;
}

.msg-row.clickable {
  cursor: pointer;
}

.msg-row.clickable:hover {
  background: rgba(99, 102, 241, 0.08);
}

.msg-row.unread .msg-title {
  font-weight: 750;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 7px;
  flex-shrink: 0;
  background: transparent;
}

.dot.on {
  background: linear-gradient(135deg, #6366f1, #a855f7);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.25);
}

.msg-body {
  flex: 1;
  min-width: 0;
}

.msg-title {
  font-size: 15px;
  line-height: 1.45;
}

.msg-detail {
  margin: 6px 0 0;
  font-size: 13px;
  color: rgba(203, 213, 225, 0.85);
  line-height: 1.5;
}

.msg-meta {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.kind-tag {
  border-color: rgba(129, 140, 248, 0.35) !important;
  color: rgba(199, 210, 254, 0.95) !important;
  background: rgba(99, 102, 241, 0.12) !important;
}

.time {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.85);
}

.chev {
  margin-top: 4px;
  color: rgba(148, 163, 184, 0.65);
  flex-shrink: 0;
}
</style>
