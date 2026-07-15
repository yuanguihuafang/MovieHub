<template>
  <div class="home" :class="{ 'home--static-bg': !dynamicPageBgEnabled }">
    <!-- 全页背景视频（固定在视口后方，滚动时持续播放） -->
    <div v-show="dynamicPageBgEnabled" class="bg-video" aria-hidden="true">
      <video
        v-if="videoUrl"
        ref="heroVideoEl"
        class="bg-video-el"
        :src="videoUrl"
        :muted="isMuted"
        playsinline
        autoplay
        preload="auto"
        @ended="onVideoEnded"
        @loadeddata="tryPlayVideo"
        @error="onVideoError"
      />
    </div>

    <!-- 固定在视口右上角：不随页面滚动 -->
    <div class="home-hero-tools">
      <button
        type="button"
        class="bg-mode-toggle"
        :aria-label="dynamicPageBgEnabled ? '切换为默认背景' : '切换为动态背景'"
        :title="dynamicPageBgEnabled ? '动态背景（开）— 点击改为默认底色' : '默认底色— 点击恢复动态背景'"
        @click="toggleDynamicBg"
      >
        <svg
          v-if="dynamicPageBgEnabled"
          class="bg-mode-svg"
          viewBox="0 0 24 24"
          width="20"
          height="20"
          aria-hidden="true"
        >
          <path
            fill="currentColor"
            d="M4 6h2v12H4V6zm5 3h2v9H9V9zm5-5h2v14h-2V4zm5 4h2v10h-2V8z"
          />
        </svg>
        <svg v-else class="bg-mode-svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path fill="currentColor" d="M4 5h16v14H4V5zm2 2v10h12V7H6z" />
        </svg>
      </button>
      <button
        v-show="dynamicPageBgEnabled && !!videoUrl"
        type="button"
        class="hero-sound"
        :aria-label="isMuted ? '取消静音' : '静音'"
        :title="isMuted ? '取消静音' : '静音'"
        @click="toggleMute"
      >
      <!-- 喇叭图标（Element Plus 图标库无标准音量图标，使用内联 SVG） -->
      <svg
        v-if="isMuted"
        class="sound-svg"
        viewBox="0 0 24 24"
        width="20"
        height="20"
        aria-hidden="true"
      >
        <!-- 喇叭静音：喇叭 + X -->
        <path fill="currentColor" d="M3 10v4h4l5 4V6L7 10H3z" />
        <path
          fill="currentColor"
          d="M16 9.3l1.4-1.4 4.6 4.6-1.4 1.4L16 9.3z"
        />
        <path
          fill="currentColor"
          d="M20.6 9.3L16 13.9l-1.4-1.4 4.6-4.6 1.4 1.4z"
        />
      </svg>
      <svg v-else class="sound-svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <!-- 更接近常见“音量开启”造型：喇叭 + 两条声波 -->
        <path fill="currentColor" d="M3 10v4h4l5 4V6L7 10H3z" />
        <path
          fill="currentColor"
          d="M14.5 8.6c1.5 1 2.5 2.6 2.5 4.4s-1 3.4-2.5 4.4l-1-1.4c1.1-.7 1.7-1.7 1.7-3s-.6-2.3-1.7-3l1-1.4z"
        />
        <path
          fill="currentColor"
          d="M16.9 6.7c2.2 1.5 3.6 3.7 3.6 6.3s-1.4 4.8-3.6 6.3l-1-1.4c1.7-1.2 2.7-2.8 2.7-4.9s-1-3.7-2.7-4.9l1-1.4z"
        />
      </svg>
    </button>
    </div>

    <div class="home-inner">
      <section v-if="userStore.userInfo" class="block quick">
        <header class="block-head">
          <h3>为你准备</h3>
          <p class="muted">基于你的偏好类型与常用功能入口</p>
        </header>
        <div class="quick-grid">
          <div class="quick-card">
            <div class="quick-title">偏好类型</div>
            <div v-if="preferredGenres.length" class="chip-row">
              <span v-for="g in preferredGenres" :key="g" class="chip">{{ g }}</span>
            </div>
            <div v-else class="quick-empty">
              还没设置偏好，去片单页勾选 10 类电影类型
            </div>
          </div>
          <button type="button" class="quick-action" @click="$router.push('/recommend')">
            <div class="qa-kicker">一键进入</div>
            <div class="qa-title">智能推荐</div>
            <div class="qa-sub">偏好 + 描述 → 生成合并排序推荐</div>
          </button>
          <button type="button" class="quick-action alt" @click="$router.push('/library')">
            <div class="qa-kicker">快捷管理</div>
            <div class="qa-title">我的片单</div>
            <div class="qa-sub">收藏 / 已看 / 偏好，一并管理</div>
          </button>
        </div>
      </section>

      <section class="block">
        <header class="block-head">
          <h3>每日推荐</h3>
          <p>根据日期轮换的高分片单，每天略有不同</p>
        </header>
        <div class="strip">
          <button v-for="m in daily" :key="'d-' + m.name" type="button" class="card accent" @click="openDetail(m)">
            <div class="card-thumb">
              <img v-if="m.poster_url" :src="m.poster_url" alt="" loading="lazy" />
              <div v-else class="thumb-ph">暂无海报</div>
            </div>
            <div class="card-head">
              <div class="card-title">{{ m.display }}</div>
              <div class="card-score">★ {{ m.score }}</div>
            </div>
            <div class="card-sub">{{ m.genres }}</div>
          </button>
        </div>
      </section>

      <section class="block">
        <header class="block-head">
          <h3>即将上映</h3>
          <p>TMDB 即将上映</p>
        </header>
        <div class="strip">
          <button v-for="m in upcoming" :key="'u-' + m.name" type="button" class="card alt" @click="openDetail(m)">
            <div class="card-thumb">
              <img v-if="m.poster_url" :src="m.poster_url" alt="" loading="lazy" />
              <div v-else class="thumb-ph">暂无海报</div>
            </div>
            <div class="card-head">
              <div class="card-title">
                <span v-if="m.from_tmdb_trending" class="trend-pill">热播</span>
                {{ m.display }}
              </div>
              <div class="card-score">★ {{ m.score }}</div>
            </div>
            <div class="card-sub">{{ m.genres }}<span v-if="m.start_time"> · {{ m.start_time }}</span></div>
          </button>
        </div>
      </section>

      <section class="block">
        <header class="block-head">
          <h3>正在热映</h3>
          <p>TMDB 正在热映</p>
        </header>
        <div class="strip">
          <button v-for="m in recent" :key="'r-' + m.name" type="button" class="card" @click="openDetail(m)">
            <div class="card-thumb">
              <img v-if="m.poster_url" :src="m.poster_url" alt="" loading="lazy" />
              <div v-else class="thumb-ph">暂无海报</div>
            </div>
            <div class="card-head">
              <div class="card-title">
                <span v-if="m.from_tmdb_trending" class="trend-pill">热播</span>
                {{ m.display }}
              </div>
              <div class="card-score">★ {{ m.score }}</div>
            </div>
            <div class="card-sub">{{ m.genres }}<span v-if="m.start_time"> · {{ m.start_time }}</span></div>
          </button>
        </div>
      </section>

      <section class="block">
        <header class="block-head">
          <h3>豆瓣高分</h3>
          <p>口碑佳作，按评分排序</p>
        </header>
        <div class="strip">
          <button v-for="m in highRated" :key="m.name" type="button" class="card" @click="openDetail(m)">
            <div class="card-thumb">
              <img v-if="m.poster_url" :src="m.poster_url" alt="" loading="lazy" />
              <div v-else class="thumb-ph">暂无海报</div>
            </div>
            <div class="card-head">
              <div class="card-title">{{ m.display }}</div>
              <div class="card-score">★ {{ m.score }}</div>
            </div>
            <div class="card-sub">{{ m.genres }}</div>
          </button>
        </div>
      </section>

      <div class="cta">
        <div>
          <h4>想浏览全部影片？</h4>
          <p>进入片库按类型筛选、搜索片名</p>
        </div>
        <el-button type="primary" size="large" round @click="$router.push('/browse')">进入片库</el-button>
      </div>
    </div>

    <el-dialog
      v-model="detailVisible"
      :show-close="false"
      width="960px"
      destroy-on-close
      class="detail-dialog"
    >
      <template #header>
        <div class="dlg-head">
          <div class="dlg-head-title">
            <div class="dlg-h1">{{ detail?.data?.title || current?.display || '影片详情' }}</div>
            <div class="dlg-hmeta">
              <span v-if="detail?.data?.score" class="pill score">★ {{ detail.data.score }}</span>
              <span v-if="detail?.data?.type" class="pill">{{ detail.data.type }}</span>
              <span v-if="detail?.data?.start_time" class="pill soft">{{ detail.data.start_time }}</span>
              <span v-else-if="current?.start_time" class="pill soft">{{ current.start_time }}</span>
            </div>
          </div>
          <button type="button" class="dlg-close" aria-label="关闭" @click="detailVisible = false">
            <el-icon><Close /></el-icon>
          </button>
        </div>
      </template>

      <div v-if="detail.data" class="dlg dlg-row">
        <div class="dlg-left">
          <div v-if="detail.poster_url" class="dlg-poster">
            <img :src="detail.poster_url" alt="" />
          </div>
          <div v-else class="dlg-ph">暂无海报</div>
        </div>
        <div class="dlg-right">
          <div v-if="detail?.data?.overview" class="dlg-overview">
            {{ detail.data.overview }}
          </div>

          <el-descriptions :column="2" border size="small" class="dlg-desc purple-desc">
            <el-descriptions-item v-if="detail.data.score" label="评分">{{ detail.data.score }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.data.rank" label="排名">{{ detail.data.rank }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.data.run_time" label="时长">{{ detail.data.run_time }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.data.start_time" label="上映">{{ detail.data.start_time }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.data.type" label="类型">{{ detail.data.type }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.data.director" label="导演">{{ detail.data.director }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.data.actor" label="演员" :span="2">
              {{ formatActor(detail.data.actor) }}
            </el-descriptions-item>
            <el-descriptions-item v-if="detail.data.area" label="地区">{{ detail.data.area }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.data.language" label="语言">{{ detail.data.language }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.data.comment_num" label="评论数">{{ detail.data.comment_num }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
      <div v-else-if="detail.attributes?.length" class="dlg">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item
            v-for="attr in detail.attributes"
            :key="attr.relation"
            :label="attr.relation_zh"
          >
            {{ attr.value }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <template #footer>
        <el-button
          v-if="userStore.userInfo && current"
          :type="isBlockedCurrent ? 'danger' : 'default'"
          @click="toggleBlockHome"
          round
        >
          {{ isBlockedCurrent ? '已屏蔽' : '屏蔽' }}
        </el-button>
        <el-button
          v-if="userStore.userInfo && current"
          :type="isLikedCurrent ? 'success' : 'default'"
          @click="toggleLikeHome"
          round
        >
          {{ isLikedCurrent ? '已喜欢' : '👍 喜欢' }}
        </el-button>
        <el-button
          v-if="userStore.userInfo && current"
          :type="isDislikedCurrent ? 'warning' : 'default'"
          @click="toggleDislikeHome"
          round
        >
          {{ isDislikedCurrent ? '已标记不喜欢' : '👎 不喜欢' }}
        </el-button>
        <AddToPlaylistLauncher
          v-if="userStore.userInfo && current"
          v-bind="homeAddToPlaylistProps"
        />
        <el-button
          v-if="userStore.userInfo && current && !isCurrentFromUpcoming"
          :type="isWatchedCurrent ? 'success' : 'default'"
          @click="openWatchedReviewHome"
          round
        >
          {{ isWatchedCurrent ? '已看' : '看过' }}
        </el-button>
        <el-button
          v-if="userStore.userInfo && current"
          :type="isFavCurrent ? 'warning' : 'primary'"
          @click="toggleFavoriteHome"
          round
        >
          {{ isFavCurrent ? '已收藏' : '收藏' }}
        </el-button>
      </template>
    </el-dialog>

    <WatchedReviewDialog
      v-model="watchedReviewVisible"
      :movie-name="current?.name || ''"
      :movie-source="current?.source || 'douban'"
      :tmdb-id="current?.tmdb_id ?? null"
      :genres="watchedReviewGenres"
      :is-watched="isWatchedCurrent"
      :initial-note="(currentFeedback?.note || '').toString()"
      @saved="onWatchedReviewSavedHome"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useDynamicPageBackground } from '@/composables/useDynamicPageBackground'
import { useUserStore } from '@/stores/user'
import { homeApi, movieApi, userApi } from '@/services/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import AddToPlaylistLauncher from '@/components/AddToPlaylistLauncher.vue'
import WatchedReviewDialog from '@/components/WatchedReviewDialog.vue'

interface HM {
  name: string
  display: string
  genres: string
  score: string
  directors: string
  start_time?: string
  poster_url?: string | null
  from_tmdb_trending?: boolean
  source?: string
  tmdb_id?: number | null
}

const userStore = useUserStore()
const { dynamicPageBgEnabled, toggleDynamicBg } = useDynamicPageBackground()
const preferredGenres = computed(() => {
  const raw: unknown = userStore.userInfo?.preferred_genres
  if (Array.isArray(raw)) return raw.filter(Boolean)
  if (typeof raw === 'string') {
    return raw
      .split(/[,，]/g)
      .map((s) => s.trim())
      .filter(Boolean)
  }
  return []
})
const carousel = ref<HM[]>([])
const highRated = ref<HM[]>([])
const recent = ref<HM[]>([])
const upcoming = ref<HM[]>([])
const daily = ref<HM[]>([])
const myFavorites = ref<string[]>([])
const feedbackMap = ref<Record<string, any>>({})

const heroVideoEl = ref<HTMLVideoElement | null>(null)
const videoList = ref<{ name: string; url: string }[]>([])
const videoIndex = ref(0)
const videoUrl = computed(() => videoList.value[videoIndex.value]?.url || '')
const isMuted = ref(true)


const detailVisible = ref(false)
const current = ref<HM | null>(null)
const detail = ref<any>({})
const myWatched = ref<string[]>([])

const isWatchedCurrent = computed(
  () => !!current.value && myWatched.value.includes(current.value.name)
)

/** 即将上映影片不提供「看过」（尚未上映） */
const isCurrentFromUpcoming = computed(() => {
  const n = current.value?.name
  if (!n) return false
  return upcoming.value.some((m) => m.name === n)
})

const isFavCurrent = computed(() => !!current.value && myFavorites.value.includes(current.value.name))

const currentFeedback = computed(() => {
  const key = current.value?.name || ''
  if (!key) return null
  return feedbackMap.value[key] || null
})
const isBlockedCurrent = computed(() => !!current.value && !!currentFeedback.value && !!currentFeedback.value.blocked)
const isLikedCurrent = computed(() => !!current.value && currentFeedback.value?.vote === 'like')
const isDislikedCurrent = computed(() => !!current.value && currentFeedback.value?.vote === 'dislike')

const homeAddToPlaylistProps = computed(() => {
  const m = current.value
  if (!m) {
    return {
      movieName: '',
      movieSource: 'douban',
      tmdbId: null as number | null,
      genres: '',
      posterUrl: '',
      genresStr: '',
      scoreStr: '',
      shortReview: undefined as string | undefined
    }
  }
  const d = detail.value?.data || {}
  const genresStr = String(d.type || m.genres || '').trim()
  const scoreStr = String(d.score != null && d.score !== '' ? d.score : m.score || '').trim()
  const posterUrl = String(detail.value?.poster_url || m.poster_url || '').trim()
  const note = (currentFeedback.value?.note || '').toString().trim()
  return {
    movieName: m.name,
    movieSource: (m.source || 'douban').toString(),
    tmdbId: m.tmdb_id ?? null,
    genres: genresStr,
    posterUrl,
    genresStr,
    scoreStr,
    shortReview: note || undefined
  }
})

const formatActor = (actor: any) => {
  if (!actor) return ''
  let raw = ''
  if (Array.isArray(actor)) raw = actor.map((x) => (x ?? '').toString().trim()).filter(Boolean).join('、')
  else raw = actor.toString().trim()
  if (!raw) return ''

  raw = raw.replace(/^主演[:：]\s*/g, '').trim()

  let jsonArr: any[] | null = null
  if (raw.startsWith('[') && raw.endsWith(']')) {
    try {
      const arr = JSON.parse(raw.replace(/'/g, '"'))
      if (Array.isArray(arr)) jsonArr = arr
    } catch {
      /* ignore */
    }
  }

  const cleaned = raw
    .replace(/（.*?）/g, ' ')
    .replace(/\(.*?\)/g, ' ')
    .replace(/[\[\]【】]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  let tokens = cleaned.split(/[,/、，；;|]/g).map((x: string) => x.trim()).filter(Boolean)
  if (jsonArr) tokens = jsonArr.map((x: any) => (x ?? '').toString().trim()).filter(Boolean)

  const names: string[] = []
  for (const t of tokens) {
    const m = t.match(/[\u4e00-\u9fa5A-Za-z·.\- ]+/g)
    const n = (m?.join('') || '').trim().replace(/\s+/g, ' ')
    if (!n) continue
    if (!names.includes(n)) names.push(n)
    if (names.length >= 5) break
  }
  if (!names.length) return tokens.slice(0, 5).join(' / ')
  return names.join(' / ')
}

const loadMyFavoritesHome = async () => {
  if (!userStore.userInfo) return
  try {
    const res = await userApi.getMyFavorites()
    if (res.data.success) {
      myFavorites.value = (res.data.favorites || []).map((f: { movie_name: string }) => f.movie_name)
    }
  } catch {
    /* ignore */
  }
}

const loadMyWatchedHome = async () => {
  if (!userStore.userInfo) return
  try {
    const res = await userApi.getMyWatched(400)
    if (res.data.success) {
      myWatched.value = (res.data.watched || []).map((w: { movie_name: string }) => w.movie_name)
    }
  } catch {
    /* ignore */
  }
}

const loadMyFeedbackHome = async () => {
  if (!userStore.userInfo) return
  try {
    const res = await userApi.getMyFeedback(undefined, undefined, 500)
    if (res.data.success) {
      const mp: Record<string, any> = {}
      for (const r of res.data.feedback || []) {
        if (r?.movie_name) mp[r.movie_name] = r
      }
      feedbackMap.value = mp
    }
  } catch {
    /* ignore */
  }
}

const openDetail = async (m: HM) => {
  current.value = m
  detailVisible.value = true
  try {
    const res = await movieApi.getMovieDetail(m.name, m.source, m.tmdb_id ?? undefined)
    detail.value = res.data
  } catch {
    detail.value = {}
  }
}

const toggleLikeHome = async () => {
  if (!userStore.userInfo || !current.value) return
  const nm = current.value.name
  const next = isLikedCurrent.value ? null : 'like'
  try {
    const res = await userApi.upsertFeedback(nm, { vote: next }, { movieSource: current.value.source || 'kg', tmdbId: current.value.tmdb_id ?? null })
    if (res.data?.success && res.data.feedback) feedbackMap.value[nm] = res.data.feedback
    ElMessage.success(next ? '已标记：喜欢' : '已取消：喜欢')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const toggleDislikeHome = async () => {
  if (!userStore.userInfo || !current.value) return
  const nm = current.value.name
  const next = isDislikedCurrent.value ? null : 'dislike'
  try {
    const res = await userApi.upsertFeedback(nm, { vote: next }, { movieSource: current.value.source || 'kg', tmdbId: current.value.tmdb_id ?? null })
    if (res.data?.success && res.data.feedback) feedbackMap.value[nm] = res.data.feedback
    ElMessage.success(next ? '已标记：不喜欢' : '已取消：不喜欢')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const toggleBlockHome = async () => {
  if (!userStore.userInfo || !current.value) return
  const nm = current.value.name
  const next = !isBlockedCurrent.value
  try {
    if (next) {
      await ElMessageBox.confirm('屏蔽后，该电影将不会再出现在推荐结果中。确定屏蔽吗？', '屏蔽电影', {
        confirmButtonText: '屏蔽',
        cancelButtonText: '取消',
        type: 'warning'
      })
    }
    const res = await userApi.upsertFeedback(nm, { blocked: next }, { movieSource: current.value.source || 'kg', tmdbId: current.value.tmdb_id ?? null })
    if (res.data?.success && res.data.feedback) feedbackMap.value[nm] = res.data.feedback
    ElMessage.success(next ? '已屏蔽' : '已取消屏蔽')
  } catch (e: any) {
    if (e === 'cancel' || e?.message === 'cancel') return
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const watchedReviewVisible = ref(false)

const watchedReviewGenres = computed(() => {
  const m = current.value
  if (!m) return ''
  return String(detail.value?.data?.type || m.genres || '').trim()
})

const openWatchedReviewHome = () => {
  if (!userStore.userInfo || !current.value || isCurrentFromUpcoming.value) return
  watchedReviewVisible.value = true
}

const onWatchedReviewSavedHome = async () => {
  await loadMyWatchedHome()
  await loadMyFeedbackHome()
}

const toggleFavoriteHome = async () => {
  if (!userStore.userInfo || !current.value) return
  const g = detail.value?.data?.type || current.value.genres || ''
  try {
    if (isFavCurrent.value) {
      await userApi.removeMyFavorite(current.value.name)
      myFavorites.value = myFavorites.value.filter((n) => n !== current.value?.name)
      ElMessage.success('已取消收藏')
    } else {
      await userApi.addMyFavorite(current.value.name, g, current.value.source || 'kg', current.value.tmdb_id ?? null)
      myFavorites.value.push(current.value.name)
      ElMessage.success('已收藏')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const load = async () => {
  try {
    const res = await homeApi.getFeed()
    if (res.data.success) {
      carousel.value = res.data.carousel || []
      highRated.value = res.data.high_rated || []
      recent.value = res.data.recent || []
      upcoming.value = res.data.upcoming || []
      daily.value = res.data.daily || []
    }
  } catch {
    carousel.value = []
  }
}

const loadVedio = async () => {
  try {
    const res = await homeApi.getVedio()
    if (res.data?.success) {
      videoList.value = res.data.videos || []
      // 初始随机一条
      videoIndex.value = pickNextVideoIndex(-1)
      // 触发播放（浏览器通常要求先静音才允许自动播放）
      setTimeout(() => tryPlayVideo(), 120)
    }
  } catch {
    videoList.value = []
  }
}

const pickNextVideoIndex = (current: number) => {
  const n = videoList.value.length
  if (n <= 1) return 0
  let next = current
  // 避免连续两次同一视频
  while (next === current) {
    next = Math.floor(Math.random() * n)
  }
  return next
}

const tryPlayVideo = () => {
  const el = heroVideoEl.value
  if (!el) return
  el.muted = !!isMuted.value
  el.volume = 0.9
  el.play?.().catch(() => {
    /* autoplay policy may block; ignore */
  })
}

const onVideoEnded = () => {
  if (!videoList.value.length) return
  videoIndex.value = pickNextVideoIndex(videoIndex.value)
  setTimeout(() => tryPlayVideo(), 120)
}

const onVideoError = () => {
  // 当前视频不可用时，跳到下一个
  if (!videoList.value.length) return
  videoIndex.value = pickNextVideoIndex(videoIndex.value)
}

const toggleMute = () => {
  isMuted.value = !isMuted.value
  const el = heroVideoEl.value
  if (el) el.muted = !!isMuted.value
  setTimeout(() => tryPlayVideo(), 30)
}

watch(dynamicPageBgEnabled, (on) => {
  const el = heroVideoEl.value
  if (!on) {
    el?.pause?.()
    return
  }
  setTimeout(() => tryPlayVideo(), 120)
})

onMounted(() => {
  load()
  loadVedio()
  loadMyWatchedHome()
  loadMyFavoritesHome()
  loadMyFeedbackHome()
})
</script>

<style scoped>
.home {
  min-height: calc(100vh - 64px);
  /* 顶部导航栏高度 64px（UserLayout）：视频紧贴导航栏下缘开始 */
  --bg-video-top: 0px;
  /* 视频底部留白（深色带），避免铺满到屏幕最底 */
  --bg-bottom-gap: 30px;
  /*
    首屏需要完整露出「为你准备」区域：把下方 UI 预留高度调大一点，
    视频占用上方剩余空间（再叠加 --bg-bottom-gap 的底部深色带）
  */
  --home-bottom-ui-h: clamp(300px, 40vh, 500px);
  /* 视频下缘与内容区之间的细小间距（避免出现你截图里那种“视频和内容之间一条深色缝”） */
  --below-video-pad: 93px;
  /* 页面底色：深色 */
  background:
    radial-gradient(900px 520px at 18% 0%, rgba(15, 18, 196, 0.22), transparent 55%),
    radial-gradient(900px 520px at 82% 18%, rgba(78, 16, 222, 0.16), transparent 58%),
    #101427;
  padding-bottom: 12px;
  position: relative;
}

.bg-video {
  position: fixed;
  top: var(--bg-video-top);
  left: 0;
  right: 0;
  height: calc(143vh - var(--bg-video-top) - var(--home-bottom-ui-h) - var(--bg-bottom-gap));
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
  background: #0b1020;
}

.home-hero-tools {
  position: fixed;
  top: calc(var(--bg-video-top) + 8px);
  right: 16px;
  z-index: 60;
  display: flex;
  align-items: center;
  gap: 8px;
  pointer-events: auto;
}

.bg-mode-toggle,
.hero-sound {
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(2, 6, 23, 0.28);
  color: rgba(255, 255, 255, 0.95);
  border-radius: 999px;
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  cursor: pointer;
  backdrop-filter: blur(12px);
  transition: transform 0.15s, background 0.15s, border-color 0.15s;
}

.bg-mode-toggle:hover,
.hero-sound:hover {
  transform: translateY(-1px);
  background: rgba(2, 6, 23, 0.36);
  border-color: rgba(255, 255, 255, 0.32);
}

.bg-mode-svg {
  display: block;
  opacity: 0.96;
}

.bg-video-el {
  width: 100%;
  height: 100%;
  /* 不拉伸素材：铺满容器时裁切溢出部分，避免出现左右黑边（contain 会 letterbox） */
  object-fit: cover;
  object-position: center;
  display: block;
}

.sound-svg {
  display: block;
  opacity: 0.96;
}

.hero-video-copy {
  max-width: 640px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.22);
  backdrop-filter: blur(12px);
}

.hero-title {
  margin-top: 12px;
  font-size: clamp(1.8rem, 3.2vw, 2.6rem);
  font-weight: 950;
  letter-spacing: -0.02em;
  line-height: 1.12;
}

.hero-sub {
  margin-top: 10px;
  font-size: 14px;
  opacity: 0.88;
  line-height: 1.55;
  max-width: 560px;
}

.hero-actions {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-video-right {
  justify-self: end;
  width: min(360px, 40vw);
}

.hero-mini {
  border-radius: 18px;
  padding: 16px 16px 14px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(14px);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.22);
}

.mini-k {
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  opacity: 0.88;
}

.mini-t {
  margin-top: 8px;
  font-size: 16px;
  font-weight: 900;
  letter-spacing: -0.01em;
  line-height: 1.3;
  display: -webkit-box;
  line-clamp: 2;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.mini-s {
  margin-top: 8px;
  font-size: 13px;
  opacity: 0.9;
}

.trend-pill {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(224, 231, 255, 0.98);
  background: rgba(99, 102, 241, 0.35);
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid rgba(165, 180, 252, 0.35);
  margin-right: 6px;
  vertical-align: middle;
}

.home-inner {
  max-width: 1240px;
  margin: 0 auto;
  /* 内容紧贴视频下缘开始（只保留很小间距） */
  padding: calc(
      var(--bg-video-top) +
        (100vh - var(--bg-video-top) - var(--home-bottom-ui-h) - var(--bg-bottom-gap)) +
        var(--below-video-pad)
    )
    20px 0;
  position: relative;
  z-index: 1;
}

.home--static-bg .home-inner {
  padding: 24px 20px 12px;
}

/* “为你准备”紧贴视频区域下方 */
.block.quick {
  margin-top: -150px;
}

.home--static-bg .block.quick {
  margin-top: 0;
}

.muted {
  color: rgba(226, 232, 240, 0.86);
}

.quick-grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 14px;
}

@media (max-width: 980px) {
  .quick-grid {
    grid-template-columns: 1fr;
  }
}

.quick-card {
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.28), rgba(14, 165, 233, 0.16));
  backdrop-filter: blur(14px);
  padding: 16px 16px 14px;
  box-shadow: 0 14px 40px rgba(2, 6, 23, 0.28);
}

.quick-title {
  font-weight: 800;
  color: rgba(255, 255, 255, 0.95);
  margin-bottom: 10px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.94);
  background: rgba(2, 6, 23, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.22);
}

.quick-empty {
  font-size: 13px;
  color: rgba(226, 232, 240, 0.92);
  line-height: 1.55;
}

.quick-action {
  border: none;
  text-align: left;
  border-radius: 18px;
  padding: 16px 16px 14px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.96);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.32), rgba(14, 165, 233, 0.18));
  border: 1px solid rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(14px);
  box-shadow: 0 12px 34px rgba(2, 6, 23, 0.22);
  transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
}

.quick-action:hover {
  transform: translateY(-3px);
  border-color: rgba(255, 255, 255, 0.26);
  box-shadow: 0 20px 52px rgba(2, 6, 23, 0.34);
}

.quick-action.alt {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.28), rgba(99, 102, 241, 0.18));
  border-color: rgba(255, 255, 255, 0.18);
}

.qa-kicker {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(226, 232, 240, 0.9);
}

.qa-title {
  margin-top: 6px;
  font-size: 18px;
  font-weight: 900;
  letter-spacing: -0.02em;
}

.qa-sub {
  margin-top: 6px;
  font-size: 13px;
  color: rgba(226, 232, 240, 0.92);
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 980px) {
  .qa-sub {
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
  }
}

.block {
  margin-top: 36px;
}

/* 「为你准备」与后续区块（如豆瓣高分）拉开间距 */
.block:not(.quick) {
  margin-top: 30px;
}

.block-head {
  margin-bottom: 18px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  position: relative;
  padding-left: 16px;
}

.block-head::before {
  content: '';
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: 3px;
  border-radius: 4px;
  background: linear-gradient(180deg, #6366f1, #a855f7, #22d3ee);
  box-shadow: 0 0 16px rgba(99, 102, 241, 0.45);
}

.block-head h3 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: rgba(255, 255, 255, 0.96);
  text-shadow: 0 10px 30px rgba(2, 6, 23, 0.55);
}

.block-head p {
  margin: 6px 0 0;
  font-size: 14px;
  color: rgba(226, 232, 240, 0.88);
  text-shadow: 0 10px 26px rgba(2, 6, 23, 0.45);
  line-height: 1.5;
  max-width: 640px;
}

.block-head .note { color: #b45309; }

.strip {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  padding: 2px 2px 10px;
  scroll-snap-type: x mandatory;
}

.strip::-webkit-scrollbar {
  height: 10px;
}
.strip::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.45);
  border-radius: 999px;
}
.strip::-webkit-scrollbar-track {
  background: transparent;
}

.card {
  flex: 0 0 220px;
  scroll-snap-align: start;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  padding: 12px 12px 12px;
  text-align: left;
  cursor: pointer;
  background: linear-gradient(165deg, rgba(30, 41, 59, 0.72), rgba(15, 23, 42, 0.55));
  backdrop-filter: blur(16px) saturate(1.1);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.06) inset,
    0 16px 44px rgba(0, 0, 0, 0.35);
  transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
  color: rgba(248, 250, 252, 0.96);
}

.card:hover {
  transform: translateY(-5px);
  border-color: rgba(165, 180, 252, 0.28);
  box-shadow:
    0 0 0 1px rgba(165, 180, 252, 0.12) inset,
    0 22px 50px rgba(99, 102, 241, 0.22);
}

.card-thumb {
  margin: -12px -12px 10px;
  border-radius: 16px 16px 12px 12px;
  overflow: hidden;
  aspect-ratio: 2 / 3;
  background: rgba(2, 6, 23, 0.65);
  position: relative;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.thumb-ph {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(148, 163, 184, 0.9);
  font-size: 12px;
  font-weight: 600;
  background: linear-gradient(145deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.95));
}

.card-thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.card.alt {
  background: linear-gradient(165deg, rgba(124, 45, 18, 0.35), rgba(15, 23, 42, 0.58));
  border-color: rgba(251, 146, 60, 0.2);
}

.card.accent {
  background: linear-gradient(165deg, rgba(67, 56, 202, 0.38), rgba(15, 23, 42, 0.55));
  border-color: rgba(129, 140, 248, 0.28);
}

.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.card-score {
  font-weight: 900;
  font-size: 13px;
  color: #f59e0b;
  white-space: nowrap;
}

.card-title {
  font-weight: 800;
  font-size: 14px;
  color: rgba(248, 250, 252, 0.96);
  line-height: 1.25;
  display: -webkit-box;
  line-clamp: 1;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-sub {
  margin-top: 6px;
  font-size: 12px;
  color: rgba(186, 198, 214, 0.92);
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  line-clamp: 1;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
}

.cta {
  margin-top: 48px;
  padding: 26px 28px;
  border-radius: 22px;
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background-color: #000;
  background-image:
    linear-gradient(
      90deg,
      rgba(99, 102, 241, 0.22) 0%,
      rgba(129, 140, 248, 0.16) 18%,
      rgba(168, 85, 247, 0.1) 26%,
      rgba(99, 102, 241, 0.08) 32%,
      rgba(2, 6, 23, 0.58) 46%,
      rgba(0, 0, 0, 0.96) 50%,
      rgba(0, 0, 0, 1) 52%,
      rgba(0, 0, 0, 1) 58%,
      rgba(0, 0, 0, 1) 66%,
      rgba(0, 0, 0, 0.98) 72%,
      rgba(2, 6, 23, 0.52) 80%,
      rgba(55, 48, 120, 0.36) 88%,
      rgba(99, 102, 241, 0.18) 94%,
      rgba(124, 58, 237, 0.14) 100%
    ),
    radial-gradient(900px 520px at 8% 0%, rgba(99, 102, 241, 0.26), transparent 58%),
    radial-gradient(760px 480px at 92% 0%, rgba(168, 85, 247, 0.18), transparent 62%),
    linear-gradient(135deg, rgba(30, 27, 75, 0.38), rgba(0, 0, 0, 0.35));
  background-repeat: no-repeat;
  background-size: cover;
  background-position: 0 0;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.08) inset,
    0 22px 60px rgba(0, 0, 0, 0.28),
    0 8px 40px rgba(79, 70, 229, 0.2);
}

.cta::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image: url('/api/background/蛛蛛侠.png');
  background-repeat: no-repeat;
  background-size: auto 100%;
  background-position: 66% 52%;
  opacity: 0.22;
  filter: blur(22px);
  /* 光晕略宽；右侧渐隐拉长，先露出底图黑带再露紫 */
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 20%,
    rgba(0, 0, 0, 0.32) 31%,
    rgba(0, 0, 0, 0.78) 39%,
    rgba(0, 0, 0, 1) 46%,
    rgba(0, 0, 0, 1) 56%,
    rgba(0, 0, 0, 0.68) 70%,
    rgba(0, 0, 0, 0.2) 84%,
    rgba(0, 0, 0, 0) 96%
  );
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 20%,
    rgba(0, 0, 0, 0.32) 31%,
    rgba(0, 0, 0, 0.78) 39%,
    rgba(0, 0, 0, 1) 46%,
    rgba(0, 0, 0, 1) 56%,
    rgba(0, 0, 0, 0.68) 70%,
    rgba(0, 0, 0, 0.2) 84%,
    rgba(0, 0, 0, 0) 96%
  );
}

.cta::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background-image: url('/api/background/蛛蛛侠.png');
  background-repeat: no-repeat;
  background-size: auto 100%;
  background-position: 66% 52%;
  opacity: 1;
  filter: none;
  /* 左：窄紫→黑→图；右：图缘后缓慢淡入，先见底图黑(54%–72%)再见紫 */
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 24%,
    rgba(0, 0, 0, 0.18) 32%,
    rgba(0, 0, 0, 1) 42%,
    rgba(0, 0, 0, 1) 54%,
    rgba(0, 0, 0, 0.55) 64%,
    rgba(0, 0, 0, 0.12) 76%,
    rgba(0, 0, 0, 0) 92%
  );
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 24%,
    rgba(0, 0, 0, 0.18) 32%,
    rgba(0, 0, 0, 1) 42%,
    rgba(0, 0, 0, 1) 54%,
    rgba(0, 0, 0, 0.55) 64%,
    rgba(0, 0, 0, 0.12) 76%,
    rgba(0, 0, 0, 0) 92%
  );
}

.cta > * {
  position: relative;
  z-index: 2;
}

.cta h4 {
  margin: 0 0 6px;
  font-size: 1.22rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.cta p {
  margin: 0;
  opacity: 0.93;
  font-size: 14px;
  line-height: 1.5;
  max-width: 420px;
}

.dlg {
  padding: 8px 0;
}

.dlg-left {
  position: sticky;
  top: 0;
}

/* 详情弹窗壳与表格：styles/movie-detail-dialog.css */

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

.dlg-poster {
  border-radius: 12px;
  overflow: hidden;
  aspect-ratio: 2 / 3;
  background: #f3f4f6;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
}

.dlg-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.dlg-ph {
  border-radius: 12px;
  aspect-ratio: 2 / 3;
  background: #f3f4f6;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 13px;
}

</style>
