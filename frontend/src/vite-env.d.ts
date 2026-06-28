/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CLAY_API_BASE_URL?: string
  readonly VITE_CLAY_OPERATOR_NAME?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
