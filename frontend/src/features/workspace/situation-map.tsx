import type { SituationMapSnapshot } from '../../types/workspace'

type SituationMapProps = {
  situationMap: SituationMapSnapshot | null
}

export function SituationMap({ situationMap }: SituationMapProps) {
  if (!situationMap) {
    return null
  }

  return (
    <section>
      <h2>Situation Map</h2>
      <p>Directional bias: {situationMap.directional_bias}</p>
      <p>Entry hint: {situationMap.entry_hint}</p>
      <p>Target hint: {situationMap.target_hint}</p>
      <p>Invalidation hint: {situationMap.invalidation_hint}</p>
      <p>{situationMap.analyst_note}</p>
    </section>
  )
}
