import { useState, useEffect } from 'react'
import { Clock, X, Zap } from 'lucide-react'

// Optimal upload times (WIB/GMT+7)
const OPTIMAL_TIMES = {
  tiktok: {
    weekday: [
      { start: 7, end: 9, label: 'Pagi (Commute)', emoji: '🌅' },
      { start: 12, end: 13, label: 'Siang (Lunch)', emoji: '☀️' },
      { start: 19, end: 22, label: 'Malam (Prime)', emoji: '🌙', best: true },
    ],
    weekend: [
      { start: 10, end: 14, label: 'Siang (Santai)', emoji: '🌴' },
      { start: 19, end: 22, label: 'Malam (Prime)', emoji: '🌙', best: true },
    ],
  },
  youtube: {
    weekday: [
      { start: 11, end: 13, label: 'Siang (Lunch)', emoji: '☀️' },
      { start: 18, end: 20, label: 'Sore (Pulang)', emoji: '🌆' },
    ],
    weekend: [
      { start: 10, end: 12, label: 'Pagi (Santai)', emoji: '🌅' },
      { start: 18, end: 21, label: 'Malam (Prime)', emoji: '🌙', best: true },
    ],
  },
}

function getNextOptimalSlot(platform) {
  const now = new Date()
  // Convert to WIB (UTC+7)
  const wibOffset = 7 * 60
  const localOffset = now.getTimezoneOffset()
  const wibTime = new Date(now.getTime() + (localOffset + wibOffset) * 60000)
  
  const hour = wibTime.getHours()
  const day = wibTime.getDay() // 0=Sun, 6=Sat
  const isWeekend = day === 0 || day === 6
  
  const times = isWeekend ? OPTIMAL_TIMES[platform].weekend : OPTIMAL_TIMES[platform].weekday
  
  // Find next slot
  for (const slot of times) {
    if (hour < slot.start) {
      const diff = slot.start - hour
      return { ...slot, diffHours: diff, isNow: false }
    }
    if (hour >= slot.start && hour < slot.end) {
      return { ...slot, diffHours: 0, isNow: true }
    }
  }
  
  // All slots passed, return first slot of tomorrow
  return { ...times[0], diffHours: 24 - hour + times[0].start, isNow: false }
}

function getDayName() {
  const days = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu']
  const now = new Date()
  const wibOffset = 7 * 60
  const localOffset = now.getTimezoneOffset()
  const wibTime = new Date(now.getTime() + (localOffset + wibOffset) * 60000)
  return days[wibTime.getDay()]
}

function getCurrentHour() {
  const now = new Date()
  const wibOffset = 7 * 60
  const localOffset = now.getTimezoneOffset()
  const wibTime = new Date(now.getTime() + (localOffset + wibOffset) * 60000)
  return wibTime.getHours()
}

export default function UploadTimeSuggestion({ platform = 'tiktok', onDismiss }) {
  const [slot, setSlot] = useState(null)
  const [countdown, setCountdown] = useState('')
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    const update = () => {
      const next = getNextOptimalSlot(platform)
      setSlot(next)
      
      if (next.isNow) {
        setCountdown('Sekarang waktu optimal! 🔥')
      } else if (next.diffHours <= 1) {
        setCountdown(`${Math.round(next.diffHours * 60)} menit lagi`)
      } else {
        setCountdown(`${Math.round(next.diffHours)} jam lagi`)
      }
    }
    
    update()
    const interval = setInterval(update, 60000) // Update every minute
    return () => clearInterval(interval)
  }, [platform])

  const handleDismiss = () => {
    setDismissed(true)
    if (onDismiss) onDismiss()
  }

  if (dismissed || !slot) return null

  const isGoodTime = slot.isNow || (getCurrentHour() >= 7 && getCurrentHour() <= 22)

  return (
    <div className="mb-3 relative">
      <div className={`
        rounded-xl p-3 border transition-all
        ${slot.isNow 
          ? 'bg-green-500/10 border-green-500/30' 
          : 'bg-amber-500/10 border-amber-500/30'
        }
      `}>
        <div className="flex items-start gap-2">
          <div className={`
            p-1.5 rounded-lg
            ${slot.isNow ? 'bg-green-500/20' : 'bg-amber-500/20'}
          `}>
            {slot.isNow ? <Zap size={14} className="text-green-400" /> : <Clock size={14} className="text-amber-400" />}
          </div>
          
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-bold text-white">
                {slot.emoji} {slot.label}
              </span>
              {slot.best && !slot.isNow && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 font-medium">
                  BEST
                </span>
              )}
            </div>
            
            <p className="text-[11px] text-zinc-400 mt-0.5">
              {getDayName()} • {slot.start}:00 - {slot.end}:00 WIB
            </p>
            
            <p className={`
              text-xs font-medium mt-1
              ${slot.isNow ? 'text-green-300' : 'text-amber-300'}
            `}>
              {countdown}
            </p>
          </div>
          
          <button
            onClick={handleDismiss}
            className="p-1 hover:bg-white/10 rounded transition-colors"
          >
            <X size={12} className="text-zinc-500" />
          </button>
        </div>
        
        {/* Visual timeline */}
        <div className="mt-2 flex gap-1">
          {[...Array(24)].map((_, i) => {
            const isOptimal = OPTIMAL_TIMES[platform].weekday.some(s => i >= s.start && i < s.end) ||
                              OPTIMAL_TIMES[platform].weekend.some(s => i >= s.start && i < s.end)
            const isCurrent = i === getCurrentHour()
            return (
              <div
                key={i}
                className={`
                  h-1.5 flex-1 rounded-full transition-all
                  ${isCurrent ? 'bg-white scale-y-150' : ''}
                  ${isOptimal ? 'bg-green-500/60' : 'bg-zinc-700/40'}
                `}
                title={`${i}:00`}
              />
            )
          })}
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-[9px] text-zinc-600">00:00</span>
          <span className="text-[9px] text-zinc-600">12:00</span>
          <span className="text-[9px] text-zinc-600">23:00</span>
        </div>
      </div>
    </div>
  )
}
