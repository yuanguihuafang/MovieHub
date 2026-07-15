export interface User {
  id: number
  username: string
  role: 'user' | 'admin'
  created_at: string
  preferred_genres?: string[]
  review_muted_until?: string
  review_mute_reason?: string
}

export interface Movie {
  name: string
  display: string
  genres: string[] | string
  director?: string
  directors?: string
  score?: string
  poster_url?: string | null
}

export interface Favorite {
  id: number
  movie_name: string
  genres: string
  poster_url?: string
  added_at: string
}

export interface RecommendPipelineStep {
  id: string
  title: string
  status: 'ok' | 'warn' | 'error' | 'skip'
  message: string
  elapsed_ms?: number
  call_kind?: 'llm'
}

export interface KgModelMeta {
  method: string
  relations_used: string[]
  preferred_relations?: string[]
  relation_weights?: Record<string, number>
  genre_boost?: number
  max_relations?: number
  note: string
  candidate_stage?: string
  /** 主链路步骤说明（后端生成） */
  flow_summary?: string
}

export interface RecommendMovieCard {
  name: string
  source: string
  display: string
  weight?: number
  tmdb_id?: number | null
  poster_url?: string | null
  genres_str?: string
  score_str?: string
  score?: string | number
  short_review?: string
}

export interface PreferenceDecomposePreview {
  query?: string
  liked_genres?: string[]
  disliked_genres?: string[]
  liked_movies?: string[]
  avoid_movies?: string[]
  relations?: string[]
  constraints?: string[]
  must_have_constraints?: string[]
  soft_constraints?: string[]
  movie_entities_zh?: string[]
  movie_entity_candidates_en?: Record<string, string[]>
}

export interface LlmInvocationRow {
  step_id: string
  title: string
  status: string
  elapsed_ms: number
  model: string
}

export interface RecommendResult {
  success: boolean
  error?: string
  movies: RecommendMovieCard[]
  kg_movies: string[]
  /** 定榜结果中来源为 KG 的实体 id（与 kg_movies 元素同口径），用于高亮「最终保留」 */
  kg_final_entity_names?: string[]
  rag_movies: Array<{ name: string; similarity: number; source?: string; metadata?: any }>
  /** 与同偏好类型相符的其他用户收藏补位候选（并入片库侧定榜池，source=peer_fav） */
  peer_fav_movies?: Array<{ name: string; display?: string; genres?: string; weight?: number }>
  seed_movies?: string[]
  genre_hints?: string[]
  watched_titles?: string[]
  recommend_text: string
  elapsed_ms: number
  log?: string
  pipeline?: RecommendPipelineStep[]
  llm_explanation?: string
  llm_explanation_error?: string
  llm_summary?: string
  llm_summary_error?: string
  kg_model_meta?: KgModelMeta
  movies_before_filter?: RecommendMovieCard[]
  movies_filtered_out?: RecommendMovieCard[]
  llm_filter_text?: string
  llm_filter_error?: string
  /** 偏好分解摘要（主链路 LLM，控制体积） */
  preference_decompose?: PreferenceDecomposePreview
  /** 主链路中已执行的大模型步骤及耗时、模型名 */
  llm_invocations?: LlmInvocationRow[]
  recommend_phase?: 'cards_ready' | 'complete'
  filter_pending?: boolean
}

export interface ModelLog {
  call_type: string
  count: number
  avg_ms: number
}
