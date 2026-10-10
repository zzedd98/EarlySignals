import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, BehaviorSubject, tap } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface User {
  id: string;
  email: string;
  role: string;
  org_id: string;
  created_at: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  org_id?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private apiUrl = environment.apiUrl;
  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUserSubject.asObservable();

  constructor(private http: HttpClient) {
    // Delay loading user to avoid circular dependency during initialization
    // Use setTimeout to defer until after interceptors are ready
    setTimeout(() => {
      this.loadUserFromStorage();
    }, 0);
  }

  private loadUserFromStorage(): void {
    const token = localStorage.getItem('access_token');
    if (token) {
      this.getCurrentUser().subscribe({
        next: (user) => this.currentUserSubject.next(user),
        error: () => this.logout(),
      });
    }
  }

  register(data: RegisterData): Observable<User> {
    return this.http.post<User>(`${this.apiUrl}/api/v1/auth/register`, data);
  }

  login(credentials: LoginCredentials): Observable<TokenResponse> {
    return this.http
      .post<TokenResponse>(`${this.apiUrl}/api/v1/auth/login`, credentials)
      .pipe(
        tap((response) => {
          console.log('[AuthService] Login successful, storing token');
          localStorage.setItem('access_token', response.access_token);
          // Load user immediately after login
          this.getCurrentUser().subscribe({
            next: (user) => {
              console.log('[AuthService] User loaded after login:', user);
              this.currentUserSubject.next(user);
            },
            error: (err) => {
              console.error('[AuthService] Error loading user after login:', err);
            }
          });
        })
      );
  }

  logout(): void {
    localStorage.removeItem('access_token');
    this.currentUserSubject.next(null);
  }

  getCurrentUser(): Observable<User> {
    return this.http.get<User>(`${this.apiUrl}/api/v1/auth/me`).pipe(
      tap((user) => this.currentUserSubject.next(user))
    );
  }

  getToken(): string | null {
    return localStorage.getItem('access_token');
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  isAdmin(): Observable<boolean> {
    return new Observable((observer) => {
      this.currentUser$.subscribe((user) => {
        observer.next(user?.role === 'admin');
        observer.complete();
      });
    });
  }

  getCurrentUserValue(): User | null {
    return this.currentUserSubject.value;
  }
}
