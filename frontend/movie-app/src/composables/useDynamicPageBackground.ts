import { ref } from 'vue'

const STORAGE_KEY = 'moviehub-dynamic-page-bg'

function readInitial(): boolean {
  if (typeof window === 'undefined') return true
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === '0' || raw === 'false') return false
    return true
  } catch {
    return true
  }
}

/** 首页 / 推荐页：动态背景（视频、平移图）与默认纯色渐变底切换，两页共用并持久化 */
export const dynamicPageBgEnabled = ref(readInitial())

export function useDynamicPageBackground() {
  function persist(v: boolean) {
    try {
      localStorage.setItem(STORAGE_KEY, v ? '1' : '0')
    } catch {
      /* ignore */
    }
  }

  function toggleDynamicBg() {
    dynamicPageBgEnabled.value = !dynamicPageBgEnabled.value
    persist(dynamicPageBgEnabled.value)
  }

  function setDynamicBg(v: boolean) {
    if (dynamicPageBgEnabled.value === v) return
    dynamicPageBgEnabled.value = v
    persist(v)
  }

  return { dynamicPageBgEnabled, toggleDynamicBg, setDynamicBg }
}
