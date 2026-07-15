<template>
  <el-button round class="add-pl-trigger" @click="openPicker">想看</el-button>
  <el-dialog
    v-model="pickerVisible"
    width="440px"
    append-to-body
    destroy-on-close
    align-center
    class="detail-dialog sub-detail-dialog"
    :show-close="false"
    @open="onDialogOpen"
  >
    <template #header>
      <div class="dlg-head">
        <div class="dlg-head-title">
          <div class="dlg-h1">加到片单</div>
          <div class="dlg-hmeta">
            <span class="pill soft">选择片单，将「想看」保存其中</span>
          </div>
        </div>
        <button type="button" class="dlg-close" aria-label="关闭" @click="pickerVisible = false">
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </template>
    <div v-loading="loading" class="add-pl-body">
      <p v-if="movieTitle" class="add-pl-film">{{ movieTitle }}</p>
      <el-select
        v-model="selectedId"
        placeholder="选择片单"
        filterable
        class="add-pl-select"
        :disabled="!playlists.length"
      >
        <el-option v-for="p in playlists" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <p v-if="!playlists.length && !loading" class="add-pl-hint">暂无片单，可在下方新建并加入。</p>

      <div class="add-pl-expand-head">
        <el-button class="add-pl-toggle" link type="primary" @click="toggleExpandNew">
          {{ expandNew ? '收起新建片单' : '新建片单并加入' }}
        </el-button>
      </div>
      <div v-show="expandNew" class="add-pl-new-block">
        <span class="add-pl-field-label">新片单名称</span>
        <el-input
          v-model="newPlaylistName"
          maxlength="64"
          show-word-limit
          placeholder="例如：周末观影"
          clearable
          @keyup.enter="onFooterPrimary"
        />
      </div>
    </div>
    <template #footer>
      <el-button round @click="pickerVisible = false">关闭</el-button>
      <el-button
        v-if="!expandNew"
        type="primary"
        round
        :disabled="!canAdd"
        :loading="submitting"
        @click="addToSelected"
      >
        加入所选片单
      </el-button>
      <el-button
        v-else
        type="primary"
        round
        :disabled="!canCreateNew"
        :loading="submitting"
        @click="submitNewPlaylistInline"
      >
        创建并加入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useUserStore } from '@/stores/user'
import { userApi } from '@/services/api'
import { ElMessage } from 'element-plus'
import { Close } from '@element-plus/icons-vue'

type PlaylistRow = { id: number; name: string }

const props = defineProps<{
  movieName: string
  movieSource?: string
  tmdbId?: number | null
  genres?: string
  posterUrl?: string
  genresStr?: string
  scoreStr?: string
  shortReview?: string
}>()

const userStore = useUserStore()

const pickerVisible = ref(false)
const playlists = ref<PlaylistRow[]>([])
const selectedId = ref<number | null>(null)
const loading = ref(false)
const submitting = ref(false)
const expandNew = ref(false)
const newPlaylistName = ref('')

const movieTitle = computed(() => (props.movieName || '').replace(/_/g, ' ').trim())

const canAdd = computed(
  () => !!props.movieName?.trim() && selectedId.value != null && !!playlists.value.length
)

const canCreateNew = computed(
  () => !!props.movieName?.trim() && !!newPlaylistName.value.trim()
)

function onFooterPrimary() {
  if (canCreateNew.value) submitNewPlaylistInline()
}

function buildExtra() {
  return {
    movieSource: props.movieSource || '',
    tmdbId: props.tmdbId ?? null,
    genres: props.genres || '',
    poster_url: props.posterUrl || '',
    genres_str: props.genresStr || props.genres || '',
    score_str: props.scoreStr || '',
    short_review: props.shortReview || ''
  }
}

async function refreshPlaylists() {
  if (!userStore.userInfo) return
  loading.value = true
  try {
    const res = await userApi.getPlaylists()
    if (res.data?.success) {
      playlists.value = res.data.playlists || []
      const sid = selectedId.value
      if (playlists.value.length) {
        if (sid == null || !playlists.value.some((p) => p.id === sid)) {
          selectedId.value = playlists.value[0].id
        }
      } else {
        selectedId.value = null
      }
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载片单失败')
  } finally {
    loading.value = false
  }
}

function openPicker() {
  if (!userStore.userInfo) {
    ElMessage.warning('请先登录')
    return
  }
  if (!props.movieName?.trim()) {
    ElMessage.warning('影片信息不完整')
    return
  }
  pickerVisible.value = true
}

function onDialogOpen() {
  expandNew.value = false
  newPlaylistName.value = ''
  refreshPlaylists()
}

function toggleExpandNew() {
  expandNew.value = !expandNew.value
  if (!expandNew.value) newPlaylistName.value = ''
}

async function addToSelected() {
  if (!canAdd.value) return
  submitting.value = true
  try {
    await userApi.addPlaylistItem(selectedId.value!, props.movieName.trim(), buildExtra())
    const name = playlists.value.find((p) => p.id === selectedId.value)?.name || ''
    ElMessage.success(name ? `已加入片单「${name}」` : '已加入片单')
    pickerVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加入失败')
  } finally {
    submitting.value = false
  }
}

async function submitNewPlaylistInline() {
  if (!userStore.userInfo || !props.movieName?.trim()) return
  const name = newPlaylistName.value.trim()
  if (!name) {
    ElMessage.warning('请输入片单名称')
    return
  }
  if (name.length > 64) {
    ElMessage.warning('片单名称最多 64 字')
    return
  }
  submitting.value = true
  try {
    const created = await userApi.createPlaylist(name)
    const newId = Number(created.data?.id || created.data?.playlist?.id || 0)
    if (!newId) {
      ElMessage.error('创建片单失败')
      return
    }
    await userApi.addPlaylistItem(newId, props.movieName.trim(), buildExtra())
    await refreshPlaylists()
    selectedId.value = newId
    expandNew.value = false
    newPlaylistName.value = ''
    ElMessage.success(`已创建片单并加入：${name}`)
    pickerVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
/* 与相邻 el-button 间距一致（约 8px，接近 Element 默认按钮组视觉） */
.add-pl-trigger {
  margin-left: 8px;
  margin-right: 8px;
}

.add-pl-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 72px;
  padding-bottom: 8px;
}

.add-pl-film {
  margin: 0;
  font-size: 14px;
  font-weight: 750;
  color: var(--el-text-color-primary);
}

.add-pl-select {
  width: 100%;
}

.add-pl-hint {
  margin: 0;
  font-size: 12px;
  color: #475569;
}

.add-pl-expand-head {
  margin-top: 4px;
}

.add-pl-toggle {
  padding: 0;
  height: auto;
}

.add-pl-new-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid rgba(99, 102, 241, 0.2);
  background: rgba(99, 102, 241, 0.06);
}

.add-pl-field-label {
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}
</style>
