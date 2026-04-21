import type { ReliabilityIncidentSnapshot } from '../../types/reliability'

type ReliabilityIncidentsPanelProps = {
  incidents: ReliabilityIncidentSnapshot[]
  isLoading: boolean
}

export function ReliabilityIncidentsPanel({
  incidents,
  isLoading,
}: ReliabilityIncidentsPanelProps) {
  return (
    <section aria-label="reliability-incidents-panel">
      <h3>Incident Review</h3>
      {isLoading ? <p>Loading incidents...</p> : null}
      {!isLoading && incidents.length === 0 ? <p>No active incidents.</p> : null}
      {!isLoading
        ? incidents.map((incident) => (
            <article key={`${incident.source_name}-${incident.recorded_at}`}>
              <h4>{incident.source_name}</h4>
              <p>Severity: {incident.severity}</p>
              <p>{incident.message}</p>
              <p>{incident.recorded_at}</p>
            </article>
          ))
        : null}
    </section>
  )
}
