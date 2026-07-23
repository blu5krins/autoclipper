import { useEffect, useState } from 'react'
import { Facebook, CheckCircle2, Link2, AlertCircle, ExternalLink, LogOut } from 'lucide-react'
import { facebookStatus, facebookPages, facebookAuthUrl, facebookCallback, facebookLogout, facebookAppSettings } from '../api.js'

export default function FacebookSettings() {
  const [status, setStatus] = useState({ configured: false, authenticated: false })
  const [pages, setPages] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [appId, setAppId] = useState('')
  const [appSecret, setAppSecret] = useState('')
  const [showConfig, setShowConfig] = useState(false)

  async function load() {
    try {
      const s = await facebookStatus()
      setStatus(s)
      if (s.authenticated) {
        try {
          const { pages: p } = await facebookPages()
          setPages(p)
        } catch (e) {
          console.error('Failed to load pages:', e)
        }
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const state = params.get('state')
    if (code && state === 'facebook') {
      setBusy(true)
      facebookCallback(code, window.location.origin + window.location.pathname)
        .then(() => {
          window.history.replaceState({}, '', window.location.pathname)
          load()
        })
        .catch((e) => setError(e.message))
        .finally(() => setBusy(false))
    }
  }, [])

  async function saveAppSettings() {
    if (!appId || !appSecret) {
      setError('App ID and App Secret are required')
      return
    }
    setBusy(true)
    setError('')
    try {
      await facebookAppSettings(appId, appSecret)
      setShowConfig(false)
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function connect() {
    setBusy(true)
    setError('')
    try {
      const redirectUri = window.location.origin + window.location.pathname
      const { auth_url } = await facebookAuthUrl(redirectUri)
      window.location.href = auth_url
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function disconnect() {
    if (!confirm('Disconnect Facebook account?')) return
    setBusy(true)
    setError('')
    try {
      await facebookLogout()
      setPages([])
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="border-t border-border pt-5">
      <div className="flex items-center gap-2 mb-3">
        <Facebook size={16} className="text-zinc-400" />
        <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">Facebook Pages</h2>
      </div>

      {loading ? (
        <p className="text-xs text-zinc-500">Checking connection…</p>
      ) : (
        <div className="bg-background border border-border rounded-lg p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {status.authenticated ? (
                <CheckCircle2 size={18} className="text-green-400" />
              ) : status.configured ? (
                <AlertCircle size={18} className="text-amber-400" />
              ) : (
                <AlertCircle size={18} className="text-zinc-500" />
              )}
              <span className="text-sm text-zinc-200">
                {status.authenticated
                  ? `Connected to Facebook (${pages.length} page${pages.length !== 1 ? 's' : ''})`
                  : status.configured
                  ? 'Not connected — authorize to enable uploads'
                  : 'App not configured — enter App ID & Secret below'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {!status.authenticated && (
                <button
                  onClick={() => setShowConfig(!showConfig)}
                  className="text-[10px] px-2 py-1 rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-400 transition-colors"
                >
                  {showConfig ? 'Hide' : 'App Settings'}
                </button>
              )}
              {!status.authenticated && status.configured && (
                <button
                  onClick={connect}
                  disabled={busy}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50"
                >
                  <Link2 size={13} /> {busy ? 'Redirecting…' : 'Connect'}
                </button>
              )}
              {status.authenticated && (
                <button
                  onClick={disconnect}
                  disabled={busy}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-zinc-300 transition-colors disabled:opacity-50"
                >
                  <LogOut size={13} /> Disconnect
                </button>
              )}
            </div>
          </div>

          {showConfig && (
            <div className="mt-3 bg-black/30 rounded-lg border border-white/5 p-3 space-y-2">
              <p className="text-[10px] text-zinc-500 mb-2">
                Get from <a href="https://developers.facebook.com" target="_blank" rel="noreferrer" className="text-blue-400 underline">developers.facebook.com</a> → My Apps → Create App (Business type)
              </p>
              <input
                value={appId}
                onChange={(e) => setAppId(e.target.value)}
                placeholder="App ID"
                className="w-full bg-background border border-border rounded px-2 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-primary"
              />
              <input
                value={appSecret}
                onChange={(e) => setAppSecret(e.target.value)}
                placeholder="App Secret"
                type="password"
                className="w-full bg-background border border-border rounded px-2 py-1.5 text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-primary"
              />
              <button
                onClick={saveAppSettings}
                disabled={busy || !appId || !appSecret}
                className="w-full py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
              >
                {busy ? 'Saving…' : 'Save App Settings'}
              </button>
            </div>
          )}

          {status.authenticated && pages.length > 0 && (
            <div className="mt-3 bg-black/30 rounded-lg border border-white/5 p-2">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2 px-1">Your Pages</div>
              <div className="space-y-1">
                {pages.map((page) => (
                  <div
                    key={page.id}
                    className="flex items-center justify-between px-2 py-1.5 rounded hover:bg-white/5 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <Facebook size={14} className="text-blue-400" />
                      <span className="text-xs text-zinc-200">{page.name}</span>
                      {page.category && (
                        <span className="text-[9px] text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded">
                          {page.category}
                        </span>
                      )}
                    </div>
                    <a
                      href={`https://facebook.com/${page.id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-zinc-500 hover:text-zinc-300 transition-colors"
                    >
                      <ExternalLink size={11} />
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}

          {status.authenticated && pages.length === 0 && (
            <p className="text-xs text-zinc-500 mt-2">
              No Pages found. Make sure you're an admin of at least one Facebook Page.
            </p>
          )}

          {error && <p className="text-xs text-red-300 mt-2">{error}</p>}
        </div>
      )}
    </section>
  )
}
