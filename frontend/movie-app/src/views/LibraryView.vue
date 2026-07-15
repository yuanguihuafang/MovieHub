<template>
  <div class="library-page page-mesh">
    <header class="lib-hero">
      <div class="lib-hero-inner">
        <h1>我的片单</h1>
        <p>把收藏、已看过与偏好类型放在一起管理；偏好类型会同步用于智能推荐。</p>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="lib-tabs">
      <el-tab-pane label="片单" name="playlists">
        <el-card class="glass panel" shadow="never">
          <template #header>
            <div class="panel-head">
              <div>
                <span class="panel-title">片单中心</span>
                <p class="panel-desc">把推荐结果一键保存为片单，也可以自己维护多个片单</p>
              </div>
              <div class="panel-actions">
                <el-button type="primary" round @click="createPlaylistUi">新建片单</el-button>
                <el-button :icon="Refresh" round @click="loadPlaylists">刷新</el-button>
              </div>
            </div>
          </template>

          <div v-if="plLoading" class="loading-state"><el-skeleton :rows="4" animated /></div>
          <div v-else class="pl-layout">
            <div class="pl-left">
              <div v-if="playlists.length === 0" class="empty-state">
                <el-empty description="暂无片单" />
              </div>
              <div v-else class="pl-list">
                <button
                  v-for="p in playlists"
                  :key="p.id"
                  type="button"
                  class="pl-item"
                  :class="{ active: p.id === activePlaylistId }"
                  @click="selectPlaylist(p.id)"
                >
                  <div class="pl-name">{{ p.name }}</div>
                  <div v-if="p.description" class="pl-desc">{{ p.description }}</div>
                </button>
              </div>
            </div>

            <div class="pl-right">
              <div v-if="!activePlaylistId" class="empty-state">
                <el-empty description="请选择左侧片单查看内容" />
              </div>
              <template v-else>
                <div class="pl-right-head">
                  <div class="pl-right-title">
                    <span class="panel-title">{{ activePlaylist?.name }}</span>
                    <span v-if="activePlaylist?.description" class="pl-right-sub">
                      {{ activePlaylist.description }}
                    </span>
                  </div>
                  <div class="pl-right-actions">
                    <el-button size="small" round @click="renamePlaylistUi">重命名</el-button>
                    <el-button size="small" type="danger" plain round @click="deletePlaylistUi">删除</el-button>
                  </div>
                </div>

                <div class="pl-add-row">
                  <el-autocomplete
                    v-model="addMovieQuery"
                    :fetch-suggestions="fetchAddMovieSuggestions"
                    placeholder="搜索并添加电影（必须是系统已有电影）"
                    clearable
                    value-key="display"
                    class="pl-add-ac"
                    popper-class="lib-pl-add-ac-popper"
                    @select="onPickAddMovie"
                  />
                  <el-button
                    type="primary"
                    round
                    :loading="addMovieSubmitting"
                    :disabled="!addMoviePicked || !addMoviePicked.movie_name"
                    @click="addPickedMovieToPlaylist"
                  >
                    添加到片单
                  </el-button>
                </div>

                <div v-if="plItemsLoading" class="loading-state"><el-skeleton :rows="4" animated /></div>
                <div v-else-if="playlistItems.length === 0" class="empty-state">
                  <el-empty description="片单暂无电影条目" />
                </div>
                <div v-else class="item-grid">
                  <article
                    v-for="it in playlistItems"
                    :key="it.id"
                    class="lib-card"
                    role="button"
                    tabindex="0"
                    @click="
                      openDetailNoTrack(it.movie_name, it.movie_source, it.tmdb_id ?? null, {
                        poster_url: it.poster_url,
                        genres_str: it.genres_str || it.genres,
                        score_str: it.score_str,
                        short_review: it.short_review
                      })
                    "
                  >
                    <div class="lib-thumb" :style="{ background: thumbStyle(it.movie_name) }">
                      <img
                        v-if="it.poster_url"
                        class="lib-poster"
                        :src="it.poster_url"
                        :alt="displayTitle(it.movie_name)"
                        loading="lazy"
                        referrerpolicy="no-referrer"
                      />
                      <span v-else class="lib-initial">{{ initialChar(it.movie_name) }}</span>
                    </div>
                    <div class="lib-body">
                      <h3 class="lib-title">{{ displayTitle(it.movie_name) }}</h3>
                      <p v-if="it.genres" class="lib-genre">{{ it.genres }}</p>
                      <time class="lib-time">{{ formatDate(it.added_at) }}</time>
                      <div class="lib-actions">
                        <el-button size="small" plain round @click.stop="removePlaylistItemUi(it.movie_name)">
                          移除
                        </el-button>
                      </div>
                    </div>
                  </article>
                </div>
              </template>
            </div>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="我的收藏" name="favorites">
        <el-card class="glass panel" shadow="never">
          <template #header>
            <div class="panel-head">
              <div>
                <span class="panel-title">收藏列表</span>
                <p class="panel-desc">从片库或详情页收藏的影片，会作为推荐“种子”参与建模</p>
              </div>
              <el-button type="primary" :icon="Refresh" round @click="loadFavorites">刷新</el-button>
            </div>
          </template>
          <div v-if="favLoading" class="loading-state"><el-skeleton :rows="4" animated /></div>
          <div v-else-if="favorites.length === 0" class="empty-state">
            <el-empty description="暂无收藏，去片库逛逛吧" />
            <el-button type="primary" round @click="$router.push('/browse')">进入片库</el-button>
          </div>
          <div v-else class="item-grid">
            <article
              v-for="row in favorites"
              :key="row.movie_name"
              class="lib-card"
              role="button"
              tabindex="0"
              @click="
                openDetailNoTrack(
                  row.movie_name,
                  guessDetailSource(row as any),
                  (row as any).tmdb_id ?? null
                )
              "
            >
              <div class="lib-thumb" :style="{ background: thumbStyle(row.movie_name) }">
                <img
                  v-if="row.poster_url"
                  class="lib-poster"
                  :src="row.poster_url"
                  :alt="displayTitle(row.movie_name)"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                />
                <span v-else class="lib-initial">{{ initialChar(row.movie_name) }}</span>
              </div>
              <div class="lib-body">
                <h3 class="lib-title">{{ displayTitle(row.movie_name) }}</h3>
                <p v-if="row.genres" class="lib-genre">{{ row.genres }}</p>
                <time class="lib-time">{{ formatDate(row.added_at) }}</time>
                <div class="lib-actions">
                  <el-button type="danger" size="small" plain round @click.stop="removeFavorite(row.movie_name)">
                    取消收藏
                  </el-button>
                </div>
              </div>
            </article>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="已看过" name="watched">
        <el-card class="glass panel" shadow="never">
          <template #header>
            <div class="panel-head">
              <div>
                <span class="panel-title">已看过</span>
                <p class="panel-desc">标记后<strong>不再重复推荐</strong>，但仍作为口味信号参与推荐</p>
              </div>
              <el-button type="primary" :icon="Refresh" round @click="loadWatched">刷新</el-button>
            </div>
          </template>
          <div v-if="watchLoading" class="loading-state"><el-skeleton :rows="4" animated /></div>
          <div v-else-if="watched.length === 0" class="empty-state">
            <el-empty description="暂无记录。在片库或首页详情中可标记已看过。" />
            <el-button type="primary" round @click="$router.push('/browse')">进入片库</el-button>
          </div>
          <div v-else class="item-grid">
            <article
              v-for="row in watched"
              :key="row.id"
              class="lib-card watched-card"
              role="button"
              tabindex="0"
              @click="openDetailNoTrack(row.movie_name, (row as any).movie_source, (row as any).tmdb_id ?? null)"
            >
              <div class="lib-thumb" :style="{ background: thumbStyle(row.movie_name) }">
                <img
                  v-if="(row as any).poster_url"
                  class="lib-poster"
                  :src="(row as any).poster_url"
                  :alt="displayTitle(row.movie_name)"
                  loading="lazy"
                  referrerpolicy="no-referrer"
                />
                <span v-else class="lib-initial">{{ initialChar(row.movie_name) }}</span>
                <span class="watched-badge">看过</span>
              </div>
              <div class="lib-body">
                <h3 class="lib-title">{{ displayTitle(row.movie_name) }}</h3>
                <p v-if="row.genres" class="lib-genre">{{ row.genres }}</p>
                <time class="lib-time">{{ formatDate(row.watched_at) }}</time>
                <div class="lib-actions">
                  <el-button size="small" plain round @click.stop="removeWatchedRow(row)">取消标记</el-button>
                </div>
              </div>
            </article>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-card class="prefs-card glass panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <div>
            <span class="panel-title">最近偏好类型</span>
            <p class="panel-desc">用于辅助推荐聚焦类型方向（可多选，推荐页会自动读取）</p>
          </div>
          <el-button type="primary" :loading="prefSaving" round @click="savePreferences">保存偏好</el-button>
        </div>
      </template>
      <el-checkbox-group v-model="prefGenres" class="genre-grid">
        <el-checkbox v-for="g in GENRE_OPTIONS" :key="g" :label="g" :value="g" class="genre-chip">{{ g }}</el-checkbox>
      </el-checkbox-group>
    </el-card>

    <!-- 详情弹窗：与片库一致风格；track=false 不写入浏览记录 -->
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
            <div class="dlg-h1">{{ mergedDetailTitle }}</div>
            <div class="dlg-hmeta">
              <span v-if="displayScore" class="pill score">★ {{ displayScore }}</span>
              <span v-if="displayTypePill" class="pill">{{ displayTypePill }}</span>
              <span v-if="movieDetail?.data?.start_time" class="pill soft">{{ movieDetail.data.start_time }}</span>
            </div>
          </div>
          <button type="button" class="dlg-close" aria-label="关闭" @click="detailVisible = false">
            <el-icon><Close /></el-icon>
          </button>
        </div>
      </template>

      <div v-if="showDlgRow" class="dlg dlg-row">
        <div class="dlg-left">
          <div v-if="mergedPosterUrl" class="dlg-poster">
            <img :src="mergedPosterUrl" alt="" loading="lazy" />
          </div>
          <div v-else class="dlg-ph">暂无海报</div>
        </div>
        <div class="dlg-right">
          <div v-if="mergedOverview" class="dlg-overview">
            {{ mergedOverview }}
          </div>
          <el-descriptions
            v-if="movieDetail.data"
            :column="2"
            border
            size="small"
            class="dlg-desc purple-desc"
          >
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
            <el-descriptions-item v-if="!movieDetail.data.type && recCardGenresLine" label="类型">
              {{ recCardGenresLine }}
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
            <el-descriptions-item v-if="!movieDetail.data.score && recCardDetail?.score_str" label="评分">
              {{ recCardDetail.score_str }}
            </el-descriptions-item>
            <el-descriptions-item
              v-if="savedShortReviewBlurb && (movieDetail.data.overview || '').trim()"
              label="推荐短评"
              :span="2"
            >
              {{ savedShortReviewBlurb }}
            </el-descriptions-item>
          </el-descriptions>
          <el-descriptions
            v-else-if="recCardDetail"
            :column="2"
            border
            size="small"
            class="dlg-desc purple-desc"
          >
            <el-descriptions-item v-if="recCardGenresLine" label="类型">
              {{ recCardGenresLine }}
            </el-descriptions-item>
            <el-descriptions-item v-if="recCardDetail.score_str" label="评分">
              {{ recCardDetail.score_str }}
            </el-descriptions-item>
          </el-descriptions>
          <div v-if="movieDetail.attributes?.length && !movieDetail.data" class="dlg-attrs">
            <el-descriptions :column="1" border size="small" class="dlg-desc purple-desc dlg-desc-attrs">
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
        </div>
      </div>
      <div v-else-if="movieDetail.attributes?.length" class="dlg">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item v-for="attr in movieDetail.attributes" :key="attr.relation" :label="attr.relation_zh">
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
        <template v-if="userStore.userInfo && currentMovieName">
          <el-button :type="isBlockedCurrent ? 'danger' : 'default'" @click="toggleBlock" round>
            {{ isBlockedCurrent ? '已屏蔽' : '屏蔽' }}
          </el-button>
          <el-button :type="isLikedCurrent ? 'success' : 'default'" @click="toggleLike" round>
            {{ isLikedCurrent ? '已喜欢' : '👍 喜欢' }}
          </el-button>
          <el-button :type="isDislikedCurrent ? 'warning' : 'default'" @click="toggleDislike" round>
            {{ isDislikedCurrent ? '已标记不喜欢' : '👎 不喜欢' }}
          </el-button>
          <AddToPlaylistLauncher v-bind="libraryAddToPlaylistProps" />
          <el-button
            :type="isWatchedCurrent ? 'success' : 'default'"
            @click="openWatchedReviewLibrary"
            round
          >
            {{ isWatchedCurrent ? '已看' : '看过' }}
          </el-button>
          <el-button :type="isFavCurrent ? 'warning' : 'primary'" @click="toggleFavoriteFromDialog" round>
            {{ isFavCurrent ? '取消收藏' : '收藏' }}
          </el-button>
        </template>
      </template>
    </el-dialog>

    <WatchedReviewDialog
      v-model="watchedReviewVisible"
      :movie-name="currentMovieName"
      :movie-source="detailMovieSource"
      :tmdb-id="detailTmdbId"
      :genres="libraryWatchedGenres"
      :is-watched="isWatchedCurrent"
      :initial-note="(currentFeedback?.note || '').toString()"
      @saved="onWatchedReviewSavedLibrary"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { userApi, movieApi, reviewApi } from '@/services/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import type { Favorite } from '@/types'
import { plainReviewText } from '@/utils/plainReview'
import AddToPlaylistLauncher from '@/components/AddToPlaylistLauncher.vue'
import WatchedReviewDialog from '@/components/WatchedReviewDialog.vue'

const GENRE_OPTIONS = [
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

const THUMB_GRADS = [
  'linear-gradient(145deg, #312e81 0%, #6366f1 100%)',
  'linear-gradient(145deg, #134e4a 0%, #0d9488 100%)',
  'linear-gradient(145deg, #831843 0%, #db2777 100%)',
  'linear-gradient(145deg, #422006 0%, #b45309 100%)',
  'linear-gradient(145deg, #0f172a 0%, #2563eb 100%)',
  'linear-gradient(145deg, #3b0764 0%, #7c3aed 100%)'
]

const route = useRoute()
const userStore = useUserStore()

const activeTab = ref<'favorites' | 'playlists' | 'watched'>('playlists')
const favorites = ref<Favorite[]>([])
const watched = ref<
  Array<{ id: number; movie_name: string; genres: string; watched_at: string; poster_url?: string }>
>([])
const favLoading = ref(false)
const watchLoading = ref(false)
const prefGenres = ref<string[]>([])
const prefSaving = ref(false)

type PlaylistRow = { id: number; user_id: number; name: string; description: string; created_at: string }
type PlaylistItemRow = {
  id: number
  playlist_id: number
  movie_name: string
  movie_source: string
  tmdb_id?: number | null
  genres: string
  poster_url?: string
  genres_str?: string
  score_str?: string
  short_review?: string
  added_at: string
}

const playlists = ref<PlaylistRow[]>([])
const playlistItems = ref<PlaylistItemRow[]>([])
const activePlaylistId = ref<number | null>(null)
const plLoading = ref(false)
const plItemsLoading = ref(false)

const activePlaylist = ref<PlaylistRow | null>(null)

// 片单内手动添加影片（从系统已有电影选择）
const addMovieQuery = ref('')
const addMoviePicked = ref<any | null>(null)
const addMovieLoading = ref(false)
const addMovieSubmitting = ref(false)

const fetchAddMovieSuggestions = async (q: string, cb: (arr: any[]) => void) => {
  const qq = (q || '').trim()
  if (qq.length < 2) return cb([])
  addMovieLoading.value = true
  try {
    const res = await reviewApi.searchMovies(qq, 10)
    cb(res.data?.movies || [])
  } catch {
    cb([])
  } finally {
    addMovieLoading.value = false
  }
}

const onPickAddMovie = (m: any) => {
  addMoviePicked.value = m
}

const addPickedMovieToPlaylist = async () => {
  if (!userStore.userInfo || !activePlaylistId.value) return
  if (!addMoviePicked.value?.movie_name) {
    ElMessage.warning('请先从下拉建议中选择电影')
    return
  }
  addMovieSubmitting.value = true
  try {
    await userApi.addPlaylistItem(activePlaylistId.value, addMoviePicked.value.movie_name, {
      movieSource: addMoviePicked.value.source || '',
      genres: addMoviePicked.value.genres || ''
    })
    ElMessage.success('已加入片单（如已存在则不重复）')
    addMoviePicked.value = null
    addMovieQuery.value = ''
    await loadPlaylistItems()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加入失败')
  } finally {
    addMovieSubmitting.value = false
  }
}

const displayTitle = (movieName: string) => movieName.replace(/_/g, ' ')
const initialChar = (movieName: string) => {
  const s = displayTitle(movieName).trim()
  return s.length ? s[0]! : '?'
}
const thumbStyle = (movieName: string) => {
  let h = 0
  for (let i = 0; i < movieName.length; i++) {
    h = (h * 31 + movieName.charCodeAt(i)) >>> 0
  }
  return THUMB_GRADS[h % THUMB_GRADS.length]
}

const formatDate = (dateStr: string) =>
  new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })

const applyRouteTab = () => {
  const t = route.query.tab as string
  if (t === 'watched') activeTab.value = 'watched'
  else if (t === 'favorites') activeTab.value = 'favorites'
  else if (t === 'playlists') activeTab.value = 'playlists'
  // 未指定 tab：保持当前（默认是 playlists）
}

const loadFavorites = async () => {
  if (!userStore.userInfo) return
  favLoading.value = true
  try {
    const response = await userApi.getMyFavorites()
    if (response.data.success) favorites.value = response.data.favorites || []
  } catch {
    ElMessage.error('加载收藏失败')
  } finally {
    favLoading.value = false
  }
}

const loadWatched = async () => {
  if (!userStore.userInfo) return
  watchLoading.value = true
  try {
    const res = await userApi.getMyWatched(200)
    if (res.data.success) watched.value = res.data.watched || []
  } catch {
    ElMessage.error('加载已看过失败')
  } finally {
    watchLoading.value = false
  }
}

const loadPreferences = async () => {
  if (!userStore.userInfo) return
  try {
    const res = await userApi.getUserProfile()
    if (res.data.success && res.data.user?.preferred_genres) {
      prefGenres.value = [...(res.data.user.preferred_genres as string[])]
    }
  } catch {
    /* ignore */
  }
}

const savePreferences = async () => {
  if (!userStore.userInfo) {
    ElMessage.warning('请先登录')
    return
  }
  prefSaving.value = true
  try {
    await userApi.updatePreferences(prefGenres.value)
    ElMessage.success('偏好已保存')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    prefSaving.value = false
  }
}

const removeFavorite = async (movieName: string) => {
  try {
    await ElMessageBox.confirm(`确定取消收藏「${displayTitle(movieName)}」？`, '确认', {
      type: 'warning'
    })
    await userApi.removeMyFavorite(movieName)
    favorites.value = favorites.value.filter((f) => f.movie_name !== movieName)
    ElMessage.success('已取消收藏')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const removeWatchedRow = async (row: { movie_name: string }) => {
  try {
    await ElMessageBox.confirm(`取消「${displayTitle(row.movie_name)}」的已看过标记？`, '确认', {
      type: 'warning'
    })
    await userApi.removeWatched(row.movie_name)
    watched.value = watched.value.filter((w) => w.movie_name !== row.movie_name)
    ElMessage.success('已取消')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const loadPlaylists = async () => {
  if (!userStore.userInfo) return
  plLoading.value = true
  try {
    const res = await userApi.getPlaylists()
    if (res.data.success) {
      playlists.value = res.data.playlists || []
      const id = activePlaylistId.value
      const exists = id != null && playlists.value.some((p) => p.id === id)
      if (exists) {
        activePlaylist.value = playlists.value.find((p) => p.id === id) || null
        await loadPlaylistItems()
      } else if (playlists.value.length > 0) {
        await selectPlaylist(playlists.value[0].id)
      } else {
        activePlaylistId.value = null
        activePlaylist.value = null
        playlistItems.value = []
      }
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载片单失败')
  } finally {
    plLoading.value = false
  }
}

const selectPlaylist = async (id: number) => {
  activePlaylistId.value = id
  activePlaylist.value = playlists.value.find((p) => p.id === id) || null
  await loadPlaylistItems()
}

const loadPlaylistItems = async () => {
  if (!userStore.userInfo || !activePlaylistId.value) return
  plItemsLoading.value = true
  try {
    const res = await userApi.getPlaylistItems(activePlaylistId.value)
    if (res.data.success) playlistItems.value = res.data.items || []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载片单内容失败')
  } finally {
    plItemsLoading.value = false
  }
}

const createPlaylistUi = async () => {
  try {
    const { value } = await ElMessageBox.prompt('请输入片单名称（最多 64 字）', '新建片单', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：本周想看 / 经典剧情片',
      inputValidator: (v) => {
        if (!v || !v.trim()) return '名称不能为空'
        if (v.length > 64) return '最多 64 字'
        return true
      }
    })
    const res = await userApi.createPlaylist(value.trim())
    if (res.data?.success) {
      ElMessage.success('片单已创建')
      await loadPlaylists()
      if (res.data.id) await selectPlaylist(res.data.id)
    }
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const renamePlaylistUi = async () => {
  if (!activePlaylistId.value || !activePlaylist.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入新的片单名称', '重命名片单', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: activePlaylist.value.name,
      inputValidator: (v) => {
        if (!v || !v.trim()) return '名称不能为空'
        if (v.length > 64) return '最多 64 字'
        return true
      }
    })
    await userApi.updatePlaylist(activePlaylistId.value, { name: value.trim() })
    ElMessage.success('已保存')
    await loadPlaylists()
    activePlaylist.value = playlists.value.find((p) => p.id === activePlaylistId.value) || null
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const deletePlaylistUi = async () => {
  if (!activePlaylistId.value || !activePlaylist.value) return
  try {
    await ElMessageBox.confirm(`确定删除片单「${activePlaylist.value.name}」？删除后不可恢复。`, '确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    await userApi.deletePlaylist(activePlaylistId.value)
    ElMessage.success('已删除')
    activePlaylistId.value = null
    activePlaylist.value = null
    playlistItems.value = []
    await loadPlaylists()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const removePlaylistItemUi = async (movieName: string) => {
  if (!activePlaylistId.value) return
  try {
    await userApi.removePlaylistItem(activePlaylistId.value, movieName)
    playlistItems.value = playlistItems.value.filter((it) => it.movie_name !== movieName)
    ElMessage.success('已移除')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const detailVisible = ref(false)
const currentMovieName = ref<string>('')
const movieDetail = ref<any>({})
const recCardDetail = ref<any>(null)
const detailMovieSource = ref('douban')
const detailTmdbId = ref<number | null>(null)
const watchedReviewVisible = ref(false)
const feedbackMap = ref<Record<string, any>>({})

const isFavoriteName = (movieName: string) => favorites.value.some((f) => f.movie_name === movieName)
const isWatchedName = (movieName: string) => watched.value.some((w) => w.movie_name === movieName)

const currentFeedback = computed(() => {
  const k = (currentMovieName.value || '').trim()
  if (!k) return null
  return feedbackMap.value[k] || null
})
const isBlockedCurrent = computed(() => !!currentFeedback.value && !!currentFeedback.value.blocked)
const isLikedCurrent = computed(() => currentFeedback.value?.vote === 'like')
const isDislikedCurrent = computed(() => currentFeedback.value?.vote === 'dislike')
const isFavCurrent = computed(() => !!currentMovieName.value && isFavoriteName(currentMovieName.value))
const isWatchedCurrent = computed(() => !!currentMovieName.value && isWatchedName(currentMovieName.value))

const mergedDetailTitle = computed(
  () => movieDetail.value?.data?.title || displayTitle(currentMovieName.value) || '影片详情'
)

const recCardGenresLine = computed(() => {
  const c = recCardDetail.value
  if (!c) return ''
  const g = (c.genres_str || c.genres || '').trim()
  return g
})

const savedShortReviewBlurb = computed(() => plainReviewText(recCardDetail.value?.short_review))

const mergedPosterUrl = computed(() => {
  const u = (movieDetail.value?.poster_url || '').trim()
  if (u) return u
  return (recCardDetail.value?.poster_url || '').trim()
})

const mergedOverview = computed(() => {
  const o = (movieDetail.value?.data?.overview || '').trim()
  if (o) return o
  return savedShortReviewBlurb.value || ''
})

const displayScore = computed(() => {
  const s = movieDetail.value?.data?.score
  if (s != null && String(s).trim() !== '') return String(s).trim()
  return (recCardDetail.value?.score_str || '').trim()
})

const displayTypePill = computed(() => {
  const t = (movieDetail.value?.data?.type || '').trim()
  if (t) return t
  return recCardGenresLine.value
})

const showDlgRow = computed(() => {
  if (movieDetail.value?.data) return true
  const c = recCardDetail.value
  if (!c) return false
  return !!(
    mergedPosterUrl.value ||
    savedShortReviewBlurb.value ||
    recCardGenresLine.value ||
    (c.score_str || '').trim()
  )
})

const libraryWatchedGenres = computed(() => {
  const d = movieDetail.value?.data || {}
  return String(d.type || recCardGenresLine.value || '').trim()
})

const libraryAddToPlaylistProps = computed(() => {
  const name = currentMovieName.value
  if (!name) {
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
  const genresStr = String(d.type || recCardGenresLine.value || '').trim()
  const scoreStr = String(d.score != null && d.score !== '' ? d.score : recCardDetail.value?.score_str || '').trim()
  const posterUrl = String(mergedPosterUrl.value || '').trim()
  const note = (currentFeedback.value?.note || '').toString().trim()
  return {
    movieName: name,
    movieSource: detailMovieSource.value,
    tmdbId: detailTmdbId.value,
    genres: genresStr,
    posterUrl,
    genresStr,
    scoreStr,
    shortReview: note || undefined
  }
})

const openWatchedReviewLibrary = () => {
  if (!userStore.userInfo || !currentMovieName.value) return
  watchedReviewVisible.value = true
}

const onWatchedReviewSavedLibrary = async () => {
  await loadWatched()
  await loadMyFeedback()
}

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

const openDetailNoTrack = async (
  movieName: string,
  source?: string,
  tmdbId?: number | null,
  card?: { poster_url?: string; genres_str?: string; score_str?: string; short_review?: string } | null
) => {
  currentMovieName.value = movieName
  detailVisible.value = true
  recCardDetail.value = card && (card.poster_url || card.genres_str || card.score_str || card.short_review) ? card : null
  detailMovieSource.value = (source || 'douban').toString().trim() || 'douban'
  detailTmdbId.value = tmdbId ?? null
  try {
    const src = detailMovieSource.value
    const res = await movieApi.getMovieDetailNoTrack(movieName, src, tmdbId ?? undefined)
    movieDetail.value = res.data
  } catch {
    movieDetail.value = {}
  }
}

const guessDetailSource = (row: any): string => {
  const raw = (row?.movie_source ?? row?.movieSource ?? '').toString().trim()
  if (raw) return raw
  const tid = row?.tmdb_id ?? row?.tmdbId ?? null
  return tid != null ? 'tmdb_api' : 'douban'
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

const toggleLike = async () => {
  if (!userStore.userInfo || !currentMovieName.value) return
  const next = isLikedCurrent.value ? null : 'like'
  try {
    const res = await userApi.upsertFeedback(
      currentMovieName.value,
      { vote: next },
      { movieSource: detailMovieSource.value, tmdbId: detailTmdbId.value }
    )
    if (res.data?.success && res.data.feedback) feedbackMap.value[currentMovieName.value] = res.data.feedback
    ElMessage.success(next ? '已标记：喜欢' : '已取消：喜欢')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const toggleDislike = async () => {
  if (!userStore.userInfo || !currentMovieName.value) return
  const next = isDislikedCurrent.value ? null : 'dislike'
  try {
    const res = await userApi.upsertFeedback(
      currentMovieName.value,
      { vote: next },
      { movieSource: detailMovieSource.value, tmdbId: detailTmdbId.value }
    )
    if (res.data?.success && res.data.feedback) feedbackMap.value[currentMovieName.value] = res.data.feedback
    ElMessage.success(next ? '已标记：不喜欢' : '已取消：不喜欢')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const toggleBlock = async () => {
  if (!userStore.userInfo || !currentMovieName.value) return
  const next = !isBlockedCurrent.value
  try {
    if (next) {
      await ElMessageBox.confirm('屏蔽后，该电影将不会再出现在推荐结果中。确定屏蔽吗？', '屏蔽电影', {
        confirmButtonText: '屏蔽',
        cancelButtonText: '取消',
        type: 'warning'
      })
    }
    const res = await userApi.upsertFeedback(
      currentMovieName.value,
      { blocked: next },
      { movieSource: detailMovieSource.value, tmdbId: detailTmdbId.value }
    )
    if (res.data?.success && res.data.feedback) feedbackMap.value[currentMovieName.value] = res.data.feedback
    ElMessage.success(next ? '已屏蔽' : '已取消屏蔽')
  } catch (e: any) {
    if (e === 'cancel') return
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const toggleFavoriteFromDialog = async () => {
  if (!userStore.userInfo || !currentMovieName.value) return
  const g = movieDetail.value?.data?.type || ''
  try {
    if (isFavCurrent.value) {
      await userApi.removeMyFavorite(currentMovieName.value)
      await loadFavorites()
      ElMessage.success('已取消收藏')
    } else {
      await userApi.addMyFavorite(currentMovieName.value, g, detailMovieSource.value, detailTmdbId.value)
      await loadFavorites()
      ElMessage.success('已收藏')
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

watch(
  () => route.fullPath,
  () => {
    applyRouteTab()
    const raw = route.query.playlist
    const pid = Number(Array.isArray(raw) ? raw[0] : raw || 0)
    if (pid) {
      activePlaylistId.value = pid
      activeTab.value = 'playlists'
    }
  },
  { immediate: true }
)

watch(
  () => route.query.playlist,
  async (q) => {
    const pid = Number(Array.isArray(q) ? q[0] : q || 0)
    if (pid) {
      activePlaylistId.value = pid
      activeTab.value = 'playlists'
      await loadPlaylists()
    }
  }
)

onMounted(() => {
  loadFavorites()
  loadWatched()
  loadPreferences()
  const raw = route.query.playlist
  const pid = Number(Array.isArray(raw) ? raw[0] : raw || 0)
  if (pid) {
    activePlaylistId.value = pid
    activeTab.value = 'playlists'
  }
  loadPlaylists()
  loadMyFeedback()
})
</script>

<style scoped>
.library-page {
  padding: 8px 20px 44px;
  max-width: 1180px;
  margin: 0 auto;
  position: relative;
}

/* 片单页两侧氛围背景（只在两侧空白显示，不影响操作） */
.library-page::before,
.library-page::after {
  content: '';
  position: fixed;
  inset: 64px 0 0 0;
  pointer-events: none;
  z-index: 0;
}

/* 双人图贴在视口右侧；纵向 top 与伪元素顶对齐（伪元素 inset-top:64px = 顶栏高度，即图顶=菜单栏底） */
.library-page::before {
  opacity: 0.28;
  filter: brightness(1.12) contrast(1.05) saturate(1.06);
  background-image: url('/api/background/双人.png');
  background-repeat: no-repeat;
  background-size: auto 100%;
  background-position: right -30% top 0%;
}


.library-page::after {
  opacity: 0.24;
  filter: brightness(1.12) contrast(1.05) saturate(1.06);
  background-image: url('/api/background/双人.png');
  background-repeat: no-repeat;
  background-size: auto 100%;
  background-position: left -850px top 0%;
}

.library-page > * {
  position: relative;
  z-index: 1;
}

.lib-hero {
  position: relative;
  margin: 0 -4px 24px;
  padding: 28px 32px;
  border-radius: 22px;
  overflow: hidden;
  background-image:
    /* 右侧先纯黑，再往左过渡到紫色氛围 */
    linear-gradient(
      90deg,
      rgba(99, 102, 241, 0.22) 0%,
      rgba(129, 140, 248, 0.16) 42%,
      rgba(168, 85, 247, 0.12) 66%,
      rgba(2, 6, 23, 0.78) 84%,
      rgba(0, 0, 0, 1) 100%
    ),
    radial-gradient(900px 520px at 12% 0%, rgba(99, 102, 241, 0.26), transparent 58%),
    radial-gradient(760px 480px at 44% 30%, rgba(168, 85, 247, 0.18), transparent 62%),
    linear-gradient(135deg, rgba(30, 27, 75, 0.38), rgba(0, 0, 0, 0.35));
  background-repeat: no-repeat;
  background-size: cover;
  background-position: 0 0;
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.08) inset,
    0 22px 60px rgba(0, 0, 0, 0.28);
}

.lib-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  background-image: url('/api/background/钢铁侠.png');
  background-repeat: no-repeat;
  background-size: contain;
  background-position: 100% 50%;
  opacity: 0.28;
  filter: blur(18px) brightness(1.04) contrast(1.03) saturate(1.03);
  pointer-events: none;
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 1) 0%,
    rgba(0, 0, 0, 1) 58%,
    rgba(0, 0, 0, 0.8) 66%,
    rgba(0, 0, 0, 0.28) 74%,
    rgba(0, 0, 0, 0) 86%,
    rgba(0, 0, 0, 0) 100%
  );
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 1) 0%,
    rgba(0, 0, 0, 1) 58%,
    rgba(0, 0, 0, 0.8) 66%,
    rgba(0, 0, 0, 0.28) 74%,
    rgba(0, 0, 0, 0) 86%,
    rgba(0, 0, 0, 0) 100%
  );
}

.lib-hero::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  background-image: url('/api/background/钢铁侠.png');
  background-repeat: no-repeat;
  background-size: contain;
  background-position: 100% 50%;
  opacity: 0.96;
  filter: brightness(1.02) contrast(1.04) saturate(1.04);
  pointer-events: none;
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 44%,
    rgba(0, 0, 0, 0.18) 54%,
    rgba(0, 0, 0, 0.62) 62%,
    rgba(0, 0, 0, 1) 70%,
    rgba(0, 0, 0, 1) 100%
  );
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 44%,
    rgba(0, 0, 0, 0.18) 54%,
    rgba(0, 0, 0, 0.62) 62%,
    rgba(0, 0, 0, 1) 70%,
    rgba(0, 0, 0, 1) 100%
  );
}

.lib-hero-inner {
  position: relative;
  z-index: 1;
}

.lib-hero-inner h1 {
  margin: 0 0 8px;
  font-size: clamp(1.35rem, 2.5vw, 1.75rem);
  color: rgba(255, 255, 255, 0.96);
  letter-spacing: -0.02em;
}

.lib-hero-inner p {
  margin: 0;
  font-size: 14px;
  color: rgba(226, 232, 240, 0.86);
  line-height: 1.55;
  max-width: 640px;
}

.lib-tabs :deep(.el-tabs__header) {
  margin-bottom: 18px;
}

.lib-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: rgba(255, 255, 255, 0.12);
}

.lib-tabs :deep(.el-tabs__item) {
  font-weight: 600;
  font-size: 15px;
  color: rgba(226, 232, 240, 0.78);
}

.lib-tabs :deep(.el-tabs__item:hover) {
  color: rgba(255, 255, 255, 0.92);
}

.lib-tabs :deep(.el-tabs__item.is-active) {
  color: rgba(255, 255, 255, 0.96);
}

.lib-tabs :deep(.el-tabs__active-bar) {
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.95), rgba(168, 85, 247, 0.9));
}

.glass.panel {
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  background-color: rgba(255, 255, 255, 0.06) !important;
  backdrop-filter: blur(18px) saturate(1.12);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.06) inset,
    0 22px 70px rgba(0, 0, 0, 0.28) !important;
}

.glass.panel :deep(.el-card__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.prefs-card :deep(.el-card__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.pl-layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 16px;
}

.pl-left {
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  padding-right: 10px;
}

.pl-list {
  display: grid;
  gap: 10px;
}

.pl-item {
  text-align: left;
  padding: 12px 12px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: rgba(226, 232, 240, 0.9);
  cursor: pointer;
  transition: 0.18s ease;
}

.pl-item:hover {
  border-color: rgba(129, 140, 248, 0.45);
  background: rgba(99, 102, 241, 0.12);
}

.pl-item.active {
  border-color: rgba(168, 85, 247, 0.6);
  background: rgba(168, 85, 247, 0.12);
}

.pl-name {
  font-weight: 800;
  font-size: 14px;
}

.pl-desc {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.72);
}

.pl-right {
  padding-left: 2px;
}

.pl-right-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.pl-right-title {
  display: grid;
  gap: 4px;
}

.pl-right-sub {
  font-size: 12px;
  color: rgba(226, 232, 240, 0.72);
}

.pl-right-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pl-add-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: nowrap;
  margin: 0 0 14px;
}

.pl-add-ac {
  flex: 1;
  min-width: 0;
}

.pl-add-row :deep(.el-input__wrapper),
.pl-add-row :deep(.el-autocomplete .el-input__wrapper) {
  /* 片单中心搜索框：暗色系，贴合当前玻璃/深色主题 */
  background: rgba(15, 23, 42, 0.55);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.18) inset;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.pl-add-row :deep(.el-input__wrapper:hover),
.pl-add-row :deep(.el-autocomplete .el-input__wrapper:hover) {
  background: rgba(15, 23, 42, 0.68);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.26) inset;
}

.pl-add-row :deep(.el-input__wrapper.is-focus),
.pl-add-row :deep(.el-autocomplete .el-input__wrapper.is-focus) {
  background: rgba(15, 23, 42, 0.74);
  box-shadow:
    0 0 0 1px rgba(148, 163, 184, 0.22) inset,
    0 0 0 1px var(--el-color-primary) inset;
}

.pl-add-row :deep(.el-input__inner) {
  color: rgba(248, 250, 252, 0.96);
}

.pl-add-row :deep(.el-input__inner::placeholder) {
  color: var(--el-text-color-placeholder);
}

@media (max-width: 880px) {
  .pl-layout {
    grid-template-columns: 1fr;
  }
  .pl-left {
    border-right: none;
    padding-right: 0;
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

.dlg-attrs {
  margin-top: 14px;
}

.dlg-left {
  position: sticky;
  top: 0;
}

.panel-title {
  font-size: 17px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.94);
}

.panel-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: rgba(226, 232, 240, 0.78);
  line-height: 1.5;
  max-width: 560px;
}

.loading-state {
  padding: 12px 0;
}

.empty-state {
  text-align: center;
  padding: 32px 16px 24px;
}

.empty-state .el-button {
  margin-top: 12px;
}

.item-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.lib-card {
  display: flex;
  gap: 14px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(2, 6, 23, 0.22);
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}

.lib-card:hover {
  border-color: rgba(99, 102, 241, 0.38);
  box-shadow: 0 16px 40px rgba(99, 102, 241, 0.18);
  transform: translateY(-2px);
}

.lib-thumb {
  position: relative;
  flex: 0 0 84px;
  width: 84px;
  height: 120px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.15);
  overflow: hidden;
}

.lib-thumb::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(0, 0, 0, 0.06), rgba(0, 0, 0, 0.28));
  pointer-events: none;
}

.lib-poster {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.lib-initial {
  position: relative;
  z-index: 1;
  font-size: 28px;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.92);
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.watched-badge {
  position: absolute;
  bottom: 6px;
  right: 6px;
  z-index: 1;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #fff;
  background: rgba(15, 23, 42, 0.55);
  padding: 2px 6px;
  border-radius: 6px;
}

.lib-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.lib-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.96);
  line-height: 1.35;
  letter-spacing: -0.01em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lib-genre {
  margin: 0;
  font-size: 12px;
  color: rgba(148, 163, 184, 0.92);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.lib-time {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.82);
  margin-top: 2px;
}

.lib-actions {
  margin-top: auto;
  padding-top: 8px;
  display: flex;
  justify-content: flex-end;
}

.prefs-card {
  margin-top: 22px;
}

.genre-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 12px;
}

.genre-grid :deep(.genre-chip) {
  margin-right: 0 !important;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(2, 6, 23, 0.28);
  color: rgba(226, 232, 240, 0.9);
  transition: background 0.2s, border-color 0.2s;
}

.genre-grid :deep(.genre-chip:hover) {
  border-color: rgba(99, 102, 241, 0.35);
  background: rgba(2, 6, 23, 0.36);
}

.genre-grid :deep(.el-checkbox.is-checked .genre-chip) {
  border-color: rgba(99, 102, 241, 0.5);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.45), rgba(168, 85, 247, 0.28));
  color: rgba(255, 255, 255, 0.96);
}

@media (max-width: 520px) {
  .library-page {
    padding: 0 14px 34px;
  }

  .lib-hero {
    padding: 22px 20px;
  }

  .item-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<style>
/* el-autocomplete 下拉挂载在 body，需单独暗色皮肤（与片单中心玻璃主题一致） */
.lib-pl-add-ac-popper.el-popper {
  background: rgba(15, 23, 42, 0.94) !important;
  border: 1px solid rgba(148, 163, 184, 0.22) !important;
  box-shadow: 0 20px 55px rgba(0, 0, 0, 0.5) !important;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.lib-pl-add-ac-popper .el-autocomplete-suggestion {
  background: transparent;
}

.lib-pl-add-ac-popper .el-autocomplete-suggestion__wrap {
  max-height: 280px;
}

.lib-pl-add-ac-popper .el-autocomplete-suggestion li {
  color: rgba(248, 250, 252, 0.94);
  background: transparent;
}

.lib-pl-add-ac-popper .el-autocomplete-suggestion li:hover,
.lib-pl-add-ac-popper .el-autocomplete-suggestion li.highlighted {
  background: rgba(99, 102, 241, 0.22);
}
</style>
