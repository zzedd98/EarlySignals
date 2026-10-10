import { Component } from '@angular/core';

@Component({
  selector: 'app-dashboard',
  template: `
    <div class="dashboard-container">
      <div class="dashboard-header">
        <h1>Dashboard</h1>
        <p>Vos opportunités business</p>
      </div>
      <app-opportunity-list></app-opportunity-list>
    </div>
  `,
  styles: [
    `
      .dashboard-container {
        max-width: 1200px;
        margin: 0 auto;
        padding: var(--spacing-xl);
      }

      .dashboard-header {
        margin-bottom: var(--spacing-xl);
      }

      .dashboard-header h1 {
        font-size: var(--font-size-3xl);
        margin-bottom: var(--spacing-sm);
      }

      .dashboard-header p {
        color: var(--color-text-light);
        font-size: var(--font-size-base);
      }
    `,
  ],
})
export class DashboardComponent {}
