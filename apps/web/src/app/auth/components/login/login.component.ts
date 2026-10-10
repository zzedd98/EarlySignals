import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { environment } from '../../../../environments/environment';
import { filter, take, switchMap } from 'rxjs/operators';

@Component({
  selector: 'app-login',
  template: `
    <div class="auth-container">
      <div class="auth-hero">
        <span class="auth-pill">⚡ Accédez à votre espace</span>
        <div class="auth-card-wrapper">
          <app-card>
            <div class="auth-header">
              <h1><span class="logo-early">Early</span><span class="logo-signals">Signals</span></h1>
              <p class="subtitle">Connectez-vous à votre compte</p>
            </div>

            <form [formGroup]="loginForm" (ngSubmit)="onSubmit()" class="auth-form">
              <app-input
                id="email"
                type="email"
                label="Email"
                placeholder="votre@email.com"
                formControlName="email"
              ></app-input>

              <app-input
                id="password"
                type="password"
                label="Mot de passe"
                placeholder="••••••••"
                formControlName="password"
              ></app-input>

              <div *ngIf="error" class="error-message">{{ error }}</div>

              <app-button
                type="submit"
                variant="primary"
                [disabled]="loginForm.invalid || loading"
                [fullWidth]="true"
              >
                {{ loading ? 'Connexion...' : 'Se connecter →' }}
              </app-button>

              <div class="auth-divider">ou</div>

              <app-button
                type="button"
                variant="secondary"
                [fullWidth]="true"
                (click)="loginWithGoogle()"
              >
                Se connecter avec Google
              </app-button>
            </form>

            <div class="auth-footer">
              <p>
                Pas encore de compte ?
                <a routerLink="/auth/register" class="accent-link">Créer un compte →</a>
              </p>
            </div>
          </app-card>
        </div>
      </div>
    </div>
  `,
  styles: [
    `
      .auth-container {
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: var(--spacing-xl);
        background: linear-gradient(180deg, var(--color-navy) 0%, var(--color-navy-light) 50%, var(--color-navy-lighter) 100%);
      }

      .auth-hero {
        text-align: center;
        width: 100%;
        max-width: 420px;
      }

      .auth-pill {
        display: inline-block;
        padding: var(--spacing-xs) var(--spacing-md);
        margin-bottom: var(--spacing-lg);
        font-size: var(--font-size-sm);
        font-weight: var(--font-weight-medium);
        color: var(--color-text-on-dark-secondary);
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: var(--radius-pill);
      }

      .auth-card-wrapper {
        width: 100%;
      }

      app-card {
        width: 100%;
      }

      .auth-header {
        text-align: center;
        margin-bottom: var(--spacing-xl);
      }

      .auth-header h1 {
        font-size: var(--font-size-3xl);
        font-weight: var(--font-weight-bold);
        margin-bottom: var(--spacing-sm);
      }

      .logo-early { color: var(--color-text); }
      .logo-signals { color: var(--color-accent); }

      .subtitle {
        color: var(--color-text-light);
        font-size: var(--font-size-base);
      }

      .auth-form {
        display: flex;
        flex-direction: column;
        gap: var(--spacing-lg);
      }

      .auth-divider {
        text-align: center;
        font-size: var(--font-size-sm);
        color: var(--color-text-muted);
        margin: var(--spacing-sm) 0;
      }

      .error-message {
        padding: var(--spacing-sm);
        background-color: #fee2e2;
        color: var(--color-error);
        border-radius: var(--radius-md);
        font-size: var(--font-size-sm);
      }

      .auth-footer {
        margin-top: var(--spacing-xl);
        text-align: center;
        font-size: var(--font-size-sm);
        color: var(--color-text-light);
      }

      .accent-link {
        color: var(--color-accent);
        font-weight: var(--font-weight-semibold);
      }
      .accent-link:hover {
        color: var(--color-accent-light);
      }
    `,
  ],
})
export class LoginComponent implements OnInit {
  loginForm: FormGroup;
  loading = false;
  error = '';

  constructor(
    private fb: FormBuilder,
    private authService: AuthService,
    private router: Router,
    private route: ActivatedRoute
  ) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6)]],
    });
  }

  ngOnInit(): void {
    this.route.queryParams.subscribe((params) => {
      if (params['error'] === 'oauth_denied') {
        this.error = 'Connexion Google annulée.';
      }
    });
  }

  loginWithGoogle(): void {
    window.location.href = `${environment.apiUrl}/api/v1/auth/google`;
  }

  onSubmit(): void {
    if (this.loginForm.valid) {
      this.loading = true;
      this.error = '';

      this.authService.login(this.loginForm.value).pipe(
        switchMap(() => {
          // Wait for user to be loaded (filter out null values)
          return this.authService.currentUser$.pipe(
            filter((user) => user !== null),
            take(1)
          );
        })
      ).subscribe({
        next: (user) => {
          console.log('[LoginComponent] User loaded, navigating...', user);
          this.loading = false;
          // Navigate based on user role
          if (user && user.role === 'admin') {
            this.router.navigate(['/admin/domains']);
          } else {
            this.router.navigate(['/onboarding']);
          }
        },
        error: (err) => {
          console.error('[LoginComponent] Error during login flow:', err);
          this.loading = false;
          this.error =
            err.error?.detail || 'Erreur lors de la connexion. Veuillez réessayer.';
        },
      });
    }
  }
}
