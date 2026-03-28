import { TestBed } from '@angular/core/testing';
import { Router, UrlTree } from '@angular/router';
import { authGuard } from './app.routes';
import { AuthService } from './services/auth';

describe('authGuard', () => {
  let authService: {
    isAuthenticated: ReturnType<typeof vi.fn>;
    isTokenExpired: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn>;
  };
  let router: {
    createUrlTree: ReturnType<typeof vi.fn>;
    navigate: ReturnType<typeof vi.fn>;
  };

  const mockUrlTree = {} as UrlTree;

  beforeEach(() => {
    authService = {
      isAuthenticated: vi.fn(),
      isTokenExpired: vi.fn(),
      logout: vi.fn(),
    };
    router = {
      createUrlTree: vi.fn().mockReturnValue(mockUrlTree),
      navigate: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: authService },
        { provide: Router, useValue: router },
      ],
    });
  });

  function runGuard(): boolean | UrlTree {
    return TestBed.runInInjectionContext(() =>
      authGuard({} as any, {} as any),
    ) as boolean | UrlTree;
  }

  it('should return true when authenticated and token not expired', () => {
    authService.isAuthenticated.mockReturnValue(true);
    authService.isTokenExpired.mockReturnValue(false);

    expect(runGuard()).toBe(true);
  });

  it('should logout and redirect when token is expired', () => {
    authService.isAuthenticated.mockReturnValue(true);
    authService.isTokenExpired.mockReturnValue(true);

    const result = runGuard();

    expect(authService.logout).toHaveBeenCalled();
    expect(router.createUrlTree).toHaveBeenCalledWith(['/login']);
    expect(result).toBe(mockUrlTree);
  });

  it('should redirect to login when not authenticated', () => {
    authService.isAuthenticated.mockReturnValue(false);

    const result = runGuard();

    expect(router.createUrlTree).toHaveBeenCalledWith(['/login']);
    expect(result).toBe(mockUrlTree);
  });
});
