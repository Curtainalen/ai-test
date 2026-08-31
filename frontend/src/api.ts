import axios from 'axios'
export type Envelope<T> = { success: true; data: T; trace_id?: string } | { success: false; error: { code: string; message: string; details?: unknown }; trace_id?: string }
export const client = axios.create({ baseURL: '/api', timeout: 30000 })
client.interceptors.request.use((config) => { const token = localStorage.getItem('access_token'); if (token) config.headers.Authorization = `Bearer ${token}`; return config })
client.interceptors.response.use((response) => response, (error) => { const body = error.response?.data as Envelope<unknown> | undefined; return Promise.reject(new Error(body && !body.success ? body.error.message : error.message || '请求失败')) })
export async function api<T>(config: Parameters<typeof client.request>[0]): Promise<T> { const response = await client.request<Envelope<T>>(config); if (!response.data.success) throw new Error(response.data.error.message); return response.data.data }
