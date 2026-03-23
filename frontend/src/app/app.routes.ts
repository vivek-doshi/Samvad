// Angular application route configuration
// Note 1: 'inject()' is Angular's functional dependency injection API. Unlike
// constructor injection (used in classes), inject() works in standalone functions
// like route guards, which is the preferred pattern in Angular 14+.
import { inject } from '@angular/core';
import { CanActivateFn, Router, Routes } from '@angular/router';
import { LoginComponent } from './auth/login/login';
import { ChatComponent } from './chat/chat';
import { AuthService } from './services/auth';

// Note 2: CanActivateFn is the type for a functional route guard. It runs
// BEFORE a route is activated (navigated to) and can either allow navigation
// (return true), redirect elsewhere (return UrlTree), or block (return false).
export const authGuard: CanActivateFn = () => {
	const authService = inject(AuthService);
	const router = inject(Router);

	if (authService.isAuthenticated()) {
		// Note 3: Even if a token exists in localStorage, we check whether it
		// has expired before allowing access. JWT tokens have an 'exp' field
		// (expiry timestamp) that is decoded client-side to avoid a round-trip
		// to the backend. If expired, the user is redirected to /login.
		if (authService.isTokenExpired()) {
			authService.logout();
			return router.createUrlTree(['/login']);
		}
		return true;
	}

	// Note 4: router.createUrlTree() creates a navigation command that the guard
	// returns. Returning a UrlTree is the modern Angular way to redirect — it is
	// type-safe and supports relative paths, unlike the older 'router.navigate()'.
	return router.createUrlTree(['/login']);
};

// Note 5: The Routes array is processed top-to-bottom by Angular's router.
// '**' is a wildcard that matches any URL not matched by earlier routes.
// It must always be LAST because any route after it would never be reached.
export const routes: Routes = [
	// Note 6: redirectTo with pathMatch:'full' redirects the exact empty path ('')
	// to '/chat'. Without pathMatch:'full', '' would also match '/chat', '/login' etc.
	// because '' is a prefix of every URL — causing unintended redirects.
	{ path: '', redirectTo: '/chat', pathMatch: 'full' },
	{ path: 'login', component: LoginComponent },
	// Note 7: canActivate: [authGuard] registers the route guard for /chat.
	// If authGuard returns false or a redirect URL, ChatComponent never loads.
	// This is the "protect route" pattern that prevents unauthenticated access.
	{ path: 'chat', component: ChatComponent, canActivate: [authGuard] },
	{ path: '**', redirectTo: '/chat' },
];
