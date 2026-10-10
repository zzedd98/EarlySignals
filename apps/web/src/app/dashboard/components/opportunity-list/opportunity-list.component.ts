import { Component, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { environment } from '../../../../environments/environment';

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
  status_flags_json?: any;
}

@Component({
  selector: 'app-opportunity-list',
  template: `
    <div class="opportunity-list">
      <div class="filters">
        <app-input
          id="search"
          type="text"
          placeholder="Rechercher (entreprise, type de signal…)"
          [(ngModel)]="searchQuery"
        ></app-input>
        <select [(ngModel)]="scoreFilter" (change)="loadOpportunities()">
          <option value="">Tous les scores</option>
          <option value="70">Score ≥ 70</option>
          <option value="50">Score ≥ 50</option>
        </select>
        <select [(ngModel)]="signalFilter" (change)="loadOpportunities()">
          <option value="">Tous les signaux</option>
          <option value="jobs">Jobs</option>
          <option value="pricing_change">Pricing</option>
          <option value="tool_added">Outils</option>
        </select>
        <select [(ngModel)]="importanceFilter" (change)="loadOpportunities()">
          <option value="">Toutes importances</option>
          <option value="strong">Fort</option>
          <option value="medium">Moyen</option>
          <option value="weak">Faible</option>
        </select>
      </div>

      <div *ngIf="loading" class="loading-state">
        <p>Chargement des opportunités…</p>
      </div>

      <div *ngIf="!loading && error" class="error-state">
        <p>{{ error }}</p>
        <app-button variant="primary" (click)="loadOpportunities()">
          Réessayer
        </app-button>
      </div>

      <div *ngIf="!loading && !error" class="opportunities-grid">
        <app-card
          *ngFor="let opp of filteredOpportunities"
          class="opportunity-card"
          (click)="viewDetail(opp.id)"
        >
          <div class="opportunity-header">
            <h3>{{ opp.company_name }}</h3>
            <app-badge [variant]="getScoreVariant(opp.score)">
              Score: {{ opp.score }}
            </app-badge>
          </div>
          <div class="opportunity-meta">
            <app-badge variant="default">{{ opp.signal_type }}</app-badge>
            <app-badge [variant]="getImportanceVariant(opp.importance)">
              {{ getImportanceLabel(opp.importance) }}
            </app-badge>
            <span class="date">{{ formatDate(opp.detected_at) }}</span>
          </div>
          <p *ngIf="opp.why_it_matters" class="why">
            {{ opp.why_it_matters }}
          </p>
          <a class="link-accent" [href]="opp.proof_url" target="_blank" (click)="$event.stopPropagation()">
            Voir la preuve →
          </a>
        </app-card>
      </div>

      <div *ngIf="!loading && !error && filteredOpportunities.length === 0" class="empty-state">
        <p>{{ emptyStateMessage }}</p>
      </div>
    </div>
  `,
  styles: [
    `
      .opportunity-list {
        display: flex;
        flex-direction: column;
        gap: var(--spacing-xl);
      }

      .filters {
        display: flex;
        gap: var(--spacing-md);
        flex-wrap: wrap;
      }

      .filters select {
        padding: var(--spacing-sm) var(--spacing-md);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
      }

      .opportunities-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: var(--spacing-lg);
      }

      .opportunity-card {
        cursor: pointer;
        transition: transform var(--transition-base);
      }

      .opportunity-card:hover {
        transform: translateY(-2px);
      }

      .opportunity-header {
        display: flex;
        justify-content: space-between;
        align-items: start;
        margin-bottom: var(--spacing-md);
      }

      .opportunity-header h3 {
        font-size: var(--font-size-lg);
        margin: 0;
      }

      .opportunity-meta {
        display: flex;
        gap: var(--spacing-sm);
        align-items: center;
        margin-bottom: var(--spacing-md);
      }

      .date {
        font-size: var(--font-size-sm);
        color: var(--color-text-light);
      }

      .why {
        color: var(--color-text-light);
        font-size: var(--font-size-sm);
        margin-bottom: var(--spacing-md);
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

      .empty-state {
        text-align: center;
        padding: var(--spacing-3xl);
        color: var(--color-text-light);
      }
    `,
  ],
})
export class OpportunityListComponent implements OnInit {
  opportunities: Opportunity[] = [];
  searchQuery = '';
  scoreFilter = '';
  signalFilter = '';
  importanceFilter = '';
  loading = false;
  error = '';

  constructor(private http: HttpClient, private router: Router) {}

  ngOnInit(): void {
    this.loadOpportunities();
  }

  loadOpportunities(): void {
    this.loading = true;
    this.error = '';
    const params: any = {
      skip: 0,
      limit: 50,
    };
    if (this.scoreFilter) {
      params.score_min = parseInt(this.scoreFilter);
    }
    if (this.signalFilter) {
      params.signal_type = this.signalFilter;
    }
    if (this.importanceFilter) {
      params.importance = this.importanceFilter;
    }

    this.http
      .get<Opportunity[]>(`${environment.apiUrl}/api/v1/opportunities`, {
        params,
      })
      .subscribe({
        next: (opps) => {
          this.opportunities = opps;
          this.loading = false;
        },
        error: (err) => {
          console.error('Error loading opportunities:', err);
          this.error =
            err.error?.detail ||
            'Impossible de charger les opportunités. Réessayez.';
          this.loading = false;
        },
      });
  }

  get filteredOpportunities(): Opportunity[] {
    const q = this.searchQuery?.trim().toLowerCase() || '';
    if (!q) return this.opportunities;
    return this.opportunities.filter(
      (opp) =>
        opp.company_name?.toLowerCase().includes(q) ||
        opp.signal_type?.toLowerCase().includes(q) ||
        (opp.why_it_matters && opp.why_it_matters.toLowerCase().includes(q))
    );
  }

  get emptyStateMessage(): string {
    if (this.searchQuery?.trim()) {
      return 'Aucun résultat pour cette recherche. Modifiez les critères.';
    }
    return 'Aucune opportunité pour le moment.';
  }

  viewDetail(id: string): void {
    this.router.navigate(['/dashboard/opportunity', id]);
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
