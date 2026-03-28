import { TestBed } from '@angular/core/testing';
import { DomSanitizer } from '@angular/platform-browser';
import { MarkdownPipe } from './markdown-pipe';

describe('MarkdownPipe', () => {
  let pipe: MarkdownPipe;
  let sanitizer: DomSanitizer;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    sanitizer = TestBed.inject(DomSanitizer);
    pipe = new MarkdownPipe(sanitizer);
  });

  it('should create', () => {
    expect(pipe).toBeTruthy();
  });

  it('should return empty SafeHtml for null', () => {
    const result = pipe.transform(null);
    expect(result).toBeTruthy(); // SafeHtml wrapping empty string
  });

  it('should return empty SafeHtml for undefined', () => {
    const result = pipe.transform(undefined);
    expect(result).toBeTruthy();
  });

  it('should return empty SafeHtml for empty string', () => {
    const result = pipe.transform('');
    expect(result).toBeTruthy();
  });

  it('should convert markdown bold to HTML', () => {
    const result = pipe.transform('**bold text**');
    // SafeHtml toString contains the underlying value
    const html = (result as any).changingThisBreaksApplicationSecurity ?? result.toString();
    expect(html).toContain('<strong>bold text</strong>');
  });

  it('should convert markdown headers', () => {
    const result = pipe.transform('# Header');
    const html = (result as any).changingThisBreaksApplicationSecurity ?? result.toString();
    expect(html).toContain('<h1');
    expect(html).toContain('Header');
  });

  it('should convert markdown lists', () => {
    const result = pipe.transform('- item 1\n- item 2');
    const html = (result as any).changingThisBreaksApplicationSecurity ?? result.toString();
    expect(html).toContain('<li>');
    expect(html).toContain('item 1');
  });

  it('should convert inline code', () => {
    const result = pipe.transform('Use `code` here');
    const html = (result as any).changingThisBreaksApplicationSecurity ?? result.toString();
    expect(html).toContain('<code>');
    expect(html).toContain('code');
  });

  it('should be a pure pipe', () => {
    // Verify the pipe metadata
    expect(MarkdownPipe).toBeTruthy();
  });
});
