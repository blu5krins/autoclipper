import { useEffect, useState } from 'react'
import { Youtube, CheckCircle2, Link2, AlertCircle, ExternalLink, RefreshCw, LogOut } from 'lucide-react'
import { youtubeStatus, youtubeAccount, youtubeAuthUrl, youtubeCallback, youtubeLogout } from '../api.js'

function formatCount(n) {
  const num = Number(n || 0)
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M'
  if (num >= 1_000) return (num / 1_000).toFixed(1).replace(/\.0$/, '') + 'K'
  return String(num)
}

export default function YouTubeSettings() {
  const [status, setStatus] = useState({ configured: false, authenticated: false })
  const [account, setAccount] = useState(null)
  const [accountError, setAccountError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    try {
      const s = await youtubeStatus()
      setStatus(s)
      if (s.authenticated) {
        try {
          const info = await youtubeAccount()
          setAccount(info)
          setAccountError('')
        } catch (e) {
          setAccountError(e.message)
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
    if (code && state !== 'facebook') {
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
    } finally {
      setBusy(false)
    }
  }

  async function disconnect() {
    if (!confirm('Disconnect YouTube account?')) return
    setBusy(true)
    setError('')
    try {
      await youtubeLogout()
      setAccount(null)
      setAccountError('')
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
            {status.authenticated && accountError && (
              <button
                onClick={connect}
                disabled={busy}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white transition-colors disabled:opacity-50"
              >
                <RefreshCw size={13} /> {busy ? 'Redirecting…' : 'Re-authorize'}
              </button>
            )}
            {status.authenticated && !accountError && (
              <button
                onClick={disconnect}
                disabled={busy}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-zinc-300 transition-colors disabled:opacity-50"
              >
                <LogOut size={13} /> Disconnect
              </button>
            )}
          </div>

          {status.authenticated && account && (
            <div className="mt-3 bg-black/30 rounded-lg border border-white/5 p-3">
              <div className="flex items-center gap-3">
                {account.thumbnail && (
                  <img
                    src={account.thumbnail}
                    alt={account.title}
                    className="w-12 h-12 rounded-full border border-white/10 object-cover"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-zinc-100 truncate">{account.title}</span>
                    {account.id && (
                      <a
                        href={`https://youtube.com/channel/${account.id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-zinc-500 hover:text-zinc-300 transition-colors shrink-0"
                        title="Open channel"
                      >
                        <ExternalLink size={12} />
                      </a>
                    )}
                  </div>
                  {account.country && (
                    <span className="text-[10px] text-zinc-500 uppercase">{account.country}</span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 mt-3">
                <div className="text-center">
                  <div className="text-sm font-bold text-zinc-100">{formatCount(account.subscriber_count)}</div>
                  <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Subscribers</div>
                </div>
                <div className="text-center">
                  <div className="text-sm font-bold text-zinc-100">{formatCount(account.video_count)}</div>
                  <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Videos</div>
                </div>
                <div className="text-center">
                  <div className="text-sm font-bold text-zinc-100">{formatCount(account.view_count)}</div>
                  <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Views</div>
                </div>
              </div>

              {account.description && (
                <p className="text-[11px] text-zinc-500 mt-2 line-clamp-2 leading-relaxed">{account.description}</p>
              )}
            </div>
          )}

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
