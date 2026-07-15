<template>
  <div v-if="payload" class="rec-snap" :class="{ 'rec-snap--embedded': embedded }">
    <p v-if="!simple && payload.user_input" class="rec-snap-in">
      <span class="rec-snap-k">本次输入</span>
      <span class="rec-snap-v">{{ payload.user_input }}</span>
    </p>
    <p v-if="!simple && payload.elapsed_ms != null" class="rec-snap-meta">耗时 {{ formatMs(payload.elapsed_ms) }}</p>

    <div class="rec-snap-block">
      <div class="rec-snap-h">最终推荐</div>
      <div class="rec-snap-tags">
        <el-tag
          v-for="(m, idx) in payload.final_movies || []"
          :key="idx"
          size="small"
          effect="plain"
          round
          class="rec-snap-tag"
        >
          {{ displayName(m) }}
        </el-tag>
        <el-empty v-if="!(payload.final_movies || []).length" description="无最终列表" :image-size="56" />
      </div>
    </div>

    <div v-if="payload.recommend_text" class="rec-snap-block">
      <div class="rec-snap-h">推荐文本（定榜说明）</div>
      <div class="rec-snap-toolbar">
        <el-button size="small" round type="primary" plain @click="copyText">复制全文</el-button>
      </div>
      <pre class="rec-snap-pre">{{ payload.recommend_text }}</pre>
    </div>

    <div v-if="!simple" class="rec-snap-grid">
      <div class="rec-snap-mini">
        <div class="rec-snap-h">图谱候选（KG 实体短名）</div>
        <div class="rec-snap-mono">
          {{ (payload.kg_movies || []).slice(0, 60).map(formatEntity).join('、') || '—' }}
        </div>
      </div>
      <div class="rec-snap-mini">
        <div class="rec-snap-h">检索候选（RAG / 豆瓣片名）</div>
        <div class="rec-snap-mono">
          {{ (payload.rag_movies || []).slice(0, 60).join('、') || '—' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'

export interface SnapMovie {
  name?: string
  display?: string
  source?: string
}

export interface RecommendSnapshotPayload {
  snapshot_version?: number
  recommend_text?: string
  final_movies?: SnapMovie[]
  kg_movies?: string[]
  rag_movies?: string[]
  elapsed_ms?: number
  user_input?: string
}

const props = defineProps<{
  payload: RecommendSnapshotPayload | null
  /** 嵌入页面时使用略紧凑的卡片样式 */
  embedded?: boolean
  /** 简版：仅显示「最终推荐 + 推荐文本」两块 */
  simple?: boolean
}>()

function displayName(m: SnapMovie) {
  const s = (m.display || m.name || '').trim()
  return s.replace(/_/g, ' ')
}

function formatEntity(s: string) {
  return (s || '').replace(/_/g, ' ')
}

function formatMs(ms: number) {
  const n = Number(ms)
  if (!Number.isFinite(n)) return '—'
  if (n >= 1000) return `${(n / 1000).toFixed(2)} s`
  return `${Math.round(n)} ms`
}

function copyText() {
  const p = (props.payload?.recommend_text || '').trim()
  if (!p) return
  navigator.clipboard.writeText(p).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.warning('复制失败')
  )
}
</script>

<style scoped>
.rec-snap-in {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(226, 232, 240, 0.9);
}

.rec-snap-k {
  display: block;
  font-size: 12px;
  color: rgba(148, 163, 184, 0.95);
  margin-bottom: 4px;
}

.rec-snap-v {
  word-break: break-word;
}

.rec-snap-meta {
  margin: 0 0 14px;
  font-size: 12px;
  color: rgba(148, 163, 184, 0.9);
}

.rec-snap-block {
  margin-bottom: 16px;
}

.rec-snap-h {
  font-size: 13px;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.96);
  margin-bottom: 8px;
}

.rec-snap-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.rec-snap-tag {
  margin: 0;
}

.rec-snap-toolbar {
  margin-bottom: 8px;
}

.rec-snap-pre {
  margin: 0;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(2, 6, 23, 0.45);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: min(52vh, 480px);
  overflow: auto;
  color: rgba(226, 232, 240, 0.92);
}

.rec-snap-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 4px;
}

@media (max-width: 720px) {
  .rec-snap-grid {
    grid-template-columns: 1fr;
  }
}

.rec-snap-mini {
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(15, 23, 42, 0.45);
  padding: 10px 12px;
}

.rec-snap-mono {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(203, 213, 225, 0.9);
}

.rec-snap--embedded {
  margin-top: 0;
  padding: 16px 18px 18px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(2, 6, 23, 0.28);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.rec-snap--embedded .rec-snap-pre {
  max-height: min(40vh, 360px);
}
</style>
