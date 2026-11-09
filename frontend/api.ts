let token = ''
export class APIError extends Error {
  constructor(message:string, public status:number){super(message)}
}
export function setToken(value: string) { token = value }

export async function api<T = any>(path: string, body?: unknown, method?: string): Promise<T> {
  const form = body instanceof FormData
  const response = await fetch('/api' + path, {
    method: method || (body === undefined ? 'GET' : 'POST'),
    headers: { 'X-Study-Token': token, ...(!form && body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    const detail = typeof data.detail === 'string' ? data.detail : '提交内容不完整，请检查输入。'
    throw new APIError(detail,response.status)
  }
  return response.json()
}

export async function uploadPhoto(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  return (await api('/uploads', form)).name
}
