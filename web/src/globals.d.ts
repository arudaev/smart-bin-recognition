/* Build-time constants, substituted by vite.config.ts `define`.
   Declared rather than imported so they cannot be read at runtime from a
   module that then has to exist in every build. */
declare const __APP_VERSION__: string;
declare const __BUILD_TIME__: string;

interface ImportMetaEnv {
  /** wss://…/stream – the inference service's streaming endpoint. */
  readonly VITE_DETECT_WS?: string;
  /** https://…/detect – one frame, one answer, for clients without a socket. */
  readonly VITE_DETECT_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv & {
    readonly DEV: boolean;
    readonly PROD: boolean;
    readonly MODE: string;
    readonly BASE_URL: string;
    readonly SSR: boolean;
  };
}

/** True on a Vercel PREVIEW build, false on production.
 *
 * Derived in vite.config.ts from `VERCEL_ENV`, not from a flag anybody sets by
 * hand, so the metrics overlay cannot reach the production deployment by
 * somebody forgetting to unset something. `check-bundle.mjs` asserts both
 * directions: present in a beta build, absent in a production one. */
declare const __BETA__: boolean;
