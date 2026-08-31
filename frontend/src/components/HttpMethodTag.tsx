import { Tag } from 'antd'

const methodColors: Record<string, string> = {
  GET: 'green',
  POST: 'blue',
  PUT: 'gold',
  PATCH: 'purple',
  DELETE: 'red',
  HEAD: 'cyan',
  OPTIONS: 'orange',
}

export function HttpMethodTag({ method }: { method: string }) {
  const normalized = method.toUpperCase()
  return <Tag color={methodColors[normalized]}>{normalized}</Tag>
}
