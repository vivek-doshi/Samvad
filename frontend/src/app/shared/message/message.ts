// MessageComponent — renders a single chat message bubble
// Note 1: This is a "presentational" (also called "dumb") component — it only
// displays data passed in via @Input() signals and emits no events. This
// design keeps it simple and reusable: it can render both user and assistant
// messages with the same component, differentiated by msg.role in the template.
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
  // Note 2: input.required<Message>() declares a REQUIRED input signal (Angular 17+
  // signal inputs API). The component will throw if rendered without providing 'msg'.
  // Signal inputs are more performant than @Input() because changes are tracked
  // reactively without Angular's change detection needing to scan the component tree.
  readonly msg = input.required<Message>();
  // Note 3: input<boolean>(false) declares an OPTIONAL input signal with a default
  // value of false. If showDisclaimer is not provided by the parent template,
  // it defaults to false and the disclaimer is hidden.
  readonly showDisclaimer = input<boolean>(false);
  readonly disclaimerText = input<string>(
    'This is informational guidance only. Not financial or legal advice.',
  );
}

