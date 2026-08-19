import {Component, ElementRef, HostListener, Inject, OnDestroy, Optional} from '@angular/core';
import {
  AbstractTaskContentComponent,
  FieldConverterService,
  LoggerService,
  NAE_ASYNC_RENDERING_CONFIGURATION,
  PaperViewService,
  TaskContentService,
  TaskEventService,
} from '@netgrif/components-core';

/**
 * Application copy of @netgrif/components' TaskContentComponent, differing in the
 * resolver it renders ({@link EtaskFieldComponentResolverComponent}) and in owning the
 * form's single description popover.
 *
 * Wired in by EtaskTaskPanelComponent through the panel's `panelContentComponent` input,
 * which AbstractTaskPanelComponent already supports - so nothing in @netgrif/components
 * is patched.
 *
 * ## Why the popover lives here and not on the fields
 *
 * Field descriptions are clipped to a couple of lines (see `--app-hint-lines`) and the
 * rest is revealed on hover. Doing that per field with CSS produced three different
 * behaviours - form fields, file/i18n fields and our own components each needed their own
 * anchor - and none of them could escape their surroundings: a field sits inside
 * `cdk-virtual-scroll-viewport` (`contain: strict`) and `mat-tab-body-content`
 * (`transform: translate(...)`), both of which clip an absolutely positioned child and
 * break `position: fixed`.
 *
 * So the form owns one popover, appended to `document.body`, driven by delegated hover.
 * That makes the behaviour identical for every field type, whoever rendered it, and lets
 * the popover be as wide as it needs without being cut off. It also only appears when the
 * text is actually clipped, so hovering a short description does nothing.
 */
@Component({
  selector: 'app-etask-task-content',
  templateUrl: './etask-task-content.component.html',
  styleUrls: ['./etask-task-content.component.scss'],
})
export class EtaskTaskContentComponent extends AbstractTaskContentComponent implements OnDestroy {

  public taskContentComponentClass = EtaskTaskContentComponent;

  private static readonly HINT = '.mat-hint';
  private static readonly TRUNCATED_CLASS = 'app-desc-truncated';
  private static readonly GAP = 6;
  private static readonly MARGIN = 12;

  private popover: HTMLElement | null = null;
  private anchor: HTMLElement | null = null;
  private readonly hideOnScroll = () => this.hide();

  constructor(fieldConverter: FieldConverterService,
              public taskContentService: TaskContentService,
              paperView: PaperViewService,
              logger: LoggerService,
              protected _elementRef: ElementRef<HTMLElement>,
              @Optional() taskEventService: TaskEventService,
              @Optional() @Inject(NAE_ASYNC_RENDERING_CONFIGURATION) config) {
    super(fieldConverter, taskContentService, paperView, logger, taskEventService, config);
    // Capture, because the scrolling happens on inner elements that do not bubble scroll.
    document.addEventListener('scroll', this.hideOnScroll, true);
    window.addEventListener('resize', this.hideOnScroll);
  }

  @HostListener('mouseover', ['$event'])
  public onMouseOver(event: MouseEvent): void {
    const hint = (event.target as HTMLElement)?.closest?.(EtaskTaskContentComponent.HINT) as HTMLElement;
    if (!hint || hint.classList.contains('mat-error')) {
      return;
    }
    // A task reference renders a nested task content; let the innermost one own the event.
    if (hint.closest('app-etask-task-content') !== this._elementRef.nativeElement) {
      return;
    }
    if (!this.isClipped(hint)) {
      hint.classList.remove(EtaskTaskContentComponent.TRUNCATED_CLASS);
      this.hide();
      return;
    }
    hint.classList.add(EtaskTaskContentComponent.TRUNCATED_CLASS);
    this.show(hint);
  }

  @HostListener('mouseout', ['$event'])
  public onMouseOut(event: MouseEvent): void {
    const hint = (event.target as HTMLElement)?.closest?.(EtaskTaskContentComponent.HINT);
    if (hint && hint === this.anchor) {
      this.hide();
    }
  }

  ngOnDestroy(): void {
    document.removeEventListener('scroll', this.hideOnScroll, true);
    window.removeEventListener('resize', this.hideOnScroll);
    this.destroyPopover();
    if (super.ngOnDestroy) {
      super.ngOnDestroy();
    }
  }

  /** The clamp hides the overflow, so this is what "there is more to read" means. */
  private isClipped(el: HTMLElement): boolean {
    return el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1;
  }

  private show(hint: HTMLElement): void {
    if (!this.popover) {
      this.popover = document.createElement('div');
      this.popover.className = 'app-desc-popover';
      document.body.appendChild(this.popover);
    }
    this.anchor = hint;
    this.popover.textContent = hint.textContent.trim();
    this.position(hint);
    this.popover.classList.add('app-desc-popover-visible');
  }

  private hide(): void {
    this.anchor = null;
    if (this.popover) {
      this.popover.classList.remove('app-desc-popover-visible');
    }
  }

  /**
   * Anchored under the description, nudged back inside the viewport horizontally and
   * flipped above the field when there is not enough room below. The size has to be read
   * after the text is in place, hence the measure-then-adjust.
   */
  private position(hint: HTMLElement): void {
    const p = this.popover;
    const gap = EtaskTaskContentComponent.GAP;
    const margin = EtaskTaskContentComponent.MARGIN;
    const rect = hint.getBoundingClientRect();

    p.style.maxWidth = Math.min(460, window.innerWidth - 2 * margin) + 'px';
    p.style.left = '0px';
    p.style.top = '0px';

    const size = p.getBoundingClientRect();
    let left = rect.left;
    if (left + size.width > window.innerWidth - margin) {
      left = window.innerWidth - margin - size.width;
    }
    let top = rect.bottom + gap;
    if (top + size.height > window.innerHeight - margin) {
      const above = rect.top - gap - size.height;
      top = above >= margin ? above : Math.max(margin, window.innerHeight - margin - size.height);
    }
    p.style.left = Math.max(margin, left) + 'px';
    p.style.top = top + 'px';
  }

  private destroyPopover(): void {
    if (this.popover?.parentNode) {
      this.popover.parentNode.removeChild(this.popover);
    }
    this.popover = null;
  }
}
