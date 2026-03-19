// AuthService — manages JWT authentication state
// Note 1: @Injectable({ providedIn: 'root' }) makes this service a singleton
// shared across the entire application. Angular creates ONE instance and injects
// the same instance wherever AuthService is requested. This is how the login
// state is shared between LoginComponent, ChatComponent, SidebarComponent, etc.
import { HttpClient } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { Router } from '@angular/router';
import { map, Observable, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { LoginRequest, User } from '../models/user.model';

// Note 2: These internal interfaces define the shape of the backend API response.
// They use snake_case (e.g. user_id) to match the Python/JSON API convention.
// The public User model uses camelCase (userId) following TypeScript conventions.
// The mapping happens inside the login() method's tap() operator.
interface LoginApiUser {
  user_id: string;
  username: string;
  display_name: string;
  role: 'admin' | 'user';
}

interface LoginApiResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: LoginApiUser;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  // Note 3: Using unique localStorage keys ('samvad_token', 'samvad_user') avoids
  // collisions if other apps are running on the same origin. localStorage persists
  // across browser sessions (unlike sessionStorage which clears on tab close).
  private readonly TOKEN_KEY = 'samvad_token';
  private readonly USER_KEY = 'samvad_user';

  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  // Note 4: signal() is Angular 17+'s reactive primitive (like useState in React).
  // A signal holds a value and notifies all consumers when it changes.
  // computed() creates a derived signal that recalculates when its dependencies change.
  // Here, 'isAuthenticated' auto-updates whenever '_token' changes.
  private readonly _token = signal<string | null>(this.loadStoredToken());
  private readonly _user = signal<User | null>(this.loadStoredUser());

  readonly isAuthenticated = computed(() => this._token() !== null);
  readonly currentUser = computed(() => this._user());
  readonly token = computed(() => this._token());

  login(request: LoginRequest): Observable<void> {
    const url = `${environment.apiBaseUrl}${environment.authEndpoint}/login`;
    const body = {
      username: request.username,
      password: request.password,
    };

    // Note 5: http.post<LoginApiResponse>() returns an Observable that emits ONE
    // value when the HTTP response arrives, then completes. RxJS operators are
    // chained with .pipe():
    // - tap()  : side effects (store token) without modifying the emitted value
    // - map()  : transform the value (LoginApiResponse -> void)
    return this.http.post<LoginApiResponse>(url, body).pipe(
      tap((response) => {
        const user: User = {
          userId: response.user.user_id,
          username: response.user.username,
          displayName: response.user.display_name,
          role: response.user.role,
        };
        // Note 6: We store BOTH the token AND the user object in localStorage.
        // The token is used for API calls; the user object powers the UI (display
        // name, role badge) without requiring a separate /me API call on every page load.
        localStorage.setItem(this.TOKEN_KEY, response.access_token);
        localStorage.setItem(this.USER_KEY, JSON.stringify(user));
        this._token.set(response.access_token);
        this._user.set(user);
      }),
      // Note 7: map(() => void 0) transforms the response to 'void' (undefined).
      // Callers of login() subscribe to know "did it succeed?" but don't need
      // the raw API response — the side effects in tap() handle state updates.
      map(() => void 0),
    );
  }

  refreshCurrentUser(): Observable<void> {
    const url = `${environment.apiBaseUrl}${environment.authEndpoint}/me`;
    return this.http.get<LoginApiUser>(url, { headers: this.getAuthHeaders() }).pipe(
      tap((response) => {
        const user: User = {
          userId: response.user_id,
          username: response.username,
          displayName: response.display_name,
          role: response.role,
        };
        localStorage.setItem(this.USER_KEY, JSON.stringify(user));
        this._user.set(user);
      }),
      map(() => void 0),
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
    // Note 8: Bearer token authentication: the 'Authorization' header format is
    // 'Bearer <token>'. The backend's HTTPBearer security scheme strips "Bearer "
    // and validates the raw JWT string. This header is required on every protected
    // API call.
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
      // Note 9: A JWT has three Base64URL-encoded parts separated by '.':
      // header.payload.signature
      // parts[1] is the payload containing claims like 'exp' (expiry).
      // atob() decodes Base64 to a string, then JSON.parse() gives the claims object.
      // We check 'exp' (a Unix timestamp in SECONDS) against the current time.
      const parts = token.split('.');
      if (parts.length < 2) {
        return true;
      }

      const payload = JSON.parse(atob(parts[1])) as { exp?: number };
      const exp = payload.exp;
      if (typeof exp !== 'number') {
        return true;
      }

      // Note 10: Date.now() returns milliseconds; JWT 'exp' is in seconds.
      // We divide by 1000 and floor to compare at second granularity.
      // '<=' (not '<') catches tokens that expire at exactly this moment.
      return exp <= Math.floor(Date.now() / 1000);
    } catch {
      return true;
    }
  }
}
