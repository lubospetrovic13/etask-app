import {Component, ElementRef, HostBinding, HostListener, Input, OnDestroy, OnInit} from '@angular/core';
import {DomSanitizer, SafeResourceUrl, SafeUrl} from '@angular/platform-browser';
import {FileField, TaskResourceService} from '@netgrif/components-core';
import {Subscription} from 'rxjs';

/** What the viewer can show. Anything else gets a download hint instead. */
type DocumentKind = 'pdf' | 'image' | 'text' | 'none';

/** Grid row height of the library, `abstract-file-field.component` (not exported there). */
const FIELD_HEIGHT = 75;
const FIELD_PADDING = 16;
/** Our toolbar above the document. Fixed, so the viewer never overflows its grid cell. */
const TOOLBAR_HEIGHT = 48;
/** Room the portal keeps above a task panel (tabs, search, list header). */
const PAGE_CHROME = 150;

/**
 * File field that shows the document itself, large, next to the form.
 *
 * The library file field has a `preview` component, but it is a thumbnail: 20 % of the
 * field width and an `<img>`, so a PDF - which is what invoices mostly are - is not
 * shown at all. There is no library component that renders an attachment across half a
 * form. That is the missing primitive that puts this in layer 3. The layout itself
 * (fields on the left, the document on the right) stays in the net, as grid positions.
 *
 * The net asks for it per dataRef:
 *
 *     <dataRef>
 *         <id>fa_skan</id>
 *         <layout><x>3</x><y>0</y><rows>20</rows><cols>3</cols>...</layout>
 *         <component><name>document</name></component>
 *     </dataRef>
 *
 * What it looks like:
 *
 *   - one slim toolbar: file name, then upload/replace and remove (only when the field
 *     is editable), download and open in a new tab
 *   - below it the document: PDF in the browser's own viewer fitted to width, an image,
 *     or an XML e-invoice as text. It sticks to the top while the form next to it is
 *     scrolled, and is never taller than the window, so the only scrollbar is the
 *     document's own
 *   - no file yet and editable: a drop zone - drag the file in or click
 *
 * Upload and delete are the library's: `nc-file-field` is inside, hidden, and this
 * component drives its file input and delete button. That keeps validation, size
 * limits, progress and the backend calls exactly the library's. It is not a subclass
 * of the library file field on purpose - that class registers its own FormControl on
 * the data field, and two of them on one field would fight over the value.
 */
@Component({
  selector: 'app-etask-file-document',
  templateUrl: './etask-document-field.component.html',
  styleUrls: ['./etask-document-field.component.scss'],
})
export class EtaskDocumentFieldComponent implements OnInit, OnDestroy {

  @Input() dataField: FileField;
  @Input() taskId: string;
  @Input() taskOffset = 0;

  public kind: DocumentKind = 'none';
  public loading = false;
  public failed = false;
  public dragging = false;
  public pdfUrl: SafeResourceUrl;
  public imageUrl: SafeUrl;
  public text: string;
  public windowHeight = window.innerHeight;

  private objectUrl: string;
  private rawUrl: string;
  private loadedName: string;
  private updated: Subscription;
  private download: Subscription;

  constructor(private readonly taskResource: TaskResourceService,
              private readonly sanitizer: DomSanitizer,
              private readonly host: ElementRef<HTMLElement>) {
  }

  ngOnInit(): void {
    this.load();
    this.updated = this.dataField.updated.subscribe(() => this.load());
  }

  ngOnDestroy(): void {
    this.updated?.unsubscribe();
    this.download?.unsubscribe();
    this.revoke();
  }

  @HostListener('window:resize')
  onResize(): void {
    this.windowHeight = window.innerHeight;
  }

  /**
   * The component fills every grid row the net gave it. The library centres a cell's
   * content vertically, so a component shorter than its cell (the viewer is capped at
   * the window height) would start in the middle of the form instead of at the top.
   * Filling the cell also gives the sticky document the room to travel in.
   */
  @HostBinding('style.height.px')
  get hostHeight(): number {
    const rows = this.dataField?.layout?.rows || 1;
    return rows * FIELD_HEIGHT - FIELD_PADDING;
  }

  get fileName(): string {
    return this.dataField?.value?.name || '';
  }

  get editable(): boolean {
    return !!this.dataField && !this.dataField.disabled;
  }

  get hasDocument(): boolean {
    return !!(this.pdfUrl || this.imageUrl || this.text !== undefined);
  }

  /**
   * The grid rows the net gave the field, minus the toolbar - but never more than the
   * window, so the document is always fully visible while it sticks to the top.
   */
  get viewerHeight(): number {
    const rows = this.dataField?.layout?.rows || 1;
    const fromGrid = rows * FIELD_HEIGHT - FIELD_PADDING - TOOLBAR_HEIGHT;
    const fromWindow = this.windowHeight - PAGE_CHROME - TOOLBAR_HEIGHT;
    return Math.max(Math.min(fromGrid, fromWindow), 240);
  }

  /** Opens the library's file picker (the hidden `nc-file-field` input). */
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
    if (this.rawUrl) {
      window.open(this.rawUrl, '_blank', 'noopener');
    }
  }

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
    this.withBlob(blob => {
      this.loading = false;
      this.show(blob);
    }, () => {
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
    if (this.kind === 'text') {
      blob.text().then(t => this.text = t);
      return;
    }
    // The server answers with application/octet-stream; the iframe needs the real type,
    // otherwise the browser downloads the PDF instead of showing it.
    const type = this.kind === 'pdf' ? 'application/pdf' : (blob.type || 'image/png');
    this.objectUrl = URL.createObjectURL(new Blob([blob], {type}));
    this.rawUrl = this.objectUrl;
    if (this.kind === 'pdf') {
      // Fit to width: the default "whole page" makes an A4 invoice unreadably small in
      // half a form. The fragment is understood by the Chromium, Firefox and Edge viewers.
      this.pdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.objectUrl + '#view=FitH&navpanes=0');
    } else {
      this.imageUrl = this.sanitizer.bypassSecurityTrustUrl(this.objectUrl);
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
    this.kind = 'none';
    this.failed = false;
    this.loading = false;
    this.pdfUrl = undefined;
    this.imageUrl = undefined;
    this.text = undefined;
    this.loadedName = undefined;
  }

  private revoke(): void {
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = undefined;
      this.rawUrl = undefined;
    }
  }
}
