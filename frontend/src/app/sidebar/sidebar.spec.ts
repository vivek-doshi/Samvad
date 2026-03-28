import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SidebarComponent } from './sidebar';
import { AuthService } from '../services/auth';
import { SessionService } from '../services/session';
import { SessionListItem } from '../models/session.model';

describe('SidebarComponent', () => {
  let component: SidebarComponent;
  let fixture: ComponentFixture<SidebarComponent>;
  let authService: {
    currentUser: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn>;
  };
  let sessionService: { clearState: ReturnType<typeof vi.fn> };

  beforeEach(async () => {
    authService = {
      currentUser: vi.fn().mockReturnValue({
        userId: 'u1',
        username: 'admin',
        displayName: 'Admin',
        role: 'admin',
      }),
      logout: vi.fn(),
    };
    sessionService = { clearState: vi.fn() };

    await TestBed.configureTestingModule({
      imports: [SidebarComponent],
      providers: [
        { provide: AuthService, useValue: authService },
        { provide: SessionService, useValue: sessionService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(SidebarComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  describe('selectSession', () => {
    it('should emit session id', () => {
      const spy = vi.fn();
      component.onSessionSelect.subscribe(spy);
      component.selectSession('s1');
      expect(spy).toHaveBeenCalledWith('s1');
    });
  });

  describe('newSession', () => {
    it('should emit void', () => {
      const spy = vi.fn();
      component.onNewSession.subscribe(spy);
      component.newSession();
      expect(spy).toHaveBeenCalled();
    });
  });

  describe('formatDate', () => {
    it('should return time for today', () => {
      const now = new Date();
      const result = component.formatDate(now);
      // Result should be a time like "14:30" or "02:30 PM"
      expect(result).toBeTruthy();
      expect(result.length).toBeLessThanOrEqual(10);
    });

    it('should return weekday for dates within last 7 days', () => {
      const threeDaysAgo = new Date();
      threeDaysAgo.setDate(threeDaysAgo.getDate() - 3);
      threeDaysAgo.setHours(10, 0, 0, 0);
      const result = component.formatDate(threeDaysAgo);
      const weekdays = [
        'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday',
      ];
      expect(weekdays.some((d) => result.includes(d))).toBe(true);
    });

    it('should return day/month for older dates', () => {
      const oldDate = new Date('2024-03-15T10:00:00');
      const result = component.formatDate(oldDate);
      // Should contain "15" and "Mar" or similar
      expect(result).toBeTruthy();
    });
  });

  describe('logout', () => {
    it('should call auth logout and clear session state', () => {
      component.logout();
      expect(authService.logout).toHaveBeenCalled();
      expect(sessionService.clearState).toHaveBeenCalled();
    });
  });
});
