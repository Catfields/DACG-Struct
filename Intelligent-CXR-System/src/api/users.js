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

export async function listUsers({ page = 1, size = 200 } = {}) {
  const search = new URLSearchParams({
    page: String(page),
    size: String(size),
  })
  return requestJson(`/users/?${search.toString()}`)
}

export async function createUser(payload) {
  return requestJson('/users/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function updateUser(userId, payload) {
  return requestJson(`/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function resetUserPassword(userId) {
  throw new Error('后端未提供重置密码接口（/users/{id}/reset-password）')
}

export async function deleteUser(userId) {
  return requestJson(`/users/${userId}`, {
    method: 'DELETE',
  })
}
