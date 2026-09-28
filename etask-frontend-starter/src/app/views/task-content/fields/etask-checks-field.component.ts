import {Component, Input, OnDestroy, OnInit} from '@angular/core';
import {TextField} from '@netgrif/components-core';
import {Subscription} from 'rxjs';

/** One status line of the net, as a chip. */
interface Check {
  tone: 'ok' | 'warn' | 'info';
  text: string;
}

/**
 * Read-only text field shown as status chips instead of a grey text box.
 *
 * A net writes one finding per line and marks each: `✓ text` for "fine", `! text` for
 * "look at this", anything else is neutral. `fa_faktura` uses it for the input checks
 * the invoice officer sees first - the point is that "is there anything to deal with"
 * is answered by colour before a word is read. A text box made every finding look the
 * same, including "everything matches".
 *
 *     <dataRef>
 *         <id>fa_validacia</id>
 *         ...
 *         <component><name>checks</name></component>
 *     </dataRef>
 *
 * Why layer 3: the library renders a text field as an input or a textarea and has no
 * way to present lines of a value differently - that is the missing primitive. The
 * value itself stays a plain text field, so the API, the tests and a portal without
 * this component still see the same text.
 */
@Component({
  selector: 'app-etask-text-checks',
  templateUrl: './etask-checks-field.component.html',
  styleUrls: ['./etask-checks-field.component.scss'],
})
export class EtaskChecksFieldComponent implements OnInit, OnDestroy {

  @Input() dataField: TextField;

  public checks: Array<Check> = [];
  private sub: Subscription;

  ngOnInit(): void {
    this.parse();
    this.sub = this.dataField.valueChanges().subscribe(() => this.parse());
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  private parse(): void {
    const raw = (this.dataField?.value || '') as string;
    this.checks = raw.split('\n')
      .map(l => l.trim())
      .filter(l => !!l)
      .map(l => {
        if (l.startsWith('✓')) {
          return {tone: 'ok', text: l.substring(1).trim()} as Check;
        }
        if (l.startsWith('!') || l.startsWith('•')) {
          return {tone: 'warn', text: l.substring(1).trim()} as Check;
        }
        return {tone: 'info', text: l} as Check;
      });
  }
}
