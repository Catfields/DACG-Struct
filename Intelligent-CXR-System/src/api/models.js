/**
 * 模型管理 API
 * 对接后端 /admin/models 系列接口
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

/** 获取所有模型列表 */
export async function listModels() {
  return requestJson('/admin/models')
}

/** 新增模型 */
export async function createModel(payload) {
  return requestJson('/admin/models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** 设为默认模型（触发分割模型热重载） */
export async function setDefaultModel(modelId) {
  return requestJson(`/admin/models/${modelId}/default`, {
    method: 'PATCH',
  })
}

/** 删除模型 */
export async function deleteModel(modelId) {
  return requestJson(`/admin/models/${modelId}`, {
    method: 'DELETE',
  })
}
