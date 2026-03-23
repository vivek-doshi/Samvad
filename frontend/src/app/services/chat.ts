// ChatService — streams LLM responses using Server-Sent Events (SSE)
// Note 1: ChatService communicates with the FastAPI /api/chat endpoint using
// the native browser Fetch API (not Angular HttpClient). This is because
// Angular's HttpClient does not support streaming responses — it waits for the
// full response before emitting. Fetch API with ReadableStream allows reading
// the SSE byte-by-byte as tokens arrive from the LLM.
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { ChatRequest, ChatStreamEvent } from '../models/message.model';
import { AuthService } from './auth';

@Injectable({
  providedIn: 'root',
})
export class ChatService {
  // Note 2: AbortController provides a way to cancel an in-progress fetch request.
  // When the user cancels a stream or navigates away, we call controller.abort()
  // which immediately closes the connection and stops token streaming.
  private abortController: AbortController | null = null;
  private readonly authService = inject(AuthService);

  sendMessage(
    query: string,
    sessionId: string | null,
    domain: string | null,
  ): Observable<ChatStreamEvent> {
    // Note 3: We wrap the Fetch API call inside an Observable so the ChatComponent
    // can use Angular's standard subscribe/unsubscribe pattern. The Observable's
    // subscriber is called for each SSE event. When the user cancels (unsubscribes),
    // the teardown function at the end of the Observable aborts the fetch.
    return new Observable<ChatStreamEvent>((subscriber) => {
      const controller = new AbortController();
      this.abortController = controller;

      const url = `${environment.apiBaseUrl}${environment.chatEndpoint}`;
      const body: ChatRequest = { query, session_id: sessionId, domain };
      const headers: HeadersInit = {
        'Content-Type': 'application/json',
        Authorization: this.authService.getAuthHeaders().Authorization,
      };

      // Note 4: sseTimeout cancels the request if the LLM does not respond within
      // the configured timeout (default 120 seconds). This prevents the UI from
      // hanging indefinitely if the model server crashes mid-stream.
      const timeoutId = setTimeout(() => {
        controller.abort();
      }, environment.sseTimeout);

      // Note 5: parseLine() is called for each 'data: ...' line received from
      // the SSE stream. It returns true when the stream should stop (done=true
      // or an error occurred), allowing the outer loop to break cleanly.
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
            // Note 6: When the LLM finishes generating, the backend sends a
            // final SSE event with done=true and the sources array. We emit
            // this to the subscriber so ChatComponent can display source citations.
            subscriber.next({ token: '', done: true, sources: event.sources ?? [] });
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
          // Note 7: TextDecoder converts raw Uint8Array bytes to a UTF-8 string.
          // { stream: true } tells the decoder that more data is coming — important
          // for multi-byte characters (e.g. Unicode) that might be split across chunks.
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            // Note 8: lines.pop() removes and returns the LAST element of the array.
            // If the buffer ends mid-line (no trailing '\n'), the last partial line
            // is stored back into 'buffer' to be completed by the next read() chunk.
            // The '?? ''' handles the edge case where lines.pop() returns undefined
            // (an empty array) — this can happen if the chunk contains only '\n' chars.
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
