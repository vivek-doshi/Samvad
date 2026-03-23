// ChatComponent — main conversation UI controller
// Note 1: This is the most complex component in Samvad. It manages:
// - The messages list (user messages + streaming assistant responses)
// - Sending messages via ChatService and receiving SSE token streams
// - Loading/switching conversation sessions via SessionService
// - Keyboard shortcuts (Enter to send, Shift+Enter for newline, Escape to cancel)
// - Auto-scrolling and textarea auto-resize
import { CommonModule } from '@angular/common';
import {
  Component,
  computed,
  ElementRef,
  inject,
  OnDestroy,
  OnInit,
  signal,
  ViewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { ChatStreamEvent, Message } from '../models/message.model';
import { SessionListItem, TurnResponse } from '../models/session.model';
import { Router } from '@angular/router';
import { AuthService } from '../services/auth';
import { ChatService } from '../services/chat';
import { SessionService } from '../services/session';
import { MessageComponent } from '../shared/message/message';
import { SidebarComponent } from '../sidebar/sidebar';
import { SourcesPanelComponent } from '../sources/sources-panel.component';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, MessageComponent, SidebarComponent, SourcesPanelComponent],
  templateUrl: './chat.html',
  styleUrl: './chat.scss',
})
export class ChatComponent implements OnInit, OnDestroy {
  private readonly chatService = inject(ChatService);
  private readonly sessionService = inject(SessionService);
  private readonly router = inject(Router);
  public readonly authService = inject(AuthService);

  // Note 2: @ViewChild grabs a reference to a DOM element in the template.
  // 'messageContainer' is used for auto-scroll detection; 'inputField' for
  // auto-resize. The '!' (non-null assertion) tells TypeScript the element
  // will be available after ngAfterViewInit — Angular wires this up automatically.
  @ViewChild('messageContainer') messageContainer!: ElementRef<HTMLDivElement>;
  @ViewChild('inputField') inputField!: ElementRef<HTMLTextAreaElement>;

  // Note 3: All UI state is stored in Angular signals. Unlike class properties,
  // signal changes trigger fine-grained re-rendering of only the affected DOM nodes.
  readonly messages = signal<Message[]>([]);
  readonly isStreaming = signal(false);
  readonly inputText = signal('');
  readonly sessions = signal<SessionListItem[]>([]);
  readonly activeSessionId = signal<string | null>(null);
  // Note 4: computed() creates a derived signal. charCount auto-recalculates
  // whenever inputText changes — no manual update needed. The template uses this
  // to display the character counter and disable the send button at 2000 chars.
  readonly charCount = computed(() => this.inputText().length);

  // Note 5: Subscription tracks the active RxJS subscription to the chat stream.
  // We store it so we can unsubscribe (cancel the stream) when needed.
  private streamSub: Subscription | null = null;
  // Note 6: streamStart records the timestamp when streaming began so we can
  // calculate total latency (time from send to last token) for the UI display.
  private streamStart = 0;

  ngOnInit(): void {
    this.sessionService.loadSessions().subscribe({
      next: (sessions) => {
        this.sessions.set(sessions);
        const active = sessions.find((s) => s.status === 'active');
        if (active) {
          this.activeSessionId.set(active.sessionId);
          this.sessionService.setActiveSession(active.sessionId);
          this.loadSessionTurns(active.sessionId);
        } else {
          this.createNewSession();
        }
      },
      error: (err) => {
        if (err.status === 401) {
          this.router.navigate(['/login']);
        }
      },
    });
  }

  sendMessage(): void {
    // Note 7: Guard conditions prevent sending: if already streaming (waiting
    // for previous response), if the input is empty/whitespace, or if the user
    // has exceeded the 2000-character limit configured in samvad.yaml.
    if (this.isStreaming() || this.inputText().trim() === '' || this.charCount() > 2000) {
      return;
    }

    const query = this.inputText().trim();
    // Note 8: crypto.randomUUID() generates a client-side UUID for each message.
    // This gives each message a stable identity for Angular's *ngFor trackBy
    // function, preventing the entire message list from re-rendering on each
    // token update — only the affected assistant message re-renders.
    const msgId = crypto.randomUUID();

    // Optimistically add user message to the list before the API call
    this.messages.update((msgs) => [
      ...msgs,
      {
        id: msgId,
        role: 'user',
        content: query,
        isStreaming: false,
        timestamp: new Date(),
      },
    ]);

    this.inputText.set('');
    this.autoResizeInput();

    // Add a placeholder assistant message that will be filled with streaming tokens
    // Note 9: We add the assistant message IMMEDIATELY (before any API response)
    // so the user sees instant feedback that the system is processing. The 'isStreaming'
    // flag triggers a loading indicator in the MessageComponent template.
    const assistantId = crypto.randomUUID();
    this.messages.update((msgs) => [
      ...msgs,
      {
        id: assistantId,
        role: 'assistant',
        content: '',
        isStreaming: true,
        timestamp: new Date(),
      },
    ]);

    this.isStreaming.set(true);
    this.streamStart = Date.now();
    this.streamSub?.unsubscribe();

    this.streamSub = this.chatService
      .sendMessage(query, this.activeSessionId(), null)
      .subscribe({
        next: (event: ChatStreamEvent) => {
          if (!event.done) {
            this.messages.update((msgs) => {
              const updated = [...msgs];
              const last = updated[updated.length - 1];
              if (last && last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + event.token,
                };
              }
              return updated;
            });
            this.scrollToBottom();
          } else if (event.done) {
            this.messages.update((msgs) => {
              const updated = [...msgs];
              const last = updated[updated.length - 1];
              if (last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  sources: event.sources ?? [],
                };
              }
              return updated;
            });
          }
        },
        error: (err: Error) => {
          this.messages.update((msgs) => {
            const updated = [...msgs];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant') {
              updated[updated.length - 1] = {
                ...last,
                isStreaming: false,
                error: err.message || 'Stream error',
              };
            }
            return updated;
          });
          this.isStreaming.set(false);
        },
        complete: () => {
          this.messages.update((msgs) => {
            const updated = [...msgs];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant') {
              updated[updated.length - 1] = {
                ...last,
                isStreaming: false,
                latencyMs: Date.now() - this.streamStart,
              };
            }
            return updated;
          });
          this.isStreaming.set(false);
          this.scrollToBottom();
          this.sessionService.loadSessions().subscribe({
            next: (sessions) => this.sessions.set(sessions),
          });
        },
      });
  }

  cancelStream(): void {
    this.chatService.cancelStream();
    this.streamSub?.unsubscribe();
    this.messages.update((msgs) => {
      const updated = [...msgs];
      const last = updated[updated.length - 1];
      if (last?.role === 'assistant' && last.isStreaming) {
        updated[updated.length - 1] = { ...last, isStreaming: false };
      }
      return updated;
    });
    this.isStreaming.set(false);
  }

  onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
      return;
    }

    if (event.key === 'Escape') {
      this.cancelStream();
    }
  }

  onInput(event: Event): void {
    this.inputText.set((event.target as HTMLTextAreaElement).value);
    this.autoResizeInput();
  }

  createNewSession(): void {
    this.sessionService.createSession().subscribe({
      next: (session) => {
        this.activeSessionId.set(session.sessionId);
        this.sessionService.setActiveSession(session.sessionId);
        this.sessions.set(this.sessionService.sessions());
        this.messages.set([]);
      },
      error: () => {
        // Session is optional for current flow; keep chat usable.
      },
    });
  }

  private loadSessionTurns(sessionId: string): void {
    this.sessionService.loadSessionTurns(sessionId).subscribe({
      next: (turns: TurnResponse[]) => {
        const messages: Message[] = turns.map((turn) => ({
          id: turn.turnId,
          role: turn.role as 'user' | 'assistant',
          content: turn.content,
          isStreaming: false,
          domain: turn.domain ?? undefined,
          sources: turn.sourcesCited,
          timestamp: turn.createdAt,
        }));
        this.messages.set(messages);
        setTimeout(() => this.scrollToBottom(), 100);
      },
      error: () => {
        // Ignore history load errors to avoid blocking chat input.
      },
    });
  }

  onSessionSelected(sessionId: string): void {
    if (sessionId === this.activeSessionId()) {
      return;
    }
    this.activeSessionId.set(sessionId);
    this.sessionService.setActiveSession(sessionId);
    this.messages.set([]);
    this.loadSessionTurns(sessionId);
  }

  onNewSession(): void {
    this.createNewSession();
  }

  trackById(_index: number, msg: Message): string {
    return msg.id;
  }

  private scrollToBottom(): void {
    try {
      const el = this.messageContainer.nativeElement;
      // Note 10: We only auto-scroll if the user is already near the bottom.
      // 120px tolerance means: if the user has scrolled up more than 120px,
      // don't interrupt them by jumping to the bottom. This is a common UX
      // pattern in chat apps — don't hijack the scroll while the user is reading.
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      if (isNearBottom) {
        el.scrollTop = el.scrollHeight;
      }
    } catch {
      // Ignore scroll failures in non-rendered or early lifecycle states.
    }
  }

  private autoResizeInput(): void {
    // Note 11: queueMicrotask() schedules the resize to run AFTER Angular has
    // updated the DOM with the new input value. Without this delay, textarea.scrollHeight
    // would reflect the old content height, giving incorrect resize dimensions.
    queueMicrotask(() => {
      const textarea = this.inputField?.nativeElement;
      if (!textarea) {
        return;
      }
      textarea.style.height = 'auto';
      // Note 12: Math.min(scrollHeight, 96) caps the textarea at 96px (about 4 lines).
      // Setting height to 'auto' first forces the browser to recalculate scrollHeight
      // based on content, then we set the actual height capped at the maximum.
      textarea.style.height = `${Math.min(textarea.scrollHeight, 96)}px`;
    });
  }

  ngOnDestroy(): void {
    // Note 13: Always unsubscribe from Observables in ngOnDestroy to prevent
    // memory leaks. If ChatComponent is destroyed while a stream is in progress,
    // the subscription would otherwise keep trying to update destroyed component state.
    this.streamSub?.unsubscribe();
    this.chatService.cancelStream();
  }

}

