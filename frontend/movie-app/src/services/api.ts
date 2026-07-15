import axios from 'axios'

const API_BASE = ''

const api = axios.create({
  baseURL: API_BASE,
  timeout: 60000
})

// 请求拦截器：自动添加 Authorization token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器：处理401错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      const path = window.location.pathname || ''
      if (!path.endsWith('/auth')) {
        const q = path && path !== '/' ? `?redirect=${encodeURIComponent(path + window.location.search)}` : ''
        window.location.href = `/auth${q}`
      }
    }
    return Promise.reject(error)
  }
)

// 首页聚合
export const homeApi = {
  getFeed() {
    return api.get('/api/home/feed')
  },
  getVedio() {
    return api.get('/api/home/vedio')
  }
}

// 电影相关API
export const movieApi = {
  getMovies(
    page: number = 1,
    pageSize: number = 16,
    genre?: string,
    search?: string,
    source?: string
  ) {
    return api.get('/api/movies', {
      params: { page, page_size: pageSize, genre, search, source }
    })
  },
  
  getMovieDetail(movieName: string, source?: string, tmdbId?: number) {
    return api.get(`/api/movies/${encodeURIComponent(movieName)}/detail`, {
      params: { source, tmdb_id: tmdbId }
    })
  },

  getMovieDetailNoTrack(movieName: string, source?: string, tmdbId?: number) {
    return api.get(`/api/movies/${encodeURIComponent(movieName)}/detail`, {
      params: { source, tmdb_id: tmdbId, track: false }
    })
  }
}

// 推荐相关API（主路径为异步 Job；解读/总结在定榜后按需请求）
export const recommendApi = {
  createRecommendJob(
    userId: number,
    userInput: string,
    topkKg: number = 6,
    topkRag: number = 10,
    selectedFavorites?: string[],
    useRecent: boolean = false,
    fastLlm: boolean = false,
    excludeTitles?: string[]
  ) {
    return api.post('/api/recommend/jobs', {
      user_id: userId,
      user_input: userInput,
      topk_kg: topkKg,
      topk_rag: topkRag,
      selected_favorites: selectedFavorites || [],
      with_llm_explain: false,
      use_recent: useRecent,
      fast_llm: fastLlm,
      exclude_titles: excludeTitles?.length ? excludeTitles : undefined
    })
  },

  getRecommendJob(jobId: string) {
    return api.get(`/api/recommend/jobs/${encodeURIComponent(jobId)}`)
  },

  createRecommendCardBlurbsJob(userInput: string, movies: any[]) {
    return api.post('/api/recommend/card-blurbs/jobs', {
      user_input: userInput,
      movies: movies || []
    })
  },

  createRecommendSummaryJob(userInput: string, movies: any[]) {
    return api.post('/api/recommend/summary/jobs', {
      user_input: userInput,
      movies: movies || []
    })
  },

  createRecommendExplainJob(payload: {
    user_input: string
    favorite_movies: string[]
    watched_titles: string[]
    seed_movies: string[]
    kg_movies: string[]
    rag_movies: any[]
    genre_hints: string[]
    final_titles?: string[]
  }) {
    return api.post('/api/recommend/explain/jobs', payload)
  }
}

// 管理员API
export const adminApi = {
  getUsers() {
    return api.get('/api/admin/users')
  },
  
  createUser(username: string, password: string, role: string = 'user') {
    return api.post('/api/admin/users', {
      username,
      password,
      role
    })
  },
  
  updateUserPassword(userId: number, newPassword: string) {
    return api.put(`/api/admin/users/${userId}/password`, {
      new_password: newPassword
    })
  },
  
  updateUserRole(userId: number, newRole: string) {
    return api.put(`/api/admin/users/${userId}/role`, {
      new_role: newRole
    })
  },
  
  deleteUser(userId: number) {
    return api.delete(`/api/admin/users/${userId}`)
  },
  
  getAllFavorites(userId?: number, username?: string) {
    const params: Record<string, string | number> = {}
    if (userId != null && userId > 0) params.user_id = userId
    else if (username && String(username).trim()) params.username = String(username).trim()
    return api.get('/api/admin/favorites', { params })
  },
  
  deleteFavoriteAdmin(favId: number) {
    return api.delete(`/api/admin/favorites/${favId}`)
  },
  
  getRecommendLogs(limit?: number) {
    return api.get('/api/admin/recommend-logs', {
      params: { limit }
    })
  },

  deleteRecommendLog(id: number) {
    return api.delete(`/api/admin/recommend-logs/${id}`)
  },
  
  getModelStats() {
    return api.get('/api/admin/model-stats')
  },

  /** 管理后台：模型评估展示（backend/data/eval/kg_eval_display.json） */
  getKgEvalDisplay() {
    return api.get('/api/admin/kg-eval-display')
  },

  getOverview() {
    return api.get('/api/admin/overview')
  },

  getBrowseHistory(limit?: number, userId?: number) {
    return api.get('/api/admin/browse-history', {
      params: { limit, user_id: userId }
    })
  },

  deleteBrowseHistoryRecord(recordId: number) {
    return api.delete(`/api/admin/browse-history/${recordId}`)
  },

  // 影评管理
  getReviewsAdmin(limit?: number, offset?: number, userId?: number, movieName?: string) {
    return api.get('/api/admin/reviews', { params: { limit, offset, user_id: userId, movie_name: movieName } })
  },
  deleteReviewAdmin(id: number) {
    return api.delete(`/api/admin/reviews/${id}`)
  },
  getReviewCommentsAdmin(limit?: number, offset?: number, userId?: number, reviewId?: number) {
    return api.get('/api/admin/review-comments', { params: { limit, offset, user_id: userId, review_id: reviewId } })
  },
  deleteReviewCommentAdmin(id: number) {
    return api.delete(`/api/admin/review-comments/${id}`)
  },
  muteUserReviews(userId: number, payload: { duration_hours?: number | null; until?: string | null; reason?: string }) {
    return api.put(`/api/admin/users/${userId}/review-mute`, payload)
  },
  unmuteUserReviews(userId: number) {
    return api.delete(`/api/admin/users/${userId}/review-mute`)
  }
}

// 影评系统API
export const reviewApi = {
  searchMovies(q: string, limit: number = 10) {
    return api.get('/api/reviews/movies/search', { params: { q, limit } })
  },
  listReviews(sort: string = 'comment_count', limit: number = 50, offset: number = 0) {
    return api.get('/api/reviews', { params: { sort, limit, offset } })
  },
  getBoard(movieLimit: number = 20, movieOffset: number = 0, perMovie: number = 5) {
    return api.get('/api/reviews/board', { params: { movie_limit: movieLimit, movie_offset: movieOffset, per_movie: perMovie } })
  },
  listByMovie(
    movieName: string,
    limit: number = 10,
    offset: number = 0,
    sort: 'like_count' | 'recent' = 'like_count',
    hasTextOnly: boolean = false
  ) {
    return api.get('/api/reviews/by-movie', {
      params: {
        movie_name: movieName,
        limit,
        offset,
        sort,
        ...(hasTextOnly ? { has_text_only: true } : {})
      }
    })
  },
  getMineForMovie(movieName: string) {
    return api.get('/api/reviews/mine', { params: { movie_name: movieName } })
  },
  getReviewDetail(id: number) {
    return api.get(`/api/reviews/${id}`)
  },
  upsertReview(payload: {
    movie_name: string
    movie_source?: string
    rating?: number | null
    content: string
  }) {
    return api.put('/api/reviews', payload)
  },
  deleteReview(id: number) {
    return api.delete(`/api/reviews/${id}`)
  },
  addComment(reviewId: number, payload: { content: string; parent_id?: number | null }) {
    return api.post(`/api/reviews/${reviewId}/comments`, payload)
  },
  deleteComment(commentId: number) {
    return api.delete(`/api/reviews/comments/${commentId}`)
  },
  like(targetType: 'review' | 'comment', targetId: number) {
    return api.post('/api/reviews/likes', { target_type: targetType, target_id: targetId })
  },
  unlike(targetType: 'review' | 'comment', targetId: number) {
    return api.delete('/api/reviews/likes', { params: { target_type: targetType, target_id: targetId } })
  }
}

// 用户个人中心API
export const userApi = {
  getUserProfile() {
    return api.get('/api/user/profile')
  },

  updatePreferences(preferredGenres: string[]) {
    return api.put('/api/user/preferences', { preferred_genres: preferredGenres })
  },

  updatePassword(oldPassword: string, newPassword: string) {
    return api.put('/api/user/password', {
      old_password: oldPassword,
      new_password: newPassword
    })
  },

  getNotifications(limit: number = 50, offset: number = 0) {
    return api.get('/api/user/notifications', { params: { limit, offset } })
  },

  getNotificationUnreadCount() {
    return api.get('/api/user/notifications/unread-count')
  },

  markNotificationsRead(payload: { ids?: number[]; mark_all?: boolean }) {
    return api.post('/api/user/notifications/read', payload)
  },

  getMyFavorites() {
    return api.get('/api/user/favorites')
  },

  addMyFavorite(movieName: string, genres?: string, movieSource?: string, tmdbId?: number | null) {
    return api.post('/api/user/favorites', {
      movie_name: movieName,
      genres: genres || '',
      movie_source: movieSource || 'kg',
      tmdb_id: tmdbId ?? null
    })
  },

  removeMyFavorite(movieName: string) {
    return api.delete('/api/user/favorites', {
      data: { movie_name: movieName }
    })
  },

  getMyWatched(limit?: number) {
    return api.get('/api/user/watched', {
      params: { limit }
    })
  },

  addWatched(movieName: string, genres?: string, movieSource?: string, tmdbId?: number | null) {
    return api.post('/api/user/watched', {
      movie_name: movieName,
      genres: genres || '',
      movie_source: movieSource || 'kg',
      tmdb_id: tmdbId ?? null
    })
  },

  removeWatched(movieName: string) {
    return api.delete('/api/user/watched', {
      params: { movie_name: movieName }
    })
  },

  getMyRecommendLogs(limit?: number) {
    return api.get('/api/user/recommend-logs', {
      params: { limit }
    })
  },

  // 👍/👎/屏蔽/短评
  getMyFeedback(vote?: 'like' | 'dislike', blocked?: boolean, limit?: number) {
    return api.get('/api/user/feedback', {
      params: { vote, blocked, limit }
    })
  },

  upsertFeedback(
    movieName: string,
    payload: { vote?: 'like' | 'dislike' | null; blocked?: boolean | null; note?: string | null },
    extra?: { movieSource?: string; tmdbId?: number | null }
  ) {
    const body: Record<string, unknown> = { movie_name: movieName }
    if (extra?.movieSource) body.movie_source = extra.movieSource
    if (extra && 'tmdbId' in extra) body.tmdb_id = extra.tmdbId ?? null
    if ('vote' in payload) body.vote = payload.vote
    if ('blocked' in payload) body.blocked = payload.blocked
    if ('note' in payload) body.note = payload.note
    return api.put('/api/user/feedback', body)
  },

  deleteFeedback(movieName: string) {
    return api.delete('/api/user/feedback', {
      params: { movie_name: movieName }
    })
  },

  // 片单
  getPlaylists() {
    return api.get('/api/user/playlists')
  },

  createPlaylist(name: string, description?: string) {
    return api.post('/api/user/playlists', { name, description: description || '' })
  },

  updatePlaylist(id: number, payload: { name?: string; description?: string }) {
    return api.put(`/api/user/playlists/${id}`, payload)
  },

  deletePlaylist(id: number) {
    return api.delete(`/api/user/playlists/${id}`)
  },

  getPlaylistItems(id: number) {
    return api.get(`/api/user/playlists/${id}/items`)
  },

  addPlaylistItem(
    id: number,
    movieName: string,
    extra?: {
      movieSource?: string
      tmdbId?: number | null
      genres?: string
      poster_url?: string
      genres_str?: string
      score_str?: string
      short_review?: string
    }
  ) {
    const e = extra || {}
    return api.post(`/api/user/playlists/${id}/items`, {
      movie_name: movieName,
      movie_source: e.movieSource || '',
      tmdb_id: e.tmdbId ?? null,
      genres: e.genres || '',
      poster_url: e.poster_url || '',
      genres_str: e.genres_str || '',
      score_str: e.score_str || '',
      short_review: e.short_review || ''
    })
  },

  removePlaylistItem(id: number, movieName: string) {
    return api.delete(`/api/user/playlists/${id}/items`, { params: { movie_name: movieName } })
  },

  saveRecommendationToPlaylist(
    id: number,
    movies: Array<{ name: string; source?: string; tmdb_id?: number | null; genres?: string }>
  ) {
    return api.post(`/api/user/playlists/${id}/save-recommendation`, { movies })
  }
}

export default api
