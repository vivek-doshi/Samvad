You are working on Samvad — a locally-hosted finance AI interface.
Angular latest, standalone component style throughout.
Dark theme, no external CSS frameworks, pure SCSS only.

The backend SSE contract (never deviate from this):
  data: {"token": "string", "done": false}   ← each token
  data: {"token": "", "done": true}           ← stream complete
  data: {"error": "message", "done": true}    ← on error

Colour variables used throughout all SCSS files:
  --navy:      #1B3A6B
  --teal:      #0D6E6E
  --bg:        #0F1117
  --surface:   #1A1D27
  --surface-2: #22263A
  --border:    #2A2D3A
  --text:      #E8EAF0
  --text-muted:#8B8FA8
  --error:     #E74C3C

=============================================================
STEP 1 — PACKAGE.JSON
=============================================================
Write frontend/package.json for Angular latest standalone application.

Dependencies:
  @angular/animations, @angular/common, @angular/compiler,
  @angular/core, @angular/forms, @angular/platform-browser,
  @angular/platform-browser-dynamic, @angular/router,
  rxjs, zone.js, marked

DevDependencies:
  @angular/cli, @angular/compiler-cli, typescript,
  @types/marked, @types/node

Scripts:
  start:  ng serve --host 0.0.0.0 --port 4200
  build:  ng build --configuration production
  test:   ng test

=============================================================
STEP 2 — TYPESCRIPT MODELS (3 files, no dependencies)
=============================================================

Write frontend/src/app/models/message.model.ts:

  export interface Message {
    id: string;                    // uuid, generated client-side
    role: 'user' | 'assistant';
    content: string;               // full accumulated content
    isStreaming: boolean;          // true while tokens still arriving
    domain?: string;
    sources?: SourceReference[];
    timestamp: Date;
    latencyMs?: number;
    error?: string;
  }

  export interface SourceReference {
    document: string;
    section?: string;
    page?: number;
    excerpt?: string;
  }

  export interface ChatStreamEvent {
    token: string;
    done: boolean;
    error?: string;
    sources?: SourceReference[];
  }

  export interface ChatRequest {
    query: string;
    session_id: string | null;
    domain: string | null;
  }

Write frontend/src/app/models/session.model.ts:

  export interface Session {
    sessionId: string;
    title: string;
    status: 'active' | 'closed' | 'archived';
    totalTurns: number;
    domainLast?: string;
    createdAt: Date;
    lastActiveAt: Date;
  }

  export interface SessionListItem {
    sessionId: string;
    title: string;
    totalTurns: number;
    domainLast?: string;
    lastActiveAt: Date;
  }

Write frontend/src/app/models/user.model.ts:

  export interface User {
    userId: string;
    username: string;
    displayName: string;
    role: 'admin' | 'user';
  }

  export interface LoginRequest {
    username: string;
    password: string;
  }

  export interface LoginResponse {
    accessToken: string;
    tokenType: string;
    user: User;
    expiresIn: number;
  }

  export interface AuthState {
    user: User | null;
    token: string | null;
    isAuthenticated: boolean;
  }

=============================================================
STEP 3 — ENVIRONMENT FILES (2 files)
=============================================================

Write frontend/src/environments/environment.ts:
  export const environment = {
    production: false,
    apiBaseUrl: 'http://localhost:8000',
    chatEndpoint: '/api/chat',
    authEndpoint: '/api/auth',
    sessionsEndpoint: '/api/sessions',
    uploadEndpoint: '/api/upload',
    healthEndpoint: '/api/health',
    sseTimeout: 120000,
    appName: 'Samvad',
    appVersion: '0.1.0',
  };

Write frontend/src/environments/environment.prod.ts:
  export const environment = {
    production: true,
    apiBaseUrl: '',
    chatEndpoint: '/api/chat',
    authEndpoint: '/api/auth',
    sessionsEndpoint: '/api/sessions',
    uploadEndpoint: '/api/upload',
    healthEndpoint: '/api/health',
    sseTimeout: 120000,
    appName: 'Samvad',
    appVersion: '0.1.0',
  };

=============================================================
STEP 4 — SERVICES (2 files)
=============================================================

Write frontend/src/app/services/auth.service.ts:

  @Injectable({ providedIn: 'root' })
  export class AuthService {

    Private constants:
      TOKEN_KEY = 'samvad_token'
      USER_KEY  = 'samvad_user'

    Private signals:
      _token = signal<string | null>(this.loadStoredToken())
      _user  = signal<User | null>(this.loadStoredUser())

    Public computed signals:
      isAuthenticated = computed(() => this._token() !== null)
      currentUser     = computed(() => this._user())
      token           = computed(() => this._token())

    Methods:

      login(request: LoginRequest): Observable<LoginResponse>
        POST to environment.apiBaseUrl + environment.authEndpoint + '/login'
        On success: store token + user in localStorage, update both signals
        Return the Observable — caller subscribes

      logout(): void
        Clear localStorage TOKEN_KEY and USER_KEY
        Set both signals to null
        Navigate to '/login'

      getAuthHeaders(): { Authorization: string }
        Return { Authorization: `Bearer ${this._token()}` }
        Throw Error('Not authenticated') if token is null

      isTokenExpired(): boolean
        Decode JWT payload — base64 decode the middle section (split by '.')
        Compare exp claim to Math.floor(Date.now() / 1000)
        Return true if expired or if any parsing error occurs

      private loadStoredToken(): string | null
        Read TOKEN_KEY from localStorage
        If found, check isTokenExpired() — return null if expired
        Return token string or null

      private loadStoredUser(): User | null
        Read USER_KEY from localStorage
        JSON.parse and return, or null if missing or parse error

Write frontend/src/app/services/chat.service.ts:

  PURPOSE: Stream chat responses from FastAPI SSE endpoint.
  Use fetch() with ReadableStream — NOT EventSource.
  Reason: EventSource does not support POST with custom headers.

  @Injectable({ providedIn: 'root' })
  export class ChatService {

    Private fields:
      private abortController: AbortController | null = null

    Inject: AuthService

    sendMessage(
      query: string,
      sessionId: string | null,
      domain: string | null
    ): Observable<ChatStreamEvent>

      Return new Observable<ChatStreamEvent>(subscriber => {

        IMPLEMENTATION:

        1. Create AbortController, store as this.abortController

        2. Build URL:
           environment.apiBaseUrl + environment.chatEndpoint

        3. Build request body:
           { query, session_id: sessionId, domain }

        4. Build headers:
           'Content-Type': 'application/json'
           'Authorization': authService.getAuthHeaders().Authorization

        5. Call fetch(url, {
             method: 'POST',
             headers,
             body: JSON.stringify(body),
             signal: controller.signal
           })

        6. On fetch response:
           - If !response.ok: subscriber.error(new Error(`HTTP ${response.status}`)), return
           - Get reader: response.body!.getReader()
           - Create TextDecoder

        7. Read loop:
           while(true) {
             const { done, value } = await reader.read()
             if (done) break
             decode chunk with TextDecoder
             split on newlines
             for each line:
               if line starts with 'data: ':
                 strip 'data: ' prefix
                 JSON.parse remainder → ChatStreamEvent
                 if event.done and event.error:
                   subscriber.error(new Error(event.error))
                   return
                 if event.done:
                   subscriber.complete()
                   return
                 else:
                   subscriber.next(event)
           }

        8. Handle partial lines across chunks:
           Keep a buffer string
           Append decoded chunk to buffer
           Split buffer on '\n'
           Process all complete lines (all but last)
           Keep last incomplete fragment in buffer

        9. Catch AbortError — call subscriber.complete() silently
           Catch other errors — call subscriber.error(err)

        10. Teardown function:
            return () => { controller.abort() }
      })

    cancelStream(): void
      if (this.abortController) {
        this.abortController.abort()
        this.abortController = null
      }

=============================================================
STEP 5 — SHARED COMPONENTS (3 files)
=============================================================

Write frontend/src/app/shared/markdown.pipe.ts:

  import { marked } from 'marked'
  import { DomSanitizer, SafeHtml } from '@angular/platform-browser'

  @Pipe({ name: 'markdown', standalone: true, pure: true })
  export class MarkdownPipe implements PipeTransform {
    constructor(private sanitizer: DomSanitizer) {}
    transform(value: string | null | undefined): SafeHtml {
      if (!value) return ''
      const html = marked.parse(value) as string
      return this.sanitizer.bypassSecurityTrustHtml(html)
    }
  }

Write frontend/src/app/shared/disclaimer.component.ts:

  @Component({
    selector: 'app-disclaimer',
    standalone: true,
    template: `
      <div class="disclaimer" *ngIf="visible()">
        <span class="icon">⚠</span>
        <span>{{ text() }}</span>
        <button (click)="visible.set(false)">✕</button>
      </div>
    `,
    styles: [`
      .disclaimer {
        display: flex; align-items: center; gap: 8px;
        padding: 8px 12px; border-radius: 6px;
        background: rgba(184, 134, 11, 0.15);
        border: 1px solid rgba(184, 134, 11, 0.4);
        font-size: 12px; color: #E8C66A;
      }
      button { margin-left: auto; background: none;
               border: none; cursor: pointer; color: inherit; }
    `]
  })
  export class DisclaimerComponent {
    text  = input<string>('This is informational guidance only. Not financial or legal advice.');
    visible = signal(true);
  }

Write frontend/src/app/shared/message.component.ts:

  @Component({
    selector: 'app-message',
    standalone: true,
    imports: [CommonModule, MarkdownPipe, DisclaimerComponent],
    template: `
      <div class="message" [class.user]="msg().role === 'user'"
                           [class.assistant]="msg().role === 'assistant'"
                           [class.streaming]="msg().isStreaming">

        <div class="bubble">
          <div class="content"
               [innerHTML]="msg().content | markdown"
               *ngIf="!msg().isStreaming || msg().content.length > 0">
          </div>
          <span class="cursor" *ngIf="msg().isStreaming"></span>
          <div class="error" *ngIf="msg().error">{{ msg().error }}</div>
        </div>

        <div class="meta">
          <span class="domain-badge" *ngIf="msg().domain">{{ msg().domain }}</span>
          <span class="timestamp">{{ msg().timestamp | date:'HH:mm' }}</span>
        </div>

        <app-disclaimer
          *ngIf="msg().role === 'assistant' && !msg().isStreaming && showDisclaimer()"
          [text]="disclaimerText()">
        </app-disclaimer>

      </div>
    `,
    styles: [`
      .message { display: flex; flex-direction: column; margin: 12px 16px; }

      .message.user { align-items: flex-end; }
      .message.assistant { align-items: flex-start; }

      .bubble {
        max-width: 75%;
        padding: 12px 16px;
        border-radius: 18px;
        font-size: 14px;
        line-height: 1.6;
        word-break: break-word;
      }
      .message.user .bubble {
        background: var(--navy);
        border-radius: 18px 18px 4px 18px;
        color: var(--text);
      }
      .message.assistant .bubble {
        background: var(--surface-2);
        border-radius: 18px 18px 18px 4px;
        color: var(--text);
      }

      .cursor::after {
        content: '▋';
        animation: blink 1s step-end infinite;
        color: var(--teal);
      }
      @keyframes blink { 50% { opacity: 0; } }

      .error { color: var(--error); font-size: 13px; margin-top: 4px; }

      .meta {
        display: flex; align-items: center; gap: 8px;
        margin-top: 4px; padding: 0 4px;
      }
      .domain-badge {
        font-size: 10px; font-weight: 600; text-transform: uppercase;
        padding: 2px 6px; border-radius: 4px;
        background: rgba(13, 110, 110, 0.25); color: var(--teal);
      }
      .timestamp { font-size: 11px; color: var(--text-muted); }
    `]
  })
  export class MessageComponent {
    msg = input.required<Message>();
    showDisclaimer = input<boolean>(false);
    disclaimerText = input<string>('This is informational guidance only. Not financial or legal advice.');
  }

=============================================================
STEP 6 — AUTH COMPONENT (login screen)
=============================================================

Write frontend/src/app/auth/login.component.ts:

  @Component({
    selector: 'app-login',
    standalone: true,
    imports: [ReactiveFormsModule, CommonModule],
    templateUrl: './login.component.html',
    styleUrls: ['./login.component.scss']
  })
  export class LoginComponent {
    private fb       = inject(FormBuilder)
    private auth     = inject(AuthService)
    private router   = inject(Router)

    loginForm = this.fb.group({
      username: ['', [Validators.required, Validators.minLength(3)]],
      password: ['', [Validators.required, Validators.minLength(6)]],
    })

    isLoading      = signal(false)
    errorMessage   = signal<string | null>(null)
    showPassword   = signal(false)

    onSubmit(): void
      Guard: return if form invalid or isLoading
      isLoading.set(true), errorMessage.set(null)
      Call auth.login(formValue)
      On success: router.navigate(['/chat'])
      On 401 error: errorMessage.set('Invalid username or password')
      On other error: errorMessage.set('Server error. Is Samvad running?')
      Finally: isLoading.set(false)

    togglePassword(): void
      showPassword.update(v => !v)

    get usernameControl() { return this.loginForm.get('username')! }
    get passwordControl() { return this.loginForm.get('password')! }
  }

Write frontend/src/app/auth/login.component.html:

  Full login page. Requirements:
  - Centred card, 400px wide
  - Top: "Samvad" in large bold navy, "Powered by Arthvidya" in teal italic below
  - Thin teal horizontal rule separator
  - Username field with label, validation error message below
  - Password field with label, show/hide toggle button on right
  - Login button full width, navy bg, shows spinner when isLoading
  - Error message box below button (red bg, only shown when errorMessage exists)
  - Form submits on Enter key
  - No registration, no forgot password

Write frontend/src/app/auth/login.component.scss:

  Center card using:
    host: display block, height 100vh, background var(--bg)
    flexbox center both axes

  Card:
    width 400px, padding 40px
    background var(--surface)
    border 1px solid var(--border)
    border-radius 12px
    box-shadow 0 8px 32px rgba(0,0,0,0.4)

  Inputs:
    width 100%, padding 10px 14px
    background var(--surface-2)
    border 1px solid var(--border)
    border-radius 6px, color var(--text)
    focus: border-color var(--teal), outline none

  Password wrapper:
    position relative
    toggle button: absolute right 10px, center vertically

  Button:
    width 100%, padding 11px
    background var(--navy), color var(--text)
    border none, border-radius 6px
    cursor pointer, font-size 15px, font-weight 600
    hover: background #254d91
    disabled: opacity 0.6, cursor not-allowed

  Error box:
    padding 10px 14px, border-radius 6px
    background rgba(231,76,60,0.15)
    border 1px solid rgba(231,76,60,0.4)
    color var(--error), font-size 13px

=============================================================
STEP 7 — SIDEBAR COMPONENT (session history)
=============================================================

Write frontend/src/app/sidebar/sidebar.component.ts:

  @Component({
    selector: 'app-sidebar',
    standalone: true,
    imports: [CommonModule],
    templateUrl: './sidebar.component.html',
    styleUrls: ['./sidebar.component.scss']
  })
  export class SidebarComponent {
    sessions = input<SessionListItem[]>([])
    activeSessionId = input<string | null>(null)
    onSessionSelect = output<string>()
    onNewSession    = output<void>()

    selectSession(sessionId: string): void
      this.onSessionSelect.emit(sessionId)

    newSession(): void
      this.onNewSession.emit()

    formatDate(date: Date): string
      Today: return time string HH:mm
      This week: return day name e.g. "Monday"
      Older: return date string DD MMM
  }

Write frontend/src/app/sidebar/sidebar.component.html:

  <div class="sidebar">
    <div class="sidebar-header">
      <span class="logo-text">Samvad</span>
      <button class="new-chat-btn" (click)="newSession()" title="New conversation">
        <span>+</span>
      </button>
    </div>

    <div class="session-list">
      <div class="empty-state" *ngIf="sessions().length === 0">
        <p>No conversations yet</p>
        <p class="sub">Start a new chat above</p>
      </div>

      <div
        *ngFor="let session of sessions()"
        class="session-item"
        [class.active]="session.sessionId === activeSessionId()"
        (click)="selectSession(session.sessionId)">
        <div class="session-title">{{ session.title }}</div>
        <div class="session-meta">
          <span class="domain" *ngIf="session.domainLast">{{ session.domainLast }}</span>
          <span class="date">{{ formatDate(session.lastActiveAt) }}</span>
        </div>
      </div>
    </div>

    <div class="sidebar-footer">
      TODO: user profile + logout (Phase 2)
    </div>
  </div>

Write frontend/src/app/sidebar/sidebar.component.scss:

  Full height, 240px wide, dark bg:
    background var(--surface)
    border-right 1px solid var(--border)
    display flex, flex-direction column

  Header:
    padding 16px
    display flex, justify-content space-between, align-items center
    border-bottom 1px solid var(--border)
    .logo-text: font-weight 700, color var(--teal), font-size 18px

  New chat button:
    32px × 32px, border-radius 6px
    background transparent, border 1px solid var(--border)
    color var(--text-muted), cursor pointer
    hover: border-color var(--teal), color var(--teal)

  Session list:
    flex 1, overflow-y auto, padding 8px

  Session item:
    padding 10px 12px, border-radius 8px
    cursor pointer, margin-bottom 2px
    .session-title: font-size 13px, color var(--text)
      white-space nowrap, overflow hidden, text-overflow ellipsis
    .session-meta: font-size 11px, color var(--text-muted)
      display flex, justify-content space-between, margin-top 3px
    hover: background var(--surface-2)
    active: background rgba(13,110,110,0.15), border-left 2px solid var(--teal)

  Empty state:
    text-align center, padding 32px 16px
    color var(--text-muted), font-size 13px
    .sub: font-size 11px, margin-top 4px

=============================================================
STEP 8 — CHAT COMPONENT (main screen)
=============================================================

Write frontend/src/app/chat/chat.component.ts:

  @Component({
    selector: 'app-chat',
    standalone: true,
    imports: [CommonModule, FormsModule, MessageComponent, SidebarComponent],
    templateUrl: './chat.component.html',
    styleUrls: ['./chat.component.scss']
  })
  export class ChatComponent implements OnInit, OnDestroy {

    private chatService = inject(ChatService)
    private authService = inject(AuthService)

    @ViewChild('messageContainer') messageContainer!: ElementRef
    @ViewChild('inputField') inputField!: ElementRef

    messages         = signal<Message[]>([])
    isStreaming      = signal(false)
    inputText        = signal('')
    sessions         = signal<SessionListItem[]>([])
    activeSessionId  = signal<string | null>(null)
    charCount        = computed(() => this.inputText().length)

    private streamSub: Subscription | null = null
    private streamStart = 0

    ngOnInit(): void
      Generate temp sessionId: crypto.randomUUID()
      activeSessionId.set(tempId)
      // TODO: [PHASE 2] Load active session from SessionService
      // TODO: [PHASE 2] Load session history list

    sendMessage(): void
      Guard: return if isStreaming() or inputText().trim() === '' or charCount() > 2000

      const query = this.inputText().trim()
      const msgId = crypto.randomUUID()

      // Add user message
      this.messages.update(msgs => [...msgs, {
        id: msgId,
        role: 'user',
        content: query,
        isStreaming: false,
        timestamp: new Date(),
      }])

      // Clear input
      this.inputText.set('')

      // Add empty assistant placeholder
      const assistantId = crypto.randomUUID()
      this.messages.update(msgs => [...msgs, {
        id: assistantId,
        role: 'assistant',
        content: '',
        isStreaming: true,
        timestamp: new Date(),
      }])

      this.isStreaming.set(true)
      this.streamStart = Date.now()

      // Subscribe to stream
      this.streamSub = this.chatService
        .sendMessage(query, this.activeSessionId(), null)
        .subscribe({
          next: (event: ChatStreamEvent) => {
            if (!event.done) {
              // Append token to last assistant message
              this.messages.update(msgs => {
                const updated = [...msgs]
                const last = updated[updated.length - 1]
                if (last.role === 'assistant') {
                  updated[updated.length - 1] = {
                    ...last,
                    content: last.content + event.token,
                  }
                }
                return updated
              })
              this.scrollToBottom()
            }
          },
          error: (err) => {
            this.messages.update(msgs => {
              const updated = [...msgs]
              const last = updated[updated.length - 1]
              if (last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  isStreaming: false,
                  error: err.message || 'Stream error',
                }
              }
              return updated
            })
            this.isStreaming.set(false)
          },
          complete: () => {
            this.messages.update(msgs => {
              const updated = [...msgs]
              const last = updated[updated.length - 1]
              if (last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  isStreaming: false,
                  latencyMs: Date.now() - this.streamStart,
                }
              }
              return updated
            })
            this.isStreaming.set(false)
            this.scrollToBottom()
          }
        })

    cancelStream(): void
      this.chatService.cancelStream()
      this.messages.update(msgs => {
        const updated = [...msgs]
        const last = updated[updated.length - 1]
        if (last?.role === 'assistant' && last.isStreaming) {
          updated[updated.length - 1] = { ...last, isStreaming: false }
        }
        return updated
      })
      this.isStreaming.set(false)

    onKeyDown(event: KeyboardEvent): void
      Enter without Shift: call sendMessage(), preventDefault()
      Escape: call cancelStream()

    onInput(event: Event): void
      this.inputText.set((event.target as HTMLTextAreaElement).value)

    private scrollToBottom(): void
      Try:
        const el = this.messageContainer.nativeElement
        const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
        if (isNearBottom) el.scrollTop = el.scrollHeight
      Catch: ignore

    ngOnDestroy(): void
      this.streamSub?.unsubscribe()
      this.chatService.cancelStream()
  }

Write frontend/src/app/chat/chat.component.html:

  Full viewport layout using CSS Grid:
  rows: 48px (header) + 1fr (body)
  columns: 240px (sidebar) + 1fr (main)

  HEADER (spans full width, row 1):
    <header class="app-header">
      <div class="header-left">
        <span class="app-name">Samvad</span>
        <span class="powered-by">powered by Arthvidya</span>
      </div>
      <div class="header-right">
        <span class="user-display">
          TODO [PHASE 2]: {{ authService.currentUser()?.displayName }}
        </span>
      </div>
    </header>

  SIDEBAR (row 2, col 1):
    <app-sidebar
      [sessions]="sessions()"
      [activeSessionId]="activeSessionId()"
      (onSessionSelect)="activeSessionId.set($event)"
      (onNewSession)="messages.set([])">
    </app-sidebar>

  MAIN AREA (row 2, col 2):
    flex column, full height

    MESSAGE LIST (flex 1, scrollable):
      <div #messageContainer class="message-list">
        <div class="empty-state" *ngIf="messages().length === 0">
          <div class="welcome-icon">💬</div>
          <h2>Ask Samvad</h2>
          <p>Income tax, equity analysis, financial documents</p>
        </div>
        <app-message
          *ngFor="let msg of messages(); trackBy: trackById"
          [msg]="msg"
          [showDisclaimer]="msg.role === 'assistant' && !msg.isStreaming">
        </app-message>
      </div>

    INPUT AREA (fixed 80px):
      <div class="input-area">
        <div class="input-wrapper">
          <textarea
            #inputField
            [value]="inputText()"
            (input)="onInput($event)"
            (keydown)="onKeyDown($event)"
            placeholder="Ask about tax, equity, or upload a document..."
            [disabled]="isStreaming()"
            rows="1"
            maxlength="2000">
          </textarea>
          <div class="input-actions">
            <span class="char-count"
                  [class.near-limit]="charCount() > 1800">
              {{ charCount() }}/2000
            </span>
            <button
              *ngIf="!isStreaming()"
              (click)="sendMessage()"
              [disabled]="!inputText().trim()"
              class="send-btn">
              Send
            </button>
            <button
              *ngIf="isStreaming()"
              (click)="cancelStream()"
              class="stop-btn">
              ■ Stop
            </button>
          </div>
        </div>
      </div>

  trackById method:
    trackById(index: number, msg: Message): string { return msg.id }

Write frontend/src/app/chat/chat.component.scss:

  :host {
    display: block;
    height: 100vh;
    background: var(--bg);
    display: grid;
    grid-template-rows: 48px 1fr;
    grid-template-columns: 240px 1fr;
    overflow: hidden;
  }

  .app-header {
    grid-column: 1 / -1;
    display: flex; align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    .app-name { font-weight: 700; color: var(--teal); font-size: 18px; }
    .powered-by { font-size: 11px; color: var(--text-muted);
                  margin-left: 8px; font-style: italic; }
    .user-display { font-size: 13px; color: var(--text-muted); }
  }

  app-sidebar { grid-row: 2; grid-column: 1; }

  .main-area {
    grid-row: 2; grid-column: 2;
    display: flex; flex-direction: column;
    overflow: hidden;
  }

  .message-list {
    flex: 1; overflow-y: auto;
    padding: 16px 0;
    scroll-behavior: smooth;
    /* custom scrollbar */
    &::-webkit-scrollbar { width: 6px; }
    &::-webkit-scrollbar-track { background: var(--bg); }
    &::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  }

  .empty-state {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100%; color: var(--text-muted);
    .welcome-icon { font-size: 48px; margin-bottom: 16px; }
    h2 { font-size: 22px; font-weight: 600; color: var(--text);
         margin: 0 0 8px; }
    p { font-size: 14px; margin: 0; }
  }

  .input-area {
    padding: 12px 20px;
    border-top: 1px solid var(--border);
    background: var(--surface);
  }

  .input-wrapper {
    display: flex; align-items: flex-end; gap: 10px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 10px 14px;
    &:focus-within { border-color: var(--teal); }
  }

  textarea {
    flex: 1; background: none; border: none; outline: none;
    color: var(--text); font-size: 14px; line-height: 1.5;
    resize: none; min-height: 24px; max-height: 96px;
    font-family: inherit;
    &::placeholder { color: var(--text-muted); }
    &:disabled { opacity: 0.5; }
  }

  .input-actions {
    display: flex; align-items: center; gap: 8px; flex-shrink: 0;
  }

  .char-count {
    font-size: 11px; color: var(--text-muted);
    &.near-limit { color: #E8C66A; }
  }

  .send-btn, .stop-btn {
    padding: 6px 16px; border-radius: 6px;
    border: none; cursor: pointer; font-size: 13px;
    font-weight: 600; transition: background 0.15s;
  }
  .send-btn {
    background: var(--navy); color: var(--text);
    &:hover { background: #254d91; }
    &:disabled { opacity: 0.4; cursor: not-allowed; }
  }
  .stop-btn {
    background: rgba(231,76,60,0.2); color: var(--error);
    border: 1px solid rgba(231,76,60,0.4);
    &:hover { background: rgba(231,76,60,0.3); }
  }

=============================================================
STEP 9 — APP WIRING (routing, root component, bootstrap)
=============================================================

Write frontend/src/app/app-routing.module.ts:

  Define routes array (export const routes: Routes):
    { path: '',      redirectTo: '/chat', pathMatch: 'full' }
    { path: 'login', component: LoginComponent }
    { path: 'chat',  component: ChatComponent, canActivate: [authGuard] }
    { path: '**',    redirectTo: '/chat' }

  Define authGuard as CanActivateFn (inline, not a class):
    const authService = inject(AuthService)
    const router      = inject(Router)
    if (authService.isAuthenticated()) {
      if (authService.isTokenExpired()) {
        authService.logout()
        return router.createUrlTree(['/login'])
      }
      return true
    }
    return router.createUrlTree(['/login'])

Write frontend/src/app/app.component.ts:

  @Component({
    selector: 'app-root',
    standalone: true,
    imports: [RouterOutlet],
    template: '<router-outlet />',
    styles: [`:host { display: block; height: 100vh; }`]
  })
  export class AppComponent {}

Write frontend/src/main.ts:

  bootstrapApplication(AppComponent, {
    providers: [
      provideRouter(routes, withComponentInputBinding()),
      provideHttpClient(withInterceptorsFromDi()),
    ]
  }).catch(err => console.error(err))

Write frontend/src/styles.scss:

  Global styles:
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI',
                   Roboto, sans-serif;
      background: #0F1117;
      color: #E8EAF0;
      -webkit-font-smoothing: antialiased;
    }
    /* CSS custom properties available globally */
    :root {
      --navy:      #1B3A6B;
      --teal:      #0D6E6E;
      --bg:        #0F1117;
      --surface:   #1A1D27;
      --surface-2: #22263A;
      --border:    #2A2D3A;
      --text:      #E8EAF0;
      --text-muted:#8B8FA8;
      --error:     #E74C3C;
    }
    /* Smooth scrolling everywhere */
    * { scroll-behavior: smooth; }
    /* Remove default button styles */
    button { font-family: inherit; }
    /* Textarea auto-height via JS */
    textarea { overflow: hidden; }

Write frontend/src/index.html:

  Standard Angular index.html:
  - title: Samvad
  - charset UTF-8
  - viewport meta
  - <app-root> in body
  - base href="/"

=============================================================
FINAL INSTRUCTION TO COPILOT
=============================================================

After generating all files above, run these commands:
  cd frontend
  npm install
  npm install marked @types/marked

Then verify the app compiles:
  npx ng build --configuration development

Report any TypeScript compilation errors found.

The app does NOT need a running backend to compile.
All backend calls are in services that only execute at runtime.