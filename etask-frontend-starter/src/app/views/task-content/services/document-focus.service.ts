import {Injectable} from '@angular/core';
import {BehaviorSubject} from 'rxjs';

/** A form field the user is looking at, so the document viewer can find its value. */
export interface FocusedValue {
  /** `getElementType()` of the field: text, number, date, dateTime, ... */
  type: string;
  /** The field's current value, as the library holds it (string, number, Date, moment). */
  value: any;
}

const SPLIT_KEY = 'etask.documentSplit';
const SPLIT_DEFAULT = 0.5;
export const SPLIT_MIN = 0.3;
export const SPLIT_MAX = 0.7;

/**
 * What the form and the document viewer next to it tell each other.
 *
 *   focused$ - the field under the pointer or in focus. The viewer highlights where its
 *              value is in the document, so checking "is this the number on the paper"
 *              is a glance, not a search.
 *   split$   - the share of the width the form gets (0.3 - 0.7). The viewer's handle
 *              moves it, the task content turns it into grid columns. Remembered per
 *              browser: people who check invoices all day settle on one width.
 */
@Injectable({providedIn: 'root'})
export class DocumentFocusService {

  readonly focused$ = new BehaviorSubject<FocusedValue | null>(null);
  readonly split$ = new BehaviorSubject<number>(DocumentFocusService.load());

  private static load(): number {
    try {
      const v = parseFloat(localStorage.getItem(SPLIT_KEY));
      if (v >= SPLIT_MIN && v <= SPLIT_MAX) {
        return v;
      }
    } catch {
      // Private mode or blocked site data: the default it is.
    }
    return SPLIT_DEFAULT;
  }

  focus(value: FocusedValue | null): void {
    this.focused$.next(value);
  }

  setSplit(split: number, persist = false): void {
    const v = Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, split));
    this.split$.next(v);
    if (persist) {
      try {
        localStorage.setItem(SPLIT_KEY, String(v));
      } catch {
        // The width holds for this tab only.
      }
    }
  }
}
