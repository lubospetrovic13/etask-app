import {Component, HostListener, Input, OnDestroy, Type} from '@angular/core';
import {AbstractFieldComponentResolverComponent, TaskContentService} from '@netgrif/components-core';
import {Subject, Subscription} from 'rxjs';
import {debounceTime} from 'rxjs/operators';

/** How long after the last keystroke the typed value is committed. */
const TYPING_DEBOUNCE_MS = 600;

/**
 * Field types where committing a half-typed value is meaningful.
 *
 * Compared against `getElementType()` - the same thing the resolver's own
 * template switches on. NOT `instanceof TextField`: measured in the browser,
 * the field object's class comes out as `E4e` after minification, so an
 * `instanceof` against the imported symbol silently answers false and the
 * whole feature quietly does nothing. `DataField` has no `type` property at
 * runtime either (`'type' in field === false`), so `getElementType()` is the
 * only honest source.
 */
const TYPABLE = ['text', 'number'];

/**
 * Application copy of @netgrif/components' FieldComponentResolverComponent.
 *
 * The library resolver dispatches field types through a hardcoded `ngSwitch` with
 * no registry or injection token, so replacing the component for a single field
 * type means owning the template. This copy differs from the library's in exactly
 * one place: BUTTON resolves to {@link EtaskButtonFieldComponent}.
 *
 * Maintenance note: field types and component variants added by a future
 * @netgrif/components release will not appear here until this template is
 * re-synced with node_modules/@netgrif/components/esm2020/lib/task-content/
 * field-component-resolver/.
 *
 *
 * SAVING WHILE TYPING
 *
 * By default a data field is saved when the input loses focus. That is not the
 * save layer's decision - it is one line in the library:
 *
 *     AbstractDataFieldComponent: new FormControl('', {updateOn: 'blur'})
 *
 * The chain is: input -(updateOn: 'blur')-> FormControl.valueChanges ->
 * DataField.value -> TaskDataService.updateTaskDataFields() -> POST /task/{id}/data.
 * So nothing between the DOM and the server needs changing; the value simply does
 * not leave the input until blur. The FormControl is created in a private field of
 * a library class with no injection token, so there is no way to ask for
 * `updateOn: 'change'` from the outside - that is the missing primitive that puts
 * this in layer 3.
 *
 * A field can opt in from the Petriflow XML:
 *
 *     <data type="text">
 *         <id>poznamka</id>
 *         <component>
 *             <name>textarea</name>
 *             <properties>
 *                 <property key="saveWhileTyping">true</property>
 *             </properties>
 *         </component>
 *     </data>
 *
 * It is opt-in and not the default on purpose. What it costs:
 *
 *   1. Every commit is a request that runs the transition's `set` actions on the
 *      server. In this stack those actions do real work (recalculations, warnings,
 *      re-rendering item lists), so a field typed into for ten seconds means
 *      ~15 action runs instead of one.
 *   2. The server's answer is written back into the input
 *      (`registerFormControl`: `_value` -> `formControl.setValue`). For a field
 *      whose action normalizes the value - trims it, formats a number, recomputes
 *      it - that write lands WHILE the user is typing and moves the caret or
 *      replaces the text. On blur this is invisible; while typing it is not.
 *      **Do not enable this on a field that an action rewrites.**
 *   3. Two requests can be in flight at once and `setData` has no version, so the
 *      slower answer wins. The debounce below makes that rare, not impossible.
 *   4. `required` and pattern validations start showing mid-word.
 *
 * What it buys: the field is saved even if the user never leaves it (closing the
 * task, clicking a button in the same form). That last case is a real trap this
 * repository already lints for - `pflint`'s `button-reads-text` rule: blur and
 * click are one gesture, so an action behind the button reads the value the field
 * had BEFORE the user typed. On a field with `saveWhileTyping` that race is gone.
 */
@Component({
  selector: 'app-etask-field-component-resolver',
  templateUrl: './etask-field-component-resolver.component.html',
  styleUrls: ['./etask-field-component-resolver.component.scss'],
})
export class EtaskFieldComponentResolverComponent extends AbstractFieldComponentResolverComponent implements OnDestroy {

  @Input() taskContentComponentClassReference: Type<any>;

  private readonly typed$ = new Subject<string>();
  private readonly sub: Subscription;

  constructor(taskContentService: TaskContentService) {
    super(taskContentService);
    this.sub = this.typed$.pipe(debounceTime(TYPING_DEBOUNCE_MS)).subscribe(raw => this.commit(raw));
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    this.typed$.complete();
  }

  /**
   * Keystrokes reach this through event delegation - the `input` event bubbles out
   * of the library's own `<input>`, so no library template has to be copied.
   */
  @HostListener('input', ['$event'])
  onInput(event: Event): void {
    if (!this.saveWhileTyping()) {
      return;
    }
    const target = event?.target as HTMLInputElement | HTMLTextAreaElement;
    if (!target || !('value' in target)) {
      return;
    }
    // A `mat-select` search box or a file input also emits `input`; only the
    // field's own control may commit.
    if (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA') {
      return;
    }
    if (target.type === 'file' || target.type === 'checkbox' || target.type === 'radio') {
      return;
    }
    this.typed$.next(target.value);
  }

  private saveWhileTyping(): boolean {
    if (!TYPABLE.includes(this.getElementType())) {
      return false;
    }
    const field = this.getDataField();
    if (!field || field.disabled) {
      return false;
    }
    return field.component?.properties?.saveWhileTyping === 'true';
  }

  private commit(raw: string): void {
    const field = this.getDataField();
    if (!field || field.disabled) {
      return;
    }
    const value = this.getElementType() === 'number' ? this.parseNumber(raw) : (raw ?? '');
    if (value === undefined) {
      return;   // half-typed number ("-", "12."), nothing to save yet
    }
    // Equal value would be a request that changes nothing - and on a number field
    // it would also re-trigger every `set` action for no reason.
    if (field.value === value) {
      return;
    }
    // Assigning `value` is what the library itself does on blur, so the whole
    // save chain (validation, changed fields, POST) stays the library's.
    field.value = value;
  }

  /** `undefined` = nothing worth saving yet ("-", "12.", "1e"). */
  private parseNumber(raw: string): number | undefined {
    const text = (raw ?? '').trim().replace(',', '.');
    if (text === '') {
      return null as unknown as number;
    }
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
}
