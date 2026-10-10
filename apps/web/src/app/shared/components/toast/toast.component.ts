import { Component, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import { ToastService, ToastMessage } from '../../../core/services/toast.service';

@Component({
  selector: 'app-toast',
  template: `
    <div
      *ngIf="message"
      class="toast"
      [class.toast-success]="message.type === 'success'"
      [class.toast-info]="message.type === 'info'"
      [class.toast-error]="message.type === 'error'"
      role="status"
    >
      {{ message.text }}
    </div>
  `,
  styles: [
    `
      .toast {
        position: fixed;
        bottom: var(--spacing-xl);
        right: var(--spacing-xl);
        padding: var(--spacing-md) var(--spacing-xl);
        border-radius: var(--radius-md);
        font-size: var(--font-size-sm);
        font-weight: var(--font-weight-medium);
        box-shadow: var(--shadow-lg);
        z-index: 9999;
        max-width: 360px;
      }

      .toast-success {
        background: var(--color-accent);
        color: white;
      }

      .toast-info {
        background-color: var(--color-info);
        color: white;
      }

      .toast-error {
        background-color: var(--color-error);
        color: white;
      }
    `,
  ],
})
export class ToastComponent implements OnDestroy {
  message: ToastMessage | null = null;
  private sub: Subscription | null = null;

  constructor(private toast: ToastService) {
    this.sub = this.toast.message$.subscribe((m) => (this.message = m));
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}
