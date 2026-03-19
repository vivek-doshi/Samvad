// SessionService — manages conversation session state
// Note 1: This service owns all session-related state and API calls. It uses
// Angular signals (signal(), computed()) to store state and Angular's HttpClient
// for REST API communication. The ChatComponent and SidebarComponent both inject
// this service to stay in sync with the same session state.
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { inject, signal } from '@angular/core';
import { map, Observable, tap } from 'rxjs';
import { environment } from '../../environments/environment';
import { SourceReference } from '../models/message.model';
import { SessionListItem, TurnResponse } from '../models/session.model';
import { AuthService } from './auth';

// Note 2: These private interfaces mirror the backend's API response shape
// (snake_case from Python) and are only used inside this service for mapping.
// They are NOT exported because the rest of the app uses the camelCase models.
interface SessionApiResponse {
  session_id: string;
  title: string;
  status: 'active' | 'closed' | 'archived';
  total_turns: number;
  domain_last: string | null;
  created_at: string;
  last_active_at: string;
}

interface TurnApiResponse {
  turn_id: string;
  session_id: string;
  turn_number: number;
  role: string;
  content: string;
  domain: string | null;
  sources_cited: SourceReference[] | null;
  created_at: string;
}

@Injectable({
  providedIn: 'root',
})
export class SessionService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);

  // Note 3: These three signals form the service's "state". Any component that
  // reads these signals will automatically re-render when the signal value changes.
  // - sessions     : all sessions for the current user (shown in sidebar)
  // - activeSession: the currently selected/active session
  // - isLoading    : true while the session list is being fetched
  readonly sessions = signal<SessionListItem[]>([]);
  readonly activeSession = signal<SessionListItem | null>(null);
  readonly isLoadingSessions = signal(false);

  loadSessions(): Observable<SessionListItem[]> {
    const url = `${environment.apiBaseUrl}${environment.sessionsEndpoint}`;
    this.isLoadingSessions.set(true);

    return this.http
      .get<SessionApiResponse[]>(url, { headers: this.auth.getAuthHeaders() })
      .pipe(
        map((rows) =>
          rows.map((row) => ({
            sessionId: row.session_id,
            title: row.title,
            status: row.status,
            totalTurns: row.total_turns,
            domainLast: row.domain_last ?? undefined,
            lastActiveAt: new Date(row.last_active_at),
          })),
        ),
        tap((mapped) => {
          this.sessions.set(mapped);
          const active = mapped.find((s) => s.status === 'active') ?? null;
          this.activeSession.set(active);
          this.isLoadingSessions.set(false);
        }),
      );
  }

  createSession(): Observable<SessionListItem> {
    const url = `${environment.apiBaseUrl}${environment.sessionsEndpoint}`;
    return this.http
      .post<SessionApiResponse>(url, {}, { headers: this.auth.getAuthHeaders() })
      .pipe(
        map((row) => ({
          sessionId: row.session_id,
          title: row.title,
          status: row.status,
          totalTurns: row.total_turns,
          domainLast: row.domain_last ?? undefined,
          lastActiveAt: new Date(row.last_active_at),
        })),
        tap((mapped) => {
          // Note 4: sessions.update() is the Angular signal equivalent of setState
          // with an updater function. We prepend the new session and filter out
          // any existing session with the same ID (in case of concurrent creates).
          this.sessions.update((items) => [mapped, ...items.filter((s) => s.sessionId !== mapped.sessionId)]);
          this.activeSession.set(mapped);
        }),
      );
  }

  loadSessionTurns(sessionId: string): Observable<TurnResponse[]> {
    const url = `${environment.apiBaseUrl}${environment.sessionsEndpoint}/${sessionId}/turns`;
    return this.http
      .get<TurnApiResponse[]>(url, { headers: this.auth.getAuthHeaders() })
      .pipe(
        map((rows) =>
          rows.map((row) => ({
            turnId: row.turn_id,
            sessionId: row.session_id,
            turnNumber: row.turn_number,
            role: row.role,
            content: row.content,
            domain: row.domain,
            sourcesCited: row.sources_cited ?? [],
            createdAt: new Date(row.created_at),
          })),
        ),
      );
  }

  setActiveSession(sessionId: string): void {
    const found = this.sessions().find((session) => session.sessionId === sessionId) ?? null;
    this.activeSession.set(found);
  }

  updateSessionTitle(sessionId: string, title: string): Observable<void> {
    const url = `${environment.apiBaseUrl}${environment.sessionsEndpoint}/${sessionId}`;
    return this.http.patch(url, { title }, { headers: this.auth.getAuthHeaders() }).pipe(
      tap(() => {
        this.sessions.update((items) =>
          items.map((item) => (item.sessionId === sessionId ? { ...item, title } : item)),
        );
      }),
      map(() => void 0),
    );
  }

  archiveSession(sessionId: string): Observable<void> {
    const url = `${environment.apiBaseUrl}${environment.sessionsEndpoint}/${sessionId}`;
    return this.http.delete(url, { headers: this.auth.getAuthHeaders() }).pipe(
      tap(() => {
        this.sessions.update((items) => items.filter((item) => item.sessionId !== sessionId));
        if (this.activeSession()?.sessionId === sessionId) {
          this.activeSession.set(null);
        }
      }),
      map(() => void 0),
    );
  }

  clearState(): void {
    this.sessions.set([]);
    this.activeSession.set(null);
  }
}
