import type { Subject } from './types'

export const subjects: { id: Subject; name: string; subtitle: string; symbol: string; color: string }[] = [
  { id: '408', name: '计算机 408', subtitle: '把复杂，拆解成清晰', symbol: '{ }', color: 'sage' },
  { id: 'math', name: '数学', subtitle: '让每一步，都有依据', symbol: '∫', color: 'clay' },
  { id: 'english', name: '英语', subtitle: '在语境里，遇见世界', symbol: 'Aa', color: 'blue' },
]
export const subjectName = (id: string) => subjects.find(s => s.id === id)?.name ?? id
export const difficultyNames: Record<string, string> = { basic: '基础', medium: '中等', hard: '较难' }
export const kindNames: Record<string, string> = { concept: '知识点', problem: '练习题', vocabulary: '单词', expression: '表达' }
export const stateNames: Record<string, string> = { new: '待学习', learning: '学习中', review: '复习中', relearning: '重新学习' }
export const ratingNames: Record<number, string> = { 1: '忘记', 2: '困难', 3: '良好', 4: '轻松' }
export function dateLabel(value: string | null, full = false) {
  if (!value) return '尚未开始'
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', ...(full ? { hour: '2-digit', minute: '2-digit' } as const : {}) }).format(new Date(value))
}
export function relativeDue(value: string, isNew = false) {
  if (isNew) return '等待第一次学习'
  const delta = new Date(value).getTime() - Date.now()
  if (delta <= 0) return '现在可以复习'
  if (delta < 60_000) return '不到 1 分钟后'
  if (delta < 3_600_000) return `${Math.ceil(delta / 60_000)} 分钟后`
  if (delta < 86_400_000) return `${Math.ceil(delta / 3_600_000)} 小时后`
  return `${Math.ceil(delta / 86_400_000)} 天后`
}
export function intervalLabel(seconds: number) {
  if (seconds < 60) return '< 1 分钟'
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟`
  if (seconds < 86400) return `${Math.round(seconds / 3600)} 小时`
  return `${Math.round(seconds / 86400)} 天`
}
export function plainText(text = '') { return text.replace(/[#*`>$\\{}_[\]]/g, '').slice(0, 140) }
export function localDate() { return new Date().toLocaleDateString('sv-SE') }

export function createRequestId() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  // getRandomValues also works on HTTP LAN pages, where randomUUID is unavailable.
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
}
