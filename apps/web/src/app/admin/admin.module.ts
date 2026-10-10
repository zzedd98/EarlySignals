import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';

import { AdminRoutingModule } from './admin-routing.module';
import { DomainManagementComponent } from './components/domain-management/domain-management.component';
import { SharedModule } from '../shared/shared.module';

@NgModule({
  declarations: [DomainManagementComponent],
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    RouterModule,
    AdminRoutingModule,
    SharedModule,
  ],
})
export class AdminModule {}
