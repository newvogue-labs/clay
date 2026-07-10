# AI Control

## Service (Orchestration)

::: clay.ai_control.service
    options:
      members:
        - AIControlService

## Runner (Transport)

::: clay.ai_control.runner
    options:
      members:
        - AgentRunner
        - RoutingModelClient
        - OllamaNativeClient
        - LiteLLMModelClient
        - ServiceModelResolver
        - ModelClient
        - ModelResolver
        - ModelResponse
        - AgentRunResult
        - ModelUnavailableError
