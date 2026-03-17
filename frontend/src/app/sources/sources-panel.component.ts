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
  sources = input<SourceReference[]>([]);
  isVisible = computed(() => this.sources().length > 0);
}
