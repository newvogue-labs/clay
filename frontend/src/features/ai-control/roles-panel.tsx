import type { RoleDefinitionSnapshot } from '../../types/ai-control'

type RolesPanelProps = {
  roles: RoleDefinitionSnapshot[]
  isLoading: boolean
}

export function RolesPanel({ roles, isLoading }: RolesPanelProps) {
  return (
    <section>
      <h2>AI Roles</h2>
      {isLoading ? (
        <p>Loading role model...</p>
      ) : (
        <ul>
          {roles.map((role) => (
            <li key={role.role_id}>
              <strong>{role.role_name}</strong>
              <div>{role.responsibility}</div>
              <div>Inputs: {role.inputs.join(', ')}</div>
              <div>Outputs: {role.outputs.join(', ')}</div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
