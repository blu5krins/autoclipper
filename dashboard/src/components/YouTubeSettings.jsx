import { useEffect, useState } from 'react'
import { Youtube, CheckCircle2, Link2, AlertCircle } from 'lucide-react'
import { youtubeStatus, youtubeAuthUrl, youtubeCallback } from '../api.js'

export default function YouTubeSettings() {
  const [status, setStatus] = useState({ configured: false, authenticated: false })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    try {
      const s = await youtubeStatus()
      setStatus(s)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // If redirected back with ?code=, complete the OAuth flow.
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    if (code) {
      setBusy(true)
      youtubeCallback(code)
        .then(() => {
          window.history.replaceState({}, '', window.location.pathname)
          load()
        })
        .catch((e) => setError(e.message))
        .finally(() => setBusy(false))
    }
  }, [])

  async function connect() {
    setBusy(true)
    setError('')
    try {
      const { auth_url } = await youtubeAuthUrl(window.location.origin + window.location.pathname)
      window.location.href = auth_url
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  return (
    <section className="border-t border-border pt-5">
      <div className="flex items-center gap-2 mb-3">
        <Youtube size={16} className="text-zinc-400" />
        <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">YouTube Shorts</h2>
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
                  ? 'Connected to YouTube'
                  : status.configured
                  ? 'Not connected — authorize to enable uploads'
                  : 'Server missing client_secret.json'}
              </span>
            </div>
            {!status.authenticated && status.configured && (
              <button
                onClick={connect}
                disabled={busy}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white transition-colors disabled:opacity-50"
              >
                <Link2 size={13} /> {busy ? 'Redirecting…' : 'Connect'}
              </button>
            )}
          </div>
          {!status.configured && (
            <p className="text-xs text-zinc-500 mt-2">
              Admin must place <code>client_secret.json</code> in the server's YouTube config dir
              (env <code>YT_CLIENT_SECRET</code>).
            </p>
          )}
          {error && <p className="text-xs text-red-300 mt-2">{error}</p>}
        </div>
      )}
    </section>
  )
}
