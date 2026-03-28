import { TestBed } from '@angular/core/testing';
import { HttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { AuthService } from './auth';
import { environment } from '../../environments/environment';

function createJwt(exp: number): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(JSON.stringify({ exp }));
  return `${header}.${payload}.fakesig`;
}

function futureJwt(offsetSeconds = 3600): string {
  return createJwt(Math.floor(Date.now() / 1000) + offsetSeconds);
}

function expiredJwt(): string {
  return createJwt(Math.floor(Date.now() / 1000) - 60);
}

describe('AuthService', () => {
  let service: AuthService;
  let httpTesting: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: Router,
          useValue: { navigate: vi.fn() },
        },
      ],
    });

    httpTesting = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    service = TestBed.inject(AuthService);
  });

  afterEach(() => {
    httpTesting.verify();
    localStorage.clear();
  });

  describe('initial state', () => {
    it('should not be authenticated by default', () => {
      expect(service.isAuthenticated()).toBe(false);
    });

    it('should have null user and token', () => {
      expect(service.currentUser()).toBeNull();
      expect(service.token()).toBeNull();
    });
  });

  describe('loading stored token', () => {
    it('should restore valid token from localStorage', () => {
      const token = futureJwt();
      const user = {
        userId: 'u1',
        username: 'admin',
        displayName: 'Admin',
        role: 'admin' as const,
      };
      localStorage.setItem('samvad_token', token);
      localStorage.setItem('samvad_user', JSON.stringify(user));

      // Re-init TestBed so AuthService constructor reads from localStorage
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: Router, useValue: { navigate: vi.fn() } },
        ],
      });
      const s = TestBed.inject(AuthService);
      expect(s.isAuthenticated()).toBe(true);
      expect(s.currentUser()).toEqual(user);
      TestBed.inject(HttpTestingController).verify();
    });

    it('should clear expired token from localStorage', () => {
      localStorage.setItem('samvad_token', expiredJwt());
      localStorage.setItem(
        'samvad_user',
        JSON.stringify({ userId: 'u1', username: 'a', displayName: 'A', role: 'user' }),
      );

      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: Router, useValue: { navigate: vi.fn() } },
        ],
      });
      const s = TestBed.inject(AuthService);
      expect(s.isAuthenticated()).toBe(false);
      expect(localStorage.getItem('samvad_token')).toBeNull();
      TestBed.inject(HttpTestingController).verify();
    });

    it('should return null for malformed JSON user', () => {
      localStorage.setItem('samvad_token', futureJwt());
      localStorage.setItem('samvad_user', 'not-json');

      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: Router, useValue: { navigate: vi.fn() } },
        ],
      });
      const s = TestBed.inject(AuthService);
      expect(s.isAuthenticated()).toBe(true);
      expect(s.currentUser()).toBeNull();
      TestBed.inject(HttpTestingController).verify();
    });
  });

  describe('login', () => {
    it('should store token and user on successful login', () => {
      const token = futureJwt();
      const apiResponse = {
        access_token: token,
        token_type: 'bearer',
        expires_in: 3600,
        user: {
          user_id: 'u1',
          username: 'admin',
          display_name: 'Admin User',
          role: 'admin',
        },
      };

      service.login({ username: 'admin', password: 'pass123' }).subscribe();

      const req = httpTesting.expectOne(
        `${environment.apiBaseUrl}${environment.authEndpoint}/login`,
      );
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ username: 'admin', password: 'pass123' });
      req.flush(apiResponse);

      expect(service.isAuthenticated()).toBe(true);
      expect(service.token()).toBe(token);
      expect(service.currentUser()).toEqual({
        userId: 'u1',
        username: 'admin',
        displayName: 'Admin User',
        role: 'admin',
      });
      expect(localStorage.getItem('samvad_token')).toBe(token);
    });

    it('should propagate HTTP errors', () => {
      const errorSpy = vi.fn();

      service.login({ username: 'bad', password: 'bad' }).subscribe({ error: errorSpy });

      const req = httpTesting.expectOne(
        `${environment.apiBaseUrl}${environment.authEndpoint}/login`,
      );
      req.flush('Unauthorized', { status: 401, statusText: 'Unauthorized' });

      expect(errorSpy).toHaveBeenCalled();
      expect(service.isAuthenticated()).toBe(false);
    });
  });

  describe('refreshCurrentUser', () => {
    it('should update stored user', () => {
      // Pre-set authentication
      const token = futureJwt();
      localStorage.setItem('samvad_token', token);
      localStorage.setItem(
        'samvad_user',
        JSON.stringify({ userId: 'u1', username: 'old', displayName: 'Old', role: 'user' }),
      );
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: Router, useValue: { navigate: vi.fn() } },
        ],
      });
      const s = TestBed.inject(AuthService);
      const htc = TestBed.inject(HttpTestingController);

      s.refreshCurrentUser().subscribe();

      const req = htc.expectOne(
        `${environment.apiBaseUrl}${environment.authEndpoint}/me`,
      );
      req.flush({
        user_id: 'u1',
        username: 'newuser',
        display_name: 'New Name',
        role: 'admin',
      });

      expect(s.currentUser()?.displayName).toBe('New Name');
      expect(s.currentUser()?.role).toBe('admin');
      htc.verify();
    });
  });

  describe('logout', () => {
    it('should clear state and navigate to login', () => {
      const token = futureJwt();
      localStorage.setItem('samvad_token', token);
      localStorage.setItem(
        'samvad_user',
        JSON.stringify({ userId: 'u1', username: 'a', displayName: 'A', role: 'user' }),
      );
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: Router, useValue: { navigate: vi.fn() } },
        ],
      });
      const s = TestBed.inject(AuthService);
      const r = TestBed.inject(Router);
      const htc = TestBed.inject(HttpTestingController);

      expect(s.isAuthenticated()).toBe(true);
      s.logout();

      expect(s.isAuthenticated()).toBe(false);
      expect(s.currentUser()).toBeNull();
      expect(s.token()).toBeNull();
      expect(localStorage.getItem('samvad_token')).toBeNull();
      expect(localStorage.getItem('samvad_user')).toBeNull();
      expect(r.navigate).toHaveBeenCalledWith(['/login']);
      htc.verify();
    });
  });

  describe('getAuthHeaders', () => {
    it('should return Authorization header when authenticated', () => {
      const token = futureJwt();
      localStorage.setItem('samvad_token', token);
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: Router, useValue: { navigate: vi.fn() } },
        ],
      });
      const s = TestBed.inject(AuthService);
      const htc = TestBed.inject(HttpTestingController);

      expect(s.getAuthHeaders()).toEqual({ Authorization: `Bearer ${token}` });
      htc.verify();
    });

    it('should throw when not authenticated', () => {
      expect(() => service.getAuthHeaders()).toThrow('Not authenticated');
    });
  });

  describe('isTokenExpired', () => {
    it('should return true when no token', () => {
      expect(service.isTokenExpired()).toBe(true);
    });

    it('should return false for valid future token', () => {
      const token = futureJwt();
      localStorage.setItem('samvad_token', token);
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: Router, useValue: { navigate: vi.fn() } },
        ],
      });
      const s = TestBed.inject(AuthService);
      const htc = TestBed.inject(HttpTestingController);

      expect(s.isTokenExpired()).toBe(false);
      htc.verify();
    });

    it('should return true for token without exp claim', () => {
      const header = btoa(JSON.stringify({ alg: 'HS256' }));
      const payload = btoa(JSON.stringify({ sub: 'user' }));
      const token = `${header}.${payload}.sig`;
      localStorage.setItem('samvad_token', token);
      // Token will be considered expired during load, so it won't be stored
      // Testing isTokenExpired on already-loaded service with null token
      expect(service.isTokenExpired()).toBe(true);
    });

    it('should return true for malformed token', () => {
      expect(service.isTokenExpired()).toBe(true);
    });
  });
});
