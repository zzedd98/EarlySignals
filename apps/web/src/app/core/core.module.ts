import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';
import { RouterModule } from '@angular/router';

import { MainLayoutComponent } from './layout/main-layout.component';

@NgModule({
  declarations: [MainLayoutComponent],
  imports: [CommonModule, HttpClientModule, RouterModule],
  exports: [MainLayoutComponent],
})
export class CoreModule {}
