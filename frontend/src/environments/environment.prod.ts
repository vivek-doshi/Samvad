// Production environment configuration
// Note 1: This file is used by the production build ('ng build --configuration production').
// Angular's build system replaces environment.ts with this file at build time.
// Only the values that differ from development need to change here.
export const environment = {
  production: true,
  // Note 2: apiBaseUrl is empty string in production because Nginx serves both
  // the Angular app AND proxies /api/* to the FastAPI backend on the SAME origin.
  // Using '' means all API calls use relative URLs (e.g. '/api/chat') which
  // automatically resolve to the correct host without hardcoding a domain name.
  apiBaseUrl: '',
  chatEndpoint: '/api/chat',
  authEndpoint: '/api/auth',
  sessionsEndpoint: '/api/sessions',
  uploadEndpoint: '/api/upload',
  healthEndpoint: '/api/health',
  sseTimeout: 120000,
  appName: 'Samvad',
  appVersion: '0.1.0',
};
