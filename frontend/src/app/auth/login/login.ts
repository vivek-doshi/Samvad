// LoginComponent — handles user authentication UI
// Note 1: This is a standalone Angular component using Reactive Forms.
// Reactive Forms (from @angular/forms) define the form structure in TypeScript
// (not in the HTML template) and provide programmatic access to form state,
// values, and validation — making them ideal for complex validation logic.
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from '../../services/auth';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, CommonModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  // Note 2: fb.nonNullable.group() creates a form group where all field values
  // are non-nullable (never null, only their default values). This gives
  // better TypeScript type safety — no need for null checks when reading values.
  readonly loginForm = this.fb.nonNullable.group({
    // Note 3: Validators.required ensures the field is non-empty.
    // Validators.minLength(n) enforces minimum length. Both validators run on
    // every keystroke. The form's 'invalid' flag is true until all validators pass.
    username: ['', [Validators.required, Validators.minLength(3)]],
    password: ['', [Validators.required, Validators.minLength(6)]],
  });

  // Note 4: These three signals manage the UI state:
  // - isLoading    : disables the submit button while the API call is in flight
  // - errorMessage : displays the error message below the form
  // - showPassword : toggles the password field between text and password type
  readonly isLoading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly showPassword = signal(false);

  onSubmit(): void {
    // Note 5: loginForm.invalid returns true if ANY validator fails. We guard
    // here to prevent submitting an invalid form — though the HTML submit button
    // should also be disabled when the form is invalid, this is a belt-and-braces
    // check that works even if the HTML is bypassed.
    if (this.loginForm.invalid || this.isLoading()) {
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set(null);

    this.auth
      .login(this.loginForm.getRawValue())
      // Note 6: finalize() is an RxJS operator that runs REGARDLESS of whether
      // the Observable completed successfully or errored. It is the RxJS equivalent
      // of a try/finally block. Here it stops the loading spinner unconditionally.
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: () => {
          this.router.navigate(['/chat']);
        },
        error: (error: unknown) => {
          const httpError = error as HttpErrorResponse;
          if (httpError.status === 401) {
            // Note 7: We show a generic "Invalid username or password" message
            // rather than specifying which was wrong. This prevents attackers
            // from using the error message to determine which usernames are valid.
            this.errorMessage.set('Invalid username or password');
            return;
          }
          this.errorMessage.set('Server error. Is Samvad running?');
        },
      });
  }

  togglePassword(): void {
    // Note 8: signal.update() takes a function that receives the current value
    // and returns the new value. It is equivalent to
    // this.showPassword.set(!this.showPassword()) but more idiomatic.
    this.showPassword.update((value) => !value);
  }

  get usernameControl() {
    // Note 9: These getters expose individual form controls to the template so
    // the HTML can check validation state (e.g. *ngIf="usernameControl?.errors?.['required']").
    // Using a getter avoids repeating 'loginForm.get("username")' in the template.
    return this.loginForm.get('username');
  }

  get passwordControl() {
    return this.loginForm.get('password');
  }
}

