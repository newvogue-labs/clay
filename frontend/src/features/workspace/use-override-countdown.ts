import { useEffect, useRef, useState } from 'react'

export function formatMMSS(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const mm = String(Math.floor(total / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

export function useOverrideCountdown(
  expiresAtIso: string | null,
  offsetMs: number,
  onExpire?: () => void,
): number | null {
  const [remaining, setRemaining] = useState<number | null>(() =>
    expiresAtIso ? Date.parse(expiresAtIso) - (Date.now() + offsetMs) : null,
  )
  const onExpireRef = useRef(onExpire)
  onExpireRef.current = onExpire

  useEffect(() => {
    if (!expiresAtIso) {
      setRemaining(null)
      return
    }
    const target = Date.parse(expiresAtIso)
    let fired = false
    const tick = () => {
      const next = target - (Date.now() + offsetMs)
      setRemaining(next)
      if (next <= 0 && !fired) {
        fired = true
        onExpireRef.current?.()
      }
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [expiresAtIso, offsetMs])

  return remaining
}
