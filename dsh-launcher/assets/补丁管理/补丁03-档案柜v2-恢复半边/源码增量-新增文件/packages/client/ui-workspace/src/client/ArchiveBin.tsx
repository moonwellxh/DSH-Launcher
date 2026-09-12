/**
 * Archive bin: the sidebar foot's entry to the registry-global archive set.
 * The wide column renders a labelled row carrying the archived count; the
 * rail renders the bare icon (the count badge is wide-only, like every other
 * label here). Opening the entry lists the archived Sessions — title plus
 * last update — each with a Restore action; a rejected restore keeps its row
 * and reports inline, while a committed one drops the row because the list is
 * driven purely by the Host archive-set snapshot (the same `archivedSessionIds`
 * the browser reads), never by local bookkeeping.
 */
import { useState } from 'react'
import clsx from 'clsx'
import {
  Button, IconArchiveOutline20, Modal, relativeTime, Tooltip,
} from '@deepseek-ai/dsh-client-ui-primitives'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { ArchiveBinProps } from './contract/slots.ts'
import css from './ArchiveBin.module.css'

/** Compact relative time from the shared bucketing, localized by this namespace. */
function timeLabel(updatedAt: number, now: number, t: ArchiveBinProps['t']): string {
  const { unit, n } = relativeTime(updatedAt, now)
  return unit === 'now' ? t('time.now') : t(`time.${unit}`, { n })
}

/**
 * Render the archive-bin entry and its panel.
 * @param props - composed slot props (foot owner share + injected restore + locale seat).
 * @returns the foot entry and the portalled panel.
 */
export function ArchiveBin({
  wide, useWorkspaces, useSessions, restoreSession, t,
}: ArchiveBinProps) {
  const archivedSessionIds = useWorkspaces(state => state.archivedSessionIds)
  const sessions = useSessions(state => state.byId)
  const [open, setOpen] = useState(false)
  const [restoring, setRestoring] = useState<SessionId | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const count = archivedSessionIds.length
  const now = Date.now()

  const close = (): void => {
    setOpen(false)
    setFailure(null)
  }

  /**
   * Restore one archived Session. The row stays until the Host archive set
   * drops the id, so a rejection leaves the panel exactly as the operator saw
   * it and only adds the failure line beside the still-active entry.
   */
  const restore = (sessionId: SessionId): Promise<void> => {
    setRestoring(sessionId)
    setFailure(null)
    return restoreSession(sessionId).then(() => {
      // The panel may have been closed mid-flight; clearing is unconditional
      // because the next open must not inherit a stale busy row.
      setRestoring(null)
    }, (reason: unknown) => {
      console.warn('session restore rejected:', reason)
      setRestoring(null)
      setFailure(t('archiveBin.restoreFailed', {
        message: reason instanceof Error ? reason.message : String(reason),
      }))
    })
  }

  // The rail carries no label of its own, so the tooltip is its only name;
  // the wide row names itself and suppresses the tooltip (shell-wide pattern).
  const entryLabel = t('archiveBin.entry')
  return (
    <div className={css.root}>
      <Tooltip label={entryLabel} delayMs={500} disabled={wide}>
        <button
          type="button"
          className={clsx(css.trigger, !wide && css.rail)}
          aria-label={entryLabel}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => { setOpen(true) }}
        >
          <IconArchiveOutline20 size={wide ? 16 : 18} />
          {wide && <span className={css.label}>{entryLabel}</span>}
          {wide && count > 0 && <span className={css.badge}>{count}</span>}
        </button>
      </Tooltip>
      <Modal
        open={open}
        onClose={close}
        closeLabel={t('close')}
        title={t('archiveBin.title')}
      >
        {count === 0
          ? <div className={css.empty} role="status">{t('archiveBin.empty')}</div>
          : (
            <ul className={css.list}>
              {archivedSessionIds.map((sessionId) => {
                const session = sessions[sessionId]
                return (
                  <li key={sessionId} className={css.row}>
                    <div className={css.rowText}>
                      {/* An archived id outside the Session list still names
                          itself: the raw id beats an empty row. */}
                      <span className={css.rowTitle}>{session?.displayTitle ?? sessionId}</span>
                      {session !== undefined && (
                        <span className={css.rowTime}>{timeLabel(session.updatedAt, now, t)}</span>
                      )}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={restoring !== null}
                      onClick={() => { void restore(sessionId) }}
                    >
                      {restoring === sessionId ? t('archiveBin.restoring') : t('archiveBin.restore')}
                    </Button>
                  </li>
                )
              })}
            </ul>
          )}
        {failure !== null && <div className={css.error} role="alert">{failure}</div>}
      </Modal>
    </div>
  )
}
