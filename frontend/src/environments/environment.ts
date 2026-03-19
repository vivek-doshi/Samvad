// Development environment configuration
// Note 1: Angular's environment files allow different settings for different
// build targets. This file is used during 'ng serve' (development mode).
// The production version (environment.prod.ts) is used when 'ng build --configuration production'
// is run. The swap happens automatically via angular.json fileReplacements config.
//
// Note 2: To add a new environment variable, add it to BOTH files (environment.ts
// and environment.prod.ts). If only added to one, the app will have a different
// set of properties in dev vs production — causing TypeScript errors at build time.
export const environment = {
  // Note 3: production: false enables Angular's development mode, which adds
  // extra runtime checks and warnings to help catch common mistakes. In production
  // builds, development mode is disabled for better performance.
  production: false,
  // Note 4: In development, apiBaseUrl points to localhost:8000 where the FastAPI
  // dev server runs. In production (environment.prod.ts), this is '' (empty string)
  // because the Angular app and API are served from the same origin via Nginx proxy.
  apiBaseUrl: 'http://localhost:8000',
  chatEndpoint: '/api/chat',
  authEndpoint: '/api/auth',
  sessionsEndpoint: '/api/sessions',
  uploadEndpoint: '/api/upload',
  healthEndpoint: '/api/health',
  // Note 5: sseTimeout = 120000ms = 2 minutes. If the LLM doesn't respond within
  // 2 minutes, the fetch is aborted. Should match the timeout_seconds in samvad.yaml.
  sseTimeout: 120000,
  appName: 'Samvad',
  appVersion: '0.1.0',
};
