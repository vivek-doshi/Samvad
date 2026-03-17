You are working on Samvad Angular 21 frontend.
Phase 3: display RAG source citations returned by the backend.

The backend now returns sources in the done event:
  data: {"token": "", "done": true,
         "sources": [
           {"document": "Income Tax Act 2025",
            "section": "80C", "page": 47}
         ]}

=============================================================
UPDATE 1: frontend/src/app/services/chat.service.ts
=============================================================

The ChatStreamEvent already has sources?: SourceReference[].
Update the stream parsing in sendMessage() to capture sources
from the done event and emit them in the final ChatStreamEvent:

  When parsing the done=true event:
  - Extract event.sources if present
  - Emit one final ChatStreamEvent:
      { token: '', done: true, sources: event.sources ?? [] }
  - Then call subscriber.complete()

=============================================================
UPDATE 2: frontend/src/app/chat/chat.component.ts
=============================================================

In the sendMessage() stream subscription next handler:
  When event.done === true (this arrives before complete()):
    Update the last assistant message to include sources:
    this.messages.update(msgs => {
      const updated = [...msgs]
      const last = updated[updated.length - 1]
      if (last.role === 'assistant') {
        updated[updated.length - 1] = {
          ...last,
          sources: event.sources ?? [],
        }
      }
      return updated
    })

=============================================================
UPDATE 3: frontend/src/app/sources/sources-panel.component.ts
=============================================================

Replace the placeholder with full implementation:

  @Component({
    selector: 'app-sources-panel',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './sources-panel.component.html',
    styleUrls: ['./sources-panel.component.scss'],
  })
  export class SourcesPanelComponent {
    sources = input<SourceReference[]>([])
    isVisible = computed(() => this.sources().length > 0)
  }

Write sources-panel.component.html:
  <div class="sources-panel" *ngIf="isVisible()">
    <div class="sources-header">
      <span class="icon">📎</span>
      <span>Sources ({{ sources().length }})</span>
    </div>
    <div class="source-list">
      <div *ngFor="let source of sources(); let i = index"
           class="source-item">
        <div class="source-number">[{{ i + 1 }}]</div>
        <div class="source-details">
          <div class="source-doc">{{ source.document }}</div>
          <div class="source-ref" *ngIf="source.section">
            Section {{ source.section }}
            <span *ngIf="source.page"> · Page {{ source.page }}</span>
          </div>
          <div class="source-excerpt" *ngIf="source.excerpt">
            "{{ source.excerpt }}"
          </div>
        </div>
      </div>
    </div>
  </div>

Write sources-panel.component.scss:
  .sources-panel {
    border-top: 1px solid var(--border);
    padding: 12px 16px;
    background: var(--surface);
  }
  .sources-header {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; font-weight: 600;
    color: var(--teal); margin-bottom: 10px;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .source-list { display: flex; flex-direction: column; gap: 8px; }
  .source-item {
    display: flex; gap: 10px; align-items: flex-start;
  }
  .source-number {
    font-size: 11px; color: var(--teal); font-weight: 700;
    min-width: 20px; padding-top: 2px;
  }
  .source-doc {
    font-size: 12px; color: var(--text); font-weight: 500;
  }
  .source-ref {
    font-size: 11px; color: var(--text-muted); margin-top: 2px;
  }
  .source-excerpt {
    font-size: 11px; color: var(--text-muted);
    font-style: italic; margin-top: 4px;
    border-left: 2px solid var(--teal); padding-left: 8px;
  }

=============================================================
UPDATE 4: frontend/src/app/chat/chat.component.html
=============================================================

Add sources panel below each assistant message.
Update the app-message loop to include sources below it:

  Replace:
    <app-message
      *ngFor="let msg of messages(); trackBy: trackById"
      [msg]="msg"
      [showDisclaimer]="msg.role === 'assistant' && !msg.isStreaming">
    </app-message>

  With:
    <ng-container *ngFor="let msg of messages(); trackBy: trackById">
      <app-message
        [msg]="msg"
        [showDisclaimer]="msg.role === 'assistant' && !msg.isStreaming">
      </app-message>
      <app-sources-panel
        *ngIf="msg.role === 'assistant' && msg.sources?.length"
        [sources]="msg.sources!">
      </app-sources-panel>
    </ng-container>

Add SourcesPanelComponent to chat.component.ts imports array.