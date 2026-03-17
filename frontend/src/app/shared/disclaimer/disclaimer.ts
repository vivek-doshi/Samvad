import { CommonModule } from '@angular/common';
import { Component, input, signal } from '@angular/core';

@Component({
  selector: 'app-disclaimer',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './disclaimer.html',
  styleUrl: './disclaimer.scss',
})
export class DisclaimerComponent {
  readonly text = input<string>(
    'This is informational guidance only. Not financial or legal advice.',
  );
  readonly visible = signal(true);
}

