import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { DashboardComponent } from './components/dashboard/dashboard.component';
import { OpportunityDetailComponent } from './components/opportunity-detail/opportunity-detail.component';

const routes: Routes = [
  { path: '', component: DashboardComponent },
  { path: 'opportunity/:id', component: OpportunityDetailComponent },
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule],
})
export class DashboardRoutingModule {}
