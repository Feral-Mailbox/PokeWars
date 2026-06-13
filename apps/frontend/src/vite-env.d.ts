/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BUG_REPORT_URL?: string;
  readonly VITE_ASSET_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
