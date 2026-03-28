import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MessageComponent } from './message';
import { Message } from '../../models/message.model';

describe('MessageComponent', () => {
  let component: MessageComponent;
  let fixture: ComponentFixture<MessageComponent>;

  const userMessage: Message = {
    id: 'msg1',
    role: 'user',
    content: 'Hello world',
    isStreaming: false,
    timestamp: new Date(),
  };

  const assistantMessage: Message = {
    id: 'msg2',
    role: 'assistant',
    content: 'Hi there',
    isStreaming: false,
    timestamp: new Date(),
    sources: [{ document: 'doc.pdf', section: '1.1' }],
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MessageComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(MessageComponent);
    component = fixture.componentInstance;
  });

  it('should create with user message', () => {
    fixture.componentRef.setInput('msg', userMessage);
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should create with assistant message', () => {
    fixture.componentRef.setInput('msg', assistantMessage);
    fixture.detectChanges();
    expect(component).toBeTruthy();
  });

  it('should apply user class for user messages', () => {
    fixture.componentRef.setInput('msg', userMessage);
    fixture.detectChanges();
    const el = fixture.nativeElement.querySelector('.message');
    expect(el.classList.contains('user')).toBe(true);
  });

  it('should apply assistant class for assistant messages', () => {
    fixture.componentRef.setInput('msg', assistantMessage);
    fixture.detectChanges();
    const el = fixture.nativeElement.querySelector('.message');
    expect(el.classList.contains('assistant')).toBe(true);
  });

  it('should apply streaming class when streaming', () => {
    const streaming = { ...userMessage, isStreaming: true };
    fixture.componentRef.setInput('msg', streaming);
    fixture.detectChanges();
    const el = fixture.nativeElement.querySelector('.message');
    expect(el.classList.contains('streaming')).toBe(true);
  });

  it('should display error message', () => {
    const errorMsg = { ...assistantMessage, error: 'Stream error' };
    fixture.componentRef.setInput('msg', errorMsg);
    fixture.detectChanges();
    const errorEl = fixture.nativeElement.querySelector('.error');
    expect(errorEl?.textContent).toContain('Stream error');
  });

  it('should display domain badge when domain is present', () => {
    const domainMsg = { ...userMessage, domain: 'tax' };
    fixture.componentRef.setInput('msg', domainMsg);
    fixture.detectChanges();
    const badge = fixture.nativeElement.querySelector('.domain-badge');
    expect(badge?.textContent).toContain('tax');
  });

  it('should accept showDisclaimer input', () => {
    fixture.componentRef.setInput('msg', assistantMessage);
    fixture.componentRef.setInput('showDisclaimer', true);
    fixture.detectChanges();
    expect(component.showDisclaimer()).toBe(true);
  });

  it('should accept custom disclaimerText', () => {
    fixture.componentRef.setInput('msg', assistantMessage);
    fixture.componentRef.setInput('disclaimerText', 'Custom disclaimer');
    fixture.detectChanges();
    expect(component.disclaimerText()).toBe('Custom disclaimer');
  });
});
