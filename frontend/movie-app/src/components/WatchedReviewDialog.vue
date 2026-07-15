<template>
  <el-dialog
    :model-value="modelValue"
    width="480px"
    append-to-body
    destroy-on-close
    align-center
    class="detail-dialog sub-detail-dialog"
    :show-close="false"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <template #header>
      <div class="dlg-head">
        <div class="dlg-head-title">
          <div class="dlg-h1">看过 · 短评与评分</div>
          <div class="dlg-hmeta">
            <span class="pill soft">短评可选；仅评分不会出现在影评广场</span>
          </div>
        </div>
        <button type="button" class="dlg-close" aria-label="关闭" @click="close">
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </template>
    <div class="wr-body">
      <div v-if="filmTitle" class="wr-film">{{ filmTitle }}</div>
      <div class="wr-field">
        <span class="wr-label">短评</span>
        <el-input
          v-model="form.note"
          type="textarea"
          :rows="4"
          maxlength="800"
          show-word-limit
          placeholder="写几句电影评价（可选，最多 800 字）"
        />
      </div>
      <div class="wr-field">
        <span class="wr-label">评分</span>
        <div class="wr-rate-row">
          <el-input-number
            v-model="form.rating"
            :min="1"
            :max="10"
            :step="0.1"
            :precision="1"
            controls-position="right"
            placeholder="1–10"
          />
          <span class="wr-rate-hint">1–10 分（可为小数），可选</span>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button round @click="close">取消</el-button>
      <el-button type="primary" round :loading="busy" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch, computed } from 'vue'
import { useUserStore } from '@/stores/user'
import { userApi, reviewApi } from '@/services/api'
import { ElMessage } from 'element-plus'
import { Close } from '@element-plus/icons-vue'

const props = defineProps<{
  modelValue: boolean
  movieName: string
  movieSource?: string
  tmdbId?: number | null
  genres: string
  isWatched: boolean
  initialNote?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'saved'): void
}>()

const userStore = useUserStore()

const form = reactive<{ note: string; rating: number | undefined }>({
  note: '',
  rating: undefined
})

const busy = ref(false)

const filmTitle = computed(() => (props.movieName || '').replace(/_/g, ' ').trim())

function close() {
  emit('update:modelValue', false)
}

async function loadForm() {
  form.note = (props.initialNote || '').trim()
  form.rating = undefined
  if (!userStore.userInfo || !props.movieName?.trim()) return
  try {
    const res = await reviewApi.getMineForMovie(props.movieName.trim())
    const mine = res.data?.review
    if (mine) {
      form.note = String(mine.content || '').trim()
      if (mine.rating != null && mine.rating !== '') {
        const n = Number(mine.rating)
        if (n >= 1 && n <= 10) form.rating = n
      }
    }
  } catch {
    /* ignore */
  }
}

function onOpen() {
  loadForm()
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) loadForm()
  }
)

async function submit() {
  if (!userStore.userInfo || !props.movieName?.trim()) return
  const note = form.note.trim()
  const hasRating = form.rating != null && form.rating >= 1 && form.rating <= 10

  if (!note && !hasRating) {
    if (!props.isWatched) {
      busy.value = true
      try {
        await userApi.addWatched(
          props.movieName.trim(),
          props.genres || '',
          props.movieSource || 'kg',
          props.tmdbId ?? null
        )
        ElMessage.success('已记录看过')
        emit('saved')
        close()
      } catch (e: any) {
        ElMessage.error(e.response?.data?.detail || '操作失败')
      } finally {
        busy.value = false
      }
      return
    }
    close()
    return
  }

  busy.value = true
  try {
    if (!props.isWatched) {
      await userApi.addWatched(
        props.movieName.trim(),
        props.genres || '',
        props.movieSource || 'kg',
        props.tmdbId ?? null
      )
    }
    await reviewApi.upsertReview({
      movie_name: props.movieName.trim(),
      movie_source: props.movieSource || '',
      rating: hasRating ? form.rating! : null,
      content: note
    })
    if (note) {
      await userApi.upsertFeedback(props.movieName.trim(), { note }, { movieSource: props.movieSource || 'kg', tmdbId: props.tmdbId ?? null })
    }
    ElMessage.success(props.isWatched ? '已更新' : '已记录看过')
    emit('saved')
    close()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.wr-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-bottom: 8px;
}

.wr-film {
  font-size: 14px;
  font-weight: 750;
  color: var(--el-text-color-primary);
}

.wr-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.wr-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--el-text-color-secondary);
}

.wr-rate-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.wr-rate-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
