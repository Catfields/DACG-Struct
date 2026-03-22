const API_BASE =
  import.meta.env.VITE_API_BASE?.replace(/\/+$/, '') || 'http://127.0.0.1:9000'

export async function translateText(englishText) {
  const resp = await fetch(`${API_BASE}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      english_text: englishText,
    }),
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
      `翻译请求失败（${resp.status}）`
    const err = new Error(message)
    err.status = resp.status
    err.payload = data
    throw err
  }

  return data
}
