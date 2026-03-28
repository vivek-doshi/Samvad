import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ChatComponent } from './chat';
import { AuthService } from '../services/auth';
import { ChatService } from '../services/chat';
import { SessionService } from '../services/session';
import { SessionListItem } from '../models/session.model';

describe('ChatComponent', () => {
  let component: ChatComponent;
  let fixture: ComponentFixture<ChatComponent>;
  let chatService: {
    sendMessage: ReturnType<typeof vi.fn>;
    cancelStream: ReturnType<typeof vi.fn>;
  };
  let sessionService: {
    loadSessions: ReturnType<typeof vi.fn>;
    createSession: ReturnType<typeof vi.fn>;
    loadSessionTurns: ReturnType<typeof vi.fn>;
    setActiveSession: ReturnType<typeof vi.fn>;
    sessions: ReturnType<typeof vi.fn>;
    clearState: ReturnType<typeof vi.fn>;
  };
  let router: { navigate: ReturnType<typeof vi.fn> };
  let authService: {
    isAuthenticated: ReturnType<typeof vi.fn>;
    currentUser: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn>;
    getAuthHeaders: ReturnType<typeof vi.fn>;
  };

  const mockSession: SessionListItem = {
    sessionId: 's1',
    title: 'Test Session',
    status: 'active',
    totalTurns: 2,
    lastActiveAt: new Date(),
  };

  beforeEach(async () => {
    chatService = {
      sendMessage: vi.fn(),
      cancelStream: vi.fn(),
    };
    sessionService = {
      loadSessions: vi.fn().mockReturnValue(of([])),
      createSession: vi.fn().mockReturnValue(of(mockSession)),
      loadSessionTurns: vi.fn().mockReturnValue(of([])),
      setActiveSession: vi.fn(),
      sessions: vi.fn().mockReturnValue([]),
      clearState: vi.fn(),
    };
    router = { navigate: vi.fn() };
    authService = {
      isAuthenticated: vi.fn().mockReturnValue(true),
      currentUser: vi.fn().mockReturnValue({ userId: 'u1', username: 'admin', displayName: 'Admin', role: 'admin' }),
      logout: vi.fn(),
      getAuthHeaders: vi.fn().mockReturnValue({ Authorization: 'Bearer token' }),
    };

    await TestBed.configureTestingModule({
      imports: [ChatComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: ChatService, useValue: chatService },
        { provide: SessionService, useValue: sessionService },
        { provide: Router, useValue: router },
        { provide: AuthService, useValue: authService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ChatComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('ngOnInit', () => {
    it('should load sessions and set active session', () => {
      sessionService.loadSessions.mockReturnValue(of([mockSession]));
      fixture.detectChanges();

      expect(sessionService.loadSessions).toHaveBeenCalled();
      expect(component.activeSessionId()).toBe('s1');
      expect(sessionService.setActiveSession).toHaveBeenCalledWith('s1');
    });

    it('should create new session when no active session', () => {
      const closedSession = { ...mockSession, status: 'closed' as const };
      sessionService.loadSessions.mockReturnValue(of([closedSession]));
      fixture.detectChanges();

      expect(sessionService.createSession).toHaveBeenCalled();
    });

    it('should navigate to login on 401 error', () => {
      sessionService.loadSessions.mockReturnValue(throwError(() => ({ status: 401 })));
      fixture.detectChanges();

      expect(router.navigate).toHaveBeenCalledWith(['/login']);
    });

    it('should load turns for active session', () => {
      sessionService.loadSessions.mockReturnValue(of([mockSession]));
      sessionService.loadSessionTurns.mockReturnValue(
        of([
          {
            turnId: 't1',
            sessionId: 's1',
            turnNumber: 1,
            role: 'user',
            content: 'Hello',
            domain: null,
            sourcesCited: [],
            createdAt: new Date(),
          },
        ]),
      );
      fixture.detectChanges();

      expect(sessionService.loadSessionTurns).toHaveBeenCalledWith('s1');
      expect(component.messages()).toHaveLength(1);
      expect(component.messages()[0].role).toBe('user');
    });
  });

  describe('sendMessage', () => {
    beforeEach(() => {
      sessionService.loadSessions.mockReturnValue(of([mockSession]));
      fixture.detectChanges();
    });

    it('should not send when streaming', () => {
      component.isStreaming.set(true);
      component.inputText.set('Hello');
      component.sendMessage();
      expect(chatService.sendMessage).not.toHaveBeenCalled();
    });

    it('should not send empty message', () => {
      component.inputText.set('   ');
      component.sendMessage();
      expect(chatService.sendMessage).not.toHaveBeenCalled();
    });

    it('should not send when over character limit', () => {
      component.inputText.set('a'.repeat(2001));
      component.sendMessage();
      expect(chatService.sendMessage).not.toHaveBeenCalled();
    });

    it('should add user and assistant messages', () => {
      chatService.sendMessage.mockReturnValue(of({ token: 'Hi', done: false }));
      component.inputText.set('Hello');

      component.sendMessage();

      const msgs = component.messages();
      expect(msgs.length).toBeGreaterThanOrEqual(2);
      expect(msgs.find((m) => m.role === 'user')?.content).toBe('Hello');
    });

    it('should clear input text after sending', () => {
      chatService.sendMessage.mockReturnValue(of({ token: '', done: true }));
      component.inputText.set('Hello');
      component.sendMessage();
      expect(component.inputText()).toBe('');
    });

    it('should handle stream error', () => {
      chatService.sendMessage.mockReturnValue(throwError(() => new Error('fail')));
      component.inputText.set('Hello');
      component.sendMessage();

      const last = component.messages().at(-1);
      expect(last?.error).toBe('fail');
      expect(component.isStreaming()).toBe(false);
    });

    it('should set isStreaming during stream and clear after', () => {
      chatService.sendMessage.mockReturnValue(of({ token: '', done: true }));
      component.inputText.set('Hello');
      component.sendMessage();
      expect(component.isStreaming()).toBe(false);
    });

    it('should append sources on done event', () => {
      chatService.sendMessage.mockReturnValue(
        of(
          { token: 'Ans', done: false },
          { token: '', done: true, sources: [{ document: 'doc.pdf' }] },
        ),
      );
      component.inputText.set('Hello');
      component.sendMessage();

      const assistant = component.messages().filter((m) => m.role === 'assistant');
      expect(assistant.at(-1)?.sources).toHaveLength(1);
    });
  });

  describe('cancelStream', () => {
    it('should call chatService.cancelStream and stop streaming', () => {
      component.isStreaming.set(true);
      component.messages.set([
        { id: '1', role: 'assistant', content: 'partial', isStreaming: true, timestamp: new Date() },
      ]);

      component.cancelStream();

      expect(chatService.cancelStream).toHaveBeenCalled();
      expect(component.isStreaming()).toBe(false);
      expect(component.messages()[0].isStreaming).toBe(false);
    });
  });

  describe('onKeyDown', () => {
    it('should call sendMessage on Enter without Shift', () => {
      const sendSpy = vi.spyOn(component, 'sendMessage');
      const event = new KeyboardEvent('keydown', { key: 'Enter', shiftKey: false });
      vi.spyOn(event, 'preventDefault');

      component.onKeyDown(event);

      expect(event.preventDefault).toHaveBeenCalled();
      expect(sendSpy).toHaveBeenCalled();
    });

    it('should not call sendMessage on Shift+Enter', () => {
      const sendSpy = vi.spyOn(component, 'sendMessage');
      const event = new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true });

      component.onKeyDown(event);

      expect(sendSpy).not.toHaveBeenCalled();
    });

    it('should call cancelStream on Escape', () => {
      const cancelSpy = vi.spyOn(component, 'cancelStream');
      const event = new KeyboardEvent('keydown', { key: 'Escape' });

      component.onKeyDown(event);

      expect(cancelSpy).toHaveBeenCalled();
    });
  });

  describe('onInput', () => {
    it('should update inputText signal', () => {
      const event = { target: { value: 'new text' } } as unknown as Event;
      component.onInput(event);
      expect(component.inputText()).toBe('new text');
    });
  });

  describe('createNewSession', () => {
    it('should call service and update state', () => {
      sessionService.createSession.mockReturnValue(of(mockSession));
      sessionService.sessions.mockReturnValue([mockSession]);

      component.createNewSession();

      expect(sessionService.createSession).toHaveBeenCalled();
      expect(component.activeSessionId()).toBe('s1');
      expect(component.messages()).toHaveLength(0);
    });
  });

  describe('onSessionSelected', () => {
    beforeEach(() => {
      sessionService.loadSessions.mockReturnValue(of([mockSession]));
      fixture.detectChanges();
    });

    it('should skip if same session', () => {
      component.activeSessionId.set('s1');
      sessionService.loadSessionTurns.mockClear();

      component.onSessionSelected('s1');

      expect(sessionService.loadSessionTurns).not.toHaveBeenCalled();
    });

    it('should load turns for new session', () => {
      sessionService.loadSessionTurns.mockReturnValue(of([]));
      component.onSessionSelected('s2');

      expect(component.activeSessionId()).toBe('s2');
      expect(sessionService.setActiveSession).toHaveBeenCalledWith('s2');
      expect(sessionService.loadSessionTurns).toHaveBeenCalledWith('s2');
    });
  });

  describe('trackById', () => {
    it('should return message id', () => {
      const msg = { id: 'abc', role: 'user' as const, content: '', isStreaming: false, timestamp: new Date() };
      expect(component.trackById(0, msg)).toBe('abc');
    });
  });

  describe('charCount', () => {
    it('should compute character count from input', () => {
      component.inputText.set('hello');
      expect(component.charCount()).toBe(5);
    });
  });

  describe('ngOnDestroy', () => {
    it('should cancel stream on destroy', () => {
      component.ngOnDestroy();
      expect(chatService.cancelStream).toHaveBeenCalled();
    });
  });
});
