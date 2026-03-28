import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SourcesPanelComponent } from './sources-panel.component';
import { SourceReference } from '../models/message.model';

describe('SourcesPanelComponent', () => {
  let component: SourcesPanelComponent;
  let fixture: ComponentFixture<SourcesPanelComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SourcesPanelComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(SourcesPanelComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should not be visible when no sources', () => {
    expect(component.isVisible()).toBe(false);
  });

  it('should not render panel when no sources', () => {
    const panel = fixture.nativeElement.querySelector('.sources-panel');
    expect(panel).toBeNull();
  });

  it('should be visible when sources present', () => {
    const sources: SourceReference[] = [
      { document: 'income_tax.pdf', section: '80C', page: 12 },
    ];
    fixture.componentRef.setInput('sources', sources);
    fixture.detectChanges();

    expect(component.isVisible()).toBe(true);
  });

  it('should render source items', () => {
    const sources: SourceReference[] = [
      { document: 'doc1.pdf', section: '1.1', page: 5, excerpt: 'Relevant text' },
      { document: 'doc2.pdf' },
    ];
    fixture.componentRef.setInput('sources', sources);
    fixture.detectChanges();

    const items = fixture.nativeElement.querySelectorAll('.source-item');
    expect(items.length).toBe(2);
  });

  it('should display source count in header', () => {
    const sources: SourceReference[] = [
      { document: 'd1.pdf' },
      { document: 'd2.pdf' },
      { document: 'd3.pdf' },
    ];
    fixture.componentRef.setInput('sources', sources);
    fixture.detectChanges();

    const header = fixture.nativeElement.querySelector('.sources-header');
    expect(header.textContent).toContain('3');
  });

  it('should display document name', () => {
    fixture.componentRef.setInput('sources', [{ document: 'companies_act.pdf' }]);
    fixture.detectChanges();

    const doc = fixture.nativeElement.querySelector('.source-doc');
    expect(doc.textContent).toContain('companies_act.pdf');
  });

  it('should display section and page when present', () => {
    fixture.componentRef.setInput('sources', [
      { document: 'doc.pdf', section: '2.3', page: 10 },
    ]);
    fixture.detectChanges();

    const ref = fixture.nativeElement.querySelector('.source-ref');
    expect(ref.textContent).toContain('Section 2.3');
    expect(ref.textContent).toContain('Page 10');
  });

  it('should not display section when absent', () => {
    fixture.componentRef.setInput('sources', [{ document: 'doc.pdf' }]);
    fixture.detectChanges();

    const ref = fixture.nativeElement.querySelector('.source-ref');
    expect(ref).toBeNull();
  });

  it('should display excerpt when present', () => {
    fixture.componentRef.setInput('sources', [
      { document: 'doc.pdf', excerpt: 'Important text here' },
    ]);
    fixture.detectChanges();

    const excerpt = fixture.nativeElement.querySelector('.source-excerpt');
    expect(excerpt.textContent).toContain('Important text here');
  });
});
