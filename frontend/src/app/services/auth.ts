import { HttpClient } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { LoginRequest, LoginResponse, User } from '../models/user.model';

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private readonly TOKEN_KEY = 'samvad_token';
  private readonly USER_KEY = 'samvad_user';

  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  private readonly _token = signal<string | null>(this.loadStoredToken());
  private readonly _user = signal<User | null>(this.loadStoredUser());

  readonly isAuthenticated = computed(() => this._token() !== null);
  readonly currentUser = computed(() => this._user());
  readonly token = computed(() => this._token());

  login(request: LoginRequest): Observable<LoginResponse> {
    const url = `${environment.apiBaseUrl}${environment.authEndpoint}/login`;

    return this.http.post<LoginResponse>(url, request).pipe(
      tap((response) => {
        this._token.set(response.accessToken);
        this._user.set(response.user);
        localStorage.setItem(this.TOKEN_KEY, response.accessToken);
        localStorage.setItem(this.USER_KEY, JSON.stringify(response.user));
      }),
    );
  }

  logout(): void {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
    this._token.set(null);
    this._user.set(null);
    this.router.navigate(['/login']);
  }

  getAuthHeaders(): { Authorization: string } {
    const token = this._token();
    if (!token) {
      throw new Error('Not authenticated');
    }
    return { Authorization: `Bearer ${token}` };
  }

  isTokenExpired(): boolean {
    const token = this._token();
    if (!token) {
      return true;
    }
    return this.isTokenExpiredFromValue(token);
  }

  private loadStoredToken(): string | null {
    const token = localStorage.getItem(this.TOKEN_KEY);
    if (!token) {
      return null;
    }

    if (this.isTokenExpiredFromValue(token)) {
      localStorage.removeItem(this.TOKEN_KEY);
      localStorage.removeItem(this.USER_KEY);
      return null;
    }

    return token;
  }

  private loadStoredUser(): User | null {
    const raw = localStorage.getItem(this.USER_KEY);
    if (!raw) {
      return null;
    }

    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  }

  private isTokenExpiredFromValue(token: string): boolean {
    try {
      const parts = token.split('.');
      if (parts.length < 2) {
        return true;
      }

      const payload = JSON.parse(atob(parts[1])) as { exp?: number };
      const exp = payload.exp;
      if (typeof exp !== 'number') {
        return true;
      }

      return exp <= Math.floor(Date.now() / 1000);
    } catch {
      return true;
    }
  }
}
