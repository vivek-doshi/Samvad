// DisclaimerComponent — dismissible legal/regulatory disclaimer banner
// Note 1: This component shows a dismissible disclaimer on financial/legal
// assistant responses. Regulatory requirements in India (SEBI, CBDT) mandate
// that AI-generated financial and tax guidance must include a disclaimer
// that it is informational only and does not constitute professional advice.
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
  // Note 2: input<string>() with a default value means the parent can override
  // the disclaimer text for specific domains (e.g. a longer equity disclaimer
  // vs a shorter general one). If not provided, the default text is used.
  readonly text = input<string>(
    'This is informational guidance only. Not financial or legal advice.',
  );
  // Note 3: visible is a local signal (not an input) because the dismiss state
  // belongs to this component — the parent does not need to know about it.
  // When the user clicks dismiss, visible.set(false) hides the banner via *ngIf.
  readonly visible = signal(true);
}

