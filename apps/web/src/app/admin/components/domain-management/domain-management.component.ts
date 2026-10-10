import { Component } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../../environments/environment';

interface Domain {
  id: string;
  domain: string;
  status: string;
  last_crawled_at: string | null;
  error_count: number;
  created_at: string;
}

@Component({
  selector: 'app-domain-management',
  template: `
    <div class="admin-container">
      <div class="admin-header">
        <h1>Gestion des domaines</h1>
        <p>Importez et gérez les domaines à surveiller</p>
      </div>

      <app-card>
        <h2>Importer un CSV</h2>
        <div class="import-section">
          <input
            type="file"
            #fileInput
            accept=".csv"
            (change)="onFileSelected($event)"
            style="display: none"
          />
          <app-button
            variant="secondary"
            (click)="fileInput.click()"
          >
            Sélectionner un fichier CSV
          </app-button>
          <span *ngIf="selectedFile" class="file-name">
            {{ selectedFile.name }}
          </span>
          <app-button
            *ngIf="selectedFile"
            variant="primary"
            (click)="importCSV()"
            [disabled]="importing"
          >
            {{ importing ? 'Import...' : 'Importer' }}
          </app-button>
        </div>

        <div *ngIf="importResult" class="import-result">
          <p><strong>Importé:</strong> {{ importResult.imported }}</p>
          <p><strong>Ignoré:</strong> {{ importResult.skipped }}</p>
          <div *ngIf="importResult.errors.length > 0">
            <p><strong>Erreurs:</strong></p>
            <ul>
              <li *ngFor="let error of importResult.errors">{{ error }}</li>
            </ul>
          </div>
        </div>
      </app-card>

      <app-card>
        <div class="domains-header">
          <h2>Domaines ({{ domains.length }})</h2>
          <div class="domains-actions">
            <input
              type="text"
              placeholder="Rechercher un domaine..."
              [(ngModel)]="searchTerm"
              (ngModelChange)="filterDomains()"
              class="search-input"
            />
            <app-button
              variant="secondary"
              (click)="toggleSelectAll()"
            >
              {{ isAllSelected() ? 'Tout désélectionner' : 'Tout sélectionner' }}
            </app-button>
            <div class="bulk-status" *ngIf="selectedDomains.size > 0">
              <select
                [(ngModel)]="bulkStatus"
                class="status-select"
              >
                <option [ngValue]="null" disabled>Choisir un statut…</option>
                <option value="active">active</option>
                <option value="paused">paused</option>
                <option value="quarantined">quarantined</option>
              </select>
              <app-button
                variant="primary"
                (click)="updateSelectedStatus()"
                [disabled]="bulkStatus === null || updatingBulk"
              >
                {{
                  updatingBulk
                    ? 'Mise à jour...'
                    : ('Appliquer à ' + selectedDomains.size + ' sélectionné(s)')
                }}
              </app-button>
            </div>
            <app-button
              variant="secondary"
              (click)="deleteSelected()"
              [disabled]="selectedDomains.size === 0"
            >
              Supprimer sélectionnés ({{ selectedDomains.size }})
            </app-button>
          </div>
        </div>
        <div class="domains-list">
          <div *ngFor="let domain of filteredDomains" class="domain-item">
            <div class="domain-checkbox">
              <input
                type="checkbox"
                [checked]="selectedDomains.has(domain.id)"
                (change)="toggleDomain(domain.id)"
              />
            </div>
            <div class="domain-info">
              <span class="domain-name">{{ domain.domain }}</span>
              <div class="domain-badges">
                <app-badge [variant]="getStatusVariant(domain.status)">
                  {{ domain.status }}
                </app-badge>
                <select
                  [value]="domain.status"
                  (change)="updateDomainStatus(domain.id, $event)"
                  class="status-select"
                >
                  <option value="active">active</option>
                  <option value="paused">paused</option>
                  <option value="quarantined">quarantined</option>
                </select>
              </div>
            </div>
            <div class="domain-meta">
              <span *ngIf="domain.last_crawled_at">
                Dernier crawl: {{ formatDate(domain.last_crawled_at) }}
              </span>
              <span *ngIf="domain.error_count > 0" class="error-count">
                Erreurs: {{ domain.error_count }}
              </span>
            </div>
            <div class="domain-actions">
              <app-button
                variant="secondary"
                (click)="deleteDomain(domain.id)"
                [disabled]="deleting === domain.id"
              >
                {{ deleting === domain.id ? 'Suppression...' : 'Supprimer' }}
              </app-button>
            </div>
          </div>
        </div>
        <div *ngIf="filteredDomains.length === 0" class="no-domains">
          <p>Aucun domaine trouvé</p>
        </div>
      </app-card>
    </div>
  `,
  styles: [
    `
      .admin-container {
        max-width: 1200px;
        margin: 0 auto;
        padding: var(--spacing-xl);
      }

      .admin-header {
        margin-bottom: var(--spacing-xl);
      }

      .admin-header h1 {
        font-size: var(--font-size-3xl);
        margin-bottom: var(--spacing-sm);
      }

      .admin-header p {
        color: var(--color-text-light);
        font-size: var(--font-size-base);
      }

      .import-section {
        display: flex;
        gap: var(--spacing-md);
        align-items: center;
        margin-top: var(--spacing-md);
      }

      .file-name {
        font-size: var(--font-size-sm);
        color: var(--color-text-light);
      }

      .import-result {
        margin-top: var(--spacing-lg);
        padding: var(--spacing-md);
        background-color: var(--color-background-alt);
        border-radius: var(--radius-md);
      }

      .domains-list {
        display: flex;
        flex-direction: column;
        gap: var(--spacing-md);
        margin-top: var(--spacing-lg);
      }

      .domains-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: var(--spacing-lg);
        flex-wrap: wrap;
        gap: var(--spacing-md);
      }

      .domains-actions {
        display: flex;
        gap: var(--spacing-md);
        align-items: center;
      }

      .search-input {
        padding: var(--spacing-sm) var(--spacing-md);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-lg);
        font-size: var(--font-size-base);
        font-family: var(--font-family);
      }

      .search-input:focus {
        outline: none;
        border-color: var(--color-accent);
        box-shadow: 0 0 0 3px rgba(255, 127, 0, 0.15);
      }

      .domains-list {
        display: flex;
        flex-direction: column;
        gap: var(--spacing-md);
        margin-top: var(--spacing-lg);
      }

      .domain-item {
        padding: var(--spacing-md);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-md);
        display: flex;
        align-items: center;
        gap: var(--spacing-md);
      }

      .domain-checkbox {
        display: flex;
        align-items: center;
      }

      .domain-info {
        flex: 1;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: var(--spacing-md);
      }

      .domain-name {
        font-weight: var(--font-weight-medium);
      }

      .domain-badges {
        display: flex;
        gap: var(--spacing-sm);
        align-items: center;
      }

      .status-select {
        padding: var(--spacing-xs) var(--spacing-sm);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-sm);
        font-size: var(--font-size-sm);
      }

      .domain-meta {
        font-size: var(--font-size-sm);
        color: var(--color-text-light);
        display: flex;
        gap: var(--spacing-md);
      }

      .error-count {
        color: var(--color-error);
      }

      .domain-actions {
        display: flex;
        gap: var(--spacing-sm);
      }

      .no-domains {
        text-align: center;
        padding: var(--spacing-xl);
        color: var(--color-text-light);
      }
    `,
  ],
})
export class DomainManagementComponent {
  domains: Domain[] = [];
  filteredDomains: Domain[] = [];
  selectedFile: File | null = null;
  importing = false;
  importResult: any = null;
  searchTerm = '';
  selectedDomains = new Set<string>();
  deleting: string | null = null;
  bulkStatus: string | null = null;
  updatingBulk = false;

  constructor(private http: HttpClient) {
    this.loadDomains();
  }

  onFileSelected(event: Event): void {
    const target = event.target as HTMLInputElement;
    if (target.files && target.files.length > 0) {
      this.selectedFile = target.files[0];
    }
  }

  importCSV(): void {
    if (!this.selectedFile) return;

    this.importing = true;
    const formData = new FormData();
    formData.append('file', this.selectedFile);

    this.http
      .post<{
        imported: number;
        skipped: number;
        errors: string[];
      }>(`${environment.apiUrl}/api/v1/domains/import`, formData)
      .subscribe({
        next: (result) => {
          this.importResult = result;
          this.importing = false;
          this.selectedFile = null;
          this.loadDomains();
        },
        error: (err) => {
          this.importing = false;
          console.error('Import error:', err);
        },
      });
  }

  loadDomains(): void {
    this.http
      .get<Domain[]>(`${environment.apiUrl}/api/v1/domains`)
      .subscribe({
        next: (domains) => {
          this.domains = domains;
          this.filterDomains();
        },
        error: (err) => {
          console.error('Error loading domains:', err);
        },
      });
  }

  filterDomains(): void {
    if (!this.searchTerm) {
      this.filteredDomains = this.domains;
    } else {
      const term = this.searchTerm.toLowerCase();
      this.filteredDomains = this.domains.filter((domain) =>
        domain.domain.toLowerCase().includes(term)
      );
    }
  }

  toggleDomain(domainId: string): void {
    if (this.selectedDomains.has(domainId)) {
      this.selectedDomains.delete(domainId);
    } else {
      this.selectedDomains.add(domainId);
    }
  }

  toggleSelectAll(): void {
    if (this.isAllSelected()) {
      // Deselect all
      this.selectedDomains.clear();
    } else {
      // Select all filtered domains
      this.filteredDomains.forEach((domain) => {
        this.selectedDomains.add(domain.id);
      });
    }
  }

  isAllSelected(): boolean {
    if (this.filteredDomains.length === 0) return false;
    return this.filteredDomains.every((domain) =>
      this.selectedDomains.has(domain.id)
    );
  }

  deleteDomain(domainId: string): void {
    if (!confirm('Êtes-vous sûr de vouloir supprimer ce domaine ?')) {
      return;
    }

    this.deleting = domainId;
    this.http
      .delete(`${environment.apiUrl}/api/v1/domains/${domainId}`)
      .subscribe({
        next: () => {
          this.loadDomains();
          this.selectedDomains.delete(domainId);
          this.deleting = null;
        },
        error: (err) => {
          console.error('Error deleting domain:', err);
          this.deleting = null;
          alert('Erreur lors de la suppression du domaine');
        },
      });
  }

  deleteSelected(): void {
    const count = this.selectedDomains.size;
    if (count === 0) return;

    if (!confirm(`Êtes-vous sûr de vouloir supprimer ${count} domaine(s) ?`)) {
      return;
    }

    const deletePromises = Array.from(this.selectedDomains).map((domainId) =>
      this.http
        .delete(`${environment.apiUrl}/api/v1/domains/${domainId}`)
        .toPromise()
    );

    Promise.all(deletePromises)
      .then(() => {
        this.loadDomains();
        this.selectedDomains.clear();
      })
      .catch((err) => {
        console.error('Error deleting domains:', err);
        alert('Erreur lors de la suppression des domaines');
      });
  }

  updateSelectedStatus(): void {
    if (!this.bulkStatus || this.selectedDomains.size === 0) {
      return;
    }

    const count = this.selectedDomains.size;
    if (
      !confirm(
        `Mettre le statut de ${count} domaine(s) à "${this.bulkStatus}" ?`
      )
    ) {
      return;
    }

    this.updatingBulk = true;

    const updatePromises = Array.from(this.selectedDomains).map((domainId) =>
      this.http
        .patch(`${environment.apiUrl}/api/v1/domains/${domainId}`, {
          status: this.bulkStatus,
        })
        .toPromise()
    );

    Promise.all(updatePromises)
      .then(() => {
        this.updatingBulk = false;
        this.bulkStatus = null;
        this.loadDomains();
      })
      .catch((err) => {
        console.error('Error updating domains status:', err);
        this.updatingBulk = false;
        alert('Erreur lors de la mise à jour du statut des domaines');
        this.loadDomains();
      });
  }

  updateDomainStatus(domainId: string, event: Event): void {
    const target = event.target as HTMLSelectElement;
    const newStatus = target.value;

    this.http
      .patch(`${environment.apiUrl}/api/v1/domains/${domainId}`, {
        status: newStatus,
      })
      .subscribe({
        next: () => {
          this.loadDomains();
        },
        error: (err) => {
          console.error('Error updating domain status:', err);
          alert('Erreur lors de la mise à jour du statut');
          this.loadDomains(); // Reload to revert UI
        },
      });
  }

  getStatusVariant(status: string): 'default' | 'success' | 'error' | 'warning' {
    switch (status) {
      case 'active':
        return 'success';
      case 'quarantined':
        return 'error';
      case 'paused':
        return 'warning';
      default:
        return 'default';
    }
  }

  formatDate(date: string): string {
    return new Date(date).toLocaleDateString('fr-FR');
  }
}
