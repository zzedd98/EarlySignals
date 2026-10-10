import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface ToastMessage {
  id: number;
  text: string;
  type: 'success' | 'info' | 'error';
}

@Injectable({
  providedIn: 'root',
})
export class ToastService {
  private nextId = 0;
  private readonly defaultDuration = 3000;
  private hideTimer: ReturnType<typeof setTimeout> | null = null;

  private messageSubject = new BehaviorSubject<ToastMessage | null>(null);
  message$ = this.messageSubject.asObservable();

  show(text: string, type: 'success' | 'info' | 'error' = 'success'): void {
    if (this.hideTimer) {
      clearTimeout(this.hideTimer);
      this.hideTimer = null;
    }
    const message: ToastMessage = {
      id: ++this.nextId,
      text,
      type,
    };
    this.messageSubject.next(message);
    this.hideTimer = setTimeout(() => {
      this.messageSubject.next(null);
      this.hideTimer = null;
    }, this.defaultDuration);
  }

  hide(): void {
    if (this.hideTimer) {
      clearTimeout(this.hideTimer);
      this.hideTimer = null;
    }
    this.messageSubject.next(null);
  }
}
