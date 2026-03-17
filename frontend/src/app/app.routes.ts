import { inject } from '@angular/core';
import { CanActivateFn, Router, Routes } from '@angular/router';
import { LoginComponent } from './auth/login/login';
import { ChatComponent } from './chat/chat';
import { AuthService } from './services/auth';

export const authGuard: CanActivateFn = () => {
	const authService = inject(AuthService);
	const router = inject(Router);

	if (authService.isAuthenticated()) {
		if (authService.isTokenExpired()) {
			authService.logout();
			return router.createUrlTree(['/login']);
		}
		return true;
	}

	return router.createUrlTree(['/login']);
};

export const routes: Routes = [
	{ path: '', redirectTo: '/chat', pathMatch: 'full' },
	{ path: 'login', component: LoginComponent },
	{ path: 'chat', component: ChatComponent, canActivate: [authGuard] },
	{ path: '**', redirectTo: '/chat' },
];
