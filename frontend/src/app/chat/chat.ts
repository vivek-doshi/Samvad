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

  @ViewChild('messageContainer') messageContainer!: ElementRef<HTMLDivElement>;
  @ViewChild('inputField') inputField!: ElementRef<HTMLTextAreaElement>;

  readonly messages = signal<Message[]>([]);
  readonly isStreaming = signal(false);
  readonly inputText = signal('');
  readonly sessions = signal<SessionListItem[]>([]);
  readonly activeSessionId = signal<string | null>(null);
  readonly charCount = computed(() => this.inputText().length);

  private streamSub: Subscription | null = null;
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
    if (this.isStreaming() || this.inputText().trim() === '' || this.charCount() > 2000) {
      return;
    }

    const query = this.inputText().trim();
    const msgId = crypto.randomUUID();

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
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      if (isNearBottom) {
        el.scrollTop = el.scrollHeight;
      }
    } catch {
      // Ignore scroll failures in non-rendered or early lifecycle states.
    }
  }

  private autoResizeInput(): void {
    queueMicrotask(() => {
      const textarea = this.inputField?.nativeElement;
      if (!textarea) {
        return;
      }
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 96)}px`;
    });
  }

  ngOnDestroy(): void {
    this.streamSub?.unsubscribe();
    this.chatService.cancelStream();
  }

}

