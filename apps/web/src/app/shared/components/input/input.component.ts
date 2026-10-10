import { Component, Input, forwardRef } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

@Component({
  selector: 'app-input',
  template: `
    <div class="input-wrapper">
      <label *ngIf="label" [for]="id">{{ label }}</label>
      <input
        [id]="id"
        [type]="type"
        [placeholder]="placeholder"
        [value]="value"
        [disabled]="disabled"
        (input)="onChange($event)"
        (blur)="onTouched()"
        class="input"
      />
    </div>
  `,
  styles: [
    `
      .input-wrapper {
        display: flex;
        flex-direction: column;
        gap: var(--spacing-xs);
      }

      label {
        font-size: var(--font-size-sm);
        font-weight: var(--font-weight-medium);
        color: var(--color-text);
      }

      .input {
        font-family: var(--font-family);
        font-size: var(--font-size-base);
        padding: var(--spacing-sm) var(--spacing-md);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        background-color: var(--color-background-alt);
        color: var(--color-text);
        transition: border-color var(--transition-base);
        width: 100%;
      }

      .input:focus {
        outline: none;
        border-color: var(--color-accent);
        box-shadow: 0 0 0 3px rgba(255, 127, 0, 0.15);
      }

      .input:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      .input::placeholder {
        color: var(--color-text-muted);
      }
    `,
  ],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => InputComponent),
      multi: true,
    },
  ],
})
export class InputComponent implements ControlValueAccessor {
  @Input() id = '';
  @Input() type: 'text' | 'email' | 'password' = 'text';
  @Input() label = '';
  @Input() placeholder = '';
  @Input() disabled = false;

  value = '';
  private onChangeFn = (value: string) => {};
  private onTouchedFn = () => {};

  onChange(event: Event): void {
    const target = event.target as HTMLInputElement;
    this.value = target.value;
    this.onChangeFn(this.value);
  }

  onTouched(): void {
    this.onTouchedFn();
  }

  writeValue(value: string): void {
    this.value = value || '';
  }

  registerOnChange(fn: (value: string) => void): void {
    this.onChangeFn = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouchedFn = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled = isDisabled;
  }
}
