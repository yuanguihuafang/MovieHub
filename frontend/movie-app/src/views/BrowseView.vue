<template>
  <div class="browse-page">
    <el-card class="search-card glass panel" shadow="never">
      <el-form :inline="true" :model="searchForm" class="search-form" label-width="72px">
        <el-form-item label="数据源" class="sf-item sf-source">
          <el-segmented
            v-model="searchForm.source"
            :options="sourceOptions"
            size="default"
            class="source-seg"
            @change="searchMovies"
          />
        </el-form-item>
        <el-form-item label="类型" class="sf-item sf-genre">
          <el-select
            v-model="searchForm.genre"
            placeholder="全部类型"
            clearable
            class="genre-select"
            popper-class="browse-genre-dropdown"
            @change="searchMovies"
          >
            <el-option
              v-for="genre in genres"
              :key="genre"
              :label="genre || '全部类型'"
              :value="genre"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词" class="sf-item sf-keyword">
          <el-input
            v-model="searchForm.keyword"
            placeholder="片名或类型（模糊）"
            clearable
            class="keyword-input"
            :prefix-icon="Search"
            @keyup.enter="searchMovies"
          />
        </el-form-item>
        <el-form-item class="sf-item sf-actions">
          <el-button type="primary" :icon="Search" round @click="searchMovies">搜索</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="movie-card glass panel" shadow="never" v-loading="loading">
      <template #header>
        <div class="card-header">
          <div class="card-header-text">
            <span class="list-title">影片列表</span>
            <span v-if="!loading" class="list-sub">共 {{ pagination.total }} 部</span>
          </div>
        </div>
      </template>

      <div v-if="movies.length === 0" class="empty-state">
        <el-empty description="暂无电影数据" />
      </div>

      <div v-else class="movie-grid">
        <div
          v-for="movie in movies"
          :key="movie.name"
          class="movie-item"
          @click="showMovieDetail(movie)"
        >
          <div v-if="shouldShowPoster" class="movie-poster">
            <img
              v-if="showPoster(movie)"
              :src="movie.poster_url!"
              alt=""
              class="poster-img"
              loading="lazy"
              @error="onPosterErr(movie)"
            />
            <div v-else class="poster-placeholder">
              <el-icon :size="48"><Film /></el-icon>
            </div>
            <div v-if="isFavorite(movie.name)" class="favorite-badge">⭐ 已收藏</div>
            <div v-if="isWatched(movie.name)" class="watched-badge">✓ 已看过</div>
          </div>
          <div class="movie-info">
            <div class="movie-title">{{ movie.display }}</div>
            <div class="movie-genres">
              <el-tag
                v-for="genre in genreTags(movie)"
                :key="genre"
                size="small"
                type="info"
                effect="plain"
              >
                {{ genre }}
              </el-tag>
            </div>
            <div
              class="movie-director"
              v-if="(movie.director || movie.directors) && (movie.director || movie.directors) !== '未知'"
            >
              <el-icon><User /></el-icon>
              {{ movie.director || movie.directors }}
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <div v-if="pagination.total > 0" class="browse-bottom">
      <el-pagination
        class="browse-pagination"
        v-model:current-page="pagination.page"
        :page-size="pagination.pageSize"
        :total="pagination.total"
        layout="total, prev, pager, next, jumper"
        background
        @current-change="onPageChange"
      />
    </div>

     <!-- 电影详情对话框 -->
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
             <div class="dlg-h1">
               {{ movieDetail?.data?.title || currentMovie?.display || '影片详情' }}
             </div>
             <div class="dlg-hmeta">
               <span v-if="movieDetail?.data?.score" class="pill score">★ {{ movieDetail.data.score }}</span>
               <span v-if="movieDetail?.data?.type" class="pill">{{ movieDetail.data.type }}</span>
               <span v-if="movieDetail?.data?.start_time" class="pill soft">{{ movieDetail.data.start_time }}</span>
             </div>
           </div>
           <button type="button" class="dlg-close" aria-label="关闭" @click="detailVisible = false">
             <el-icon><Close /></el-icon>
           </button>
         </div>
       </template>
       <div v-if="movieDetail.data" class="dlg dlg-row">
         <div class="dlg-left">
           <div v-if="currentMovie && shouldShowPoster && showPoster(currentMovie)" class="dlg-poster">
             <img
               :src="currentMovie.poster_url!"
               alt=""
               loading="lazy"
               @error="onPosterErr(currentMovie)"
             />
           </div>
           <div v-else class="dlg-ph">暂无海报</div>
         </div>
         <div class="dlg-right">
           <div v-if="movieDetail?.data?.overview" class="dlg-overview">
             {{ movieDetail.data.overview }}
           </div>
           <el-descriptions :column="2" border size="small" class="dlg-desc purple-desc">
             <el-descriptions-item v-if="movieDetail.data.score" label="评分">
               {{ movieDetail.data.score }}
             </el-descriptions-item>
             <el-descriptions-item v-if="movieDetail.data.rank" label="排名">
               {{ movieDetail.data.rank }}
             </el-descriptions-item>
             <el-descriptions-item v-if="movieDetail.data.run_time" label="时长">
               {{ movieDetail.data.run_time }}
             </el-descriptions-item>
             <el-descriptions-item v-if="movieDetail.data.start_time" label="上映">
               {{ movieDetail.data.start_time }}
             </el-descriptions-item>
             <el-descriptions-item v-if="movieDetail.data.type" label="类型">
               {{ movieDetail.data.type }}
             </el-descriptions-item>
             <el-descriptions-item v-if="movieDetail.data.director" label="导演">
               {{ movieDetail.data.director }}
             </el-descriptions-item>
             <el-descriptions-item v-if="movieDetail.data.actor" label="演员" :span="2">
               {{ formatActor(movieDetail.data.actor) }}
             </el-descriptions-item>
             <el-descriptions-item v-if="movieDetail.data.area" label="地区">
               {{ movieDetail.data.area }}
             </el-descriptions-item>
             <el-descriptions-item v-if="movieDetail.data.language" label="语言">
               {{ movieDetail.data.language }}
             </el-descriptions-item>
             <el-descriptions-item v-if="movieDetail.data.comment_num" label="评论数">
               {{ movieDetail.data.comment_num }}
             </el-descriptions-item>
           </el-descriptions>
         </div>
       </div>
       <div v-else-if="movieDetail.attributes" class="dlg">
         <el-descriptions :column="1" border size="small">
           <el-descriptions-item
             v-for="attr in movieDetail.attributes"
             :key="attr.relation"
             :label="attr.relation_zh"
           >
             <template v-if="attr.relation === 'actor'">
               {{ formatActor(attr.value) }}
             </template>
             <template v-else>
               {{ attr.value }}
             </template>
           </el-descriptions-item>
         </el-descriptions>
       </div>
       <div v-else class="no-detail">
         <el-empty description="暂无详细信息" />
       </div>
      <template #footer>
        <template v-if="currentMovie && userStore.userInfo">
          <el-button
            :type="isBlockedCurrent ? 'danger' : 'default'"
            @click="toggleBlockBrowse"
            round
          >
            {{ isBlockedCurrent ? '已屏蔽' : '屏蔽' }}
          </el-button>
          <el-button
            :type="isLikedCurrent ? 'success' : 'default'"
            @click="toggleLikeBrowse"
            round
          >
            {{ isLikedCurrent ? '已喜欢' : '👍 喜欢' }}
          </el-button>
          <el-button
            :type="isDislikedCurrent ? 'warning' : 'default'"
            @click="toggleDislikeBrowse"
            round
          >
            {{ isDislikedCurrent ? '已标记不喜欢' : '👎 不喜欢' }}
          </el-button>
          <AddToPlaylistLauncher v-bind="browseAddToPlaylistProps" />
          <el-button
            :type="isWatched(currentMovie.name) ? 'success' : 'default'"
            @click="openWatchedReviewBrowse"
            round
          >
            {{ isWatched(currentMovie.name) ? '已看' : '看过' }}
          </el-button>
          <el-button
            :type="isFavorite(currentMovie.name) ? 'warning' : 'primary'"
            @click="toggleFavorite"
            round
          >
            {{ isFavorite(currentMovie.name) ? '取消收藏' : '收藏' }}
          </el-button>
        </template>
      </template>
    </el-dialog>

    <WatchedReviewDialog
      v-model="watchedReviewVisible"
      :movie-name="currentMovie?.name || ''"
      :movie-source="searchForm.source"
      :tmdb-id="null"
      :genres="browseWatchedGenres"
      :is-watched="currentMovie ? isWatched(currentMovie.name) : false"
      :initial-note="(currentFeedback?.note || '').toString()"
      @saved="onWatchedReviewSavedBrowse"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useUserStore } from '@/stores/user'
import { movieApi, userApi } from '@/services/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Film, User } from '@element-plus/icons-vue'
import type { Movie } from '@/types'
import AddToPlaylistLauncher from '@/components/AddToPlaylistLauncher.vue'
import WatchedReviewDialog from '@/components/WatchedReviewDialog.vue'

const userStore = useUserStore()
const feedbackMap = ref<Record<string, any>>({})

const currentFeedback = computed(() => {
  const key = currentMovie.value?.name || ''
  if (!key) return null
  return feedbackMap.value[key] || null
})
const isBlockedCurrent = computed(() => !!currentMovie.value && !!currentFeedback.value && !!currentFeedback.value.blocked)
const isLikedCurrent = computed(() => !!currentMovie.value && currentFeedback.value?.vote === 'like')
const isDislikedCurrent = computed(() => !!currentMovie.value && currentFeedback.value?.vote === 'dislike')

const browseAddToPlaylistProps = computed(() => {
  const m = currentMovie.value
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
  const d = movieDetail.value?.data || {}
  const genresStr = String(
    detailGenresStr() || (typeof m.genres === 'string' ? m.genres : genreTags(m).join('/'))
  ).trim()
  const scoreStr = String(d.score != null && d.score !== '' ? d.score : m.score || '').trim()
  const posterUrl = String(movieDetail.value?.poster_url || m.poster_url || '').trim()
  const note = (currentFeedback.value?.note || '').toString().trim()
  return {
    movieName: m.name,
    movieSource: searchForm.source,
    tmdbId: null,
    genres: genresStr,
    posterUrl,
    genresStr,
    scoreStr,
    shortReview: note || undefined
  }
})

// 固定的10种电影类型
const ALLOWED_GENRES = [
  '剧情',
  '喜剧',
  '爱情',
  '动作',
  '科幻',
  '悬疑',
  '动画',
  '纪录片',
  '战争',
  '奇幻'
]

const genreTags = (movie: Movie): string[] => {
  const g = movie.genres
  if (Array.isArray(g)) return g.filter(Boolean)
  if (typeof g === 'string') return g.split('/').map((s) => s.trim()).filter(Boolean)
  return []
}

// 格式化演员列表（最多显示前5个）
const formatActor = (actor: any) => {
  if (!actor) return ''

  // 兼容：后端可能返回 array / JSON 字符串 / 普通字符串
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

// 搜索表单
const searchForm = reactive({
  source: 'douban',
  keyword: '',
  genre: ''
})

// 电影列表
const movies = ref<Movie[]>([])
const loading = ref(false)
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// 电影详情
const detailVisible = ref(false)
const currentMovie = ref<Movie | null>(null)
const movieDetail = ref<any>({})

// 类型列表（固定10种）
const genres = ref<string[]>(['', ...ALLOWED_GENRES])

const sourceOptions = [
  { label: '豆瓣', value: 'douban' },
  { label: 'TMDB API', value: 'tmdb_api' },
  { label: 'TMDB-CSV', value: 'tmdb' }
]

const shouldShowPoster = computed(() => searchForm.source === 'douban' || searchForm.source === 'tmdb_api')

// 我的收藏
const myFavorites = ref<string[]>([])
const myWatched = ref<string[]>([])
const posterBroken = ref<Record<string, boolean>>({})

const showPoster = (movie: Movie) =>
  !!(movie.poster_url && !posterBroken.value[movie.name])

const onPosterErr = (movie: Movie) => {
  posterBroken.value = { ...posterBroken.value, [movie.name]: true }
}

const loadMyFeedback = async () => {
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

// 初始化
onMounted(() => {
  loadMovies()
  if (userStore.isLoggedIn && userStore.userInfo) {
    loadMyFavorites()
    loadMyWatched()
    loadMyFeedback()
  }
})

// 加载电影列表
const loadMovies = async () => {
  loading.value = true
  try {
    const response = await movieApi.getMovies(
      pagination.page,
      pagination.pageSize,
      searchForm.genre,
      searchForm.keyword,
      searchForm.source
    )
    if (response.data.success) {
      movies.value = response.data.movies
      pagination.total = response.data.pagination.total
      genres.value = [''].concat(response.data.genres || ALLOWED_GENRES)
    }
  } catch (error: any) {
    ElMessage.error('加载电影失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

// 搜索
const searchMovies = () => {
  pagination.page = 1
  loadMovies()
}

// 分页
const onPageChange = () => {
  loadMovies()
}

// 加载我的收藏
const loadMyFavorites = async () => {
  if (!userStore.userInfo) return
  try {
    const response = await userApi.getMyFavorites()
    if (response.data.success) {
      myFavorites.value = response.data.favorites.map((f: any) => f.movie_name)
    }
  } catch (error) {
    console.error('加载收藏失败', error)
  }
}

// 判断是否收藏
const isFavorite = (movieName: string) => {
  return myFavorites.value.includes(movieName)
}

const loadMyWatched = async () => {
  if (!userStore.userInfo) return
  try {
    const response = await userApi.getMyWatched(400)
    if (response.data.success) {
      myWatched.value = (response.data.watched || []).map((w: { movie_name: string }) => w.movie_name)
    }
  } catch (error) {
    console.error('加载已看过失败', error)
  }
}

const isWatched = (movieName: string) => myWatched.value.includes(movieName)

const detailGenresStr = () => {
  if (movieDetail.value.data?.type) return String(movieDetail.value.data.type)
  if (movieDetail.value.attributes) {
    return (
      movieDetail.value.attributes
        ?.filter((attr: { relation: string }) => attr.relation === 'genre')
        .map((attr: { value: string }) => attr.value)
        .join('/') || ''
    )
  }
  return ''
}

// 显示电影详情（不再自动写入「看过」，需用户主动勾选）
const showMovieDetail = async (movie: Movie) => {
  currentMovie.value = movie
  detailVisible.value = true

  try {
    const response = await movieApi.getMovieDetail(movie.name, searchForm.source, (movie as any).tmdb_id ?? undefined)
    movieDetail.value = response.data
  } catch (error) {
    console.error('加载详情失败', error)
    movieDetail.value = { attributes: [] }
  }
}

const toggleLikeBrowse = async () => {
  if (!userStore.userInfo || !currentMovie.value) return
  const nm = currentMovie.value.name
  const next = isLikedCurrent.value ? null : 'like'
  try {
    const res = await userApi.upsertFeedback(nm, { vote: next })
    if (res.data?.success && res.data.feedback) feedbackMap.value[nm] = res.data.feedback
    ElMessage.success(next ? '已标记：喜欢' : '已取消：喜欢')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const toggleDislikeBrowse = async () => {
  if (!userStore.userInfo || !currentMovie.value) return
  const nm = currentMovie.value.name
  const next = isDislikedCurrent.value ? null : 'dislike'
  try {
    const res = await userApi.upsertFeedback(nm, { vote: next })
    if (res.data?.success && res.data.feedback) feedbackMap.value[nm] = res.data.feedback
    ElMessage.success(next ? '已标记：不喜欢' : '已取消：不喜欢')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const toggleBlockBrowse = async () => {
  if (!userStore.userInfo || !currentMovie.value) return
  const nm = currentMovie.value.name
  const next = !isBlockedCurrent.value
  try {
    if (next) {
      await ElMessageBox.confirm('屏蔽后，该电影将不会再出现在推荐结果中。确定屏蔽吗？', '屏蔽电影', {
        confirmButtonText: '屏蔽',
        cancelButtonText: '取消',
        type: 'warning'
      })
    }
    const res = await userApi.upsertFeedback(nm, { blocked: next })
    if (res.data?.success && res.data.feedback) feedbackMap.value[nm] = res.data.feedback
    ElMessage.success(next ? '已屏蔽' : '已取消屏蔽')
  } catch (e: any) {
    if (e === 'cancel' || e?.message === 'cancel') return
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const watchedReviewVisible = ref(false)

const browseWatchedGenres = computed(() => {
  if (!currentMovie.value) return ''
  return String(detailGenresStr() || '').trim()
})

const openWatchedReviewBrowse = () => {
  if (!userStore.userInfo || !currentMovie.value) return
  watchedReviewVisible.value = true
}

const onWatchedReviewSavedBrowse = async () => {
  await loadMyWatched()
  await loadMyFeedback()
}

// 收藏/取消收藏
const toggleFavorite = async () => {
  if (!userStore.userInfo || !currentMovie.value) return
  
  try {
    if (isFavorite(currentMovie.value.name)) {
      await userApi.removeMyFavorite(currentMovie.value.name)
      myFavorites.value = myFavorites.value.filter(
        name => name !== currentMovie.value?.name
      )
      ElMessage.success('已取消收藏')
    } else {
      // 获取电影类型信息
      const genres = detailGenresStr()

      await userApi.addMyFavorite(currentMovie.value.name, genres)
      myFavorites.value.push(currentMovie.value.name)
      ElMessage.success('已收藏')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '操作失败')
  }
}
</script>

<style scoped>
.browse-page {
  padding: 8px 20px 44px;
  max-width: 1240px;
  margin: 0 auto;
  background:
    radial-gradient(900px 520px at 12% 0%, rgba(99, 102, 241, 0.16), transparent 55%),
    radial-gradient(700px 420px at 88% 12%, rgba(168, 85, 247, 0.12), transparent 50%),
    radial-gradient(600px 360px at 50% 100%, rgba(14, 165, 233, 0.06), transparent 50%);
  position: relative;
}

.browse-page::before {
  content: '';
  position:fixed;
  top: 64px;
  bottom: 0;
  left: 0;
  right: 0;
  /* 片库页两侧氛围背景（只在两侧空白显示，不影响操作） */
  opacity: 0.24;
  pointer-events: none;
  z-index: 0;
  filter: brightness(0.96) contrast(1.06) saturate(1.02);
  background-image:
    radial-gradient(520px 420px at 18% 22%, rgba(99, 102, 241, 0.22), transparent 60%),
    radial-gradient(520px 420px at 82% 22%, rgba(168, 85, 247, 0.18), transparent 60%),
    url('/api/background/片库5.jpg'),
    url('/api/background/片库4.jpg'),
    url('/api/background/片库1.png');
  background-repeat: no-repeat;

  background-size:
    520px 420px,
    520px 420px,
    contain,
    contain,
    contain;

  background-position:
    18% 18%,
    82% 18%,
    -8% 56%,
    50% 56%,
    108% 56%;
}

.browse-page::after {
  content: '';
  position: fixed;
  inset: 64px 0 0 0;
  pointer-events: none;
  z-index: 0;
  background-image: url('/api/background/4.jpg');
  background-repeat: no-repeat;
  background-size: contain;
  /* 让中间区域更“柔和”的模糊底图位置（调这个可改变中间纹理位置） */
  background-position: 50% 56%;
  filter: blur(18px);
  opacity: 0.46;
  /* mask：中间可见、两侧透明。想反过来（两侧可见）就把 0/1 调换 */
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 32%,
    rgba(0, 0, 0, 1) 32%,
    rgba(0, 0, 0, 1) 68%,
    rgba(0, 0, 0, 0) 68%,
    rgba(0, 0, 0, 0) 100%
  );
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 32%,
    rgba(0, 0, 0, 1) 32%,
    rgba(0, 0, 0, 1) 68%,
    rgba(0, 0, 0, 0) 68%,
    rgba(0, 0, 0, 0) 100%
  );
}

.browse-page > * {
  position: relative;
  z-index: 1;
}

@media (max-width: 900px) {
  .browse-page::before {
    opacity: 0.14;
    background-size:
      auto,
      auto,
      contain,
      contain,
      contain;
    background-position:
      18% 18%,
      82% 18%,
      -8% 56%,
      50% 56%,
      108% 56%;
  }

  .browse-page::after {
    filter: blur(14px);
    opacity: 0.76;
    -webkit-mask-image: linear-gradient(
      90deg,
      rgba(0, 0, 0, 0) 0%,
      rgba(0, 0, 0, 0) 28%,
      rgba(0, 0, 0, 1) 28%,
      rgba(0, 0, 0, 1) 72%,
      rgba(0, 0, 0, 0) 72%,
      rgba(0, 0, 0, 0) 100%
    );
    mask-image: linear-gradient(
      90deg,
      rgba(0, 0, 0, 0) 0%,
      rgba(0, 0, 0, 0) 28%,
      rgba(0, 0, 0, 1) 28%,
      rgba(0, 0, 0, 1) 72%,
      rgba(0, 0, 0, 0) 72%,
      rgba(0, 0, 0, 0) 100%
    );
  }
}

.glass.panel {
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  background: rgba(255, 255, 255, 0.06) !important;
  backdrop-filter: blur(18px) saturate(1.12);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.06) inset,
    0 22px 70px rgba(0, 0, 0, 0.28) !important;
}

.search-card :deep(.el-card__body) {
  padding: 18px 20px 14px;
}

.search-card {
  margin-bottom: 20px;
}

.search-form {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 4px 8px;
}

.search-form :deep(.el-form-item) {
  margin-bottom: 10px;
  margin-right: 8px;
}

.search-form :deep(.el-form-item__label) {
  color: rgba(226, 232, 240, 0.82);
  font-weight: 600;
}

.sf-source {
  min-width: min(100%, 300px);
}

.source-seg {
  width: 220px;
}

.sf-genre .genre-select {
  width: 160px;
}

.sf-keyword .keyword-input {
  width: min(100vw - 80px, 280px);
}

.sf-actions :deep(.el-form-item__content) {
  margin-left: 0 !important;
}

.search-card :deep(.el-input__wrapper),
.search-card :deep(.el-select .el-input__wrapper) {
  background: rgba(2, 6, 23, 0.38);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset;
}

.search-card :deep(.el-input__inner) {
  color: rgba(248, 250, 252, 0.94);
}

.search-card :deep(.el-select .el-input__inner) {
  color: rgba(248, 250, 252, 0.94);
}

.search-card :deep(.el-select__placeholder) {
  color: rgba(148, 163, 184, 0.88);
}

/* Element Plus 2.x：部分版本用 el-select__wrapper 而非 el-input__wrapper */
.search-card :deep(.el-select__wrapper) {
  background: rgba(2, 6, 23, 0.38) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.12) inset !important;
}

.search-card :deep(.el-select__selected-item) {
  color: rgba(248, 250, 252, 0.94);
}

.search-card :deep(.el-select__caret) {
  color: rgba(226, 232, 240, 0.75);
}

.search-card :deep(.el-segmented) {
  --el-segmented-item-selected-color: rgba(248, 250, 252, 0.98);
  --el-segmented-item-selected-bg-color: rgba(99, 102, 241, 0.36);
  --el-segmented-item-hover-bg-color: rgba(255, 255, 255, 0.06);
  background: rgba(2, 6, 23, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.search-card :deep(.el-segmented__item-label) {
  color: rgba(226, 232, 240, 0.88);
}

.search-card :deep(.el-segmented__item:hover .el-segmented__item-label) {
  color: rgba(248, 250, 252, 0.92);
}

.movie-card {
  min-height: 520px;
}

.movie-card :deep(.el-card__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding: 14px 18px;
}

.movie-card :deep(.el-card__body) {
  padding: 16px 18px 22px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.card-header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.list-title {
  font-size: 17px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.94);
  letter-spacing: -0.02em;
}

.list-sub {
  font-size: 13px;
  color: rgba(148, 163, 184, 0.95);
}

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
  .card-header {
    flex-direction: column;
    align-items: stretch;
  }

  .browse-pagination :deep(.el-pagination) {
    justify-content: center;
  }

  .source-seg {
    width: 100%;
    max-width: 320px;
  }
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
  width: 40px;
  height: 40px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(15, 23, 42, 0.18);
  color: #fff;
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

.dlg {
  padding: 8px 0;
}

.dlg-left {
  position: sticky;
  top: 0;
}

.movie-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 18px;
  padding: 4px 0 8px;
}

.movie-item {
  background: rgba(2, 6, 23, 0.45);
  border-radius: 18px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.22s ease, box-shadow 0.22s ease, transform 0.22s ease;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.28);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.movie-item:hover {
  transform: translateY(-4px);
  border-color: rgba(99, 102, 241, 0.45);
  box-shadow: 0 20px 48px rgba(99, 102, 241, 0.22);
}

.movie-poster {
  position: relative;
  width: 100%;
  padding-top: 150%;
  background: linear-gradient(145deg, #312e81 0%, #6366f1 55%, #7c3aed 100%);
  overflow: hidden;
}

.movie-poster::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 55%, rgba(2, 6, 23, 0.55) 100%);
  pointer-events: none;
}

.poster-img {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.poster-placeholder {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.88);
  opacity: 0.95;
}

.favorite-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 1;
  background: rgba(15, 23, 42, 0.55);
  color: #fde68a;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  border: 1px solid rgba(253, 224, 71, 0.35);
  backdrop-filter: blur(8px);
}

.watched-badge {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 1;
  background: rgba(15, 23, 42, 0.55);
  color: #bbf7d0;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  border: 1px solid rgba(74, 222, 128, 0.35);
  backdrop-filter: blur(8px);
}

.movie-info {
  padding: 12px 14px 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.movie-title {
  font-weight: 700;
  font-size: 14px;
  margin-bottom: 8px;
  color: rgba(248, 250, 252, 0.96);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.movie-genres {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.movie-genres :deep(.el-tag) {
  border-radius: 999px;
  border-color: rgba(148, 163, 184, 0.35);
  background: rgba(15, 23, 42, 0.4);
  color: rgba(226, 232, 240, 0.92);
}

.movie-director {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: rgba(148, 163, 184, 0.95);
}

.movie-director .el-icon {
  color: rgba(129, 140, 248, 0.85);
}

.detail-poster {
  margin-bottom: 16px;
  border-radius: 12px;
  overflow: hidden;
  max-height: 280px;
  background: #f3f4f6;
}

.detail-poster img {
  width: 100%;
  max-height: 280px;
  object-fit: cover;
  display: block;
}

.movie-detail {
  padding: 10px 0;
}

.no-detail {
  text-align: center;
  padding: 40px 0;
}

.empty-state {
  padding: 48px 0 56px;
}

.empty-state :deep(.el-empty__description p) {
  color: rgba(148, 163, 184, 0.95);
}
</style>

<!-- el-select 下拉层 teleport 到 body，需非 scoped 才能命中 popper-class -->
<style>
.browse-genre-dropdown.el-select__popper,
.browse-genre-dropdown.el-popper {
  background: rgba(15, 23, 42, 0.98) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.45) !important;
}

.browse-genre-dropdown .el-select-dropdown__item {
  color: rgba(226, 232, 240, 0.92);
}

.browse-genre-dropdown .el-select-dropdown__item.is-hovering,
.browse-genre-dropdown .el-select-dropdown__item:hover {
  background: rgba(99, 102, 241, 0.22) !important;
}

.browse-genre-dropdown .el-select-dropdown__item.is-selected {
  color: rgba(255, 255, 255, 0.98);
  font-weight: 700;
  background: rgba(99, 102, 241, 0.32) !important;
}

.browse-genre-dropdown .el-select-dropdown__empty {
  color: rgba(148, 163, 184, 0.95);
}
</style>
