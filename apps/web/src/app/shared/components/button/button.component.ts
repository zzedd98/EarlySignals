import { Component, Input, Output, EventEmitter } from '@angular/core';

@Component({
  selector: 'app-button',
  template: `
    <button
      [type]="type"
      [disabled]="disabled"
      [class]="buttonClass"
      (click)="onClick.emit($event)"
    >
      <ng-content></ng-content>
    </button>
  `,
  styles: [
    `
      button {
        font-family: var(--font-family);
        font-size: var(--font-size-base);
        font-weight: var(--font-weight-semibold);
        padding: var(--spacing-sm) var(--spacing-lg);
        border-radius: var(--radius-lg);
        cursor: pointer;
        transition: all var(--transition-base);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--spacing-sm);
        border: none;
      }

      button.primary {
        background: var(--color-accent-gradient);
        color: var(--color-text-on-dark);
        box-shadow: var(--shadow-md);
      }

      button.primary:hover:not(:disabled) {
        filter: brightness(1.05);
        box-shadow: var(--shadow-lg);
      }

      button.secondary {
        background-color: transparent;
        color: var(--color-text);
        border: 1px solid var(--color-border);
      }

      button.secondary:hover:not(:disabled) {
        background-color: var(--color-border-light);
        border-color: var(--color-text-light);
      }

      button.ghost {
        background-color: transparent;
        color: var(--color-text-on-dark);
        border: 1px solid rgba(255, 255, 255, 0.5);
      }

      button.ghost:hover:not(:disabled) {
        background-color: rgba(255, 255, 255, 0.1);
        border-color: var(--color-text-on-dark);
      }

      button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      button.full-width {
        width: 100%;
      }
    `,
  ],
})
export class ButtonComponent {
  @Input() type: 'button' | 'submit' = 'button';
  @Input() variant: 'primary' | 'secondary' | 'ghost' = 'primary';
  @Input() disabled = false;
  @Input() fullWidth = false;

  get buttonClass(): string {
    return `${this.variant} ${this.fullWidth ? 'full-width' : ''}`;
  }

  onClick = new EventEmitter<MouseEvent>();
}
