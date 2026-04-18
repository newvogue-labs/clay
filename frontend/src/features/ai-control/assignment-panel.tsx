import { StatusBadge } from '../../components/status-badge'
import type { AssignmentSnapshot, ModelVersionSnapshot } from '../../types/ai-control'

type AssignmentPanelProps = {
  assignments: AssignmentSnapshot[]
  models: ModelVersionSnapshot[]
  isLoading: boolean
  isActing: boolean
  onReviewAssignment: (roleId: string, modelId: string) => void
}

export function AssignmentPanel({
  assignments,
  models,
  isLoading,
  isActing,
  onReviewAssignment,
}: AssignmentPanelProps) {
  return (
    <section>
      <h2>Model Assignments</h2>
      {isLoading ? (
        <p>Loading assignments...</p>
      ) : (
        <ul>
          {assignments.map((assignment) => {
            const alternatives = models.filter(
              (model) =>
                model.compatible_roles.includes(assignment.role_id) &&
                model.model_id !== assignment.model_id,
            )

            return (
              <li key={assignment.role_id}>
                <strong>{assignment.role_name}</strong>
                <div>Current model: {assignment.model_display_name}</div>
                <div>Provider: {assignment.provider}</div>
                <div>Mode: <StatusBadge label={assignment.assignment_mode} /></div>
                <div>Health: <StatusBadge label={assignment.assignment_health} /></div>
                <div>{assignment.reason}</div>
                <div>
                  {alternatives.map((model) => (
                    <button
                      key={`${assignment.role_id}-${model.model_id}`}
                      disabled={isActing}
                      onClick={() => {
                        onReviewAssignment(assignment.role_id, model.model_id)
                      }}
                      type="button"
                    >
                      Review {model.display_name}
                    </button>
                  ))}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
