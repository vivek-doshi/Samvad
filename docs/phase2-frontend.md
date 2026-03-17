You are working on Samvad Angular 21 frontend.
Phase 2: wire up real auth and session history.
All components are already created — update existing files only.
Do not recreate files from scratch, make targeted changes.

Backend API contract (match exactly):

  POST /api/auth/login
    Body:    { username: string, password: string }
    Returns: { access_token: string, token_type: string,
               expires_in: number, user: UserResponse }

  POST /api/auth/logout
    Header:  Authorization: Bearer <token>
    Returns: { message: string }

  GET /api/auth/me
    Header:  Authorization: Bearer <token>
    Returns: UserResponse

  GET /api/sessions
    Header:  Authorization: Bearer <token>
    Returns: SessionResponse[]

  POST /api/sessions
    Header:  Authorization: Bearer <token>
    Returns: SessionResponse (newly created session)

  GET /api/sessions/{id}/turns
    Header:  Authorization: Bearer <token>
    Returns: TurnResponse[]

  Where:
    UserResponse:    { user_id, username, display_name, role }
    SessionResponse: { session_id, title, status, total_turns,
                       domain_last, created_at, last_active_at }
    TurnResponse:    { turn_id, session_id, turn_number, role,
                       content, domain, sources_cited, created_at }

  Note: backend returns snake_case — map to camelCase in services.

=============================================================
UPDATE 1: frontend/src/app/services/auth.service.ts
=============================================================

The login() method currently calls the endpoint but may not
map the response correctly. Update it to:

  login(request: LoginRequest): Observable<void>
    POST to environment.apiBaseUrl + environment.authEndpoint + '/login'
    Body: { username: request.username, password: request.password }
    On success (LoginResponse received):
      - Store token: localStorage.setItem(TOKEN_KEY, response.access_token)
      - Map response.user (snake_case) to User (camelCase):
          { userId: response.user.user_id,
            username: response.user.username,
            displayName: response.user.display_name,
            role: response.user.role }
      - Store mapped user: localStorage.setItem(USER_KEY, JSON.stringify(user))
      - Update _token signal and _user signal
    Return pipe(map(() => void 0))
    — caller only needs to know success/failure, not the token value

Add method: refreshCurrentUser(): Observable<void>
    GET environment.apiBaseUrl + environment.authEndpoint + '/me'
    With Authorization header
    Update _user signal with mapped response
    Used on app startup to validate stored token is still good

=============================================================
UPDATE 2: frontend/src/app/services/session.service.ts
=============================================================

Create this file (it was empty). Full implementation:

  @Injectable({ providedIn: 'root' })
  export class SessionService {

    private http   = inject(HttpClient)
    private auth   = inject(AuthService)

    // Reactive state
    sessions        = signal<SessionListItem[]>([])
    activeSession   = signal<SessionListItem | null>(null)
    isLoadingSessions = signal(false)

    loadSessions(): Observable<SessionListItem[]>
      GET environment.apiBaseUrl + environment.sessionsEndpoint
      Headers: this.auth.getAuthHeaders()
      Map response array snake_case → camelCase SessionListItem:
        sessionId:    r.session_id
        title:        r.title
        totalTurns:   r.total_turns
        domainLast:   r.domain_last
        lastActiveAt: new Date(r.last_active_at)
      On success: sessions.set(mapped)
      Return mapped Observable

    createSession(): Observable<SessionListItem>
      POST environment.apiBaseUrl + environment.sessionsEndpoint
      Headers: this.auth.getAuthHeaders(), body: {}
      Map response snake_case → camelCase
      On success:
        Add to front of sessions signal
        Set as activeSession
      Return mapped Observable

    loadSessionTurns(sessionId: string): Observable<TurnResponse[]>
      GET environment.apiBaseUrl + environment.sessionsEndpoint
          + '/' + sessionId + '/turns'
      Headers: this.auth.getAuthHeaders()
      Map each turn:
        turnId:      t.turn_id
        sessionId:   t.session_id
        turnNumber:  t.turn_number
        role:        t.role
        content:     t.content
        domain:      t.domain
        sourcesCited: t.sources_cited ?? []
        createdAt:   new Date(t.created_at)
      Return mapped Observable

    setActiveSession(sessionId: string): void
      Find session in sessions signal by sessionId
      activeSession.set(found session or null)

    updateSessionTitle(sessionId: string, title: string): Observable<void>
      PATCH environment.apiBaseUrl + environment.sessionsEndpoint
            + '/' + sessionId
      Body: { title }
      Headers: this.auth.getAuthHeaders()
      On success: update title in sessions signal in-place
      Return pipe(map(() => void 0))

    archiveSession(sessionId: string): Observable<void>
      DELETE environment.apiBaseUrl + environment.sessionsEndpoint
             + '/' + sessionId
      Headers: this.auth.getAuthHeaders()
      On success: remove from sessions signal
      Return pipe(map(() => void 0))

    clearState(): void
      sessions.set([])
      activeSession.set(null)

=============================================================
UPDATE 3: frontend/src/app/chat/chat.component.ts
=============================================================

Replace the TODO placeholders in ngOnInit with real implementations.

Current ngOnInit:
  ngOnInit(): void
    Generate temp sessionId: crypto.randomUUID()
    activeSessionId.set(tempId)
    // TODO: [PHASE 2] Load active session from SessionService
    // TODO: [PHASE 2] Load session history list

Replace entirely with:

  ngOnInit(): void
    // Load session list for sidebar
    this.sessionService.loadSessions().subscribe({
      next: (sessions) => {
        this.sessions.set(sessions)
        // If there is an active session, load its turns
        const active = sessions.find(s => s.status === 'active')
        if (active) {
          this.activeSessionId.set(active.sessionId)
          this.loadSessionTurns(active.sessionId)
        } else {
          // No active session — create one
          this.createNewSession()
        }
      },
      error: (err) => {
        // Auth error — redirect to login
        if (err.status === 401) this.router.navigate(['/login'])
      }
    })

Add these methods to ChatComponent:

  private sessionService = inject(SessionService)
  private router         = inject(Router)

  createNewSession(): void
    this.sessionService.createSession().subscribe({
      next: (session) => {
        this.activeSessionId.set(session.sessionId)
        this.sessions.set(this.sessionService.sessions())
        this.messages.set([])
      },
      error: () => {} // silent fail — session is optional for Phase 1 flow
    })

  private loadSessionTurns(sessionId: string): void
    this.sessionService.loadSessionTurns(sessionId).subscribe({
      next: (turns) => {
        // Map TurnResponse[] to Message[]
        const messages: Message[] = turns.map(t => ({
          id: t.turnId,
          role: t.role as 'user' | 'assistant',
          content: t.content,
          isStreaming: false,
          domain: t.domain,
          sources: t.sourcesCited,
          timestamp: t.createdAt,
        }))
        this.messages.set(messages)
        // Scroll to bottom after loading history
        setTimeout(() => this.scrollToBottom(), 100)
      },
      error: () => {}
    })

  onSessionSelected(sessionId: string): void
    if (sessionId === this.activeSessionId()) return
    this.activeSessionId.set(sessionId)
    this.messages.set([])
    this.loadSessionTurns(sessionId)

  onNewSession(): void
    this.createNewSession()

Also update the sendMessage() method.
After the stream completes (in the complete: callback),
add a session turns reload to keep history fresh:
  // Refresh session list to update turn counts
  this.sessionService.loadSessions().subscribe({
    next: (sessions) => this.sessions.set(sessions)
  })

Also update the template bindings in chat.component.html:
  Change (onSessionSelect)="activeSessionId.set($event)"
  To:    (onSessionSelect)="onSessionSelected($event)"

  Change (onNewSession)="messages.set([])"
  To:    (onNewSession)="onNewSession()"

=============================================================
UPDATE 4: frontend/src/app/sidebar/sidebar.component.ts
=============================================================

Add logout button functionality.
Currently has: TODO: user profile + logout (Phase 2)

Add to component:
  private auth           = inject(AuthService)
  private sessionService = inject(SessionService)
  currentUser            = this.auth.currentUser

  logout(): void
    this.auth.logout()
    this.sessionService.clearState()

Update sidebar.component.html footer section.
Replace the TODO comment with:

  <div class="sidebar-footer">
    <div class="user-info" *ngIf="currentUser()">
      <div class="user-avatar">{{ currentUser()!.displayName[0].toUpperCase() }}</div>
      <div class="user-details">
        <div class="user-name">{{ currentUser()!.displayName }}</div>
        <div class="user-role">{{ currentUser()!.role }}</div>
      </div>
      <button class="logout-btn" (click)="logout()" title="Logout">
        ⏻
      </button>
    </div>
  </div>

Add to sidebar.component.scss:
  .sidebar-footer {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
  }
  .user-info {
    display: flex; align-items: center; gap: 10px;
  }
  .user-avatar {
    width: 32px; height: 32px; border-radius: 50%;
    background: var(--teal); color: white;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 14px; flex-shrink: 0;
  }
  .user-details {
    flex: 1; overflow: hidden;
    .user-name {
      font-size: 13px; color: var(--text);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .user-role {
      font-size: 11px; color: var(--teal);
      text-transform: capitalize;
    }
  }
  .logout-btn {
    background: none; border: none; cursor: pointer;
    color: var(--text-muted); font-size: 16px; padding: 4px;
    border-radius: 4px; flex-shrink: 0;
    &:hover { color: var(--error); background: rgba(231,76,60,0.1); }
  }

=============================================================
UPDATE 5: frontend/src/app/chat/chat.component.html
=============================================================

Find the header right section. Currently:
  <span class="user-display">
    TODO [PHASE 2]: {{ authService.currentUser()?.displayName }}
  </span>

Replace with:
  <span class="user-display">
    {{ authService.currentUser()?.displayName }}
  </span>

=============================================================
FINAL: ng build check
=============================================================

After all updates, run:
  ng build --configuration development

Fix any TypeScript errors found.
Common issues to watch for:
  - SessionService not injected in ChatComponent (add to inject())
  - Router not injected in ChatComponent (add to inject())
  - TurnResponse interface not imported (add to session.model.ts if missing)
  - authService referenced in chat.component.html but not public
    (make it public: public authService = inject(AuthService))