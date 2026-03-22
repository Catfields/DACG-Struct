const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/+$/, '') || 'http://127.0.0.1:9000'

async function postJson(path, payload) {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

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

export async function loginWithPassword({ loginName, password, roleName }) {
  return postJson('/auth/login', {
    login_name: loginName,
    password,
    role_name: roleName,
  })
}
