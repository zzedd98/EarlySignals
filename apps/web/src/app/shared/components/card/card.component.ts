import { Component } from '@angular/core';

@Component({
  selector: 'app-card',
  template: `
    <div class="card">
      <ng-content></ng-content>
    </div>
  `,
  styles: [
    `
      .card {
        background-color: var(--color-background-card);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-lg);
        padding: var(--spacing-xl);
        box-shadow: var(--shadow-sm);
        transition: box-shadow var(--transition-base);
      }

      .card:hover {
        box-shadow: var(--shadow-md);
      }
    `,
  ],
})
export class CardComponent {}
