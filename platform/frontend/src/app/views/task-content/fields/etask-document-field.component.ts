import {Component, Input, OnDestroy, OnInit} from '@angular/core';
import {DomSanitizer, SafeResourceUrl, SafeUrl} from '@angular/platform-browser';
import {FileField, TaskResourceService} from '@netgrif/components-core';
import {Subscription} from 'rxjs';

/** What the viewer can show. Anything else gets a download hint instead. */
type DocumentKind = 'pdf' | 'image' | 'text' | 'none';

/** Grid row height of the library, `abstract-file-field.component` (not exported there). */
const FIELD_HEIGHT = 75;
const FIELD_PADDING = 16;
/** The upload/download row of `nc-file-field` above the viewer. */
const HEADER_HEIGHT = 64;

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
 *         <layout><x>3</x><y>0</y><rows>14</rows><cols>3</cols>...</layout>
 *         <component><name>document</name></component>
 *     </dataRef>
 *
 * Upload, download and delete stay the library's: this component wraps `nc-file-field`
 * and only adds the viewer below it. It is not a subclass of the library file field on
 * purpose - that class registers its own FormControl on the data field, and two of them
 * on one field would fight over the value.
 *
 *   PDF          - the browser's own PDF viewer in an iframe (object URL, same origin)
 *   PNG, JPG     - the image, scaled to fit
 *   XML, TXT     - the text, so an e-invoice can be read without downloading it
 *   anything else - a sentence saying why there is nothing to see
 *
 * The file is downloaded again whenever the field changes (a new upload).
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
  public pdfUrl: SafeResourceUrl;
  public imageUrl: SafeUrl;
  public text: string;

  private objectUrl: string;
  private loadedName: string;
  private updated: Subscription;
  private download: Subscription;

  constructor(private readonly taskResource: TaskResourceService,
              private readonly sanitizer: DomSanitizer) {
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

  get fileName(): string {
    return this.dataField?.value?.name || '';
  }

  /** Viewer height: every grid row the net gave the field, minus the upload row. */
  get viewerHeight(): number {
    const rows = this.dataField?.layout?.rows || 1;
    return Math.max(rows * FIELD_HEIGHT - FIELD_PADDING - HEADER_HEIGHT, 160);
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
    if (this.kind === 'none') {
      this.loadedName = name;
      return;
    }
    const taskId = this.dataField.parentTaskId ? this.dataField.parentTaskId : this.taskId;
    if (!taskId) {
      return;
    }
    this.loading = true;
    this.download?.unsubscribe();
    // `downloadFile` emits progress events first and the Blob last - the same filter
    // the library file field uses.
    this.download = this.taskResource.downloadFile(taskId, this.dataField.stringId).subscribe(response => {
      if (!(response instanceof Blob)) {
        return;
      }
      this.loading = false;
      this.loadedName = name;
      this.show(response);
    }, () => {
      this.loading = false;
      this.failed = true;
    });
  }

  private show(blob: Blob): void {
    if (this.kind === 'text') {
      blob.text().then(t => this.text = t);
      return;
    }
    // The server answers with application/octet-stream; the iframe needs the real type,
    // otherwise the browser downloads the PDF instead of showing it.
    const typed = new Blob([blob], {type: this.kind === 'pdf' ? 'application/pdf' : blob.type});
    this.objectUrl = URL.createObjectURL(typed);
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
    }
  }
}
