import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { ButtonComponent } from './components/button/button.component';
import { CardComponent } from './components/card/card.component';
import { InputComponent } from './components/input/input.component';
import { BadgeComponent } from './components/badge/badge.component';
import { ToastComponent } from './components/toast/toast.component';

@NgModule({
  declarations: [
    ButtonComponent,
    CardComponent,
    InputComponent,
    BadgeComponent,
    ToastComponent,
  ],
  imports: [CommonModule, FormsModule, ReactiveFormsModule],
  exports: [
    ButtonComponent,
    CardComponent,
    InputComponent,
    BadgeComponent,
    ToastComponent,
  ],
})
export class SharedModule {}
