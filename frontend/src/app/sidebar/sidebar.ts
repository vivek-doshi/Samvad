// SidebarComponent — session list and navigation panel
// Note 1: The sidebar shows all conversation sessions and lets the user
// switch between them or start a new one. It uses the "smart/dumb" component
// pattern: data comes IN via input signals, user actions go OUT via output
// signals — ChatComponent owns the state and passes it down.
import { CommonModule } from '@angular/common';
import { Component, inject, input, output } from '@angular/core';
import { SessionListItem } from '../models/session.model';
import { AuthService } from '../services/auth';
import { SessionService } from '../services/session';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.scss',
})
export class SidebarComponent {
  private readonly auth = inject(AuthService);
  private readonly sessionService = inject(SessionService);

  // Note 2: currentUser is a computed signal from AuthService. The sidebar
  // template reads currentUser()?.displayName to show the logged-in user's name.
  readonly currentUser = this.auth.currentUser;
  // Note 3: input<SessionListItem[]>([]) = optional input with empty-array default.
  // This prevents null errors in the template before the parent sets sessions.
  readonly sessions = input<SessionListItem[]>([]);
  readonly activeSessionId = input<string | null>(null);
  // Note 4: output<string>() declares a typed event emitter. The parent template
  // binds to it with (onSessionSelect)="onSessionSelected($event)".
  readonly onSessionSelect = output<string>();
  readonly onNewSession = output<void>();

  selectSession(sessionId: string): void {
    this.onSessionSelect.emit(sessionId);
  }

  newSession(): void {
    this.onNewSession.emit();
  }

  formatDate(date: Date): string {
    // Note 5: Relative timestamp display: "09:30" for today, "Monday" for this
    // week, "14 Mar" for older dates — mirrors messaging app conventions.
    const value = new Date(date);
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const diffMs = now.getTime() - value.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (value >= startOfToday) {
      return value.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      });
    }

    if (diffDays < 7) {
      return value.toLocaleDateString([], { weekday: 'long' });
    }

    return value.toLocaleDateString([], {
      day: '2-digit',
      month: 'short',
    });
  }

  logout(): void {
    // Note 6: clearState() resets session signals so stale data is not shown
    // if a different user logs in on the same tab without a full page refresh.
    this.auth.logout();
    this.sessionService.clearState();
  }

}

