import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { RouterModule } from '@angular/router';

import { OnboardingRoutingModule } from './onboarding-routing.module';
import { OnboardingComponent } from './components/onboarding/onboarding.component';
import { SharedModule } from '../shared/shared.module';

@NgModule({
  declarations: [OnboardingComponent],
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    RouterModule,
    OnboardingRoutingModule,
    SharedModule,
  ],
})
export class OnboardingModule {}
