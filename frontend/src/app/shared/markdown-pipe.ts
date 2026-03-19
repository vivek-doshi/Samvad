// MarkdownPipe — converts markdown text to safe HTML for rendering
// Note 1: A Pipe in Angular is a transformation function used in templates:
// {{ msg.content | markdown }} passes msg.content through the transform() method
// and renders the result as HTML. The 'pure: true' flag (the default) means the
// pipe only re-runs when the INPUT reference changes — not on every change detection
// cycle — making it efficient for messages that update frequently during streaming.
import { Pipe, PipeTransform } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';
// Note 2: 'marked' is a fast, CommonMark-compliant Markdown parser. It converts
// Markdown syntax (e.g. **bold**, `code`, | table |) to HTML strings.
// The LLM uses Markdown formatting in its responses for readability.

@Pipe({
  name: 'markdown',
  standalone: true,
  pure: true,
})
export class MarkdownPipe implements PipeTransform {
  constructor(private readonly sanitizer: DomSanitizer) {}

  transform(value: string | null | undefined): SafeHtml {
    if (!value) {
      return this.sanitizer.bypassSecurityTrustHtml('');
    }

    const html = marked.parse(value) as string;
    // Note 3: bypassSecurityTrustHtml() tells Angular's DOM sanitizer to trust
    // this HTML and render it as-is. Normally Angular strips <script> tags and
    // event handlers from HTML to prevent XSS (Cross-Site Scripting) attacks.
    // We bypass sanitisation here because the HTML came from marked.parse()
    // which itself sanitises dangerous content. The LLM output is also constrained
    // by the system prompt to never include scripts or iframes.
    return this.sanitizer.bypassSecurityTrustHtml(html);
  }
}
