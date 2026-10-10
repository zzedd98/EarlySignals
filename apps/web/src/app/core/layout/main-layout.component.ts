import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-main-layout',
  template: `
    <div class="main-layout">
      <header class="header">
        <a routerLink="/dashboard" class="logo">
          <span class="logo-icon">⚡</span>
          <span class="logo-early">Early</span><span class="logo-signals">Signals</span>
        </a>
        <nav class="nav">
          <a routerLink="/dashboard" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">
            Dashboard
          </a>
          <a *ngIf="isAdmin" routerLink="/admin" routerLinkActive="active">
            Admin
          </a>
        </nav>
        <div class="user-menu">
          <span class="user-email">{{ userEmail }}</span>
          <button type="button" class="logout-btn" (click)="logout()">
            Déconnexion →
          </button>
        </div>
      </header>
      <main class="content">
        <router-outlet></router-outlet>
      </main>
    </div>
  `,
  styles: [
    `
      .main-layout {
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        background-color: var(--color-background);
      }

      .header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--spacing-md) var(--spacing-xl);
        background: var(--color-navy);
        background: linear-gradient(180deg, var(--color-navy) 0%, var(--color-navy-light) 100%);
        flex-wrap: wrap;
        gap: var(--spacing-md);
        box-shadow: var(--shadow-md);
      }

      .logo {
        display: inline-flex;
        align-items: center;
        gap: var(--spacing-xs);
        font-size: var(--font-size-xl);
        font-weight: var(--font-weight-bold);
        text-decoration: none;
      }

      .logo-icon {
        color: var(--color-accent);
        font-size: 1.25em;
      }

      .logo-early {
        color: var(--color-text-on-dark);
      }

      .logo-signals {
        color: var(--color-accent);
      }

      .logo:hover .logo-early,
      .logo:hover .logo-signals {
        opacity: 0.95;
      }

      .nav {
        display: flex;
        gap: var(--spacing-lg);
        align-items: center;
      }

      .nav a {
        font-size: var(--font-size-base);
        font-weight: var(--font-weight-medium);
        color: var(--color-text-on-dark-secondary);
        text-decoration: none;
        padding: var(--spacing-sm) var(--spacing-md);
        border-radius: var(--radius-lg);
      }

      .nav a:hover {
        color: var(--color-text-on-dark);
        background-color: rgba(255, 255, 255, 0.1);
      }

      .nav a.active {
        color: var(--color-text-on-dark);
        background-color: rgba(255, 255, 255, 0.15);
      }

      .user-menu {
        display: flex;
        align-items: center;
        gap: var(--spacing-md);
      }

      .user-email {
        font-size: var(--font-size-sm);
        color: var(--color-text-on-dark-secondary);
      }

      .logout-btn {
        font-family: var(--font-family);
        font-size: var(--font-size-sm);
        font-weight: var(--font-weight-medium);
        padding: var(--spacing-sm) var(--spacing-md);
        border: 1px solid rgba(255, 255, 255, 0.5);
        border-radius: var(--radius-lg);
        background: transparent;
        color: var(--color-text-on-dark);
        cursor: pointer;
      }

      .logout-btn:hover {
        background-color: rgba(255, 255, 255, 0.1);
        border-color: var(--color-text-on-dark);
      }

      .content {
        flex: 1;
        overflow: auto;
      }
    `,
  ],
})
export class MainLayoutComponent {
  isAdmin = false;
  userEmail = '';

  constructor(
    private auth: AuthService,
    private router: Router
  ) {
    const user = this.auth.getCurrentUserValue();
    if (user) {
      this.userEmail = user.email;
      this.isAdmin = user.role === 'admin';
    }
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/auth/login']);
  }
}
