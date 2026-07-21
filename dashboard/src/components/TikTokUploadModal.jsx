import { useState } from 'react'
import { Send } from 'lucide-react'
import { tiktokUpload, tiktokStatus } from '../api.js'

export default function TikTokUploadModal({ source, onClose, onDone }) {
  // source: { jobId?, name?, filename, title, description }
  const [caption, setCaption] = useState(source.description || source.title || '')
  const [visibility, setVisibility] = useState('PUBLIC_TO_EVERYONE')
  const [disableComment, setDisableComment] = useState(false)
  const [disableDuet, setDisableDuet] = useState(false)
  const [disableStitch, setDisableStitch] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  async function submit() {
    setBusy(true)
    setError('')
    try {
      const auth = await tiktokStatus()
      if (!auth.authenticated) {
        setError('TikTok not connected. Connect it in Settings first.')
        setBusy(false)
        return
      }
      const payload = {
        job_id: source.jobId || null,
        name: source.name || null,
        filename: source.filename,
        caption,
        visibility,
        disable_comment: disableComment,
        disable_duet: disableDuet,
        disable_stitch: disableStitch,
      }
      const res = await tiktokUpload(payload)
      setResult(res)
      if (onDone) setTimeout(onDone, 1500)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-[#121214] border border-white/10 rounded-2xl w-full max-w-md p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-zinc-500 hover:text-white">
          ✕
        </button>
        <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-[#fe2c55]">
            <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1v-3.51a6.37 6.37 0 0 0-.79-.05A6.34 6.34 0 0 0 3.16 15.2a6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.34-6.34V8.73a8.19 8.19 0 0 0 4.78 1.53V6.81a4.84 4.84 0 0 1-1.03-.12z" fill="currentColor"/>
          </svg>
          Upload to TikTok
        </h3>

        {result ? (
          <div className="text-center py-4">
            <p className="text-green-300 text-sm mb-2">
              {result.ok ? 'Posted successfully!' : 'Upload failed'}
            </p>
            {result.video_url && (
              <a href={result.video_url} target="_blank" rel="noreferrer" className="text-[#fe2c55] text-sm underline">
                View on TikTok
              </a>
            )}
            {result.error && (
              <p className="text-sm text-red-300 mt-2">{result.error}</p>
            )}
          </div>
        ) : (
          <>
            <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-1 block">Caption</label>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={3}
              maxLength={2200}
              placeholder="Add a caption with hashtags... #fyp #viral"
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-[#fe2c55]/50 resize-none mb-3"
            />
            <p className="text-[10px] text-zinc-500 -mt-2 mb-3">{caption.length}/2200 characters</p>

            <label className="text-xs font-bold text-zinc-400 uppercase tracking-wider mb-1 block">Visibility</label>
            <select
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-[#fe2c55]/50 mb-3"
            >
              <option value="PUBLIC_TO_EVERYONE">Everyone</option>
              <option value="MUTUAL_FOLLOW_FRIENDS">Friends</option>
              <option value="FOLLOWER_OF_CREATOR">Followers</option>
              <option value="SELF_ONLY">Only me</option>
            </select>

            <div className="space-y-2 mb-4">
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={disableComment}
                  onChange={(e) => setDisableComment(e.target.checked)}
                  className="accent-[#fe2c55] w-4 h-4"
                />
                Disable comments
              </label>
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={disableDuet}
                  onChange={(e) => setDisableDuet(e.target.checked)}
                  className="accent-[#fe2c55] w-4 h-4"
                />
                Disable duet
              </label>
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={disableStitch}
                  onChange={(e) => setDisableStitch(e.target.checked)}
                  className="accent-[#fe2c55] w-4 h-4"
                />
                Disable stitch
              </label>
            </div>

            {error && <p className="text-sm text-red-300 mb-2">{error}</p>}

            <button
              onClick={submit}
              disabled={busy}
              className="w-full py-2.5 rounded-lg bg-[#fe2c55] hover:bg-[#e02548] text-white font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {busy ? 'Posting…' : <><Send size={15} /> Post to TikTok</>}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
