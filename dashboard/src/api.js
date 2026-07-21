export const API_URL = import.meta.env.VITE_API_URL || ''

// --- Auth token (client-side session) ----------------------------------
const TOKEN_KEY = 'ac_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function isLoggedIn() {
  return Boolean(getToken())
}

export async function login(username, password) {
  const res = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `Login failed (${res.status})`)
  }
  const data = await res.json()
  setToken(data.access_token)
  return data
}

export async function register(username, password) {
  const res = await fetch(`${API_URL}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `Register failed (${res.status})`)
  }
  return res.json()
}

export async function fetchSettings() {
  const res = await authFetch(`${API_URL}/api/auth/settings`)
  if (!res.ok) throw new Error('Failed to load settings')
  return res.json()
}

export async function saveSettings(settings) {
  const payload = {
    groq_key: settings.groqKey || '',
    gemini_key: settings.geminiKey || '',
    youtube_api_key: settings.youtubeApiKey || '',
    gemini_model: settings.geminiModel || '',
    whisper_model: settings.whisperModel || '',
    youtube_cookies: settings.youtubeCookies || '',
  }
  const res = await authFetch(`${API_URL}/api/auth/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || 'Failed to save settings')
  }
  return res.json()
}

// Authenticated fetch with the bearer token; 401 triggers logout.
export async function authFetch(url, options = {}) {
  const headers = { ...(options.headers || {}) }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(url, { ...options, headers })
  if (res.status === 401) {
    setToken('')
    window.dispatchEvent(new Event('ac:unauthorized'))
  }
  return res
}

export async function submitJob(payload, file, onProgress) {
  // Backend /api/process expects multipart/form-data (Form fields), so we
  // always send FormData — with a 'file' for uploads or 'source' for URLs.
  if (!file) {
    const fd = new FormData()
    for (const [k, v] of Object.entries(payload)) {
      if (v !== undefined && v !== null) fd.append(k, String(v))
    }
    const res = await authFetch(`${API_URL}/api/process`, { method: 'POST', body: fd })
    if (!res.ok) {
      let detail = ''
      try {
        detail = (await res.json()).detail || ''
      } catch {
        /* ignore */
      }
      throw new Error(`Submit failed (${res.status}) ${detail}`)
    }
    return res.json()
  }

  // Single-step: stream the file directly into /api/process (matches OpenShorts).
  return new Promise((resolve, reject) => {
    const fd = new FormData()
    fd.append('file', file)
    for (const [k, v] of Object.entries(payload)) {
      if (v !== undefined && v !== null) fd.append(k, String(v))
    }
    const xhr = new XMLHttpRequest()
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText))
        } catch {
          resolve({})
        }
      } else {
        let detail = ''
        try {
          detail = JSON.parse(xhr.responseText).detail || ''
        } catch {
          /* ignore */
        }
        // Surface 401 as a clear message so the UI can redirect to login.
        if (xhr.status === 401) {
          setToken('')
          window.dispatchEvent(new Event('ac:unauthorized'))
        }
        reject(new Error(`Submit failed (${xhr.status}) ${detail}`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error'))
    xhr.open('POST', `${API_URL}/api/process`)
    const token = getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.send(fd)
  })
}

export async function uploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const fd = new FormData()
    fd.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)) } catch { resolve({}) }
      } else {
        let detail = ''
        try { detail = JSON.parse(xhr.responseText).detail || '' } catch { /* ignore */ }
        reject(new Error(`Upload failed (${xhr.status}) ${detail}`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error'))
    xhr.open('POST', `${API_URL}/api/upload`)
    xhr.send(fd)
  })
}

export async function prepareGaming({ source, filename, camBox, gameBox, layout }) {
  const body = { cam_box: camBox, game_box: gameBox, layout }
  if (source) body.source = source
  else if (filename) body.file = filename
  const res = await fetch(`${API_URL}/api/gaming/prepare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`Gaming prepare failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function getStatus(jobId) {
  const res = await fetch(`${API_URL}/api/status/${jobId}`)
  if (!res.ok) throw new Error(`Status failed (${res.status})`)
  return res.json()
}

export async function listJobs() {
  const res = await fetch(`${API_URL}/api/jobs`)
  if (!res.ok) throw new Error('List failed')
  return res.json()
}

export function fileUrl(jobId, filename) {
  return `${API_URL}/api/files/${jobId}/${encodeURIComponent(filename)}`
}

export async function listLibrary() {
  const res = await fetch(`${API_URL}/api/library`)
  if (!res.ok) throw new Error('Library fetch failed')
  return res.json()
}

export async function deleteLibraryClip(name, filename) {
  const res = await fetch(`${API_URL}/api/library/${encodeURIComponent(name)}/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail || ''
    } catch {
      /* ignore */
    }
    throw new Error(`Delete clip failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function deleteLibraryFolder(name) {
  const res = await fetch(`${API_URL}/api/library/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail || ''
    } catch {
      /* ignore */
    }
    throw new Error(`Delete folder failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export function libraryFileUrl(name, filename) {
  return `${API_URL}/api/library/${encodeURIComponent(name)}/${encodeURIComponent(filename)}`
}

export function cacheFileUrl(filename) {
  return `${API_URL}/api/cache/${encodeURIComponent(filename)}`
}

export function librarySrtUrl(name, filename) {
  const base = filename.replace(/\.mp4$/i, '')
  return `${API_URL}/api/library/${encodeURIComponent(name)}/${encodeURIComponent(base)}.srt`
}

export async function registerBurn({ name, sourceFile, resultFile }) {
  const res = await fetch(`${API_URL}/api/library/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name,
      source_file: sourceFile,
      result_file: resultFile,
    }),
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail || ''
    } catch {
      /* ignore */
    }
    throw new Error(`Register burned clip failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function saveToLibrary({ jobId, filename, title, clipTitle, description, hook }) {
  const res = await fetch(`${API_URL}/api/library/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      job_id: jobId,
      filename,
      title: title || undefined,
      clip_title: clipTitle || undefined,
      description: description || undefined,
      hook: hook || undefined,
    }),
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail || ''
    } catch {
      /* ignore */
    }
    throw new Error(`Save to library failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function getSrt(jobId, filename) {
  const res = await fetch(fileUrl(jobId, filename))
  if (!res.ok) throw new Error(`SRT fetch failed (${res.status})`)
  return res.text()
}

export async function applySubtitles({ jobId, filename, cues, style, name }) {
  const payload = { filename, cues, style }
  if (name) payload.name = name
  else payload.job_id = jobId
  const res = await fetch(`${API_URL}/api/subtitle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail || ''
    } catch {
      /* ignore */
    }
    throw new Error(`Subtitle burn failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function applyHook(jobId, filename, text, position = 'top', fontScale = 1.0, opts = {}) {
  const res = await fetch(`${API_URL}/api/hook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      job_id: jobId,
      filename,
      text,
      position,
      font_scale: fontScale,
      size: opts.size || 'M',
      entrance: opts.entrance || 'fade',
      hold_seconds: opts.holdSeconds || 5,
    }),
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail || ''
    } catch {
      /* ignore */
    }
    throw new Error(`Hook burn failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function hookPreview(jobId, filename, text, position = 'top', fontScale = 1.0, opts = {}) {
  const res = await fetch(`${API_URL}/api/hook/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      job_id: jobId,
      filename,
      text,
      position,
      font_scale: fontScale,
      size: opts.size || 'M',
    }),
  })
  if (!res.ok) throw new Error('Preview failed')
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

export async function youtubeStatus() {
  const res = await authFetch(`${API_URL}/api/youtube/status`)
  if (!res.ok) throw new Error('YouTube status failed')
  return res.json()
}

export async function youtubeAccount() {
  const res = await authFetch(`${API_URL}/api/youtube/account`)
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`YouTube account failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function youtubeAuthUrl(redirectUri) {
  const res = await authFetch(`${API_URL}/api/youtube/auth_url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ redirect_uri: redirectUri || undefined }),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`Auth URL failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function youtubeCallback(code, redirectUri) {
  const res = await authFetch(`${API_URL}/api/youtube/callback?code=${encodeURIComponent(code)}${redirectUri ? `&redirect_uri=${encodeURIComponent(redirectUri)}` : ''}`, {
    method: 'POST',
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`YouTube callback failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function youtubeLogout() {
  const res = await authFetch(`${API_URL}/api/youtube/logout`, { method: 'POST' })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`YouTube logout failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function youtubeUpload(payload) {
  const res = await authFetch(`${API_URL}/api/youtube/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`YouTube upload failed (${res.status}) ${detail}`)
  }
  return res.json()
}

// ── TikTok ─────────────────────────────────────────────────────────────────

export async function tiktokStatus() {
  const res = await authFetch(`${API_URL}/api/tiktok/status`)
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`TikTok status failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function tiktokConnect(cookies) {
  const res = await authFetch(`${API_URL}/api/tiktok/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookies }),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`TikTok connect failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function tiktokAccount() {
  const res = await authFetch(`${API_URL}/api/tiktok/account`)
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`TikTok account failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function tiktokUpload(payload) {
  const res = await authFetch(`${API_URL}/api/tiktok/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`TikTok upload failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function tiktokLogout() {
  const res = await authFetch(`${API_URL}/api/tiktok/logout`, { method: 'POST' })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`TikTok logout failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function applyVoiceOver(payload) {
  const res = await authFetch(`${API_URL}/api/voiceover`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `Voice-over failed (${res.status})`)
  }
  return res.json()
}

export async function enhanceClip(payload) {
  const res = await authFetch(`${API_URL}/api/enhance`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `Enhance failed (${res.status})`)
  }
  return res.json()
}

export async function enhanceDraft(payload) {
  const res = await authFetch(`${API_URL}/api/enhance/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `Draft failed (${res.status})`)
  }
  return res.json()
}

export async function enhancePreview(payload) {
  const res = await authFetch(`${API_URL}/api/enhance/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `Preview failed (${res.status})`)
  }
  return res.json()
}

export async function previewVoiceOver(payload) {
  const res = await authFetch(`${API_URL}/api/voiceover/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `Preview failed (${res.status})`)
  }
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

export function voiceOverFileUrl(jobId, name, filename) {
  if (name) return `${API_URL}/api/library/${encodeURIComponent(name)}/${encodeURIComponent(filename)}`
  return fileUrl(jobId, filename)
}

export async function chatSplitDetect(name, filename, numFrames = 5) {
  const res = await authFetch(`${API_URL}/api/chat-split/detect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, filename, num_frames: numFrames }),
  })
  return res.json()
}

export async function chatSplitRender(name, filename, person1, person2) {
  const res = await authFetch(`${API_URL}/api/chat-split/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, filename, person1, person2 }),
  })
  return res.json()
}

export async function runCleanup(hours) {
  const res = await fetch(`${API_URL}/api/cleanup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hours: hours ?? null }),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`Cleanup failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export function parseSrt(text) {
  const blocks = text.replace(/\r/g, '').trim().split(/\n\s*\n/)
  const cues = []
  for (const block of blocks) {
    const lines = block.split('\n').filter((l) => l.trim())
    if (lines.length < 2) continue
    const timeIdx = lines.findIndex((l) => l.includes('-->'))
    if (timeIdx === -1) continue
    const [start, end] = lines[timeIdx].split('-->').map((t) => t.trim())
    const textLines = lines.slice(timeIdx + 1)
    cues.push({ start: srtToSeconds(start), end: srtToSeconds(end), text: textLines.join(' ') })
  }
  return cues
}

export async function getTrending({ niche, count }, opts = {}) {
  const params = new URLSearchParams()
  if (niche) params.set('niche', niche)
  if (count) params.set('count', String(count))
  const res = await authFetch(`${API_URL}/api/trending?${params.toString()}`, {
    signal: opts.signal,
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(`Trending fetch failed (${res.status}) ${detail}`)
  }
  return res.json()
}

export async function getYoutubeTrending({ region, category, maxResults, windowDays, enrich }, opts = {}) {
  const params = new URLSearchParams()
  if (region) params.set('region', region)
  if (category) params.set('category', category)
  if (maxResults) params.set('max_results', String(maxResults))
  if (windowDays) params.set('window_days', String(windowDays))
  if (enrich === false) params.set('enrich', 'false')
  const res = await authFetch(`${API_URL}/api/trending/youtube?${params.toString()}`, {
    signal: opts.signal,
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json()).detail || '' } catch { /* ignore */ }
    throw new Error(detail || `YouTube trending failed (${res.status})`)
  }
  return res.json()
}

function srtToSeconds(t) {
  const m = t.match(/(\d+):(\d+):(\d+)[,.](\d+)/)
  if (!m) return 0
  return (
    parseInt(m[1], 10) * 3600 +
    parseInt(m[2], 10) * 60 +
    parseInt(m[3], 10) +
    parseInt(m[4], 10) / 1000
  )
}

