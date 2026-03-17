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

  readonly currentUser = this.auth.currentUser;
  readonly sessions = input<SessionListItem[]>([]);
  readonly activeSessionId = input<string | null>(null);
  readonly onSessionSelect = output<string>();
  readonly onNewSession = output<void>();

  selectSession(sessionId: string): void {
    this.onSessionSelect.emit(sessionId);
  }

  newSession(): void {
    this.onNewSession.emit();
  }

  formatDate(date: Date): string {
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
    this.auth.logout();
    this.sessionService.clearState();
  }

}

