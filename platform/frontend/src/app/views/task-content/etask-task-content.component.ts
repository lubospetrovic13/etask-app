import {Component, ElementRef, HostListener, Inject, OnDestroy, Optional} from '@angular/core';
import {
  AbstractTaskContentComponent,
  AfterAction,
  ChangedFieldsService,
  FieldConverterService,
  LoggerService,
  NAE_ASYNC_RENDERING_CONFIGURATION,
  PaperViewService,
  TaskContentService,
  TaskDataService,
  TaskEventService,
  TaskRefField,
} from '@netgrif/components-core';
import {Subscription} from 'rxjs';

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

  private changedFieldsSub: Subscription | null = null;
  private reloading = false;

  constructor(fieldConverter: FieldConverterService,
              public taskContentService: TaskContentService,
              paperView: PaperViewService,
              logger: LoggerService,
              protected _elementRef: ElementRef<HTMLElement>,
              @Optional() taskEventService: TaskEventService,
              @Optional() @Inject(NAE_ASYNC_RENDERING_CONFIGURATION) config,
              @Optional() private _taskDataService: TaskDataService,
              @Optional() private _changedFieldsService: ChangedFieldsService) {
    super(fieldConverter, taskContentService, paperView, logger, taskEventService, config);
    // Capture, because the scrolling happens on inner elements that do not bubble scroll.
    document.addEventListener('scroll', this.hideOnScroll, true);
    window.addEventListener('resize', this.hideOnScroll);
    this.reloadOnTaskRefChange();
  }

  /**
   * Re-fetches the task when one of its task reference fields is pointed at a
   * different task.
   *
   * A task reference is expanded on the server: GET /task/{id}/data returns the
   * referenced task's data groups inline, and the frontend then splits them out
   * around the reference (see AbstractTaskContentComponent.rearrangeDataGroups).
   * A setData response, by contrast, carries only changed field values, so
   * changing a reference's value updates the value and nothing else - the newly
   * referenced form has no data groups anywhere in the response and the old ones
   * are still on screen. The swap only appeared after a reload.
   *
   * Forcing a data reload gives the server a chance to expand the new reference.
   * `force` matters: without it the request is skipped when the task is already
   * loaded, which it always is here.
   *
   * Nested task content components are instances of this same class, so the
   * check that the changed task is this component's own task is what keeps
   * exactly one of them reacting.
   */
  private reloadOnTaskRefChange(): void {
    if (!this._changedFieldsService || !this._taskDataService) {
      return;
    }
    this.changedFieldsSub = this._changedFieldsService.changedFields$.subscribe(changedFields => {
      if (this.reloading || !this.becameTaskRefChange(changedFields)) {
        return;
      }
      this.reloading = true;
      // AfterAction is a Subject that resolves once the request settles, so the
      // flag is cleared whether the reload succeeded or not.
      const done = new AfterAction();
      done.subscribe(() => this.reloading = false);
      this._taskDataService.initializeTaskDataFields(done, true);
    });
  }

  /** True when the change touches the value of a task reference on this task. */
  private becameTaskRefChange(changedFields: object): boolean {
    const taskId = this.taskContentService?.task?.stringId;
    const fieldsOfThisTask = this.taskContentService?.taskFieldsIndex?.[taskId]?.fields;
    if (!taskId || !fieldsOfThisTask || !changedFields) {
      return false;
    }

    // The map arrives keyed by case and task in some paths and flat in others,
    // so rather than assume a depth, walk it and test every key that names a
    // field of this task.
    const seen = new Set<object>();
    const walk = (node: unknown): boolean => {
      if (!node || typeof node !== 'object' || seen.has(node as object)) {
        return false;
      }
      seen.add(node as object);
      return Object.entries(node).some(([key, child]) => {
        const field = fieldsOfThisTask[key];
        if (field instanceof TaskRefField && child && typeof child === 'object' && 'value' in child) {
          return true;
        }
        return walk(child);
      });
    };
    return walk(changedFields);
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
    this.changedFieldsSub?.unsubscribe();
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
