import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-badge',
  template: `
    <span [class]="badgeClass">
      <ng-content></ng-content>
    </span>
  `,
  styles: [
    `
      span {
        display: inline-flex;
        align-items: center;
        padding: var(--spacing-xs) var(--spacing-sm);
        border-radius: var(--radius-pill);
        font-size: var(--font-size-xs);
        font-weight: var(--font-weight-semibold);
      }

      .default {
        background-color: var(--color-border-light);
        color: var(--color-text);
      }

      .success {
        background-color: var(--color-accent);
        color: var(--color-text-on-dark);
      }

      .warning {
        background-color: #fef3c7;
        color: var(--color-warning);
      }

      .error {
        background-color: #fee2e2;
        color: var(--color-error);
      }

      .info {
        background-color: #dbeafe;
        color: var(--color-info);
      }
    `,
  ],
})
export class BadgeComponent {
  @Input() variant: 'default' | 'success' | 'error' | 'warning' | 'info' =
    'default';

  get badgeClass(): string {
    return this.variant;
  }
}
