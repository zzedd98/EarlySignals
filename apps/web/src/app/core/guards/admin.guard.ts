import { Injectable } from '@angular/core';
import {
  Router,
  CanActivate,
  ActivatedRouteSnapshot,
  RouterStateSnapshot,
} from '@angular/router';
import { AuthService } from '../services/auth.service';
import { Observable, of } from 'rxjs';
import { map, catchError } from 'rxjs/operators';

@Injectable({
  providedIn: 'root',
})
export class AdminGuard implements CanActivate {
  constructor(private authService: AuthService, private router: Router) {}

  canActivate(
    route: ActivatedRouteSnapshot,
    state: RouterStateSnapshot
  ): Observable<boolean> | boolean {
    if (!this.authService.isAuthenticated()) {
      console.log('[AdminGuard] Not authenticated, redirecting to login');
      this.router.navigate(['/auth/login']);
      return false;
    }

    // Get current user value
    const currentUser = this.authService.getCurrentUserValue();
    console.log('[AdminGuard] Current user value:', currentUser);
    
    // If user is already loaded, check immediately
    if (currentUser) {
      if (currentUser.role === 'admin') {
        console.log('[AdminGuard] User is admin, allowing access');
        return true;
      }
      console.log('[AdminGuard] User is not admin, redirecting to dashboard');
      this.router.navigate(['/dashboard']);
      return false;
    }

    // If user not loaded, load it first then check
    console.log('[AdminGuard] User not loaded, fetching from API...');
    return this.authService.getCurrentUser().pipe(
      map((user) => {
        console.log('[AdminGuard] User loaded from API:', user);
        if (user && user.role === 'admin') {
          console.log('[AdminGuard] User is admin, allowing access');
          return true;
        }
        // Not admin, redirect to dashboard
        console.log('[AdminGuard] User is not admin, redirecting to dashboard');
        this.router.navigate(['/dashboard']);
        return false;
      }),
      catchError((error) => {
        console.error('[AdminGuard] Error loading user:', error);
        // If error (401, 403, etc.), redirect to login
        this.router.navigate(['/auth/login']);
        return of(false);
      })
    );
  }
}
