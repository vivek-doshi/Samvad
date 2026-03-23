// Root application component — the single component that is bootstrapped in main.ts
// Note 1: AppComponent is intentionally minimal. Its only job is to host the
// <router-outlet> which acts as a placeholder where Angular inserts the component
// that matches the current URL. All real UI is in child components (LoginComponent,
// ChatComponent) loaded by the router.
import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
// Note 2: RouterOutlet is the Angular directive that renders the active route's
// component. When the URL changes to '/chat', Angular replaces the outlet's
// content with ChatComponent; '/login' renders LoginComponent.

@Component({
  selector: 'app-root',
  // Note 3: 'standalone: true' means this component does not belong to any
  // NgModule. Standalone components manage their own imports directly in the
  // @Component decorator, which makes them self-contained and easier to understand.
  standalone: true,
  imports: [RouterOutlet],
  // Note 4: The template is a single <router-outlet /> element. Angular's router
  // replaces this element with the appropriate page component based on the URL.
  template: '<router-outlet />',
  // Note 5: ':host { display: block; height: 100vh; }' makes the root component
  // fill the full viewport height. ':host' targets the <app-root> custom element
  // itself in the DOM. This is needed because custom elements are inline by default.
  styles: [':host { display: block; height: 100vh; }'],
})
export class AppComponent {}

