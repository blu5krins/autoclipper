import { useState, useEffect } from 'react'
import { Compass, RefreshCw, ExternalLink, Youtube, Globe2, Copy, Check } from 'lucide-react'
import { getYoutubeTrending } from '../api.js'

const CATEGORIES = [
  { id: 'general', label: 'Explore' },
  { id: 'music', label: 'Music' },
  { id: 'gaming', label: 'Gaming' },
  { id: 'news', label: 'News' },
  { id: 'sports', label: 'Sports' },
  { id: 'entertainment', label: 'Entertainment' },
  { id: 'education', label: 'Education' },
  { id: 'tech', label: 'Tech & Science' },
  { id: 'howto', label: 'Howto & Style' },
  { id: 'people', label: 'People & Blogs' },
  { id: 'podcast', label: 'Podcasts' },
  { id: 'movies', label: 'Movies' },
  { id: 'anime', label: 'Anime' },
  { id: 'vehicles', label: 'Autos' },
  { id: 'comedy', label: 'Comedy' },
  { id: 'shows', label: 'Shows' },
  { id: 'trailers', label: 'Trailers' },
]

const REGIONS = [
  { id: 'id', label: 'Indonesia' },
  { id: 'us', label: 'United States' },
  { id: 'gb', label: 'United Kingdom' },
  { id: 'kr', label: 'South Korea' },
  { id: 'jp', label: 'Japan' },
  { id: 'in', label: 'India' },
]

function formatViews(n) {
  if (!n) return '0'
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(n)
}

export default function TrendingPage({ settings }) {
  const [category, setCategory] = useState('general')
  const [region, setRegion] = useState('id')
  const [maxResults, setMaxResults] = useState(12)
  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copiedId, setCopiedId] = useState(null)
  const [categoryFiltered, setCategoryFiltered] = useState(true)
  const [categoryLabel, setCategoryLabel] = useState('Explore')

  function copyLink(url, id) {
    navigator.clipboard?.writeText(url)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  async function generate() {
    if (!settings?.youtubeApiKey) {
      setError('YouTube Data API Key belum diisi di Settings. Tambahkan dulu untuk memuat video Explore.')
      return
    }
    setLoading(true)
    setError('')
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 25000)
    try {
      const res = await getYoutubeTrending({
        region,
        category,
        maxResults,
        youtubeKey: settings?.youtubeApiKey || undefined,
        geminiKey: settings?.geminiKey || undefined,
        geminiModel: settings?.geminiModel || undefined,
      }, { signal: controller.signal })
      const vids = res.videos || []
      setVideos(vids)
      setCategoryFiltered(res.category_filtered !== false)
      setCategoryLabel(res.category_label || 'Explore')
      if (vids.length === 0) {
        setError('Tidak ada video ditemukan untuk kategori/region ini. Coba ganti Region atau pilih "Explore".')
      }
    } catch (e) {
      setError(e.message || 'Gagal memuat Explore.')
      setVideos([])
    } finally {
      clearTimeout(timer)
      setLoading(false)
    }
  }

  // Auto-load on mount / when category+region change.
  useEffect(() => {
    if (settings?.youtubeApiKey) generate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, region])

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 bg-orange-500/20 rounded-lg flex items-center justify-center">
          <Compass size={20} className="text-orange-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-white">Explore</h1>
          <p className="text-sm text-zinc-400">
            YouTube retired Trending in July 2025 — this shows most-popular by category (Explore-style). Shorts filtered out.
          </p>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-2xl p-6 mb-6">
        {/* Category tabs */}
        <div className="flex flex-wrap gap-2 mb-5">
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setCategory(c.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                category === c.id
                  ? 'bg-orange-500/20 border-orange-500 text-orange-300'
                  : 'border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>

        <div className="flex flex-col sm:flex-row gap-4">
          <div className="w-full sm:w-48">
            <label className="block text-xs text-zinc-400 mb-2 uppercase tracking-wider">
              <Globe2 size={12} className="inline mr-1" /> Region
            </label>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm
                         text-white focus:outline-none focus:border-primary"
            >
              {REGIONS.map((r) => (
                <option key={r.id} value={r.id}>{r.label}</option>
              ))}
            </select>
          </div>

          <div className="w-full sm:w-36">
            <label className="block text-xs text-zinc-400 mb-2 uppercase tracking-wider">
              # Videos
            </label>
            <input
              type="number"
              min={3}
              max={25}
              value={maxResults}
              onChange={(e) => setMaxResults(Math.max(3, Math.min(25, parseInt(e.target.value || '3', 10))))}
              className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-sm
                         text-white focus:outline-none focus:border-primary"
            />
          </div>

          <div className="flex items-end sm:ml-auto">
            <button
              type="button"
              onClick={generate}
              disabled={loading}
              className="w-full sm:w-auto flex items-center justify-center gap-2 rounded-lg bg-orange-500
                         hover:bg-orange-600 disabled:opacity-50 text-white font-medium text-sm px-5 py-2.5
                         transition-colors"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Loading…
                </>
              ) : (
                <>
                  <RefreshCw size={16} />
                  Reload
                </>
              )}
            </button>
          </div>
        </div>

        {settings?.youtubeApiKey ? (
          <p className="text-xs text-zinc-500 mt-4">
            Using your YouTube Data API key from Settings. Gemini enriches each video with a clip idea.
          </p>
        ) : (
          <p className="text-xs text-amber-400/80 mt-4">
            Add a YouTube Data API Key in Settings to load real Explore videos.
          </p>
        )}
      </div>

      {error && (
        <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {videos.length > 0 && !categoryFiltered && category !== 'general' && (
        <div className="mb-6 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-300 px-4 py-3 text-sm">
          No “{categoryLabel}” videos trending in this region right now. Showing the general
          Explore list instead — YouTube Explore is region-based, not category-based.
        </div>
      )}

      {videos.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {videos.map((v) => (
            <div
              key={v.video_id}
              className="bg-surface border border-border rounded-xl overflow-hidden hover:border-orange-500/40 transition-colors"
            >
              <a href={v.url} target="_blank" rel="noreferrer" className="block relative">
                <img
                  src={v.thumbnail}
                  alt={v.title}
                  className="w-full aspect-video object-cover bg-zinc-800"
                />
                <span className="absolute bottom-2 right-2 bg-black/70 text-white text-[10px] px-1.5 py-0.5 rounded">
                  {v.duration_sec ? `${Math.floor(v.duration_sec / 60)}:${String(v.duration_sec % 60).padStart(2, '0')} · ` : ''}{formatViews(v.views)} views
                </span>
              </a>
              <div className="p-3">
                <a
                  href={v.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block text-sm font-medium text-white leading-snug hover:text-orange-300 line-clamp-2"
                >
                  {v.title}
                </a>
                <p className="text-xs text-zinc-500 mt-1 truncate">{v.channel}</p>

                <button
                  type="button"
                  onClick={() => copyLink(v.url, v.video_id)}
                  className="mt-2 flex items-center gap-1.5 text-xs text-zinc-400 hover:text-primary transition-colors"
                >
                  <Copy size={13} />
                  {copiedId === v.video_id ? 'Copied!' : 'Copy link to Clip Generator'}
                </button>

                {v.idea && (
                  <div className="mt-3 pt-3 border-t border-border">
                    <div className="flex items-start gap-2">
                      <Youtube size={14} className="text-orange-400 shrink-0 mt-0.5" />
                      <p className="text-xs text-zinc-300 italic">{v.idea}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && videos.length === 0 && !error && (
        <div className="text-center py-16 text-zinc-500">
          <Compass size={40} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">Pick a category & region, then Reload Explore.</p>
        </div>
      )}
    </div>
  )
}
