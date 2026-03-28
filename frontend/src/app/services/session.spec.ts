import { TestBed } from '@angular/core/testing';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { SessionService } from './session';
import { AuthService } from './auth';
import { environment } from '../../environments/environment';

function createAuthServiceStub() {
  return {
    getAuthHeaders: vi.fn().mockReturnValue({ Authorization: 'Bearer test-token' }),
  };
}

describe('SessionService', () => {
  let service: SessionService;
  let httpTesting: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: createAuthServiceStub() },
      ],
    });

    service = TestBed.inject(SessionService);
    httpTesting = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpTesting.verify());

  const baseUrl = `${environment.apiBaseUrl}${environment.sessionsEndpoint}`;

  const apiSession = (id: string, status: 'active' | 'closed' = 'active') => ({
    session_id: id,
    title: `Session ${id}`,
    status,
    total_turns: 5,
    domain_last: null,
    created_at: '2025-01-01T00:00:00Z',
    last_active_at: '2025-01-02T00:00:00Z',
  });

  describe('loadSessions', () => {
    it('should fetch sessions and set signals', () => {
      const responseSpy = vi.fn();
      service.loadSessions().subscribe(responseSpy);

      const req = httpTesting.expectOne(baseUrl);
      expect(req.request.method).toBe('GET');
      req.flush([apiSession('s1'), apiSession('s2', 'closed')]);

      expect(responseSpy).toHaveBeenCalled();
      const sessions = service.sessions();
      expect(sessions).toHaveLength(2);
      expect(sessions[0].sessionId).toBe('s1');
      expect(sessions[0].status).toBe('active');
      expect(sessions[1].sessionId).toBe('s2');
    });

    it('should set activeSession to first active session', () => {
      service.loadSessions().subscribe();

      httpTesting
        .expectOne(baseUrl)
        .flush([apiSession('s1', 'closed'), apiSession('s2', 'active')]);

      expect(service.activeSession()?.sessionId).toBe('s2');
    });

    it('should set activeSession to null when none active', () => {
      service.loadSessions().subscribe();

      httpTesting.expectOne(baseUrl).flush([apiSession('s1', 'closed')]);

      expect(service.activeSession()).toBeNull();
    });

    it('should set isLoadingSessions correctly', () => {
      expect(service.isLoadingSessions()).toBe(false);
      service.loadSessions().subscribe();
      // Loading is set immediately in loadSessions()
      const req = httpTesting.expectOne(baseUrl);
      req.flush([]);
      expect(service.isLoadingSessions()).toBe(false);
    });

    it('should map domain_last null to undefined', () => {
      service.loadSessions().subscribe();
      httpTesting.expectOne(baseUrl).flush([apiSession('s1')]);
      expect(service.sessions()[0].domainLast).toBeUndefined();
    });

    it('should map domain_last string correctly', () => {
      const session = { ...apiSession('s1'), domain_last: 'tax' };
      service.loadSessions().subscribe();
      httpTesting.expectOne(baseUrl).flush([session]);
      expect(service.sessions()[0].domainLast).toBe('tax');
    });
  });

  describe('createSession', () => {
    it('should POST and add session to list', () => {
      service.createSession().subscribe();

      const req = httpTesting.expectOne(baseUrl);
      expect(req.request.method).toBe('POST');
      req.flush(apiSession('new1'));

      expect(service.sessions()[0].sessionId).toBe('new1');
      expect(service.activeSession()?.sessionId).toBe('new1');
    });

    it('should replace existing session with same id', () => {
      // Pre-load sessions
      service.loadSessions().subscribe();
      httpTesting.expectOne(baseUrl).flush([apiSession('s1')]);

      service.createSession().subscribe();
      httpTesting.expectOne(baseUrl).flush(apiSession('s1'));

      const count = service.sessions().filter((s) => s.sessionId === 's1').length;
      expect(count).toBe(1);
    });
  });

  describe('loadSessionTurns', () => {
    it('should map turn response correctly', () => {
      const turnsSpy = vi.fn();
      service.loadSessionTurns('s1').subscribe(turnsSpy);

      const url = `${baseUrl}/s1/turns`;
      const req = httpTesting.expectOne(url);
      expect(req.request.method).toBe('GET');
      req.flush([
        {
          turn_id: 't1',
          session_id: 's1',
          turn_number: 1,
          role: 'user',
          content: 'Hello',
          domain: 'tax',
          sources_cited: [{ document: 'doc.pdf', section: '1.1' }],
          created_at: '2025-01-01T00:00:00Z',
        },
      ]);

      const turns = turnsSpy.mock.calls[0][0];
      expect(turns).toHaveLength(1);
      expect(turns[0].turnId).toBe('t1');
      expect(turns[0].role).toBe('user');
      expect(turns[0].domain).toBe('tax');
      expect(turns[0].sourcesCited).toHaveLength(1);
    });

    it('should default null sources_cited to empty array', () => {
      const turnsSpy = vi.fn();
      service.loadSessionTurns('s1').subscribe(turnsSpy);

      httpTesting.expectOne(`${baseUrl}/s1/turns`).flush([
        {
          turn_id: 't1',
          session_id: 's1',
          turn_number: 1,
          role: 'assistant',
          content: 'Hi',
          domain: null,
          sources_cited: null,
          created_at: '2025-01-01T00:00:00Z',
        },
      ]);

      expect(turnsSpy.mock.calls[0][0][0].sourcesCited).toEqual([]);
    });
  });

  describe('setActiveSession', () => {
    it('should set activeSession when session exists', () => {
      service.loadSessions().subscribe();
      httpTesting.expectOne(baseUrl).flush([apiSession('s1'), apiSession('s2')]);

      service.setActiveSession('s2');
      expect(service.activeSession()?.sessionId).toBe('s2');
    });

    it('should set null if session not found', () => {
      service.loadSessions().subscribe();
      httpTesting.expectOne(baseUrl).flush([apiSession('s1')]);

      service.setActiveSession('nonexistent');
      expect(service.activeSession()).toBeNull();
    });
  });

  describe('updateSessionTitle', () => {
    it('should PATCH and update session in list', () => {
      service.loadSessions().subscribe();
      httpTesting.expectOne(baseUrl).flush([apiSession('s1')]);

      service.updateSessionTitle('s1', 'New Title').subscribe();

      const req = httpTesting.expectOne(`${baseUrl}/s1`);
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body).toEqual({ title: 'New Title' });
      req.flush({});

      expect(service.sessions()[0].title).toBe('New Title');
    });

    it('should not change other sessions', () => {
      service.loadSessions().subscribe();
      httpTesting
        .expectOne(baseUrl)
        .flush([apiSession('s1'), apiSession('s2')]);

      service.updateSessionTitle('s1', 'Changed').subscribe();
      httpTesting.expectOne(`${baseUrl}/s1`).flush({});

      expect(service.sessions().find((s) => s.sessionId === 's2')?.title).toBe(
        'Session s2',
      );
    });
  });

  describe('archiveSession', () => {
    it('should DELETE and remove session from list', () => {
      service.loadSessions().subscribe();
      httpTesting.expectOne(baseUrl).flush([apiSession('s1'), apiSession('s2')]);

      service.archiveSession('s1').subscribe();

      const req = httpTesting.expectOne(`${baseUrl}/s1`);
      expect(req.request.method).toBe('DELETE');
      req.flush({});

      expect(service.sessions()).toHaveLength(1);
      expect(service.sessions()[0].sessionId).toBe('s2');
    });

    it('should clear activeSession if archived session was active', () => {
      service.loadSessions().subscribe();
      httpTesting.expectOne(baseUrl).flush([apiSession('s1')]);

      expect(service.activeSession()?.sessionId).toBe('s1');

      service.archiveSession('s1').subscribe();
      httpTesting.expectOne(`${baseUrl}/s1`).flush({});

      expect(service.activeSession()).toBeNull();
    });

    it('should not clear activeSession if different session archived', () => {
      service.loadSessions().subscribe();
      httpTesting
        .expectOne(baseUrl)
        .flush([apiSession('s1', 'active'), apiSession('s2', 'closed')]);

      service.archiveSession('s2').subscribe();
      httpTesting.expectOne(`${baseUrl}/s2`).flush({});

      expect(service.activeSession()?.sessionId).toBe('s1');
    });
  });

  describe('clearState', () => {
    it('should reset sessions and activeSession', () => {
      service.loadSessions().subscribe();
      httpTesting.expectOne(baseUrl).flush([apiSession('s1')]);

      expect(service.sessions()).toHaveLength(1);
      service.clearState();

      expect(service.sessions()).toHaveLength(0);
      expect(service.activeSession()).toBeNull();
    });
  });
});
