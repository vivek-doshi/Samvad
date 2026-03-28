import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { LoginComponent } from './login';
import { AuthService } from '../../services/auth';

describe('LoginComponent', () => {
  let component: LoginComponent;
  let fixture: ComponentFixture<LoginComponent>;
  let authService: { login: ReturnType<typeof vi.fn> };
  let router: { navigate: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    authService = { login: vi.fn() };
    router = { navigate: vi.fn() };

    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: authService },
        { provide: Router, useValue: router },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('form validation', () => {
    it('should have invalid form by default', () => {
      expect(component.loginForm.valid).toBe(false);
    });

    it('should require username minimum 3 characters', () => {
      component.loginForm.patchValue({ username: 'ab', password: '123456' });
      expect(component.loginForm.valid).toBe(false);

      component.loginForm.patchValue({ username: 'abc' });
      expect(component.loginForm.valid).toBe(true);
    });

    it('should require password minimum 6 characters', () => {
      component.loginForm.patchValue({ username: 'admin', password: '12345' });
      expect(component.loginForm.valid).toBe(false);

      component.loginForm.patchValue({ password: '123456' });
      expect(component.loginForm.valid).toBe(true);
    });

    it('should require both fields', () => {
      component.loginForm.patchValue({ username: '', password: '' });
      expect(component.loginForm.valid).toBe(false);
    });
  });

  describe('onSubmit', () => {
    beforeEach(() => {
      component.loginForm.patchValue({ username: 'admin', password: 'password123' });
    });

    it('should not submit when form is invalid', () => {
      component.loginForm.patchValue({ username: '', password: '' });
      component.onSubmit();
      expect(authService.login).not.toHaveBeenCalled();
    });

    it('should not submit when already loading', () => {
      component.isLoading.set(true);
      component.onSubmit();
      expect(authService.login).not.toHaveBeenCalled();
    });

    it('should navigate to /chat on success', () => {
      authService.login.mockReturnValue(of(void 0));
      component.onSubmit();

      expect(authService.login).toHaveBeenCalledWith({
        username: 'admin',
        password: 'password123',
      });
      expect(router.navigate).toHaveBeenCalledWith(['/chat']);
    });

    it('should set loading state during request', () => {
      authService.login.mockReturnValue(of(void 0));
      expect(component.isLoading()).toBe(false);

      component.onSubmit();

      // After completion, isLoading should be false due to finalize
      expect(component.isLoading()).toBe(false);
    });

    it('should show error for 401 response', () => {
      authService.login.mockReturnValue(
        throwError(() => ({ status: 401 })),
      );
      component.onSubmit();

      expect(component.errorMessage()).toBe('Invalid username or password');
    });

    it('should show server error for other HTTP errors', () => {
      authService.login.mockReturnValue(
        throwError(() => ({ status: 500 })),
      );
      component.onSubmit();

      expect(component.errorMessage()).toBe('Server error. Is Samvad running?');
    });

    it('should clear previous error on new submit', () => {
      component.errorMessage.set('Previous error');
      authService.login.mockReturnValue(of(void 0));
      component.onSubmit();

      expect(component.errorMessage()).toBeNull();
    });
  });

  describe('togglePassword', () => {
    it('should toggle showPassword signal', () => {
      expect(component.showPassword()).toBe(false);
      component.togglePassword();
      expect(component.showPassword()).toBe(true);
      component.togglePassword();
      expect(component.showPassword()).toBe(false);
    });
  });

  describe('getters', () => {
    it('should return username control', () => {
      expect(component.usernameControl).toBe(component.loginForm.get('username'));
    });

    it('should return password control', () => {
      expect(component.passwordControl).toBe(component.loginForm.get('password'));
    });
  });
});
