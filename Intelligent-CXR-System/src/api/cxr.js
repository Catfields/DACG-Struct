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

async function requestBlob(path) {
  let resp
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      headers: buildHeaders(),
    })
  } catch (error) {
    throw new Error(
      `无法连接后端服务（${API_BASE}），请确认后端已启动且 VITE_API_BASE 配置正确`
    )
  }

  if (!resp.ok) {
    let data = null
    try {
      data = await resp.json()
    } catch {
      data = null
    }
    const message =
      (data && (data.message || data.detail)) ||
      `请求失败（${resp.status}）`
    const err = new Error(message)
    err.status = resp.status
    err.payload = data
    throw err
  }

  return resp.blob()
}

async function requestForm(path, formData, method = 'POST') {
  let resp
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      method,
      headers: buildHeaders(),
      body: formData,
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

export async function fetchXrayList({ page = 1, size = 50 } = {}) {
  const search = new URLSearchParams({
    page: String(page),
    size: String(size),
  })
  return requestJson(`/xray/?${search.toString()}`)
}

export async function fetchReportsByXrayId(xrayId) {
  const search = new URLSearchParams({
    xray_id: String(xrayId),
    page: '1',
    size: '20',
  })
  return requestJson(`/reports/?${search.toString()}`)
}

export async function fetchXrayVisualizationBlob(xrayId) {
  return requestBlob(`/xray/${xrayId}/visualization`)
}

export async function fetchXrayMaskBlob(xrayId) {
  return requestBlob(`/xray/${xrayId}/mask`)
}

export async function fetchXrayOriginalBlob(xrayId) {
  return requestBlob(`/xray/${xrayId}/original`)
}

export async function saveManualReport({
  file,
  patientName,
  patientGender,
  patientAge,
  examDate,
  xrayFormat,
  reportContent,
}) {
  const form = new FormData()
  form.append('file', file)
  form.append('patient_name', patientName || '')
  if (patientGender !== null && patientGender !== undefined) {
    form.append('patient_gender', String(patientGender))
  }
  if (patientAge !== null && patientAge !== undefined && patientAge !== '') {
    form.append('patient_age', String(patientAge))
  }
  if (examDate) {
    form.append('exam_date', examDate)
  }
  form.append('xray_format', xrayFormat || 'PNG')
  form.append('report_content', reportContent || '')
  return requestForm('/reports/manual-save', form, 'POST')
}

export async function reviseReport(reportId, reportContent) {
  return requestJson(`/reports/${reportId}/revise`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      revise_content: '前端保存更新',
      report_content: reportContent,
    }),
  })
}
