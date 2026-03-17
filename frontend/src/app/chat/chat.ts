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
import { SessionListItem } from '../models/session.model';
import { AuthService } from '../services/auth';
import { ChatService } from '../services/chat';
import { MessageComponent } from '../shared/message/message';
import { SidebarComponent } from '../sidebar/sidebar';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, MessageComponent, SidebarComponent],
  templateUrl: './chat.html',
  styleUrl: './chat.scss',
})
export class ChatComponent implements OnInit, OnDestroy {
  private readonly chatService = inject(ChatService);
  readonly authService = inject(AuthService);

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
    const tempId = crypto.randomUUID();
    this.activeSessionId.set(tempId);
    // TODO: [PHASE 2] Load active session from SessionService
    // TODO: [PHASE 2] Load session history list
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
                  sources: event.sources ?? last.sources,
                };
              }
              return updated;
            });
            this.scrollToBottom();
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

  onNewSession(): void {
    this.messages.set([]);
    this.activeSessionId.set(crypto.randomUUID());
    this.inputText.set('');
    this.autoResizeInput();
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

