/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "false" switches the API layer from mocks to the real backend. */
  readonly VITE_USE_MOCKS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
