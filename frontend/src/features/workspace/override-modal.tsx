import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import type { ExecutionOverrideState } from '../../types/workspace'
import { formatMMSS } from './use-override-countdown'

type OverrideModalProps = {
  open: boolean
  state: ExecutionOverrideState | null
  remaining: number | null
  isActing: boolean
  error: string | null
  onConfirm: () => void
  onRevoke: () => void
  onClose: () => void
}

export function OverrideModal({
  open, state, remaining, isActing, error, onConfirm, onRevoke, onClose,
}: OverrideModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<Element | null>(null)

  useEffect(() => {
    if (!open) return
    triggerRef.current = document.activeElement
    dialogRef.current?.querySelector<HTMLElement>('button')?.focus()

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose(); return }
      if (e.key === 'Tab' && dialogRef.current) {
        const f = dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled])')
        if (f.length === 0) return
        const first = f[0], last = f[f.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      ;(triggerRef.current as HTMLElement | null)?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onMouseDown={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="override-modal-title"
        className="w-full max-w-sm rounded border border-neutral-700 bg-neutral-900 p-5 text-sm text-neutral-100"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 id="override-modal-title" className="text-xs font-black uppercase tracking-wide">
          Execution override
        </h2>

        {state === 'pending' && (
          <p className="mt-3 text-neutral-300">
            Override запрошен и ждёт подтверждения. Confirm активирует его на 1 час.
          </p>
        )}
        {state === 'confirmed' && (
          <p className="mt-3 text-neutral-300">
            Override активен. Истекает через{' '}
            <span className="font-black">
              {remaining !== null && remaining > 0 ? formatMMSS(remaining) : '00:00'}
            </span>.
          </p>
        )}

        {error && <p className="mt-3 text-red-400">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          {state === 'pending' && (
            <button type="button" disabled={isActing} onClick={onConfirm}
              className="rounded border border-emerald-600 px-3 py-1 text-xs font-black uppercase text-emerald-400 disabled:opacity-50">
              Confirm
            </button>
          )}
          {(state === 'pending' || state === 'confirmed') && (
            <button type="button" disabled={isActing} onClick={onRevoke}
              className="rounded border border-red-600 px-3 py-1 text-xs font-black uppercase text-red-400 disabled:opacity-50">
              Revoke
            </button>
          )}
          <button type="button" disabled={isActing} onClick={onClose}
            className="rounded border border-neutral-600 px-3 py-1 text-xs font-black uppercase text-neutral-300 disabled:opacity-50">
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
