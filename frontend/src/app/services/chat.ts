import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { ChatRequest, ChatStreamEvent } from '../models/message.model';
import { AuthService } from './auth';

@Injectable({
  providedIn: 'root',
})
export class ChatService {
  private abortController: AbortController | null = null;
  private readonly authService = inject(AuthService);

  sendMessage(
    query: string,
    sessionId: string | null,
    domain: string | null,
  ): Observable<ChatStreamEvent> {
    return new Observable<ChatStreamEvent>((subscriber) => {
      const controller = new AbortController();
      this.abortController = controller;

      const url = `${environment.apiBaseUrl}${environment.chatEndpoint}`;
      const body: ChatRequest = { query, session_id: sessionId, domain };
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        Authorization: this.authService.getAuthHeaders().Authorization,
      };

      const timeoutId = setTimeout(() => {
        controller.abort();
      }, environment.sseTimeout);

      const parseLine = (line: string): boolean => {
        if (!line.startsWith('data: ')) {
          return false;
        }

        const jsonPayload = line.slice(6).trim();
        if (!jsonPayload) {
          return false;
        }

        try {
          const event = JSON.parse(jsonPayload) as ChatStreamEvent;
          if (event.done && event.error) {
            subscriber.error(new Error(event.error));
            return true;
          }

          if (event.done) {
            subscriber.complete();
            return true;
          }

          subscriber.next(event);
          return false;
        } catch {
          return false;
        }
      };

      void (async () => {
        try {
          const response = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
            signal: controller.signal,
          });

          if (!response.ok) {
            subscriber.error(new Error(`HTTP ${response.status}`));
            return;
          }

          if (!response.body) {
            subscriber.error(new Error('No response body'));
            return;
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';

            for (const rawLine of lines) {
              const line = rawLine.replace(/\r$/, '').trim();
              if (!line) {
                continue;
              }
              const stop = parseLine(line);
              if (stop) {
                return;
              }
            }
          }

          if (buffer.trim().length > 0) {
            parseLine(buffer.trim());
          }

          subscriber.complete();
        } catch (error) {
          const err = error as DOMException;
          if (err.name === 'AbortError') {
            subscriber.complete();
            return;
          }
          subscriber.error(error);
        } finally {
          clearTimeout(timeoutId);
          if (this.abortController === controller) {
            this.abortController = null;
          }
        }
      })();

      return () => {
        clearTimeout(timeoutId);
        controller.abort();
        if (this.abortController === controller) {
          this.abortController = null;
        }
      };
    });
  }

  cancelStream(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }
}
