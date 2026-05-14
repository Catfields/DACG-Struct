/**
 * 日志审计 API
 * 对接后端 /admin/logs 接口
 */

function resolveDefaultApiBase() {
  if (typeof window === 'undefined') {
    return 'http://127.0.0.1:8000'
  }
  const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:'
  const hostname = window.location.hostname || '127.0.0.1'
  return `${protocol}//${hostname}:8000`
}

const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/+$/, '') || resolveDefaultApiBase()

function buildHeaders(extra = {}) {
  const token = localStorage.getItem('access_token')
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

async function requestJson(path, options = {}) {
  let resp
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: buildHeaders(options.headers || {}),
    })
  } catch (error) {
    throw new Error(
      `无法连接后端服务（${API_BASE}），请确认后端已启动且 VITE_API_BASE 配置正确`
    )
  }

  let data = null
  try {
    data = await resp.json()
  } catch {
    data = null
  }

  if (!resp.ok) {
    const message =
      (data && (data.message || data.detail)) ||
      `请求失败（${resp.status}）`
    const err = new Error(message)
    err.status = resp.status
    err.payload = data
    throw err
  }

  return data
}

export async function listAuditLogs(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    search.set(key, String(value))
  })
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return requestJson(`/admin/logs${suffix}`)
}
