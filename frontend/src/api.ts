import { QueryClient } from '@tanstack/react-query'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/v1${path}`, { credentials: 'same-origin', ...options,
      headers: { ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...options.headers } })
  } catch { throw new ApiError(0, '连接暂时中断，请检查网络后重试。你的内容仍保留在页面上。') }
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: '服务暂时不可用，请稍后重试' }))
    const message = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map((e: { msg: string }) => e.msg).join('；') : '操作未完成，请重试'
    throw new ApiError(response.status, message)
  }
  return response.status === 204 ? undefined as T : response.json()
}
export const post = <T,>(path: string, data?: unknown) => api<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) })
export const patch = <T,>(path: string, data: unknown) => api<T>(path, { method: 'PATCH', body: JSON.stringify(data) })
export const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 20_000, retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 1, refetchOnWindowFocus: true } } })
export function refreshLearning() {
  for (const key of ['items', 'item', 'stats', 'queue', 'history', 'preview', 'chapters']) void queryClient.invalidateQueries({ queryKey: [key] })
}
