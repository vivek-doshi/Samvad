import { TestBed } from '@angular/core/testing';
import { ChatService } from './chat';
import { AuthService } from './auth';
import { ReadableStream as PolyRS } from 'node:stream/web';

if (typeof globalThis.ReadableStream === 'undefined') {
  (globalThis as any).ReadableStream = PolyRS;
}

describe('ChatService', () => {
  let service: ChatService;
  let authStub: { getAuthHeaders: ReturnType<typeof vi.fn> };
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    authStub = {
      getAuthHeaders: vi.fn().mockReturnValue({ Authorization: 'Bearer test-token' }),
    };

    TestBed.configureTestingModule({
      providers: [{ provide: AuthService, useValue: authStub }],
    });
    service = TestBed.inject(ChatService);

    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function makeStream(lines: string[]): ReadableStream<Uint8Array> {
    const encoder = new TextEncoder();
    const chunks = lines.map((l) => encoder.encode(l + '\n'));
    let index = 0;
    return new ReadableStream({
      pull(controller) {
        if (index < chunks.length) {
          controller.enqueue(chunks[index++]);
        } else {
          controller.close();
        }
      },
    });
  }

  describe('sendMessage', () => {
    it('should stream tokens and complete on done event', () => {
      const stream = makeStream([
        'data: {"token":"Hello","done":false}',
        'data: {"token":" world","done":false}',
        'data: {"token":"","done":true,"sources":[{"document":"doc.pdf"}]}',
      ]);

      fetchSpy.mockResolvedValue({
        ok: true,
        body: stream,
      } as unknown as Response);

      const events: any[] = [];
      service.sendMessage('hi', 'sess1', null).subscribe({
        next: (e) => events.push(e),
        complete: () => {
          expect(events.length).toBeGreaterThanOrEqual(2);
          expect(events[0].token).toBe('Hello');
          expect(events[1].token).toBe(' world');
        },
      });
    });

    it('should error on non-ok HTTP response', () =>
      new Promise<void>((done) => {
        fetchSpy.mockResolvedValue({
          ok: false,
          status: 500,
        } as unknown as Response);

        service.sendMessage('hi', null, null).subscribe({
          error: (err: Error) => {
            expect(err.message).toBe('HTTP 500');
            done();
          },
        });
      }));

    it('should error when response has no body', () =>
      new Promise<void>((done) => {
        fetchSpy.mockResolvedValue({
          ok: true,
          body: null,
        } as unknown as Response);

        service.sendMessage('hi', null, null).subscribe({
          error: (err: Error) => {
            expect(err.message).toBe('No response body');
            done();
          },
        });
      }));

    it('should error on server error event', () =>
      new Promise<void>((done) => {
        const stream = makeStream([
          'data: {"token":"","done":true,"error":"LLM unavailable"}',
        ]);
        fetchSpy.mockResolvedValue({ ok: true, body: stream } as unknown as Response);

        service.sendMessage('hi', null, null).subscribe({
          error: (err: Error) => {
            expect(err.message).toBe('LLM unavailable');
            done();
          },
        });
      }));

    it('should pass correct request body and headers', () => {
      const stream = makeStream(['data: {"token":"","done":true}']);
      fetchSpy.mockResolvedValue({ ok: true, body: stream } as unknown as Response);

      service.sendMessage('query', 'sess1', 'tax').subscribe();

      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('/api/chat'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Authorization: 'Bearer test-token',
          }),
        }),
      );

      const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
      expect(body).toEqual({ query: 'query', session_id: 'sess1', domain: 'tax' });
    });

    it('should ignore non-data lines', () =>
      new Promise<void>((done) => {
        const stream = makeStream([
          ':keepalive',
          '',
          'data: {"token":"ok","done":false}',
          'data: {"token":"","done":true}',
        ]);
        fetchSpy.mockResolvedValue({ ok: true, body: stream } as unknown as Response);

        const tokens: string[] = [];
        service.sendMessage('hi', null, null).subscribe({
          next: (e) => tokens.push(e.token),
          complete: () => {
            expect(tokens).toContain('ok');
            done();
          },
        });
      }));

    it('should handle malformed JSON gracefully', () =>
      new Promise<void>((done) => {
        const stream = makeStream([
          'data: {bad json',
          'data: {"token":"","done":true}',
        ]);
        fetchSpy.mockResolvedValue({ ok: true, body: stream } as unknown as Response);

        service.sendMessage('hi', null, null).subscribe({
          complete: () => done(),
        });
      }));
  });

  describe('cancelStream', () => {
    it('should abort inflight request', () => {
      const abortSpy = vi.fn();
      const mockController = { abort: abortSpy, signal: new AbortController().signal };
      (service as any).abortController = mockController;

      service.cancelStream();

      expect(abortSpy).toHaveBeenCalled();
      expect((service as any).abortController).toBeNull();
    });

    it('should be safe to call when no stream is active', () => {
      expect(() => service.cancelStream()).not.toThrow();
    });
  });
});
