import { StatusBadge } from '../../components/status-badge'
import type { UpdateMetaSnapshot } from '../../types/workspace'

type UpdateMetaStripProps = {
  meta: UpdateMetaSnapshot | null
}

export function UpdateMetaStrip({ meta }: UpdateMetaStripProps) {
  if (!meta) {
    return null
  }

  return (
    <section>
      <h2>Update Meta</h2>
      <p>Focus updated: {meta.focus_last_updated_at}</p>
      <p>Market: <StatusBadge label={meta.market_status} /></p>
      <p>Context: <StatusBadge label={meta.context_status} /></p>
      <p>Last ingestion: {meta.last_ingestion_at ?? 'unknown'}</p>
    </section>
  )
}
