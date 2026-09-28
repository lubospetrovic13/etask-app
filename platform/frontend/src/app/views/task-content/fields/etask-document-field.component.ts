import {
  AfterViewInit, Component, ElementRef, HostListener, Input, NgZone, OnDestroy, OnInit, ViewChild,
} from '@angular/core';
import {DomSanitizer, SafeUrl} from '@angular/platform-browser';
import {FileField, TaskResourceService} from '@netgrif/components-core';
import * as pdfjs from 'pdfjs-dist/legacy/build/pdf';
import {Subscription} from 'rxjs';
import {DocumentFocusService, FocusedValue} from '../services/document-focus.service';

/** What the viewer can show. Anything else gets a download hint instead. */
type DocumentKind = 'pdf' | 'image' | 'text' | 'none';

/** One piece of text on a rendered PDF page, in CSS pixels of that page. */
interface TextBox {
  norm: string;
  left: number;
  top: number;
  width: number;
  height: number;
}

/** A rendered PDF page. */
interface Page {
  el: HTMLElement;
  marks: HTMLElement;
  boxes: Array<TextBox>;
}

/** Grid row height of the library, `abstract-file-field.component` (not exported there). */
const FIELD_HEIGHT = 75;
const FIELD_PADDING = 16;
/** Our toolbar above the document. Fixed, so the viewer never overflows its grid cell. */
const TOOLBAR_HEIGHT = 48;
/** Room the portal keeps above a task panel (tabs, search, list header), when it cannot be measured. */
const PAGE_CHROME = 150;
/** `top` of the sticky document (scss), kept free below it as well. */
const STICKY_GAP = 8;
const PAGE_GAP = 12;

// The worker is copied next to the app by angular.json (assets, pdfjs).
pdfjs.GlobalWorkerOptions.workerSrc = 'assets/pdfjs/pdf.worker.min.js';

/**
 * File field that shows the document itself, large, next to the form - and points at
 * the value of the field you are looking at.
 *
 * The library file field has a `preview` component, but it is a thumbnail: 20 % of the
 * field width and an `<img>`, so a PDF - which is what invoices mostly are - is not
 * shown at all. There is no library component that renders an attachment across half a
 * form. That is the missing primitive that puts this in layer 3. The layout itself
 * (fields on the left, the document on the right) stays in the net, as grid positions.
 *
 *     <dataRef>
 *         <id>fa_skan</id>
 *         <layout><x>2</x><y>0</y><rows>10</rows><cols>2</cols>...</layout>
 *         <component><name>document</name></component>
 *     </dataRef>
 *
 * `rows` is the minimum height; the viewer runs down beside the whole form on its own
 * (layoutOf in the task content). Keep it at 10 or less: Netgrif Builder moves a taller
 * field below the form and saves it there.
 *
 * What it does:
 *
 *   - PDF is rendered here with PDF.js, page by page, fitted to the width. Not the
 *     browser's own viewer: that one is a closed iframe, nothing can be marked in it.
 *   - Point at a field (hover or focus) and its value is marked in the document and
 *     scrolled into view: amount, dates, IBAN, invoice number, supplier. That is the
 *     whole job of the person checking an invoice - is this number the one on the
 *     paper - made a glance. Works on PDFs with a text layer and on XML e-invoices;
 *     a scanned image has no text to search, so nothing is marked there.
 *   - A handle on the left edge moves the boundary between form and document; the
 *     width is remembered (DocumentFocusService).
 *   - One toolbar: name, zoom, upload/replace and remove (when editable), download,
 *     open in a new tab. No file yet and editable: a drop zone.
 *   - It sticks to the top while the form scrolls and is never taller than the window,
 *     so the only scrollbar is the document's own.
 *
 * Upload and delete are the library's: `nc-file-field` is inside, hidden, and this
 * component drives its file input and delete button - validation, size limits and the
 * backend calls stay exactly the library's. It is not a subclass of the library file
 * field on purpose: that class registers its own FormControl on the data field, and
 * two of them on one field would fight over the value.
 */
@Component({
  selector: 'app-etask-file-document',
  templateUrl: './etask-document-field.component.html',
  styleUrls: ['./etask-document-field.component.scss'],
})
export class EtaskDocumentFieldComponent implements OnInit, AfterViewInit, OnDestroy {

  @Input() dataField: FileField;
  @Input() taskId: string;
  @Input() taskOffset = 0;

  @ViewChild('sheet') sheetRef: ElementRef<HTMLElement>;
  @ViewChild('pages') pagesRef: ElementRef<HTMLElement>;

  public kind: DocumentKind = 'none';
  public loading = false;
  public failed = false;
  public dragging = false;
  public resizing = false;
  public imageUrl: SafeUrl;
  public text: string;
  public textHtml: string;
  public zoom = 1;
  public found = 0;
  public windowHeight = window.innerHeight;
  public hostHeight = 0;
  private room = 0;
  private readonly watched = new Set<Element>();

  private objectUrl: string;
  private loadedName: string;
  private pdf: any;
  private pages: Array<Page> = [];
  private renderToken = 0;
  private lastFocus: FocusedValue | null = null;
  private resizeObserver: ResizeObserver;
  private resizeTimer: any;
  private lastWidth = 0;
  private subs: Array<Subscription> = [];
  private download: Subscription;

  constructor(private readonly taskResource: TaskResourceService,
              private readonly sanitizer: DomSanitizer,
              private readonly host: ElementRef<HTMLElement>,
              private readonly zone: NgZone,
              private readonly documentFocus: DocumentFocusService) {
  }

  ngOnInit(): void {
    this.load();
    this.subs.push(this.dataField.updated.subscribe(() => this.load()));
    this.subs.push(this.documentFocus.focused$.subscribe(f => {
      this.lastFocus = f;
      this.mark(true);
    }));
  }

  ngAfterViewInit(): void {
    // Re-fit when the sheet changes width: window resize, or the boundary handle.
    this.resizeObserver = new ResizeObserver(() => {
      const h = this.host.nativeElement.clientHeight;
      const room = this.room;
      this.measureRoom();
      if (h !== this.hostHeight || room !== this.room) {
        this.zone.run(() => this.hostHeight = h);
      }
      const w = this.sheetRef?.nativeElement?.clientWidth || 0;
      if (Math.abs(w - this.lastWidth) < 4) {
        return;
      }
      this.lastWidth = w;
      clearTimeout(this.resizeTimer);
      this.resizeTimer = setTimeout(() => this.zone.run(() => this.renderPdf()), 150);
    });
    // The host is sized by its grid cell (the whole form's height, see layoutOf in the
    // task content), so it is watched too: the viewer follows the form as it grows.
    this.resizeObserver.observe(this.host.nativeElement);
    if (this.sheetRef) {
      this.resizeObserver.observe(this.sheetRef.nativeElement);
    }
  }

  ngOnDestroy(): void {
    this.subs.forEach(s => s.unsubscribe());
    this.download?.unsubscribe();
    this.resizeObserver?.disconnect();
    clearTimeout(this.resizeTimer);
    this.pdf?.destroy?.();
    this.revoke();
  }

  @HostListener('window:resize')
  onResize(): void {
    this.windowHeight = window.innerHeight;
    this.measureRoom();
  }

  /**
   * Height the stuck document has: the list that scrolls the form, less the sticky
   * offset above and the action row pinned below it. Measured, not guessed - the fixed
   * `PAGE_CHROME` left the bottom 60 px of the document under the action row (1440×900:
   * list 700 px from y=200, action row 45 px).
   */
  private measureRoom(): void {
    // From above the grid: the cell itself is `overflow-y: auto` in the library.
    let el = (this.host.nativeElement.closest('.grid-rows-auto') || this.host.nativeElement).parentElement;
    while (el && el !== document.body) {
      // Not "does it overflow": the task list is a cdk-virtual-scroll-viewport, which
      // reports scrollHeight == clientHeight and still is what scrolls the form.
      if (/(auto|scroll)/.test(getComputedStyle(el).overflowY)) {
        break;
      }
      el = el.parentElement;
    }
    if (!el || el === document.body) {
      this.room = 0;
      return;
    }
    const actions = this.host.nativeElement.closest('mat-expansion-panel')?.querySelector('.mat-action-row') as HTMLElement;
    // Both settle only after the panel has expanded, later than the host: watched too,
    // or the first (wrong) measurement stayed until something else resized.
    [el, actions].filter(e => e && !this.watched.has(e)).forEach(e => {
      this.watched.add(e);
      this.resizeObserver?.observe(e);
    });
    this.room = Math.max(0, el.clientHeight - 2 * STICKY_GAP - (actions?.offsetHeight || 0));
  }

  get fileName(): string {
    return this.dataField?.value?.name || '';
  }

  get editable(): boolean {
    return !!this.dataField && !this.dataField.disabled;
  }

  get hasDocument(): boolean {
    return !!(this.pages.length || this.imageUrl || this.text !== undefined);
  }

  get canZoom(): boolean {
    return this.kind === 'pdf' || this.kind === 'image';
  }

  /** The cell, minus the toolbar, never taller than the room the form scrolls in. */
  get viewerHeight(): number {
    const cell = this.hostHeight || ((this.dataField?.layout?.rows || 1) * FIELD_HEIGHT - FIELD_PADDING);
    const fromGrid = cell - TOOLBAR_HEIGHT;
    const fromWindow = (this.room || this.windowHeight - PAGE_CHROME) - TOOLBAR_HEIGHT;
    return Math.max(Math.min(fromGrid, fromWindow), 240);
  }

  // ------------------------------------------------------------------ toolbar

  pick(): void {
    if (this.editable) {
      this.fileInput()?.click();
    }
  }

  /** Clicks the library's own delete button, so deleting stays the library's. */
  remove(): void {
    const button = Array.from(this.host.nativeElement.querySelectorAll<HTMLButtonElement>('nc-file-field button'))
      .find(b => b.textContent?.trim() === 'close');
    button?.click();
  }

  saveFile(): void {
    this.withBlob(blob => {
      const a = document.createElement('a');
      const url = URL.createObjectURL(blob);
      a.href = url;
      a.download = this.fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  openInTab(): void {
    if (this.objectUrl) {
      window.open(this.objectUrl, '_blank', 'noopener');
    }
  }

  zoomBy(factor: number): void {
    this.zoom = Math.min(4, Math.max(0.5, Math.round(this.zoom * factor * 100) / 100));
    this.renderPdf();
  }

  zoomFit(): void {
    this.zoom = 1;
    this.renderPdf();
  }

  // ------------------------------------------------------------------ boundary handle

  startResize(event: MouseEvent): void {
    event.preventDefault();
    const grid = this.host.nativeElement.closest('.grid-rows-auto') as HTMLElement;
    if (!grid) {
      return;
    }
    const width = grid.getBoundingClientRect().width;
    const startX = event.clientX;
    const start = this.documentFocus.split$.value;
    this.resizing = true;
    const move = (e: MouseEvent) => this.documentFocus.setSplit(start + (e.clientX - startX) / width);
    const up = (e: MouseEvent) => {
      this.documentFocus.setSplit(start + (e.clientX - startX) / width, true);
      this.resizing = false;
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', up);
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
  }

  // ------------------------------------------------------------------ drop zone

  @HostListener('dragover', ['$event'])
  onDragOver(event: DragEvent): void {
    if (!this.editable) {
      return;
    }
    event.preventDefault();
    this.dragging = true;
  }

  @HostListener('dragleave')
  onDragLeave(): void {
    this.dragging = false;
  }

  /**
   * A dropped file goes through the library upload: it is put on the library's own
   * input and its change handler is called - the same path a picked file takes.
   */
  @HostListener('drop', ['$event'])
  onDrop(event: DragEvent): void {
    this.dragging = false;
    if (!this.editable || !event.dataTransfer?.files?.length) {
      return;
    }
    event.preventDefault();
    const input = this.fileInput();
    if (!input) {
      return;
    }
    const dt = new DataTransfer();
    dt.items.add(event.dataTransfer.files[0]);
    input.files = dt.files;
    if (typeof input.onchange === 'function') {
      input.onchange(new Event('change'));
    } else {
      input.dispatchEvent(new Event('change'));
    }
  }

  // ------------------------------------------------------------------ loading

  private fileInput(): HTMLInputElement | null {
    return this.host.nativeElement.querySelector('nc-file-field input[type=file]');
  }

  private load(): void {
    const name = this.fileName;
    if (!name) {
      this.reset();
      return;
    }
    if (name === this.loadedName && !this.failed) {
      return;
    }
    this.reset();
    this.kind = this.kindOf(name);
    this.loadedName = name;
    if (this.kind === 'none') {
      return;
    }
    this.loading = true;
    this.withBlob(blob => this.show(blob), () => {
      this.loading = false;
      this.failed = true;
    });
  }

  private withBlob(done: (blob: Blob) => void, failed?: () => void): void {
    const taskId = this.dataField.parentTaskId ? this.dataField.parentTaskId : this.taskId;
    if (!taskId || !this.fileName) {
      return;
    }
    this.download?.unsubscribe();
    // `downloadFile` emits progress events first and the Blob last - the same filter
    // the library file field uses.
    this.download = this.taskResource.downloadFile(taskId, this.dataField.stringId).subscribe(response => {
      if (response instanceof Blob) {
        done(response);
      }
    }, () => failed?.());
  }

  private show(blob: Blob): void {
    // The server answers with application/octet-stream; opening in a new tab needs the
    // real type, otherwise the browser downloads the file instead of showing it.
    const type = this.kind === 'pdf' ? 'application/pdf' : this.kind === 'text' ? 'text/plain' : (blob.type || 'image/png');
    const typed = new Blob([blob], {type});
    this.objectUrl = URL.createObjectURL(typed);
    if (this.kind === 'text') {
      typed.text().then(t => {
        this.text = t;
        this.loading = false;
        this.mark(true);
      });
    } else if (this.kind === 'image') {
      this.imageUrl = this.sanitizer.bypassSecurityTrustUrl(this.objectUrl);
      this.loading = false;
    } else {
      typed.arrayBuffer()
        .then(buf => pdfjs.getDocument({data: new Uint8Array(buf)}).promise)
        .then(pdf => {
          this.pdf = pdf;
          this.loading = false;
          // The sheet is in the DOM only once `loading` is false.
          setTimeout(() => this.renderPdf());
        })
        .catch(() => {
          this.loading = false;
          this.failed = true;
        });
    }
  }

  /**
   * Renders every page to a canvas at the sheet width × zoom, and keeps each text
   * item's box so a value can be marked without a selectable text layer.
   */
  private async renderPdf(): Promise<void> {
    if (this.kind === 'image') {
      return;
    }
    const container = this.pagesRef?.nativeElement;
    const sheet = this.sheetRef?.nativeElement;
    if (!this.pdf || !container || !sheet) {
      return;
    }
    const token = ++this.renderToken;
    const width = Math.max(sheet.clientWidth - 2 * PAGE_GAP, 200);
    const dpr = window.devicePixelRatio || 1;
    const pages: Array<Page> = [];
    const frag = document.createDocumentFragment();
    for (let n = 1; n <= this.pdf.numPages; n++) {
      const page = await this.pdf.getPage(n);
      if (token !== this.renderToken) {
        return;
      }
      const base = page.getViewport({scale: 1});
      const scale = (width / base.width) * this.zoom;
      const vp = page.getViewport({scale});

      const el = document.createElement('div');
      el.className = 'doc__page';
      el.style.width = vp.width + 'px';
      el.style.height = vp.height + 'px';
      const canvas = document.createElement('canvas');
      canvas.width = Math.floor(vp.width * dpr);
      canvas.height = Math.floor(vp.height * dpr);
      canvas.style.width = vp.width + 'px';
      canvas.style.height = vp.height + 'px';
      const marks = document.createElement('div');
      marks.className = 'doc__marks';
      el.appendChild(canvas);
      el.appendChild(marks);
      frag.appendChild(el);

      const ctx = canvas.getContext('2d');
      await page.render({canvasContext: ctx, viewport: vp, transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined}).promise;
      const content = await page.getTextContent();
      const boxes: Array<TextBox> = [];
      for (const item of content.items as Array<any>) {
        const str = (item.str || '').trim();
        if (!str) {
          continue;
        }
        const t = pdfjs.Util.transform(vp.transform, item.transform);
        const h = Math.hypot(t[2], t[3]) || 10;
        boxes.push({norm: norm(str), left: t[4], top: t[5] - h, width: item.width * scale, height: h * 1.15});
      }
      pages.push({el, marks, boxes});
      if (token !== this.renderToken) {
        return;
      }
    }
    container.innerHTML = '';
    container.appendChild(frag);
    this.pages = pages;
    this.mark(false);
  }

  // ------------------------------------------------------------------ marking

  /** Marks the focused field's value in the document; scrolls to the first hit. */
  private mark(scroll: boolean): void {
    const cands = candidates(this.lastFocus);
    if (this.kind === 'text') {
      this.markText(cands);
      return;
    }
    let first: {page: Page, box: TextBox} | null = null;
    let count = 0;
    for (const page of this.pages) {
      page.marks.innerHTML = '';
      if (!cands.length) {
        continue;
      }
      for (const box of page.boxes) {
        if (!matches(box.norm, cands, this.lastFocus?.type)) {
          continue;
        }
        const m = document.createElement('div');
        m.className = 'doc__mark';
        m.style.left = (box.left - 2) + 'px';
        m.style.top = (box.top - 1) + 'px';
        m.style.width = (box.width + 4) + 'px';
        m.style.height = (box.height + 2) + 'px';
        page.marks.appendChild(m);
        count++;
        first = first || {page, box};
      }
    }
    this.found = count;
    const sheet = this.sheetRef?.nativeElement;
    if (scroll && first && sheet) {
      const top = first.page.el.offsetTop + first.box.top - sheet.clientHeight / 3;
      sheet.scrollTo({top: Math.max(0, top), behavior: 'smooth'});
    }
  }

  private markText(cands: Array<string>): void {
    if (this.text === undefined) {
      return;
    }
    const esc = escapeHtml(this.text);
    const raw = cands.map(c => c.trim()).filter(c => c.length >= 2);
    if (!raw.length) {
      this.textHtml = esc;
      this.found = 0;
      return;
    }
    const re = new RegExp('(' + raw.map(c => escapeHtml(c).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi');
    let count = 0;
    this.textHtml = esc.replace(re, m => {
      count++;
      return '<mark>' + m + '</mark>';
    });
    this.found = count;
    if (count) {
      setTimeout(() => this.host.nativeElement.querySelector('.doc__text mark')?.scrollIntoView({block: 'center'}));
    }
  }

  private kindOf(name: string): DocumentKind {
    const ext = name.split('.').pop().toLowerCase();
    if (ext === 'pdf') {
      return 'pdf';
    }
    if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) {
      return 'image';
    }
    if (['xml', 'txt', 'isdoc'].includes(ext)) {
      return 'text';
    }
    return 'none';
  }

  private reset(): void {
    this.revoke();
    this.renderToken++;
    this.pdf?.destroy?.();
    this.pdf = undefined;
    this.pages = [];
    if (this.pagesRef?.nativeElement) {
      this.pagesRef.nativeElement.innerHTML = '';
    }
    this.kind = 'none';
    this.failed = false;
    this.loading = false;
    this.imageUrl = undefined;
    this.text = undefined;
    this.textHtml = undefined;
    this.loadedName = undefined;
    this.found = 0;
  }

  private revoke(): void {
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = undefined;
    }
  }
}

// -------------------------------------------------------------------- matching

/** Case, spaces and no-break spaces do not matter: "SK64 7500" is "sk647500". */
function norm(s: string): string {
  return (s || '').toLowerCase().replace(/[\s ]/g, '');
}

function pad(n: number): string {
  return n < 10 ? '0' + n : String(n);
}

/** The ways the field's value may be printed on the document. */
function candidates(f: FocusedValue | null): Array<string> {
  if (!f || f.value === null || f.value === undefined || f.value === '') {
    return [];
  }
  const v = f.value;
  if (f.type === 'number') {
    const n = Number(v);
    if (!isFinite(n) || n === 0) {
      return [];
    }
    const fixed = n.toFixed(2);
    const out = [fixed, fixed.replace('.', ',')];
    if (Number.isInteger(n) && Math.abs(n) >= 100) {
      out.push(String(n));
    }
    return out;
  }
  if (f.type === 'date' || f.type === 'dateTime') {
    let d: number;
    let m: number;
    let y: number;
    if (Array.isArray(v)) {
      [y, m, d] = v;
    } else if (v && typeof v.year === 'function') {
      y = v.year();
      m = v.month() + 1;
      d = v.date();
    } else {
      const dt = new Date(v);
      if (isNaN(dt.getTime())) {
        return [];
      }
      y = dt.getFullYear();
      m = dt.getMonth() + 1;
      d = dt.getDate();
    }
    return [`${d}.${m}.${y}`, `${pad(d)}.${pad(m)}.${y}`, `${y}-${pad(m)}-${pad(d)}`];
  }
  const s = String(v).trim();
  return s.length >= 3 ? [s] : [];
}

/**
 * Numbers and dates must appear whole. Text may be broken into several items on a PDF
 * line ("Perfect Distribution a. s. -" / "organizačná zložka"), so an item that is a
 * substantial piece of the value counts too.
 */
function matches(item: string, cands: Array<string>, type: string): boolean {
  for (const c of cands) {
    const nc = norm(c);
    if (!nc) {
      continue;
    }
    if (item.includes(nc)) {
      return true;
    }
    if (type === 'text' && item.length >= 5 && nc.includes(item)) {
      return true;
    }
  }
  return false;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
