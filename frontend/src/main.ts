// Angular 21 application bootstrap entry point
// Note 1: bootstrapApplication() is Angular's standalone API for starting
// the app without NgModule. It takes the root component (AppComponent) and a
// configuration object. This is the "standalone" pattern introduced in Angular 14
// and is the recommended approach in Angular 17+/21 — no AppModule needed.
import { bootstrapApplication } from '@angular/platform-browser';
import {
  provideHttpClient,
  // Note 2: withInterceptorsFromDi() enables HTTP interceptors registered via
  // dependency injection. Interceptors are used to automatically attach the
  // Authorization header to every outgoing request, handle 401 responses, etc.
  withInterceptorsFromDi,
} from '@angular/common/http';
import {
  provideRouter,
  // Note 3: withComponentInputBinding() allows route parameters to be bound
  // directly as @Input() properties on routed components — eliminating the need
  // to inject ActivatedRoute manually just to read a route parameter.
  withComponentInputBinding,
} from '@angular/router';
import { AppComponent } from './app/app';
import { routes } from './app/app.routes';

// Note 4: The providers array here is the application-level DI (Dependency
// Injection) configuration. Anything listed here is available throughout the
// entire application. Route-level providers are also possible for lazy loading.
bootstrapApplication(AppComponent, {
  providers: [
    // Note 5: provideRouter(routes, ...) registers the route table defined in
    // app.routes.ts. Angular's router monitors the browser URL and renders
    // the matching component into <router-outlet> inside AppComponent.
    provideRouter(routes, withComponentInputBinding()),
    // Note 6: provideHttpClient() makes Angular's HttpClient available for
    // injection across all services. It is the primary HTTP abstraction in Angular
    // and supports interceptors, typed responses, and RxJS integration.
    provideHttpClient(withInterceptorsFromDi()),
  ],
}).catch((err) => console.error(err));
// Note 7: .catch() handles critical bootstrap failures (e.g. missing component,
// DI configuration error). In production, you would send this to an error
// monitoring service (e.g. Sentry) rather than just logging to the console.
