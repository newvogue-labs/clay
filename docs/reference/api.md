# API

Clay API — локальный control plane на FastAPI. HTTP-контракт (пути, методы,
request/response-схемы, статусы) — источник истины OpenAPI: живой Swagger
`/docs` и `/openapi.json`. Ниже — Python-поверхность приложения: фабрика,
lifespan и dependency injection провайдеры.

## Application Factory

::: clay.api.main
    options:
      members:
        - create_app

## Lifespan

::: clay.api.lifespan
    options:
      members:
        - lifespan

## Dependencies

::: clay.api.dependencies
    options:
      members:
        - get_ingestion_settings
        - get_session_factory
        - get_db_session
        - get_market_ingestion_service
        - get_context_connector_manager
        - get_ingestion_cycle_service
        - get_control_center_service
        - get_event_bus
        - get_workspace_service
        - get_ai_control_service
        - get_signal_engine_service
        - get_session_control_service
        - get_demo_trading_service
        - get_session_review_service
        - get_knowledge_service
        - get_validation_lab_service
        - get_execution_config
        - get_execution_client
        - get_override_service
        - get_reliability_service
        - get_alpha_readiness_service
