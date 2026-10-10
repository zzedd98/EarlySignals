import { Component } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';

interface Profile {
  value: string;
  label: string;
}

@Component({
  selector: 'app-onboarding',
  template: `
    <div class="onboarding-container">
      <app-card>
        <div class="onboarding-header">
          <h1>Configuration de votre compte</h1>
          <p class="subtitle">Personnalisez Early Signals selon vos besoins</p>
        </div>

        <form
          [formGroup]="onboardingForm"
          (ngSubmit)="onSubmit()"
          class="onboarding-form"
        >
          <div class="form-group">
            <label for="profile">Profil</label>
            <select
              id="profile"
              formControlName="profile"
              class="select"
            >
              <option value="">Sélectionnez un profil</option>
              <option *ngFor="let profile of profiles" [value]="profile.value">
                {{ profile.label }}
              </option>
            </select>
          </div>

          <div class="form-group">
            <label>Pays ciblés</label>
            <div class="countries-grid">
              <label
                *ngFor="let country of countries"
                class="checkbox-label"
              >
                <input
                  type="checkbox"
                  [value]="country.code"
                  (change)="onCountryChange($event)"
                />
                {{ country.name }}
              </label>
            </div>
          </div>

          <div class="form-group">
            <label>Canaux de notification</label>
            <label class="checkbox-label">
              <input
                type="checkbox"
                formControlName="emailNotifications"
              />
              Email digest quotidien
            </label>
            <label class="checkbox-label">
              <input
                type="checkbox"
                formControlName="instantNotifications"
              />
              Notifications instantanées (score élevé)
            </label>
          </div>

          <div *ngIf="error" class="error-message">{{ error }}</div>

          <app-button
            type="submit"
            variant="primary"
            [disabled]="onboardingForm.invalid || loading"
            [fullWidth]="true"
          >
            {{ loading ? 'Enregistrement...' : 'Continuer' }}
          </app-button>
        </form>
      </app-card>
    </div>
  `,
  styles: [
    `
      .onboarding-container {
        min-height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: var(--spacing-xl);
        background-color: var(--color-background);
      }

      app-card {
        width: 100%;
        max-width: 600px;
      }

      .onboarding-header {
        text-align: center;
        margin-bottom: var(--spacing-xl);
      }

      .onboarding-header h1 {
        font-size: var(--font-size-3xl);
        font-weight: var(--font-weight-bold);
        margin-bottom: var(--spacing-sm);
      }

      .subtitle {
        color: var(--color-text-light);
        font-size: var(--font-size-base);
      }

      .onboarding-form {
        display: flex;
        flex-direction: column;
        gap: var(--spacing-xl);
      }

      .form-group {
        display: flex;
        flex-direction: column;
        gap: var(--spacing-sm);
      }

      .form-group label {
        font-size: var(--font-size-sm);
        font-weight: var(--font-weight-medium);
        color: var(--color-text);
      }

      .select {
        font-family: var(--font-family);
        font-size: var(--font-size-base);
        padding: var(--spacing-sm) var(--spacing-md);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        background-color: var(--color-background);
        color: var(--color-text);
        transition: border-color var(--transition-base);
      }

      .select:focus {
        outline: none;
        border-color: var(--color-accent);
        box-shadow: 0 0 0 3px rgba(255, 127, 0, 0.15);
      }

      .countries-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
        gap: var(--spacing-sm);
      }

      .checkbox-label {
        display: flex;
        align-items: center;
        gap: var(--spacing-sm);
        font-weight: var(--font-weight-normal);
        cursor: pointer;
      }

      .checkbox-label input[type='checkbox'] {
        cursor: pointer;
      }

      .error-message {
        padding: var(--spacing-sm);
        background-color: #fee2e2;
        color: var(--color-error);
        border-radius: var(--radius-md);
        font-size: var(--font-size-sm);
      }
    `,
  ],
})
export class OnboardingComponent {
  onboardingForm: FormGroup;
  loading = false;
  error = '';

  profiles: Profile[] = [
    { value: 'dev_agency', label: 'Agence de développement' },
    { value: 'growth_agency', label: 'Agence growth marketing' },
    { value: 'recruitment', label: 'Recrutement' },
    { value: 'automation', label: 'Automatisation' },
    { value: 'premium_freelance', label: 'Freelance premium' },
    { value: 'ecommerce', label: 'E-commerce' },
  ];

  countries = [
    { code: 'FR', name: 'France' },
    { code: 'BE', name: 'Belgique' },
    { code: 'CH', name: 'Suisse' },
    { code: 'CA', name: 'Canada' },
    { code: 'US', name: 'États-Unis' },
    { code: 'GB', name: 'Royaume-Uni' },
  ];

  selectedCountries: string[] = [];

  constructor(
    private fb: FormBuilder,
    private http: HttpClient,
    private router: Router
  ) {
    this.onboardingForm = this.fb.group({
      profile: ['', Validators.required],
      emailNotifications: [true],
      instantNotifications: [false],
    });
  }

  onCountryChange(event: Event): void {
    const target = event.target as HTMLInputElement;
    const code = target.value;
    if (target.checked) {
      this.selectedCountries.push(code);
    } else {
      this.selectedCountries = this.selectedCountries.filter((c) => c !== code);
    }
  }

  onSubmit(): void {
    if (this.onboardingForm.valid && this.selectedCountries.length > 0) {
      this.loading = true;
      this.error = '';

      const orgData = {
        profile: this.onboardingForm.value.profile,
        countries: this.selectedCountries,
        notification_settings: {
          email: this.onboardingForm.value.emailNotifications,
          instant: this.onboardingForm.value.instantNotifications,
        },
      };

      // TODO: Get org_id from current user
      // For now, we'll create/update organization
      this.http
        .put(`${environment.apiUrl}/api/v1/organizations/me`, orgData)
        .subscribe({
          next: () => {
            this.router.navigate(['/dashboard']);
          },
          error: (err) => {
            this.loading = false;
            this.error =
              err.error?.detail ||
              'Erreur lors de l\'enregistrement. Veuillez réessayer.';
          },
        });
    } else {
      this.error = 'Veuillez remplir tous les champs requis.';
    }
  }
}
