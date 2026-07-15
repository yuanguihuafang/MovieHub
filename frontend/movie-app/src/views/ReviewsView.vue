<template>
  <div class="reviews-page page-mesh">
    <div class="rv-bg" aria-hidden="true">
      <div class="rv-bg-left" />
      <div class="rv-bg-left-blur" />
      <div class="rv-bg-right" />
    </div>
    <header class="rv-hero">
      <div class="rv-hero-inner">
        <div class="hero-left">
          <h1>影评广场</h1>
          <p>选择系统已有电影，打分（可选）并发布短评；也可以在影评下讨论、点赞。</p>
          <div v-if="userStore.userInfo && !userStore.isAdmin && isMeMutedNow()" class="rv-mute-banner">
            你已被禁言，解封时间：{{ myMutedUntilText() }}
          </div>
        </div>
        <div class="hero-actions">
          <el-autocomplete
            v-model="searchQuery"
            :fetch-suggestions="fetchMovieSuggestions"
            placeholder="搜索电影影评"
            clearable
            value-key="display"
            class="search-ac"
            @select="onSelectSearchMovie"
          />
          <el-button type="primary" round @click="openPostDialog">发布影评</el-button>
          <el-button :icon="Refresh" round @click="loadBoard">刷新</el-button>
        </div>
      </div>
    </header>

    <el-card class="glass panel" shadow="never">

      <div class="board" v-loading="loading">
        <!-- 搜索直达 -->
        <section v-if="searchBlock" class="mv-section search-section">
          <div class="mv-layout">
            <aside class="mv-left">
              <div class="mv-head">
                <div class="mv-poster-lg">
                  <img v-if="searchBlock.poster_url" :src="searchBlock.poster_url" alt="" loading="lazy" />
                  <div v-else class="mv-ph">暂无海报</div>
                </div>
                <div class="mv-info">
                  <div class="mv-title-lg">{{ searchBlock.movie_name }}</div>
                  <div class="mv-sub-lg">
                    <span v-if="searchBlock.genres" class="pill-mini soft">{{ searchBlock.genres }}</span>
                    <span class="pill-mini">评论 {{ searchBlock.review_count || 0 }}</span>
                    <span v-if="searchBlock.score" class="pill-mini">★ {{ searchBlock.score }}</span>
                  </div>
                  <div class="mv-actions">
                    <el-button size="small" round @click="openMovieDetail(searchBlock.movie_name)">详情</el-button>
                    <el-button size="small" plain round @click="clearSearch">清除</el-button>
                  </div>
                </div>
              </div>
            </aside>
            <div class="mv-right">
              <div class="mv-right-inner">

              <div v-if="!searchBlock.reviews?.length" class="empty inner-empty">
                <el-empty description="该电影暂无影评" />
                <el-button type="primary" round @click="openPostDialogWithMovie(searchBlock)">添加影评</el-button>
              </div>
              <div v-else class="feed">
                <article v-for="r in searchBlock.reviews" :key="r.id" class="rv-card">
                  <div class="rv-body">
                    <div class="msg-line">
                      <span class="msg-name">{{ r.username }}</span>
                      <span class="msg-colon">：</span>
                      <span class="msg-bubble">{{ r.content }}</span>
                    </div>
                    <div v-if="extraFeedbackNote(r)" class="msg-line msg-line-sub">
                      <span class="msg-name sub-lbl">反馈短评</span>
                      <span class="msg-colon">：</span>
                      <span class="msg-bubble msg-bubble-sub">{{ extraFeedbackNote(r) }}</span>
                    </div>
                    <div class="rv-side">
                      <div v-if="r.rating" class="rv-rating-side">★ {{ r.rating }}</div>
                    </div>
                  </div>
                  <div class="rv-foot">
                    <div class="rv-meta">
                      <span class="rv-time">{{ fmtTime(r.updated_at) }}</span>
                      <el-button
                        v-if="userStore.userInfo && r.user_id === userStore.userInfo.id"
                        size="small"
                        link
                        type="danger"
                        class="rv-del"
                        @click="deleteMyReview(r.id)"
                      >
                      删除
                      </el-button>
                      <el-button
                        v-else-if="userStore.isAdmin"
                        size="small"
                        link
                        type="danger"
                        class="rv-del"
                        @click="adminDeleteReview(r.id)"
                      >
                        删除
                      </el-button>
                      <el-button v-if="userStore.isAdmin" size="small" link class="reply-link" @click="adminMuteUser(r.user_id)">
                        禁言
                      </el-button>
                      <el-button v-if="userStore.isAdmin" size="small" link class="reply-link" @click="adminUnmuteUser(r.user_id)">
                        解禁
                      </el-button>
                    </div>
                    <div class="rv-actions">
                      <el-button size="small" link :icon="Pointer" :class="{ liked: !!r.my_liked }" @click="toggleReviewLike(r, searchBlock.movie_name)">
                        {{ r.like_count || 0 }}
                      </el-button>
                      <el-button size="small" link :icon="ChatDotRound" @click="toggleReplyBox(r)">
                        回复 {{ r.comment_count || 0 }}
                      </el-button>
                    </div>
                  </div>

                  <div v-if="Number(r.comment_count || 0) > 0" class="reply-thread">
                    <div v-if="replyLoading[r.id]" class="muted">回复加载中…</div>
                    <div v-else class="reply-list">
                      <div v-for="c in replyMap[r.id] || []" :key="c.id" class="reply-row">
                        <div class="msg-line reply-indent">
                          <span class="msg-name">{{ c.username }}</span>
                          <span class="msg-colon">：</span>
                          <span class="msg-bubble">{{ c.content }}</span>
                        </div>
                        <div class="reply-foot">
                          <span class="reply-time">{{ fmtTime(c.created_at) }}</span>
                          <el-button size="small" link class="reply-link" @click="prepareReplyTo(r.id, c)">
                            回复
                          </el-button>
                          <el-button
                            v-if="userStore.userInfo && c.user_id === userStore.userInfo.id"
                            size="small"
                            link
                            type="danger"
                            @click="deleteMyReply(c.id, r)"
                          >
                            删除
                          </el-button>
                        <el-button
                          v-else-if="userStore.isAdmin"
                          size="small"
                          link
                          type="danger"
                          @click="adminDeleteReply(c.id, r)"
                        >
                          删除
                        </el-button>
                        <el-button v-if="userStore.isAdmin" size="small" link class="reply-link" @click="adminMuteUser(c.user_id)">禁言</el-button>
                        <el-button v-if="userStore.isAdmin" size="small" link class="reply-link" @click="adminUnmuteUser(c.user_id)">解禁</el-button>
                        </div>
                      </div>
                      <div v-if="!replyLoading[r.id] && !(replyMap[r.id] || []).length" class="muted">暂无回复</div>
                    </div>
                  </div>

                  <div v-if="replyBoxOpen[r.id]" class="reply-box">
                    <div class="reply-rowline">
                      <el-input
                        v-model="inlineReplyText[r.id]"
                        maxlength="800"
                        :placeholder="replyPlaceholder[r.id] || '写下你的回复…'"
                        clearable
                        class="reply-input"
                      />
                      <el-button size="small" link class="reply-link" @click="toggleReplyBox(r)">收起</el-button>
                      <el-button
                        type="primary"
                        size="small"
                        link
                        class="reply-link"
                        :loading="!!inlineReplyLoading[r.id]"
                        @click="submitInlineReply(r, searchBlock.movie_name)"
                      >
                        发布
                      </el-button>
                    </div>
                  </div>
                </article>
              </div>
            </div>
          </div>
          </div>
        </section>

        <div v-if="!movieBlocks.length" class="empty">
          <el-empty description="暂无影评" />
        </div>

        <section v-for="m in movieBlocks" :key="m.movie_name" class="mv-section">
          <div class="mv-layout">
            <aside class="mv-left">
              <div class="mv-head">
                <div class="mv-poster-lg">
                  <img v-if="m.poster_url" :src="m.poster_url" alt="" loading="lazy" />
                  <div v-else class="mv-ph">暂无海报</div>
                </div>
                <div class="mv-info">
                  <div class="mv-title-lg">{{ m.movie_name }}</div>
                  <div class="mv-sub-lg">
                    <span v-if="m.genres" class="pill-mini soft">{{ m.genres }}</span>
                    <span class="pill-mini">评论 {{ m.review_count }}</span>
                    <span v-if="m.score" class="pill-mini">★ {{ m.score }}</span>
                  </div>
                  <div class="mv-actions">
                    <el-button size="small" round @click="openMovieDetail(m.movie_name)">详情</el-button>
                  </div>
                </div>
              </div>
            </aside>
            <div class="mv-right">
              <div class="mv-right-inner">
                <div class="feed">
                  <article v-for="r in m.reviews" :key="r.id" class="rv-card">
              <div class="rv-body">
                <div class="msg-line">
                  <span class="msg-name">{{ r.username }}</span>
                  <span class="msg-colon">：</span>
                  <span class="msg-bubble">{{ r.content }}</span>
                </div>
                <div v-if="extraFeedbackNote(r)" class="msg-line msg-line-sub">
                  <span class="msg-name sub-lbl">反馈短评</span>
                  <span class="msg-colon">：</span>
                  <span class="msg-bubble msg-bubble-sub">{{ extraFeedbackNote(r) }}</span>
                </div>
                <div class="rv-side">
                  <div v-if="r.rating" class="rv-rating-side">★ {{ r.rating }}</div>
                </div>
              </div>
              <div class="rv-foot">
                <div class="rv-meta">
                  <span class="rv-time">{{ fmtTime(r.updated_at) }}</span>
                  <el-button
                    v-if="userStore.userInfo && r.user_id === userStore.userInfo.id"
                    size="small"
                    link
                    type="danger"
                    class="rv-del"
                    @click="deleteMyReview(r.id)"
                  >
                    删除
                  </el-button>
                  <el-button
                    v-else-if="userStore.isAdmin"
                    size="small"
                    link
                    type="danger"
                    class="rv-del"
                    @click="adminDeleteReview(r.id)"
                  >
                    删除
                  </el-button>
                  <el-button v-if="userStore.isAdmin" size="small" link class="reply-link" @click="adminMuteUser(r.user_id)">
                    禁言
                  </el-button>
                  <el-button v-if="userStore.isAdmin" size="small" link class="reply-link" @click="adminUnmuteUser(r.user_id)">
                    解禁
                  </el-button>
                </div>
                <div class="rv-actions">
                  <el-button
                    size="small"
                    link
                    :icon="Pointer"
                    :class="{ liked: !!r.my_liked }"
                    @click="toggleReviewLike(r, m.movie_name)"
                  >
                    {{ r.like_count || 0 }}
                  </el-button>
                  <el-button size="small" link :icon="ChatDotRound" @click="toggleReplyBox(r)">
                    回复 {{ r.comment_count || 0 }}
                  </el-button>
                </div>
              </div>
              <div v-if="Number(r.comment_count || 0) > 0" class="reply-thread">
                <div v-if="replyLoading[r.id]" class="muted">回复加载中…</div>
                <div v-else class="reply-list">
                  <div v-for="c in replyMap[r.id] || []" :key="c.id" class="reply-row">
                    <div class="msg-line reply-indent">
                      <span class="msg-name">{{ c.username }}</span>
                      <span class="msg-colon">：</span>
                      <span class="msg-bubble">{{ c.content }}</span>
                    </div>
                    <div class="reply-foot">
                      <span class="reply-time">{{ fmtTime(c.created_at) }}</span>
                      <el-button size="small" link class="reply-link" @click="prepareReplyTo(r.id, c)">回复</el-button>
                      <el-button
                        v-if="userStore.userInfo && c.user_id === userStore.userInfo.id"
                        size="small"
                        link
                        type="danger"
                        @click="deleteMyReply(c.id, r)"
                      >
                        删除
                      </el-button>
                      <el-button
                        v-else-if="userStore.isAdmin"
                        size="small"
                        link
                        type="danger"
                        @click="adminDeleteReply(c.id, r)"
                      >
                        删除
                      </el-button>
                      <el-button v-if="userStore.isAdmin" size="small" link class="reply-link" @click="adminMuteUser(c.user_id)">禁言</el-button>
                      <el-button v-if="userStore.isAdmin" size="small" link class="reply-link" @click="adminUnmuteUser(c.user_id)">解禁</el-button>
                    </div>
                  </div>
                  <div v-if="!replyLoading[r.id] && !(replyMap[r.id] || []).length" class="muted">暂无回复</div>
                </div>
              </div>

              <div v-if="replyBoxOpen[r.id]" class="reply-box">
                <div class="reply-rowline">
                  <el-input
                    v-model="inlineReplyText[r.id]"
                    maxlength="800"
                    :placeholder="replyPlaceholder[r.id] || '写下你的回复…'"
                    clearable
                    class="reply-input"
                  />
                  <el-button size="small" link class="reply-link" @click="toggleReplyBox(r)">收起</el-button>
                  <el-button
                    type="primary"
                    size="small"
                    link
                    class="reply-link"
                    :loading="!!inlineReplyLoading[r.id]"
                    @click="submitInlineReply(r, m.movie_name)"
                  >
                    发布
                  </el-button>
                </div>
              </div>
                </article>
              </div>

          <div class="more-row" v-if="m.reviews.length < m.review_count">
            <el-button round :loading="!!m.loading_more" @click="loadMoreForMovie(m.movie_name)">更多</el-button>
            <span class="muted">每次再加载 10 条</span>
          </div>
            </div>
              </div>
          </div>
        </section>

        <div v-if="totalMovies > pageSize" class="browse-bottom">
          <el-pagination
            class="browse-pagination"
            v-model:current-page="page"
            :page-size="pageSize"
            :total="totalMovies"
            layout="total, prev, pager, next, jumper"
            @current-change="onPageChange"
          />
        </div>
      </div>
    </el-card>

    <!-- 发布影评弹窗 -->
    <el-dialog v-model="postVisible" :show-close="false" width="720px" destroy-on-close class="detail-dialog">
      <template #header>
        <div class="dlg-head">
          <div class="dlg-head-title">
            <div class="dlg-h1">发布影评</div>
            <div class="dlg-hmeta">
              <span class="pill soft">必须选择系统已有电影</span>
            </div>
          </div>
          <button type="button" class="dlg-close" aria-label="关闭" @click="postVisible = false">
            <el-icon><CircleClose /></el-icon>
          </button>
        </div>
      </template>
      <div class="dlg">
        <div class="post-grid">
          <div class="movie-pick">
            <div class="field-label">选择电影</div>
            <el-autocomplete
              v-model="movieQuery"
              :fetch-suggestions="fetchMovieSuggestions"
              placeholder="搜索电影名（豆瓣 / TMDB-CSV / KG）"
              clearable
              value-key="display"
              class="movie-ac"
              @select="onSelectMovie"
            />
            <div v-if="pickedMovie" class="picked">
              <el-tag size="small" effect="plain" round>{{ sourceLabel(pickedMovie.source) }}</el-tag>
              <span class="picked-title">{{ pickedMovie.display }}</span>
            </div>
            <el-alert
              v-else-if="movieQuery.trim().length >= 2"
              type="info"
              show-icon
              :closable="false"
              title="未选择电影"
              description="请从下拉建议中选择系统已有电影；若无结果，表示系统暂无该电影信息。"
              class="picked-alert"
            />
          </div>

          <div class="post-form">
            <div class="field-label">评分（可选）</div>
            <el-input-number v-model="rating" :min="1" :max="10" :step="0.1" :precision="1" controls-position="right" />
            <div class="field-label" style="margin-top: 12px">短评</div>
            <el-input
              v-model="content"
              type="textarea"
              :autosize="{ minRows: 3, maxRows: 6 }"
              maxlength="800"
              show-word-limit
              placeholder="写下你的影评（最多 800 字）"
            />
          </div>
        </div>
      </div>
      <template #footer>
        <el-button round @click="postVisible = false">取消</el-button>
        <el-button type="primary" round :loading="posting" @click="submitReview">发布</el-button>
      </template>
    </el-dialog>

    <!-- 电影详情 -->
    <el-dialog
      v-model="movieDetailVisible"
      :show-close="false"
      width="960px"
      destroy-on-close
      class="detail-dialog"
    >
      <template #header>
        <div class="dlg-head">
          <div class="dlg-head-title">
            <div class="dlg-h1">{{ movieDetail?.data?.title || currentMovieName || '影片详情' }}</div>
            <div class="dlg-hmeta">
              <span v-if="movieDetail?.data?.score" class="pill score">★ {{ movieDetail.data.score }}</span>
              <span v-if="movieDetail?.data?.type" class="pill">{{ movieDetail.data.type }}</span>
              <span v-if="movieDetail?.data?.start_time" class="pill soft">{{ movieDetail.data.start_time }}</span>
            </div>
          </div>
          <button type="button" class="dlg-close" aria-label="关闭" @click="movieDetailVisible = false">
            <el-icon><Close /></el-icon>
          </button>
        </div>
      </template>

      <div v-loading="movieDetailLoading" class="dlg dlg-row">
        <div class="dlg-left">
          <div v-if="movieDetail?.poster_url" class="dlg-poster">
            <img :src="movieDetail.poster_url" alt="" />
          </div>
          <div v-else class="dlg-ph">暂无海报</div>
        </div>
        <div class="dlg-right">
          <div v-if="movieDetail?.data?.overview" class="dlg-overview">
            {{ movieDetail.data.overview }}
          </div>

          <el-descriptions v-if="movieDetail?.data" :column="2" border size="small" class="dlg-desc purple-desc">
            <el-descriptions-item v-if="movieDetail.data.score" label="评分">{{ movieDetail.data.score }}</el-descriptions-item>
            <el-descriptions-item v-if="movieDetail.data.rank" label="排名">{{ movieDetail.data.rank }}</el-descriptions-item>
            <el-descriptions-item v-if="movieDetail.data.run_time" label="时长">{{ movieDetail.data.run_time }}</el-descriptions-item>
            <el-descriptions-item v-if="movieDetail.data.start_time" label="上映">{{ movieDetail.data.start_time }}</el-descriptions-item>
            <el-descriptions-item v-if="movieDetail.data.type" label="类型">{{ movieDetail.data.type }}</el-descriptions-item>
            <el-descriptions-item v-if="movieDetail.data.director" label="导演">{{ movieDetail.data.director }}</el-descriptions-item>
            <el-descriptions-item v-if="movieDetail.data.actor" label="演员" :span="2">
              {{ formatActor(movieDetail.data.actor) }}
            </el-descriptions-item>
            <el-descriptions-item v-if="movieDetail.data.area" label="地区">{{ movieDetail.data.area }}</el-descriptions-item>
            <el-descriptions-item v-if="movieDetail.data.language" label="语言">{{ movieDetail.data.language }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick, h } from 'vue'
import { useRoute } from 'vue-router'
import { reviewApi, movieApi, adminApi } from '@/services/api'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, CircleClose, ChatDotRound, Pointer, Close } from '@element-plus/icons-vue'

const userStore = useUserStore()
const route = useRoute()

const _parseDateLike = (s: string) => {
  const v = (s || '').toString().trim()
  if (!v) return null
  // 后端格式通常是 "YYYY-MM-DD HH:mm:ss"
  const iso = v.includes('T') ? v : v.replace(' ', 'T')
  const t = Date.parse(iso)
  return Number.isFinite(t) ? t : null
}
const myMutedUntilText = () => (userStore.userInfo?.review_muted_until || '').toString().trim()
const myMuteReasonText = () => (userStore.userInfo as any)?.review_mute_reason?.toString?.().trim?.() || ''
const isMeMutedNow = () => {
  const until = myMutedUntilText()
  const t = _parseDateLike(until)
  if (!t) return false
  return Date.now() < t
}

const _friendlyApiError = (e: any, fallback: string) => {
  const status = Number(e?.response?.status || 0)
  const d = e?.response?.data?.detail
  const s = (typeof d === 'string' ? d : '').trim()
  if (s && s !== '.') return s
  if (status === 403) return '你已被禁言，无法执行该操作'
  return fallback
}

const sourceLabel = (s: string) => {
  if (s === 'douban') return '豆瓣'
  if (s === 'tmdb_csv') return 'TMDB-CSV'
  if (s === 'kg') return '图谱'
  return s || '系统'
}

const fmtTime = (v: any) => {
  const s = (v || '').toString().trim()
  if (!s) return '—'
  return s.replace('T', ' ').replace('Z', '')
}

/** 用户反馈里的短评与影评正文不一致时一并展示（例如在详情写过短评，又在广场写了更长影评） */
const extraFeedbackNote = (r: { content?: string; feedback_note?: string | null }) => {
  const note = (r.feedback_note ?? '').toString().trim()
  if (!note) return ''
  const main = (r.content ?? '').toString().trim()
  if (note === main) return ''
  return note
}

const formatActor = (actor: any) => {
  if (!actor) return ''

  // 兼容：后端可能返回 array / JSON 字符串 / 普通字符串
  let raw = ''
  if (Array.isArray(actor)) raw = actor.map((x) => (x ?? '').toString().trim()).filter(Boolean).join('、')
  else raw = actor.toString().trim()
  if (!raw) return ''

  // 去掉常见前缀
  raw = raw.replace(/^主演[:：]\s*/g, '').trim()

  // 优先兼容：JSON 数组字符串（不要被后续清洗把 [] 整段删掉）
  let jsonArr: any[] | null = null
  if (raw.startsWith('[') && raw.endsWith(']')) {
    try {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr)) jsonArr = arr
    } catch {
      // ignore
    }
  }

  // 只保留名字：去掉括号内容等杂字符；最多展示 5 个
  const cleaned = raw
    .replace(/（.*?）/g, ' ')
    .replace(/\(.*?\)/g, ' ')
    // 不整段删除 []/【】 内内容，只去掉括号字符本身
    .replace(/[\[\]【】]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  let tokens = cleaned.split(/[,/、，；;|]/g).map((x: string) => x.trim()).filter(Boolean)
  if (jsonArr) {
    tokens = jsonArr.map((x: any) => (x ?? '').toString().trim()).filter(Boolean)
  }

  const names: string[] = []
  for (const t of tokens) {
    // 提取“像名字”的片段：中文/英文/中点/空格/点/连字符
    const m = t.match(/[\u4e00-\u9fa5A-Za-z·.\- ]+/g)
    const n = (m?.join('') || '').trim().replace(/\s+/g, ' ')
    if (!n) continue
    if (!names.includes(n)) names.push(n)
    if (names.length >= 5) break
  }

  // 兜底：避免清洗过头导致空白
  if (!names.length) {
    const fallback = tokens
      .map((x) => x.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .slice(0, 5)
    return fallback.join(' / ')
  }
  return names.join(' / ')
}

const movieQuery = ref('')
const pickedMovie = ref<any | null>(null)
const rating = ref<number | null>(null)
const content = ref('')
const posting = ref(false)
const postVisible = ref(false)

const searchQuery = ref('')
const searchBlock = ref<any | null>(null)

const fetchMovieSuggestions = async (q: string, cb: (arr: any[]) => void) => {
  const qq = (q || '').trim()
  if (qq.length < 2) return cb([])
  try {
    const res = await reviewApi.searchMovies(qq, 10)
    cb(res.data.movies || [])
  } catch {
    cb([])
  }
}

const onSelectMovie = (m: any) => {
  pickedMovie.value = m
}

const onSelectSearchMovie = async (m: any) => {
  if (!m?.movie_name) return
  searchQuery.value = m.display || m.movie_name
  await loadSearchBlock(m.movie_name, m.source)
}

const submitReview = async () => {
  if (!userStore.userInfo) {
    ElMessage.warning('请先登录')
    return
  }
  if (isMeMutedNow()) {
    const until = myMutedUntilText()
    const reason = myMuteReasonText()
    const msg = `你已被禁言${until ? `，至 ${until}` : ''}${reason ? `。原因：${reason}` : ''}`
    ElMessage.error(msg || '你已被禁言，无法发布影评')
    return
  }
  if (!pickedMovie.value) {
    ElMessage.warning('请先选择系统已有电影')
    return
  }
  const txt = (content.value || '').trim()
  if (!txt) {
    ElMessage.warning('请填写影评内容')
    return
  }
  posting.value = true
  try {
    await reviewApi.upsertReview({
      movie_name: pickedMovie.value.movie_name,
      movie_source: pickedMovie.value.source,
      rating: rating.value,
      content: txt
    })
    ElMessage.success('已发布')
    await loadBoard()
    // 若当前正在搜索该电影，则同步刷新搜索块
    const nm = (pickedMovie.value.movie_name || '').trim()
    if (searchBlock.value?.movie_name === nm) {
      await loadSearchBlock(nm, pickedMovie.value.source)
    }
    postVisible.value = false
  } catch (e: any) {
    ElMessage.error(_friendlyApiError(e, '发布失败'))
  } finally {
    posting.value = false
  }
}

const movieBlocks = ref<any[]>([])
const page = ref(1)
const pageSize = 8
const totalMovies = ref(0)
const loading = ref(false)
const posterMap = ref<Record<string, string>>({})
const genresMap = ref<Record<string, string>>({})
const scoreMap = ref<Record<string, string>>({})

const openPostDialog = () => {
  if (!userStore.userInfo) {
    ElMessage.warning('请先登录')
    return
  }
  postVisible.value = true
}

const loadBoard = async () => {
  loading.value = true
  try {
    const res = await reviewApi.getBoard(pageSize, (page.value - 1) * pageSize, 5)
    const arr = (res.data.movies || []) as any[]
    totalMovies.value = Number(res.data.total_movies || 0)
    movieBlocks.value = arr.map((m) => ({
      ...m,
      poster_url: posterMap.value[m.movie_name] || '',
      genres: genresMap.value[m.movie_name] || '',
      score: scoreMap.value[m.movie_name] || '',
      loading_more: false
    }))
    await hydrateMovieMetaForBlocks()
    // 默认展示回复：对当前页内有 comment_count 的影评懒加载一次回复列表
    for (const blk of movieBlocks.value || []) {
      for (const r of blk.reviews || []) {
        if (Number(r.comment_count || 0) > 0) ensureRepliesLoaded(r)
      }
    }
  } catch (e: any) {
    ElMessage.error(_friendlyApiError(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

const onPageChange = (p: number) => {
  page.value = p
  loadBoard()
}

const hydrateMovieMetaForBlocks = async () => {
  const movies = Array.from(new Set((movieBlocks.value || []).map((m) => m.movie_name).filter(Boolean)))
  for (const nm of movies.slice(0, 40)) {
    if (posterMap.value[nm] || genresMap.value[nm] || scoreMap.value[nm]) continue
    try {
      const res = await movieApi.getMovieDetailNoTrack(nm, 'douban')
      if (res.data?.poster_url) posterMap.value = { ...posterMap.value, [nm]: res.data.poster_url }
      const g = res.data?.data?.type || ''
      if (g) genresMap.value = { ...genresMap.value, [nm]: g }
      const sc = res.data?.data?.score ? String(res.data.data.score) : ''
      if (sc) scoreMap.value = { ...scoreMap.value, [nm]: sc }
    } catch {
      /* ignore */
    }
  }
  movieBlocks.value = (movieBlocks.value || []).map((m: any) => ({
    ...m,
    poster_url: posterMap.value[m.movie_name] || m.poster_url || '',
    genres: genresMap.value[m.movie_name] || m.genres || '',
    score: scoreMap.value[m.movie_name] || m.score || ''
  }))
}

const clearSearch = () => {
  searchBlock.value = null
  searchQuery.value = ''
}

const loadSearchBlock = async (movieName: string, source?: string) => {
  const name = (movieName || '').trim()
  if (!name) return
  const blk: any = { movie_name: name, movie_source: source || 'douban', reviews: [], poster_url: '', genres: '', score: '' }
  searchBlock.value = blk
  try {
    const res = await reviewApi.listByMovie(name, 5, 0, 'like_count', true)
    blk.reviews = res.data.reviews || []
  } catch {
    blk.reviews = []
  }
  try {
    const md = await movieApi.getMovieDetailNoTrack(name, 'douban')
    blk.poster_url = md.data?.poster_url || ''
    blk.genres = md.data?.data?.type || ''
    blk.score = md.data?.data?.score ? String(md.data.data.score) : ''
  } catch {
    /* ignore */
  }
  searchBlock.value = { ...blk }
  for (const r of blk.reviews || []) {
    if (Number(r.comment_count || 0) > 0) ensureRepliesLoaded(r)
  }
}

const openPostDialogWithMovie = (blk: any) => {
  pickedMovie.value = { movie_name: blk.movie_name, source: blk.movie_source || 'douban', display: blk.movie_name }
  movieQuery.value = blk.movie_name
  postVisible.value = true
}

const deleteMyReview = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除你的影评？', '提示', { type: 'warning' })
    await reviewApi.deleteReview(id)
    ElMessage.success('已删除')
    loadBoard()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const adminDeleteReview = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除该影评？（管理员操作）', '提示', { type: 'warning' })
    await adminApi.deleteReviewAdmin(id)
    ElMessage.success('已删除')
    loadBoard()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const toggleReviewLike = async (r: any, movieName?: string) => {
  if (!userStore.userInfo) {
    ElMessage.warning('请先登录')
    return
  }
  const id = Number(r?.id || 0)
  if (!id) return
  const likedNow = !!r.my_liked
  // 乐观更新：立刻反馈按钮高亮与数字变化
  r.my_liked = !likedNow
  r.like_count = Math.max(0, Number(r.like_count || 0) + (likedNow ? -1 : 1))
  try {
    if (likedNow) await reviewApi.unlike('review', id)
    else await reviewApi.like('review', id)
  } catch (e: any) {
    // 回滚
    r.my_liked = likedNow
    r.like_count = Math.max(0, Number(r.like_count || 0) + (likedNow ? 1 : -1))
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    // 局部刷新：如果能定位到电影块，只刷新该电影的当前展开数量
    if (movieName) {
      const blk = (movieBlocks.value || []).find((x) => x.movie_name === movieName)
      const want = blk?.reviews?.length || 5
      try {
        const res = await reviewApi.listByMovie(movieName, want, 0, 'like_count', true)
        if (blk) blk.reviews = res.data.reviews || []
      } catch {
        loadBoard()
      }
    } else {
      loadBoard()
    }
  }
}

const loadMoreForMovie = async (movieName: string) => {
  const blk = (movieBlocks.value || []).find((x) => x.movie_name === movieName)
  if (!blk) return
  if (blk.loading_more) return
  blk.loading_more = true
  try {
    const offset = Number(blk.reviews?.length || 0)
    const res = await reviewApi.listByMovie(movieName, 10, offset, 'like_count', true)
    const more = res.data.reviews || []
    blk.reviews = [...(blk.reviews || []), ...more]
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    blk.loading_more = false
  }
}

const inlineReplyText = ref<Record<number, string>>({})
const inlineReplyLoading = ref<Record<number, boolean>>({})
const replyParentId = ref<Record<number, number | null>>({})
const replyPlaceholder = ref<Record<number, string>>({})

const replyMap = ref<Record<number, any[]>>({})
const replyLoading = ref<Record<number, boolean>>({})
const replyLoaded = ref<Record<number, boolean>>({})
const replyBoxOpen = ref<Record<number, boolean>>({})

const ensureRepliesLoaded = async (reviewRow: any) => {
  const rid = Number(reviewRow?.id || 0)
  if (!rid) return
  if (inlineReplyText.value[rid] === undefined) inlineReplyText.value = { ...inlineReplyText.value, [rid]: '' }
  if (replyLoaded.value[rid]) return

  replyLoading.value = { ...replyLoading.value, [rid]: true }
  try {
    const res = await reviewApi.getReviewDetail(rid)
    replyMap.value = { ...replyMap.value, [rid]: res.data?.comments || [] }
    replyLoaded.value = { ...replyLoaded.value, [rid]: true }
  } catch {
    replyMap.value = { ...replyMap.value, [rid]: [] }
    replyLoaded.value = { ...replyLoaded.value, [rid]: true }
  } finally {
    replyLoading.value = { ...replyLoading.value, [rid]: false }
  }
}

const toggleReplyBox = async (reviewRow: any) => {
  const rid = Number(reviewRow?.id || 0)
  if (!rid) return
  const open = !!replyBoxOpen.value[rid]
  replyBoxOpen.value = { ...replyBoxOpen.value, [rid]: !open }
  if (!open) {
    replyParentId.value = { ...replyParentId.value, [rid]: null }
    replyPlaceholder.value = { ...replyPlaceholder.value, [rid]: '写下你的回复…' }
    await ensureRepliesLoaded(reviewRow)
  }
}

const prepareReplyTo = (reviewId: number, commentRow: any) => {
  const rid = Number(reviewId || 0)
  if (!rid) return
  const cid = Number(commentRow?.id || 0)
  replyBoxOpen.value = { ...replyBoxOpen.value, [rid]: true }
  replyParentId.value = { ...replyParentId.value, [rid]: cid || null }
  const uname = (commentRow?.username || '').toString().trim()
  replyPlaceholder.value = { ...replyPlaceholder.value, [rid]: uname ? `回复 @${uname} …` : '写下你的回复…' }
}

const deleteMyReply = async (commentId: number, reviewRow: any) => {
  try {
    await ElMessageBox.confirm('确定删除该回复？', '提示', { type: 'warning' })
    await reviewApi.deleteComment(commentId)
    ElMessage.success('已删除')
    const rid = Number(reviewRow?.id || 0)
    if (rid) {
      const cur = replyMap.value[rid] || []
      replyMap.value = { ...replyMap.value, [rid]: cur.filter((x) => Number(x?.id) !== Number(commentId)) }
      reviewRow.comment_count = Math.max(0, Number(reviewRow.comment_count || 0) - 1)
    }
    loadBoard()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const adminDeleteReply = async (commentId: number, reviewRow: any) => {
  try {
    await ElMessageBox.confirm('确定删除该回复？（管理员操作）', '提示', { type: 'warning' })
    await adminApi.deleteReviewCommentAdmin(commentId)
    ElMessage.success('已删除')
    const rid = Number(reviewRow?.id || 0)
    if (rid) {
      const cur = replyMap.value[rid] || []
      replyMap.value = { ...replyMap.value, [rid]: cur.filter((x) => Number(x?.id) !== Number(commentId)) }
      reviewRow.comment_count = Math.max(0, Number(reviewRow.comment_count || 0) - 1)
    }
    loadBoard()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const adminMuteUser = async (userId: number) => {
  try {
    let hours = 24
    let reason = '刷屏'
    const REASONS = ['刷屏', '辱骂', '广告', '其他']

    await ElMessageBox({
      title: '影评禁言',
      message: h('div', { style: 'display:flex;flex-direction:column;gap:10px;' }, [
        h('div', { style: 'font-size:12px;opacity:.75;' }, '禁言时长（小时）。例如 2/12/24；输入 0 视为解除禁言。'),
        h('div', { style: 'display:flex;align-items:center;gap:10px;' }, [
          h('div', { style: 'width:84px;font-weight:700;' }, '时长'),
          h('input', {
            type: 'number',
            min: 0,
            step: 1,
            value: String(hours),
            style:
              'flex:1;border:1px solid var(--el-border-color);border-radius:8px;padding:8px 10px;background:var(--el-fill-color-blank);color:var(--el-text-color-primary);',
            onInput: (e: any) => {
              const v = Number(e?.target?.value ?? 0)
              hours = Number.isFinite(v) ? Math.max(0, Math.floor(v)) : 0
            }
          })
        ]),
        h('div', { style: 'display:flex;align-items:center;gap:10px;' }, [
          h('div', { style: 'width:84px;font-weight:700;' }, '原因'),
          h(
            'select',
            {
              value: reason,
              style:
                'flex:1;border:1px solid var(--el-border-color);border-radius:8px;padding:8px 10px;background:var(--el-fill-color-blank);color:var(--el-text-color-primary);',
              onChange: (e: any) => {
                const v = String(e?.target?.value ?? '').trim()
                reason = REASONS.includes(v) ? v : '其他'
              }
            },
            REASONS.map((r) => h('option', { value: r }, r))
          )
        ])
      ]),
      showCancelButton: true,
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      closeOnClickModal: false
    })

    if (!hours) {
      await adminApi.unmuteUserReviews(userId)
      ElMessage.success('已解除禁言')
      return
    }
    await adminApi.muteUserReviews(userId, { duration_hours: hours, reason })
    ElMessage.success(`已禁言 ${hours} 小时`)
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const adminUnmuteUser = async (userId: number) => {
  try {
    await adminApi.unmuteUserReviews(userId)
    ElMessage.success('已解除禁言')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const submitInlineReply = async (reviewRow: any, _movieName: string) => {
  if (!userStore.userInfo) {
    ElMessage.warning('请先登录')
    return
  }
  if (isMeMutedNow()) {
    const until = myMutedUntilText()
    const reason = myMuteReasonText()
    const msg = `你已被禁言${until ? `，至 ${until}` : ''}${reason ? `。原因：${reason}` : ''}`
    ElMessage.error(msg || '你已被禁言，无法执行该操作')
    return
  }
  const rid = Number(reviewRow?.id || 0)
  if (!rid) return
  const txt = (inlineReplyText.value[rid] || '').trim()
  if (!txt) return
  inlineReplyLoading.value = { ...inlineReplyLoading.value, [rid]: true }
  try {
    await reviewApi.addComment(rid, { content: txt, parent_id: replyParentId.value[rid] ?? null })
    inlineReplyText.value = { ...inlineReplyText.value, [rid]: '' }
    reviewRow.comment_count = Number(reviewRow.comment_count || 0) + 1
    const d = await reviewApi.getReviewDetail(rid)
    replyMap.value = { ...replyMap.value, [rid]: d.data?.comments || [] }
    replyLoaded.value = { ...replyLoaded.value, [rid]: true }
    replyBoxOpen.value = { ...replyBoxOpen.value, [rid]: false }
    replyParentId.value = { ...replyParentId.value, [rid]: null }
    replyPlaceholder.value = { ...replyPlaceholder.value, [rid]: '写下你的回复…' }
  } catch (e: any) {
    ElMessage.error(_friendlyApiError(e, '回复失败'))
  } finally {
    inlineReplyLoading.value = { ...inlineReplyLoading.value, [rid]: false }
  }
}

const movieDetailVisible = ref(false)
const movieDetailLoading = ref(false)
const movieDetail = ref<any | null>(null)
const currentMovieName = ref('')

const openMovieDetail = async (movieName: string) => {
  const name = (movieName || '').trim()
  if (!name) return
  currentMovieName.value = name
  movieDetailVisible.value = true
  movieDetailLoading.value = true
  movieDetail.value = null
  const sourceGuess = (movieBlocks.value.find((x) => x.movie_name === name)?.movie_source || 'douban') as string
  try {
    const res = await movieApi.getMovieDetailNoTrack(name, sourceGuess)
    movieDetail.value = res.data
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
    movieDetailVisible.value = false
  } finally {
    movieDetailLoading.value = false
  }
}

async function focusReviewFromRoute() {
  const raw = route.query.review
  const rid = Number(Array.isArray(raw) ? raw[0] : raw || 0)
  if (!rid) return
  try {
    const res = await reviewApi.getReviewDetail(rid)
    const rev = res.data?.review
    if (!rev) return
    const nm = (rev.movie_name || '').trim()
    if (!nm) return
    await loadSearchBlock(nm, rev.movie_source || 'douban')
    await nextTick()
    let row = searchBlock.value?.reviews?.find((x: any) => Number(x.id) === rid)
    if (!row && searchBlock.value) {
      const synth: any = {
        id: rev.id,
        user_id: rev.user_id,
        username: rev.username,
        movie_name: rev.movie_name,
        movie_source: rev.movie_source,
        rating: rev.rating,
        content: rev.content,
        created_at: rev.created_at,
        updated_at: rev.updated_at,
        comment_count: (res.data?.comments || []).length,
        like_count: res.data?.review_like_count ?? 0,
        my_liked: false,
        feedback_note: rev.feedback_note
      }
      searchBlock.value.reviews = [synth, ...(searchBlock.value.reviews || [])]
      row = synth
    }
    if (row) {
      replyBoxOpen.value = { ...replyBoxOpen.value, [rid]: true }
      replyMap.value = { ...replyMap.value, [rid]: res.data?.comments || [] }
      replyLoaded.value = { ...replyLoaded.value, [rid]: true }
    }
  } catch {
    /* 忽略：影评已删或网络错误 */
  }
}

onMounted(() => {
  loadBoard()
  focusReviewFromRoute()
})

watch(
  () => route.query.review,
  () => {
    focusReviewFromRoute()
  }
)
</script>

<style scoped>
/* ReviewsView 样式 */
.reviews-page {
  padding: 8px 20px 44px;
  max-width: 1180px;
  margin: 0 auto;
  position: relative;
}

/* 影评页两侧氛围背景（只在两侧空白显示，不影响操作） */
.reviews-page::before {
  content: '';
  position: fixed;
  inset: 64px 0 0 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.2;
  filter: brightness(1.1) contrast(1.06) saturate(1.06);
  background-image:
    radial-gradient(520px 420px at 18% 18%, rgba(99, 102, 241, 0.16), transparent 60%),
    radial-gradient(520px 420px at 82% 18%, rgba(168, 85, 247, 0.12), transparent 60%);
  background-repeat: no-repeat;
  background-size: auto, auto;
  background-position: 18% 18%, 82% 18%;
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

.rv-bg {
  position: fixed;
  inset: 64px 0 0 0;
  pointer-events: none;
  z-index: 0;
}

.rv-bg-left,
.rv-bg-left-blur,
.rv-bg-right {
  position: fixed;
  inset: 0px 0 0 0;
  pointer-events: none;
  z-index: 0;
  background-image: url('/api/background/漫威.jpg');
  background-repeat: no-repeat;
  background-size: auto 86%;
  background-position: 0 80%;
  opacity: 0.22;
  filter: brightness(1.1) contrast(1.06) saturate(1.06);
}

/* 左侧：只显示左半边，右侧直接截断 */
.rv-bg-left {
  background-position: -3% 50%;
  -webkit-mask-image:
    linear-gradient(
      90deg,
      rgba(0, 0, 0, 1) 0%,
      rgba(0, 0, 0, 1) 70%,
      rgba(0, 0, 0, 0) 72%,
      rgba(0, 0, 0, 0) 100%
    ),
    linear-gradient(180deg, rgba(0, 0, 0, 0) 0%, rgba(0, 0, 0, 1) 10%, rgba(0, 0, 0, 1) 90%, rgba(0, 0, 0, 0) 100%);
  mask-image:
    linear-gradient(
      90deg,
      rgba(0, 0, 0, 1) 0%,
      rgba(0, 0, 0, 1) 70%,
      rgba(0, 0, 0, 0) 72%,
      rgba(0, 0, 0, 0) 100%
    ),
    linear-gradient(180deg, rgba(0, 0, 0, 0) 0%, rgba(0, 0, 0, 1) 10%, rgba(0, 0, 0, 1) 90%, rgba(0, 0, 0, 0) 100%);
}

/* 左侧的右半部：模糊过渡，并在最右透明化 */
.rv-bg-left-blur {
  background-position: -1% 40%;
  opacity: 0.18;
  filter: blur(18px) brightness(1.08) contrast(1.04) saturate(1.04);
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 46%,
    rgba(0, 0, 0, 1) 60%,
    rgba(0, 0, 0, 1) 90%,
    rgba(0, 0, 0, 0) 100%
  ),
  linear-gradient(180deg, rgba(0, 0, 0, 0) 0%, rgba(0, 0, 0, 1) 12%, rgba(0, 0, 0, 1) 88%, rgba(0, 0, 0, 0) 100%);
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 46%,
    rgba(0, 0, 0, 1) 60%,
    rgba(0, 0, 0, 1) 90%,
    rgba(0, 0, 0, 0) 100%
  ),
  linear-gradient(180deg, rgba(0, 0, 0, 0) 0%, rgba(0, 0, 0, 1) 12%, rgba(0, 0, 0, 1) 88%, rgba(0, 0, 0, 0) 100%);
}

/* 右侧：只显示右半边；左侧与中间透明化 */
.rv-bg-right {
  background-image: url('/api/background/漫威右.jpg');
  background-position: 108% 50%;
  opacity: 0.16;
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 50%,
    rgba(0, 0, 0, 1) 56%,
    rgba(0, 0, 0, 1) 100%
  ),
  linear-gradient(180deg, rgba(0, 0, 0, 0) 0%, rgba(0, 0, 0, 1) 10%, rgba(0, 0, 0, 1) 90%, rgba(0, 0, 0, 0) 100%);
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 50%,
    rgba(0, 0, 0, 1) 56%,
    rgba(0, 0, 0, 1) 100%
  ),
  linear-gradient(180deg, rgba(0, 0, 0, 0) 0%, rgba(0, 0, 0, 1) 10%, rgba(0, 0, 0, 1) 90%, rgba(0, 0, 0, 0) 100%);
}

.reviews-page > * {
  position: relative;
  z-index: 1;
}

/* 顶部横幅（标题 + 说明 + 搜索/发布/刷新） */
.rv-hero {
  position: relative;
  margin: 0 -4px 24px;
  padding: 28px 32px;
  border-radius: 22px;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.54), rgba(168, 85, 247, 0.1));
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.08) inset,
    0 22px 60px rgba(0, 0, 0, 0.28);
}
.rv-hero::after {
  content: '';
  position: absolute;
  inset: -30%;
  background: radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.1), transparent 45%);
  pointer-events: none;
}
.rv-hero-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: nowrap;
  position: relative;
  z-index: 1;
}
.hero-left {
  min-width: 0;
}
.hero-left h1 {
  margin: 0 0 8px;
  color: rgba(248, 250, 252, 0.96);
  font-size: clamp(1.35rem, 2.5vw, 1.75rem);
  letter-spacing: -0.02em;
  font-weight: 900;
}
.hero-left p {
  margin: 0;
  color: rgba(226, 232, 240, 0.86);
  font-size: 14px;
  line-height: 1.55;
  max-width: 640px;
}
.rv-mute-banner {
  margin-top: 10px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 12px;
  border: 1px solid rgba(248, 113, 113, 0.35);
  background: rgba(248, 113, 113, 0.12);
  color: rgba(254, 242, 242, 0.92);
  font-size: 13px;
  font-weight: 800;
}
.hero-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: nowrap;
}

/* 主体玻璃卡片容器（el-card） */
.glass.panel {
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  background: rgba(255, 255, 255, 0.28) !important;
  backdrop-filter: blur(18px) saturate(1.12);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.06) inset,
    0 22px 70px rgba(0, 0, 0, 0.28) !important;
}

.dlg {
  padding: 8px 0;
}

/* 详情弹窗壳：styles/movie-detail-dialog.css */

.dlg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.dlg-head-title {
  position: relative;
  z-index: 1;
  min-width: 0;
}

.dlg-h1 {
  font-size: 18px;
  font-weight: 900;
  letter-spacing: -0.02em;
  line-height: 1.25;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: min(720px, 78vw);
}

.dlg-hmeta {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 800;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.24);
  backdrop-filter: blur(10px);
}

.pill.soft {
  opacity: 0.95;
  font-weight: 700;
}

.pill.score {
  background: rgba(253, 230, 138, 0.18);
  border-color: rgba(253, 230, 138, 0.32);
}

.dlg-close {
  position: relative;
  z-index: 1;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(15, 23, 42, 0.18);
  color: #fff;
  border-radius: 999px;
  width: 40px;
  height: 40px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.15s, background 0.15s, border-color 0.15s;
}

.dlg-close:hover {
  transform: translateY(-1px);
  background: rgba(15, 23, 42, 0.28);
  border-color: rgba(255, 255, 255, 0.35);
}

/* 影评广场主体：按电影分块的列表 */
.board {
  display: grid;
  gap: 16px;
}
.mv-layout {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 0;
}
@media (max-width: 980px) {
  .mv-layout {
    grid-template-columns: 1fr;
  }
}
.mv-left {
  border-right: 1px solid rgba(255, 255, 255, 0.1);
}
@media (max-width: 980px) {
  .mv-left {
    border-right: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }
}
.mv-right {
  padding: 12px 12px;
  display: flex;
  justify-content: flex-start;
}
.mv-right-inner {
  width: 100%;
  max-width: 760px;
}

/* 单个电影块外框（左电影信息 + 右评论区） */
.mv-section {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
  overflow: hidden;
}
.mv-section.search-section {
  border-color: rgba(168, 85, 247, 0.38);
  box-shadow: 0 0 0 1px rgba(168, 85, 247, 0.08) inset;
}
.mv-head {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 14px;
  padding: 14px;
  background: rgba(15, 23, 42, 0.18);
}
@media (max-width: 860px) {
  .mv-head {
    grid-template-columns: 1fr;
  }
}
.mv-poster-lg {
  width: 120px;
  aspect-ratio: 2 / 3;
  border-radius: 14px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.mv-poster-lg img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.mv-ph {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: rgba(203, 213, 225, 0.72);
}
.mv-body {
  min-width: 0;
}
.mv-info {
  min-width: 0;
}
.mv-title-lg {
  font-weight: 900;
  color: rgba(248, 250, 252, 0.96);
  line-height: 1.25;
  font-size: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mv-sub-lg {
  margin-top: 10px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.mv-meta {
  margin-top: 10px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.mv-actions {
  margin-top: 10px;
}
.pill-mini {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(15, 23, 42, 0.32);
  font-weight: 800;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.9);
}
.pill-mini.soft {
  font-weight: 700;
  opacity: 0.9;
}

/* 右侧评论列表容器 */
.feed {
  display: grid;
  gap: 0;
}
.rv-card {
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding: 14px 10px;
}
.rv-card:first-child {
  padding-top: 6px;
}
.rv-card:last-child {
  border-bottom: none;
  padding-bottom: 6px;
}
.rv-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.rv-movie-title {
  font-weight: 900;
  color: rgba(248, 250, 252, 0.96);
}
.rv-src {
  margin-left: 8px;
}
.rv-user {
  color: rgba(203, 213, 225, 0.82);
  font-size: 12px;
  font-weight: 800;
}

/* 评论/回复统一“用户名 + 气泡”布局（核心对齐模块） */
.msg-line {
  display: flex;
  gap: 1px;
  align-items: flex-start;
  min-width: 0;
  font-size: 15px;
  line-height: 1.5;
}

/* 用户名：这里会影响“用户名和气泡是否同一行、是否贴左” */
.msg-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 900;
  font-size: 17px;
  color: rgba(226, 232, 240, 0.92);
  white-space: nowrap;
  justify-content: flex-start;
}
.msg-name::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.95), rgba(99, 102, 241, 0.95));
  box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.12);
}
.msg-colon {
  color: rgba(203, 213, 225, 0.78);
  white-space: nowrap;
}

/* 气泡：宽度是否撑到右侧评分列左边，取决于这里的 flex: 1 与外层 .rv-body 网格 */
.msg-line-sub {
  margin-top: 8px;
  opacity: 0.95;
}

.sub-lbl {
  color: rgba(100, 116, 139, 0.95);
  font-weight: 700;
}

.msg-bubble-sub {
  background: rgba(241, 245, 249, 0.95);
  border: 1px dashed rgba(148, 163, 184, 0.45);
}

.msg-bubble {
  flex: 1;
  min-width: 0;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(15, 23, 42, 0.12);
  padding: 4px 10px;
  color: rgba(226, 232, 240, 0.88);
  white-space: pre-wrap;
  word-break: break-word;
  margin-right: 15px;
}
.reply-indent {
  margin-left: 40px;
}

/* 影评上半部分：左气泡、右评分列 */
.rv-body {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  align-items: start;
}

/* 右侧评分列（你若想把操作放“评分下面”，也可以放到模板里的 .rv-side 内） */
.rv-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}
.rv-side-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
/* legacy rv-* name styles removed (replaced by msg-*) */
.rv-rating-side {
  white-space: nowrap;
  font-weight: 800;
  color: rgba(41, 117, 216, 0.9);
  padding-top: 5px;
}

/* 影评底部一行：左边时间/删除，右边点赞/回复 */
.rv-foot {
  margin-top: 0px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0px;
  flex-wrap: wrap;
}
.rv-meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: rgba(203, 213, 225, 0.72);
  font-size: 12px;
  font-weight: 700;
}
.rv-time {
  opacity: 0.95;
}
.rv-score {
  font-weight: 900;
  color: rgba(226, 232, 240, 0.88);
}
.rv-score.soft {
  font-weight: 800;
  color: rgba(203, 213, 225, 0.76);
}
.rv-actions {
  display: inline-flex;
  align-items: center;
  gap: 1px;
}
.rv-rating-right {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
}
.rv-del {
  margin-left: 4px;
  color: rgba(255, 255, 255, 0.92);
}
.rv-actions :deep(.el-button) {
  font-weight: 900;
  color: rgba(255, 255, 255, 0.92);
}
.rv-actions :deep(.el-button:hover) {
  color: rgba(168, 85, 247, 0.9);
}
.rv-actions :deep(.el-button.liked) {
  color: rgba(168, 85, 247, 0.98);
}
.rv-actions :deep(.el-button.liked:hover) {
  color: rgba(129, 140, 248, 0.98);
}

.more-row {
  padding: 12px 14px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.pager {
  display: flex;
  justify-content: center;
  padding: 8px 0 4px;
}

/* 与 BrowseView 的分页一致（复制同款样式，避免跨页面 scoped 样式失效） */
.browse-pagination {
  flex: 1;
  justify-content: flex-end;
  min-width: 0;
}

.browse-pagination :deep(.el-pagination) {
  flex-wrap: wrap;
  justify-content: flex-end;
  row-gap: 8px;
}

.browse-pagination :deep(.el-pagination__total),
.browse-pagination :deep(.el-pagination__jump),
.browse-pagination :deep(.el-input__inner) {
  color: rgba(226, 232, 240, 0.88);
}

.browse-pagination :deep(.btn-prev),
.browse-pagination :deep(.btn-next),
.browse-pagination :deep(.el-pager li) {
  background: rgba(2, 6, 23, 0.35) !important;
  color: rgba(241, 245, 249, 0.92) !important;
}

.browse-pagination :deep(.el-pagination__sizes .el-select .el-input__wrapper) {
  background: rgba(2, 6, 23, 0.35);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
}

/* 分页「前往」输入框 */
.browse-pagination :deep(.el-pagination__editor .el-input__wrapper),
.browse-pagination :deep(.el-pagination__editor .el-select__wrapper) {
  background: rgba(2, 6, 23, 0.45) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.14) inset !important;
}

.browse-pagination :deep(.el-pagination__editor .el-input__inner) {
  color: rgba(248, 250, 252, 0.95) !important;
}

.browse-pagination :deep(.el-pagination__editor .el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.45) inset !important;
}

.browse-bottom {
  margin-top: 18px;
  display: flex;
  justify-content: center;
}

.browse-bottom .browse-pagination :deep(.el-pagination) {
  justify-content: center;
}

@media (max-width: 900px) {
  .browse-pagination :deep(.el-pagination) {
    justify-content: center;
  }
}
.inner-empty {
  padding: 18px 1px 22px;
}
.reply-box {
  /* 点击“回复”后的输入区：不要外部框，只保留输入框本体 */
  margin: 10px 0 0px;
  padding: 0px;
  border: none;
  background: transparent;
}

/* 回复输入：同一行（输入框 + 收起 + 发布） */
.reply-rowline {
  display: flex;
  gap: 2px;
  align-items: center;
  margin-left: 40px;
}
.reply-link {
  font-weight: 500;
  color: rgba(255, 255, 255, 0.92) !important;
}
.reply-link:hover {
  color: rgba(255, 255, 255, 0.98) !important;
}

/* 回复区“删除”(danger link) 也统一为白色 */
.reply-foot :deep(.el-button.is-link.el-button--danger) {
  color: rgba(255, 255, 255, 0.92) !important;
}
.reply-foot :deep(.el-button.is-link.el-button--danger:hover) {
  color: rgba(255, 255, 255, 0.98) !important;
}
.reply-input {
  flex: 1;
  min-width: 0;
}
.reply-input :deep(.el-input__wrapper) {
  /* 让“回复输入框”看起来像 msg-bubble 的可编辑版本 */
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  background: rgba(15, 23, 42, 0.12) !important;
  box-shadow: none !important;
  padding: 2px 8px !important;
}
.reply-box :deep(.el-input__wrapper) {
  /* 保留 reply-box 内其他 el-input 的暗色基调（但 reply-input 自己会覆盖成气泡样式） */
  background: rgba(15, 23, 42, 0.22) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.14) inset !important;
  border-radius: 12px;
}
.reply-box :deep(.el-input__inner) {
  color: rgba(226, 232, 240, 0.92) !important;
}
.reply-box :deep(.el-input__inner::placeholder) {
  color: rgba(203, 213, 225, 0.62) !important;
}

/* 回复列表容器（默认展示） */
.reply-thread {
  margin-top: 10px;
  padding-left: 40px;
}
.reply-list {
  margin: 8px 0 10px;
  padding: 0;
  border-radius: 0px;
  border: none;
  background: transparent;
}
.reply-row + .reply-row {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed rgba(255, 255, 255, 0.14);
}

/* 回复底部一行：时间 + 回复/删除（并与 reply-indent 对齐） */
.reply-foot {
  margin-top: 2px;
  display: flex;
  gap: 8px;
  align-items: center;
  margin-left: 40px;
  color: rgba(203, 213, 225, 0.72);
  font-size: 13px;
  font-weight: 700;
}
.reply-time {
  opacity: 0.95;
}
.muted {
  color: rgba(203, 213, 225, 0.76);
  font-size: 12px;
  font-weight: 700;
}

.dlg-left {
  position: sticky;
  top: 0;
}
.search-ac {
  width: min(420px, 42vw);
}
.search-ac :deep(.el-input__wrapper) {
  background: rgba(15, 23, 42, 0.26) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.14) inset !important;
  border-radius: 999px;
}
.search-ac :deep(.el-input__inner) {
  color: rgba(226, 232, 240, 0.92) !important;
}
.search-ac :deep(.el-input__inner::placeholder) {
  color: rgba(203, 213, 225, 0.6) !important;
}
@media (max-width: 860px) {
  .rv-hero-inner {
    flex-wrap: wrap;
    align-items: flex-start;
  }
  .hero-actions {
    flex-wrap: wrap;
  }
  .search-ac {
    width: 100%;
  }
}
.sort-sel {
  width: 160px;
}

.post-grid {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  gap: 14px;
}
@media (max-width: 980px) {
  .post-grid {
    grid-template-columns: 1fr;
  }
}
.field-label {
  font-weight: 800;
  color: rgba(226, 232, 240, 0.9);
  margin-bottom: 8px;
}
.picked {
  margin-top: 10px;
  display: flex;
  gap: 10px;
  align-items: center;
}
.picked-title {
  color: rgba(248, 250, 252, 0.92);
  font-weight: 800;
}
.picked-alert {
  margin-top: 10px;
}
.post-actions {
  margin-top: 12px;
}
.muted {
  color: rgba(203, 213, 225, 0.72);
}

.rv-content {
  white-space: pre-wrap;
  line-height: 1.7;
  color: rgba(15, 23, 42, 0.9);
}
.rv-actions {
  margin-top: 10px;
  display: flex;
  gap: 10px;
}
.cnt {
  margin-left: 6px;
  opacity: 0.8;
}
.comment-box {
  margin-top: 14px;
}
.comment-list {
  margin-top: 14px;
}
.c-row {
  padding: 10px 0;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
}
.c-meta {
  display: flex;
  gap: 10px;
  color: rgba(51, 65, 85, 0.78);
  font-size: 12px;
}
.c-user {
  font-weight: 900;
}
.c-body {
  margin-top: 6px;
  color: rgba(15, 23, 42, 0.9);
  white-space: pre-wrap;
}
.c-actions {
  margin-top: 6px;
  display: flex;
  gap: 10px;
}
</style>

