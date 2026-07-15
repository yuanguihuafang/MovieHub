/**
 * 将大模型返回的短评规范为纯文本（去掉 JSON 数组/对象、代码围栏等）。
 */
export function plainReviewText(raw: unknown): string {
  let s = String(raw ?? '').trim()
  if (!s) return ''

  s = s.replace(/^```(?:json|JSON|text)?\s*/m, '').replace(/\s*```$/m, '').trim()

  const tryParseJson = (t: string): string | null => {
    const x = t.trim()
    if (!x) return null
    try {
      const v = JSON.parse(x)
      if (Array.isArray(v)) {
        const parts = v
          .map((item) => {
            if (typeof item === 'string') return item.trim()
            if (item && typeof item === 'object') {
              const o = item as Record<string, unknown>
              const a =
                o.text ?? o.blurb ?? o.review ?? o.content ?? o.short_review ?? o.value
              if (typeof a === 'string') return a.trim()
            }
            return ''
          })
          .filter(Boolean)
        return parts.join(' ').trim() || null
      }
      if (v && typeof v === 'object') {
        const o = v as Record<string, unknown>
        const a =
          o.text ?? o.blurb ?? o.review ?? o.content ?? o.short_review ?? o.summary
        if (typeof a === 'string' && a.trim()) return a.trim()
      }
    } catch {
      return null
    }
    return null
  }

  const fromJson = tryParseJson(s)
  if (fromJson) return fromJson

  if (/^\[/.test(s) || /^\{/.test(s)) {
    const again = tryParseJson(s)
    if (again) return again
  }

  return s
    .replace(/^\s*[\[\{"]+/, '')
    .replace(/[\]\}"]+\s*$/, '')
    .replace(/^["']|["']$/g, '')
    .trim()
}
