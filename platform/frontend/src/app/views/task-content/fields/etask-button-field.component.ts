import {Component, Inject, OnInit, Optional} from '@angular/core';
import {
  AbstractButtonFieldComponent,
  DialogService,
  NAE_INFORM_ABOUT_INVALID_DATA,
} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';

/**
 * Button field that can show its own state.
 *
 * The library renders an icon button's glyph from `dataField.placeholder`, and
 * Petriflow cannot change a placeholder at runtime: the engine's `change <field>`
 * DSL accepts only `value`, `choices`, `options`, `allowedNets` and `validations`
 * (ActionDelegate.groovy:565), so a one-button collapse toggle could never flip
 * its arrow. That is why section toggles in the processes had to be boolean
 * fields instead.
 *
 * A button's value increments on every click - `AbstractButtonFieldComponent`
 * `resolveValue()` does `setValue(value + 1)` - so the value's parity already *is*
 * the toggle state. This component reads two icons from the component properties
 * and picks between them on that parity, which needs no engine support at all:
 *
 *     <component>
 *         <name>icon</name>
 *         <properties>
 *             <property key="iconOff">expand_more</property>
 *             <property key="iconOn">expand_less</property>
 *         </properties>
 *     </component>
 *
 * With neither property set the behaviour is identical to the library's.
 */
@Component({
  selector: 'app-etask-button-field',
  templateUrl: './etask-button-field.component.html',
  styleUrls: ['./etask-button-field.component.scss'],
})
export class EtaskButtonFieldComponent extends AbstractButtonFieldComponent implements OnInit {

  /** `<property key="align">start|center|end</property>` */
  public align: string;
  /** `<property key="stretch">true</property>` - button fills the cell width */
  public stretch: string;

  constructor(translate: TranslateService,
              dialogService: DialogService,
              @Optional() @Inject(NAE_INFORM_ABOUT_INVALID_DATA) informAboutInvalidData: boolean | null) {
    super(translate, dialogService, informAboutInvalidData);
  }

  ngOnInit(): void {
    super.ngOnInit();
    const properties = this.dataField?.component?.properties;
    if (properties?.align) {
      this.align = properties.align;
    }
    if (properties?.stretch) {
      this.stretch = properties.stretch;
    }
  }

  /**
   * True on every odd click. The value is set locally before the request is sent,
   * so the icon flips immediately rather than after the server round trip, and it
   * survives a reload because the counter is persisted.
   */
  public isToggledOn(): boolean {
    const value = this.dataField?.value;
    return typeof value === 'number' && Math.abs(value) % 2 === 1;
  }

  /**
   * Glyph for an icon-type button: `iconOn`/`iconOff` when either is configured,
   * otherwise the placeholder the library would have used.
   */
  public resolveIcon(): string {
    const properties = this.dataField?.component?.properties;
    const on = properties?.iconOn;
    const off = properties?.iconOff;

    if (on !== undefined || off !== undefined) {
      const chosen = this.isToggledOn() ? on : off;
      return chosen !== undefined ? chosen : this.dataField.placeholder;
    }
    return this.dataField.placeholder;
  }
}
