// SourcesPanelComponent — displays cited source references below a response
// Note 1: After the LLM finishes streaming, the final SSE event includes a
// 'sources' array of SourceReference objects. This component renders those
// citations as a compact panel below the assistant message, allowing the
// user to see which document and section each claim was drawn from.
import { CommonModule } from '@angular/common';
import { Component, computed, input } from '@angular/core';
import { SourceReference } from '../models/message.model';

@Component({
  selector: 'app-sources-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './sources-panel.component.html',
  styleUrls: ['./sources-panel.component.scss'],
})
export class SourcesPanelComponent {
  // Note 2: input<SourceReference[]>([]) — the sources list is optional (default []).
  // If no sources are available (e.g. the LLM answered from training data or
  // retrieval returned nothing), the panel hides itself via isVisible.
  sources = input<SourceReference[]>([]);
  // Note 3: isVisible is a computed signal that returns true only when there
  // is at least one source to show. The template uses this to conditionally
  // render the sources panel via *ngIf="isVisible()".
  isVisible = computed(() => this.sources().length > 0);
}
