import { Component, OnInit, Inject } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';
import { ToastService } from '../../../core/services/toast.service';

interface Opportunity {
  id: string;
  company_name: string;
  signal_type: string;
  importance: string;
  score: number;
  detected_at: string;
  proof_url: string;
  why_it_matters?: string;
  suggested_approach?: string;
  country?: string;
}

@Component({
  selector: 'app-opportunity-detail',
  template: `
    <div class="detail-container">
      <app-button variant="secondary" (click)="goBack()">← Retour</app-button>

      <div *ngIf="loading" class="loading-state">
        <p>Chargement de l'opportunité…</p>
      </div>

      <div *ngIf="!loading && error" class="error-state">
        <p>{{ error }}</p>
        <app-button variant="primary" (click)="retry()">
          Réessayer
        </app-button>
      </div>

      <app-card *ngIf="!loading && !error && opportunity" class="detail-card">
        <div class="detail-header">
          <h1>{{ opportunity.company_name }}</h1>
          <app-badge [variant]="getScoreVariant(opportunity.score)">
            Score: {{ opportunity.score }}
          </app-badge>
        </div>

        <div class="detail-meta">
          <app-badge variant="default">{{ opportunity.signal_type }}</app-badge>
          <app-badge [variant]="getImportanceVariant(opportunity.importance)">
            {{ getImportanceLabel(opportunity.importance) }}
          </app-badge>
          <span *ngIf="opportunity.country">{{ opportunity.country }}</span>
          <span>{{ formatDate(opportunity.detected_at) }}</span>
        </div>

        <div class="detail-section">
          <h3>Pourquoi c'est intéressant</h3>
          <p>{{ opportunity.why_it_matters || '—' }}</p>
        </div>

        <div class="detail-section">
          <h3>Angle d'approche suggéré</h3>
          <div class="approach-box">
            <p>{{ opportunity.suggested_approach || '—' }}</p>
            <app-button variant="secondary" (click)="copyApproach()">
              Copier
            </app-button>
          </div>
        </div>

        <div class="detail-section">
          <h3>Preuve</h3>
          <a class="link-accent" [href]="opportunity.proof_url" target="_blank">
            {{ opportunity.proof_url }} →
          </a>
        </div>

        <div class="detail-actions">
          <app-button variant="primary" (click)="markToContact()">
            Marquer "À contacter"
          </app-button>
          <app-button variant="secondary" (click)="markFavorite()">
            Favori
          </app-button>
        </div>
      </app-card>
    </div>
  `,
  styles: [
    `
      .detail-container {
        max-width: 800px;
        margin: 0 auto;
        padding: var(--spacing-xl);
      }

      .detail-card {
        margin-top: var(--spacing-lg);
      }

      .detail-header {
        display: flex;
        justify-content: space-between;
        align-items: start;
        margin-bottom: var(--spacing-lg);
      }

      .detail-header h1 {
        font-size: var(--font-size-3xl);
        margin: 0;
      }

      .detail-meta {
        display: flex;
        gap: var(--spacing-md);
        align-items: center;
        margin-bottom: var(--spacing-xl);
        color: var(--color-text-light);
      }

      .detail-section {
        margin-bottom: var(--spacing-xl);
      }

      .detail-section h3 {
        font-size: var(--font-size-lg);
        margin-bottom: var(--spacing-md);
      }

      .approach-box {
        padding: var(--spacing-md);
        background-color: var(--color-background-alt);
        border-radius: var(--radius-md);
        display: flex;
        justify-content: space-between;
        align-items: start;
        gap: var(--spacing-md);
      }

      .detail-actions {
        display: flex;
        gap: var(--spacing-md);
        margin-top: var(--spacing-xl);
      }

      .loading-state,
      .error-state {
        text-align: center;
        padding: var(--spacing-3xl);
        color: var(--color-text-light);
      }

      .error-state {
        color: var(--color-error);
      }

      .error-state app-button {
        margin-top: var(--spacing-md);
      }
    `,
  ],
})
export class OpportunityDetailComponent implements OnInit {
  opportunity: Opportunity | null = null;
  loading = false;
  error = '';

  constructor(
    private route: ActivatedRoute,
    private http: HttpClient,
    private router: Router,
    @Inject(ToastService) private toastService: ToastService
  ) {}

  retry(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) this.loadOpportunity(id);
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.loadOpportunity(id);
    }
  }

  loadOpportunity(id: string): void {
    this.loading = true;
    this.error = '';
    this.http
      .get<Opportunity>(`${environment.apiUrl}/api/v1/opportunities/${id}`)
      .subscribe({
        next: (opp) => {
          this.opportunity = opp;
          this.loading = false;
        },
        error: (err) => {
          console.error('Error loading opportunity:', err);
          this.error =
            err.error?.detail ||
            'Impossible de charger cette opportunité. Réessayez.';
          this.loading = false;
        },
      });
  }

  goBack(): void {
    this.router.navigate(['/dashboard']);
  }

  copyApproach(): void {
    if (this.opportunity?.suggested_approach) {
      navigator.clipboard.writeText(this.opportunity.suggested_approach);
      this.toastService.show('Angle d\'approche copié !');
    }
  }

  markToContact(): void {
    if (this.opportunity) {
      this.http
        .patch(
          `${environment.apiUrl}/api/v1/opportunities/${this.opportunity.id}`,
          { status_flags_json: { to_contact: true } }
        )
        .subscribe({
          next: () => this.toastService.show('Marqué « À contacter »'),
          error: () =>
            this.toastService.show('Erreur lors de la mise à jour', 'error'),
        });
    }
  }

  markFavorite(): void {
    if (this.opportunity) {
      this.http
        .patch(
          `${environment.apiUrl}/api/v1/opportunities/${this.opportunity.id}`,
          { status_flags_json: { favorite: true } }
        )
        .subscribe({
          next: () => this.toastService.show('Ajouté aux favoris'),
          error: () =>
            this.toastService.show('Erreur lors de la mise à jour', 'error'),
        });
    }
  }

  getScoreVariant(score: number): 'success' | 'warning' | 'default' {
    if (score >= 70) return 'success';
    if (score >= 50) return 'warning';
    return 'default';
  }

  getImportanceLabel(importance: string): string {
    const labels: Record<string, string> = {
      strong: 'Fort',
      medium: 'Moyen',
      weak: 'Faible',
    };
    return labels[importance] || importance;
  }

  getImportanceVariant(
    importance: string
  ): 'success' | 'warning' | 'default' {
    if (importance === 'strong') return 'success';
    if (importance === 'medium') return 'warning';
    return 'default';
  }

  formatDate(date: string): string {
    return new Date(date).toLocaleDateString('fr-FR');
  }
}
