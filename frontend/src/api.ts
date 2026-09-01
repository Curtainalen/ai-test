import axios from 'axios'
export type Envelope<T> = { success: true; data: T; trace_id?: string } | { success: false; error: { code: string; message: string; details?: unknown }; trace_id?: string }
export const client = axios.create({ baseURL: '/api', timeout: 30000 })
client.interceptors.request.use((config) => { const token = localStorage.getItem('access_token'); if (token) config.headers.Authorization = `Bearer ${token}`; return config })
function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as Partial<Envelope<unknown>> | string | undefined
    if (body && typeof body === 'object' && body.success === false && body.error?.message) return body.error.message
    if (typeof body === 'string' && body.trim()) return body.trim()
    return error.message || '请求失败'
  }
  return error instanceof Error ? error.message : '请求失败'
}
client.interceptors.response.use((response) => response, (error) => Promise.reject(new Error(errorMessage(error))))
export async function api<T>(config: Parameters<typeof client.request>[0]): Promise<T> {
  try {
    const response = await client.request<Envelope<T>>(config)
    if (!response.data.success) throw new Error(response.data.error?.message || '请求失败')
    return response.data.data
  } catch (error) {
    throw new Error(errorMessage(error))
  }
}
