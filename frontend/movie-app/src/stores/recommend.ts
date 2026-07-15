import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import type { RecommendResult } from '@/types'
import { recommendApi } from '@/services/api'

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** 推荐任务轮询间隔（越大后端 access log 越少，但进度刷新略慢） */
const RECOMMEND_JOB_POLL_MS = 1500

function patchPipelineStep(
  pipeline: unknown,
  id: string,
  patch: { status: string; elapsed_ms: number; message: string }
): any[] {
  const p = Array.isArray(pipeline) ? [...pipeline] : []
  const i = p.findIndex((s: any) => s && s.id === id)
  if (i === -1) return p
  const row = { ...(p[i] as object), ...patch, call_kind: 'llm' as const }
  const next = [...p]
  next[i] = row
  return next
}

/** 推荐页「参数与偏好」：与路由无关保留，切页/返回后勾选仍在 */
export type RecommendFormPrefs = {
  userInput: string
  selectedGenres: string[]
  selectedFavorites: string[]
  topkKg: number
  topkRag: number
  useRecent: boolean
}

function titlesFromRecommendResult(r: RecommendResult | null): string[] {
  if (!r?.movies?.length) return []
  return (r.movies as any[])
    .map((m) => String(m?.display || m?.name || '').trim())
    .filter(Boolean)
}

export const useRecommendStore = defineStore('recommend', () => {
  const last = ref<RecommendResult | null>(null)
  const lastAt = ref<number | null>(null)
  /** 本会话已成功推荐过的定榜片名，用于下一手请求 exclude_titles 换一批（换账号时在 resetForNewUser 中清空） */
  const sessionExcludeTitles = ref<string[]>([])

  const formPrefs = reactive<RecommendFormPrefs>({
    userInput: '',
    selectedGenres: [],
    selectedFavorites: [],
    topkKg: 4,
    topkRag: 4,
    useRecent: false
  })

  const running = ref(false)
  const summaryRunning = ref(false)
  const explainRunning = ref(false)
  const filterPending = ref(false)

  const progressStep = ref(0)
  const progressSteps = ref<string[]>([])
  const progressText = ref('')
  const error = ref<string | null>(null)

  const setLast = (r: RecommendResult | null) => {
    last.value = r
    lastAt.value = r ? Date.now() : null
  }

  const pushSessionExcludeFromResult = (r: RecommendResult | null) => {
    const seen = new Set(sessionExcludeTitles.value)
    for (const t of titlesFromRecommendResult(r)) {
      if (seen.has(t)) continue
      seen.add(t)
      sessionExcludeTitles.value.push(t)
    }
    if (sessionExcludeTitles.value.length > 36) {
      sessionExcludeTitles.value = sessionExcludeTitles.value.slice(-36)
    }
  }

  const clear = () => setLast(null)

  /** 退出登录或切换账号：清空推荐表单、结果与会话排除列表 */
  const resetForNewUser = () => {
    setLast(null)
    sessionExcludeTitles.value = []
    formPrefs.userInput = ''
    formPrefs.selectedGenres = []
    formPrefs.selectedFavorites = []
    formPrefs.topkKg = 4
    formPrefs.topkRag = 4
    formPrefs.useRecent = false
    running.value = false
    summaryRunning.value = false
    explainRunning.value = false
    filterPending.value = false
    progressStep.value = 0
    progressSteps.value = []
    progressText.value = ''
    error.value = null
  }

  const _pollJob = async (jobId: string) => {
    while (true) {
      const res = await recommendApi.getRecommendJob(jobId)
      const data = res.data || {}
      if (Array.isArray(data.steps)) progressSteps.value = data.steps
      progressStep.value = Number(data.step ?? 0)
      progressText.value = String(data.text || '')
      if (data.error) error.value = String(data.error)

      if (data.done) {
        filterPending.value = false
        const r = data.result as any
        if (r && Array.isArray(r.movies)) {
          setLast(r as RecommendResult)
        }
        return data
      }
      await sleep(RECOMMEND_JOB_POLL_MS)
    }
  }

  const recommend = async (payload: any) => {
    if (running.value) return last.value

    running.value = true
    filterPending.value = false
    error.value = null
    progressStep.value = 0
    progressSteps.value = []
    progressText.value = '准备任务…'

    // 质量优先：保留偏好分解与（可选）解读；卡片“推荐理由/简介”由 TMDB overview 提供，不走大模型短评
    const fastLlm = Boolean(payload?.fast_llm ?? false)
    const excludeRaw = (payload?.exclude_titles ?? sessionExcludeTitles.value) as string[]
    const excludeTitles = Array.isArray(excludeRaw)
      ? [...new Set(excludeRaw.map((x) => String(x || '').trim()).filter(Boolean))].slice(0, 40)
      : []

    try {
      const createRes = await recommendApi.createRecommendJob(
        Number(payload?.user_id || 0),
        String(payload?.user_input || ''),
        Number(payload?.topk_kg ?? 6),
        Number(payload?.topk_rag ?? 10),
        (payload?.favorites || payload?.selected_favorites || []) as string[],
        Boolean(payload?.with_recent ?? payload?.use_recent ?? false),
        fastLlm,
        excludeTitles
      )
      const jobId = String(createRes.data?.job_id || '')
      if (!jobId) throw new Error('创建推荐任务失败')

      const job = await _pollJob(jobId)
      if (job.error) throw new Error(String(job.error))
      const result = (job.result || null) as RecommendResult | null
      if (!result) throw new Error('推荐结果为空')
      if (!result.success) throw new Error(String((result as any).error || '推荐失败'))

      setLast(result)
      pushSessionExcludeFromResult(result)
      try {
        window.dispatchEvent(new Event('notifications:updated'))
      } catch {
        /* ignore */
      }

      return last.value
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '推荐失败'
      error.value = String(msg)
      throw e
    } finally {
      running.value = false
    }
  }

  const generateSummary = async (payload: { user_input: string }) => {
    if (summaryRunning.value) return last.value
    const base = last.value
    if (!base || !Array.isArray(base.movies) || !base.movies.length) {
      throw new Error('暂无推荐结果')
    }

    summaryRunning.value = true
    error.value = null
    progressStep.value = 0
    progressSteps.value = ['生成推荐总结（大模型）']
    progressText.value = '生成推荐总结（大模型）…'

    try {
      const c = await recommendApi.createRecommendSummaryJob(String(payload.user_input || ''), (base.movies || []).slice(0, 10))
      const jobId = String(c.data?.job_id || '')
      if (!jobId) throw new Error('创建总结任务失败')

      const job = await _pollJob(jobId)
      if (job.error) throw new Error(String(job.error))
      const out = (job.result || {}) as any

      // 必须与「当前」last 合并：若用户几乎同时点了解读+总结，另一路可能已先写完 last；
      // 若仍用请求开始时的 base 展开，会覆盖掉先完成的那条字段。
      const cur = last.value
      if (!cur || !Array.isArray(cur.movies) || !cur.movies.length) {
        throw new Error('推荐结果已变化，请重新推荐后再试')
      }
      const next: any = { ...(cur as any) }
      next.llm_summary = String(out.llm_summary || '').trim()
      next.llm_summary_error = String(out.llm_summary_error || '').trim()
      const ms = Number(out.elapsed_ms ?? 0)
      const ok = Boolean(next.llm_summary)
      next.pipeline = patchPipelineStep(cur.pipeline, 'llm_summary', {
        status: ok ? 'ok' : 'warn',
        elapsed_ms: ms,
        message: ok
          ? `总结已生成（大模型 API，耗时 ${ms} ms）。`
          : `总结未生成或失败：${String(next.llm_summary_error || out.error || '').slice(0, 180)}`
      })
      setLast(next as RecommendResult)
      return last.value
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '总结生成失败'
      error.value = String(msg)
      throw e
    } finally {
      summaryRunning.value = false
      progressText.value = ''
      progressSteps.value = []
    }
  }

  const generateExplain = async (payload: {
    user_input: string
    favorite_movies: string[]
    watched_titles: string[]
    seed_movies: string[]
    kg_movies: string[]
    rag_movies: any[]
    genre_hints: string[]
  }) => {
    if (explainRunning.value) return last.value
    const base = last.value
    if (!base || !Array.isArray(base.kg_movies)) {
      throw new Error('暂无推荐上下文')
    }

    explainRunning.value = true
    error.value = null
    progressStep.value = 0
    progressSteps.value = ['生成推荐解读（大模型）']
    progressText.value = '生成推荐解读（大模型）…'

    try {
      const finalTitles = (base.movies || [])
        .map((m: any) => String(m?.display || m?.name || '').trim())
        .filter(Boolean)
        .slice(0, 16)
      const c = await recommendApi.createRecommendExplainJob({
        ...payload,
        final_titles: finalTitles.length ? finalTitles : undefined
      })
      const jobId = String(c.data?.job_id || '')
      if (!jobId) throw new Error('创建解读任务失败')

      const job = await _pollJob(jobId)
      if (job.error) throw new Error(String(job.error))
      const out = (job.result || {}) as any

      const cur = last.value
      if (!cur || !Array.isArray(cur.kg_movies)) {
        throw new Error('推荐结果已变化，请重新推荐后再试')
      }
      const next: any = { ...(cur as any) }
      next.llm_explanation = String(out.llm_explanation || '').trim()
      next.llm_explanation_error = String(out.llm_explanation_error || '').trim()
      const ms = Number(out.elapsed_ms ?? 0)
      const ok = Boolean(next.llm_explanation)
      next.pipeline = patchPipelineStep(cur.pipeline, 'llm_explain', {
        status: ok ? 'ok' : next.llm_explanation_error ? 'warn' : 'error',
        elapsed_ms: ms,
        message: ok
          ? `解读已生成（大模型 API，耗时 ${ms} ms）。`
          : `解读未生成或失败：${String(next.llm_explanation_error || '').slice(0, 180)}`
      })
      setLast(next as RecommendResult)
      return last.value
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '解读生成失败'
      error.value = String(msg)
      throw e
    } finally {
      explainRunning.value = false
      progressText.value = ''
      progressSteps.value = []
    }
  }

  return {
    last,
    lastAt,
    sessionExcludeTitles,
    formPrefs,
    running,
    summaryRunning,
    explainRunning,
    filterPending,
    progressStep,
    progressSteps,
    progressText,
    error,
    setLast,
    clear,
    resetForNewUser,
    recommend,
    generateSummary,
    generateExplain
  }
})
