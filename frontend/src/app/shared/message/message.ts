import { CommonModule } from '@angular/common';
import { Component, input } from '@angular/core';
import { Message } from '../../models/message.model';
import { DisclaimerComponent } from '../disclaimer/disclaimer';
import { MarkdownPipe } from '../markdown-pipe';

@Component({
  selector: 'app-message',
  standalone: true,
  imports: [CommonModule, MarkdownPipe, DisclaimerComponent],
  templateUrl: './message.html',
  styleUrl: './message.scss',
})
export class MessageComponent {
  readonly msg = input.required<Message>();
  readonly showDisclaimer = input<boolean>(false);
  readonly disclaimerText = input<string>(
    'This is informational guidance only. Not financial or legal advice.',
  );
}

