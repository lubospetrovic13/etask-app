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
  TaskElementType,
  TaskEventService,
  TaskRefField,
} from '@netgrif/components-core';
import {Subscription} from 'rxjs';
import {DocumentFocusService} from './services/document-focus.service';

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
  private readonly _layouts = new WeakMap<object, {key: string, source: any, areas: string, content: Array<any>}>();
  private reloading = false;

  constructor(fieldConverter: FieldConverterService,
              public taskContentService: TaskContentService,
              paperView: PaperViewService,
              logger: LoggerService,
              protected _elementRef: ElementRef<HTMLElement>,
              @Optional() taskEventService: TaskEventService,
              @Optional() @Inject(NAE_ASYNC_RENDERING_CONFIGURATION) config,
              @Optional() private _taskDataService: TaskDataService,
              @Optional() private _changedFieldsService: ChangedFieldsService,
              private readonly _documentFocus: DocumentFocusService) {
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

  /**
   * The subgrid that holds a document viewer (`<component><name>document</name>`), or
   * undefined. The viewer's x is where the form ends and the document begins.
   */
  private documentItem(subgrid: any): any {
    return (subgrid?.content || []).find(i => i?.item?.component?.name === 'document' && i?.item?.layout);
  }

  /**
   * Grid columns of one subgrid. Without a document viewer it is the library's
   * `repeat(n, 1fr)`. With one, the columns left of the viewer share the form's part of
   * the width and the rest share the document's, so dragging the viewer's handle moves
   * the boundary without the net knowing. `minmax(0, …)` lets a column shrink below its
   * content's minimum - without it a long value would push the document off screen.
   */
  /**
   * Grid areas and cells of one subgrid, with the document viewer stretched down over
   * every empty row below it - so it runs alongside the whole form, however long.
   *
   * The net cannot say that itself. Netgrif Builder keeps a field at most 10 rows tall:
   * a taller one is moved below the form on opening the transition's form and written
   * back there on save (measured: rows 10 stays at x=2, rows 11 lands at x=0 under the
   * last field). So the net gives the viewer a builder-safe height (`rows` ≤ 10, which
   * is also its minimum height here), and the rest of the column is claimed here. The
   * library fills empty tiles with one blank cell each; those in the viewer's columns
   * are dropped and their tiles given to the viewer. It stops at the first row where
   * any of those columns holds a real field.
   */
  layoutOf(subgrid: any): {areas: string, content: Array<any>} {
    const key = subgrid?.gridAreas || '';
    const cached = this._layouts.get(subgrid);
    if (cached && cached.key === key && cached.source === subgrid.content) {
      return cached;
    }
    const layout = {key, source: subgrid.content, areas: key, content: subgrid.content || []};
    const doc = this.documentItem(subgrid);
    if (doc && key) {
      const grid: Array<Array<string>> = key.split(' | ').map(row => row.split(' '));
      const id = doc.gridAreaId;
      const lastRow = grid.map(row => row.includes(id)).lastIndexOf(true);
      const cols = lastRow < 0 ? [] : grid[lastRow].map((a, i) => a === id ? i : -1).filter(i => i >= 0);
      const blanks = new Set(layout.content.filter(i => i?.type === TaskElementType.BLANK).map(i => i.gridAreaId));
      const taken = new Set<string>();
      for (let r = lastRow + 1; cols.length && r < grid.length; r++) {
        if (!cols.every(c => blanks.has(grid[r][c]))) {
          break;
        }
        cols.forEach(c => {
          taken.add(grid[r][c]);
          grid[r][c] = id;
        });
      }
      if (taken.size) {
        layout.areas = grid.map(row => row.join(' ')).join(' | ');
        layout.content = layout.content.filter(i => !taken.has(i.gridAreaId));
      }
    }
    this._layouts.set(subgrid, layout);
    return layout;
  }

  /** Minimum height of the viewer's cell: the rows the net gave it. */
  documentMinHeight(item: any): number | null {
    return item?.item?.component?.name === 'document' ? (item.item.layout?.rows || 1) * 75 - 16 : null;
  }

  columnsOf(subgrid: any): string {
    const doc = this.documentItem(subgrid);
    const cols = subgrid?.cols || 1;
    const x = doc?.item?.layout?.x || 0;
    if (!doc || x <= 0 || x >= cols) {
      return subgrid.getGridColumns();
    }
    const split = this._documentFocus.split$.value;
    const left = (split / x).toFixed(4);
    const right = ((1 - split) / (cols - x)).toFixed(4);
    return `repeat(${x}, minmax(0, ${left}fr)) repeat(${cols - x}, minmax(0, ${right}fr))`;
  }

  @HostListener('mouseover', ['$event'])
  public onMouseOver(event: MouseEvent): void {
    // The info icon of a compact form: always shows its text, there is no clamp to test.
    const info = (event.target as HTMLElement)?.closest?.('.app-field-info') as HTMLElement;
    if (info && info.closest('app-etask-task-content') === this._elementRef.nativeElement) {
      this.show(info, info.dataset.desc || '');
      return;
    }
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
    const hint = (event.target as HTMLElement)?.closest?.(EtaskTaskContentComponent.HINT + ', .app-field-info');
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

  private show(hint: HTMLElement, text?: string): void {
    if (!this.popover) {
      this.popover = document.createElement('div');
      this.popover.className = 'app-desc-popover';
      document.body.appendChild(this.popover);
    }
    this.anchor = hint;
    this.popover.textContent = (text ?? hint.textContent).trim();
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
