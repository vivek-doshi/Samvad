import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DisclaimerComponent } from './disclaimer';

describe('DisclaimerComponent', () => {
  let component: DisclaimerComponent;
  let fixture: ComponentFixture<DisclaimerComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DisclaimerComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(DisclaimerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should have default disclaimer text', () => {
    expect(component.text()).toBe(
      'This is informational guidance only. Not financial or legal advice.',
    );
  });

  it('should be visible by default', () => {
    expect(component.visible()).toBe(true);
  });

  it('should render disclaimer text in DOM', () => {
    const el = fixture.nativeElement.querySelector('.disclaimer');
    expect(el).toBeTruthy();
    expect(el.textContent).toContain('informational guidance');
  });

  it('should hide when visible is set to false', () => {
    component.visible.set(false);
    fixture.detectChanges();
    const el = fixture.nativeElement.querySelector('.disclaimer');
    expect(el).toBeNull();
  });

  it('should hide when close button is clicked', () => {
    const button = fixture.nativeElement.querySelector('button');
    button.click();
    fixture.detectChanges();
    const el = fixture.nativeElement.querySelector('.disclaimer');
    expect(el).toBeNull();
    expect(component.visible()).toBe(false);
  });

  it('should accept custom text input', () => {
    fixture.componentRef.setInput('text', 'Custom warning');
    fixture.detectChanges();
    const el = fixture.nativeElement.querySelector('.disclaimer');
    expect(el.textContent).toContain('Custom warning');
  });
});
