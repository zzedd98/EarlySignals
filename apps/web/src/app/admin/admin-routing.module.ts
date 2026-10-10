import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { DomainManagementComponent } from './components/domain-management/domain-management.component';
import { AdminGuard } from '../core/guards/admin.guard';

const routes: Routes = [
  {
    path: 'domains',
    component: DomainManagementComponent,
    canActivate: [AdminGuard],
  },
  { path: '', redirectTo: 'domains', pathMatch: 'full' },
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule],
})
export class AdminRoutingModule {}
