import {Component, Inject, OnInit, Optional} from '@angular/core';
import {AbstractBooleanFieldComponent, NAE_INFORM_ABOUT_INVALID_DATA} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';

/** Visual variants selectable from the Petriflow XML. */
export type EtaskBooleanVariant = 'toggle' | 'section' | 'segmented' | 'checkbox' | 'chip';

const VARIANTS: Array<EtaskBooleanVariant> = ['toggle', 'section', 'segmented', 'checkbox', 'chip'];

/** Status keywords a chip may use, mapped to tokens in the stylesheet. */
const CHIP_TONES = ['success', 'danger', 'warning', 'info', 'accent', 'muted'];

/**
 * Boolean field with selectable presentation.
 *
 * @netgrif/components renders every boolean as a mat-slide-toggle and has no component
 * switch at all - but `field-converter.service.ts:41` does pass `item.component` into
 * `BooleanField`, so the `<component>` element and its `<properties>` are available on
 * the field and are simply thrown away. This component reads them:
 *
 *     <component>
 *         <name>toggle</name>
 *         <properties>
 *             <property key="variant">section</property>
 *         </properties>
 *     </component>
 *
 * Variants:
 *   toggle    - mat-slide-toggle, identical to the library. The default, so a field
 *               without properties keeps behaving exactly as before.
 *   section   - the whole row is the control: title on the left, chevron on the right.
 *               This is what lets a collapsible section stop looking like a switch.
 *               `iconOn` / `iconOff` override the chevron.
 *   segmented - two joined buttons, the active one filled. State is readable without
 *               reading the label next to a switch.
 *   checkbox  - the most compact variant, for forms with many flags.
 *   chip      - a coloured dot and a label, for computed or read-only flags. Tones come
 *               from `chipTrue` / `chipFalse` (success, danger, warning, info, accent,
 *               muted); it stays clickable while the field is editable.
 */
@Component({
  selector: 'app-etask-boolean-field',
  templateUrl: './etask-boolean-field.component.html',
  styleUrls: ['./etask-boolean-field.component.scss'],
})
export class EtaskBooleanFieldComponent extends AbstractBooleanFieldComponent implements OnInit {

  public variant: EtaskBooleanVariant = 'toggle';

  constructor(translate: TranslateService,
              @Optional() @Inject(NAE_INFORM_ABOUT_INVALID_DATA) informAboutInvalidData: boolean | null) {
    super(translate, informAboutInvalidData);
  }

  ngOnInit(): void {
    super.ngOnInit();
    const requested = this.dataField?.component?.properties?.variant;
    if (VARIANTS.includes(requested)) {
      this.variant = requested;
    }
  }

  public isOn(): boolean {
    return !!this.formControl.value;
  }

  /** Petriflow sends a boolean value, so the control is set directly rather than counted up. */
  public setValue(value: boolean): void {
    if (!this.formControl.disabled && value !== this.isOn()) {
      this.formControl.setValue(value);
    }
  }

  public toggle(): void {
    this.setValue(!this.isOn());
  }

  /** Chevron for the `section` variant; overridable the same way as on a button field. */
  public sectionIcon(): string {
    const properties = this.dataField?.component?.properties;
    const custom = this.isOn() ? properties?.iconOn : properties?.iconOff;
    return custom !== undefined ? custom : (this.isOn() ? 'expand_less' : 'expand_more');
  }

  /** Tone class for the `chip` variant. Defaults: on = success, off = muted. */
  public chipClass(): string {
    const properties = this.dataField?.component?.properties;
    const requested = this.isOn() ? properties?.chipTrue : properties?.chipFalse;
    const tone = CHIP_TONES.includes(requested) ? requested : (this.isOn() ? 'success' : 'muted');
    return 'app-chip-' + tone;
  }
}
