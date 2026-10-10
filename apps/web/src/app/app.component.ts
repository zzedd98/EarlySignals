import { Component } from '@angular/core';

@Component({
  selector: 'app-root',
  template: `
    <router-outlet></router-outlet>
    <app-toast></app-toast>
  `,
  styles: [],
})
export class AppComponent {
  title = 'Early Signals';
}
