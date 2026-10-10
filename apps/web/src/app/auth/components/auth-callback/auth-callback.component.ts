import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-auth-callback',
  template: `
    <div class="callback-container">
      <p *ngIf="!error">{{ message }}</p>
      <p *ngIf="error" class="error">{{ error }}</p>
    </div>
  `,
  styles: [
    `
      .callback-container {
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: var(--spacing-xl);
        background: linear-gradient(
          180deg,
          var(--color-navy) 0%,
          var(--color-navy-light) 50%,
          var(--color-navy-lighter) 100%
        );
        color: var(--color-text-on-dark);
      }

      .error {
        color: #fca5a5;
      }
    `,
  ],
})
export class AuthCallbackComponent implements OnInit {
  message = 'Connexion en cours…';
  error = '';

  constructor(
    private auth: AuthService,
    private router: Router,
    private route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    const hash = window.location.hash?.replace(/^#/, '') || '';
    const params = new URLSearchParams(hash);
    const token = params.get('token');

    if (!token) {
      this.error = 'Token manquant. Redirection vers la connexion.';
      setTimeout(() => this.router.navigate(['/auth/login']), 2000);
      return;
    }

    localStorage.setItem('access_token', token);

    this.auth.getCurrentUser().subscribe({
      next: (user) => {
        if (user.role === 'admin') {
          this.router.navigate(['/admin/domains']);
        } else {
          this.router.navigate(['/onboarding']);
        }
      },
      error: () => {
        this.error = 'Session invalide. Redirection vers la connexion.';
        localStorage.removeItem('access_token');
        setTimeout(() => this.router.navigate(['/auth/login']), 2000);
      },
    });
  }
}
