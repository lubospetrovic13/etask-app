import {AfterViewInit, Component, Optional} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {
  AbstractWorkflowPanelComponent,
  ConfigurationService,
  LoggerService,
  OverflowService,
  PetriNetResourceService,
  SnackBarService,
  TextField,
  WorkflowViewService,
} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';

interface ModelLink {
  path: string;
  expiresAt: number;
  validForSeconds: number;
}

@Component({
  selector: 'app-workflow-panel',
  templateUrl: './workflow-panel.component.html',
  styleUrls: ['./workflow-panel.component.scss'],
})
export class WorkflowPanelComponent extends AbstractWorkflowPanelComponent implements AfterViewInit {

  readonly location = location;
  publicUrlTextField: TextField;

  constructor(log: LoggerService,
              translate: TranslateService,
              workflowService: WorkflowViewService,
              petriNetResource: PetriNetResourceService,
              private _config: ConfigurationService,
              private _snackbar: SnackBarService,
              private _http: HttpClient,
              @Optional() overflowService: OverflowService) {
    super(log, translate, workflowService, petriNetResource, overflowService);
    translate.onLangChange.subscribe(() => {
      this.publicUrlTextField.title = this._translate.instant('workflow.publicUrl');
    });
  }

  ngAfterViewInit() {
    const publicViewPath = this._config.getPathsByView('publicTaskView')[0];
    let encodedIdentifier = btoa(this.panelContent.netIdentifier.value);
    encodedIdentifier = encodedIdentifier.endsWith('=') ? encodedIdentifier.substring(0, encodedIdentifier.length - 1) : encodedIdentifier;
    const publicUrl = location.origin + publicViewPath.substring(0, publicViewPath.indexOf('/:')) + '/' + encodedIdentifier;
    this.publicUrlTextField = new TextField(this.panelContent.netIdentifier + '-publicUrl', this._translate.instant('workflow.publicUrl'), publicUrl, {visible: true});
  }

  public copyToClipboard(content: string) {
    navigator.clipboard.writeText(content).then(() => {
      this._snackbar.openSuccessSnackBar(this._translate.instant('snackbar.publicUrlCopied'));
    });
  }

  /** Whether the builder button makes sense at all - it needs a configured builder. */
  public get builderUrl(): string | undefined {
    return (this._config.get() as any)?.services?.builder?.modelerUrl;
  }

  /**
   * Opens the model in the Netgrif builder instead of downloading the XML.
   *
   * The builder takes `?modelUrl=` and fetches that URL itself, from its own
   * page, carrying none of our authentication - so we cannot point it at
   * `/api/petrinet/{id}/file` (401 anonymously) and we cannot inline the model
   * as a `data:` URL (the builder's nginx answers 414 well below the size of a
   * real net). The backend therefore mints a signed link valid for a few
   * minutes, and that is what the builder gets.
   */
  public openInBuilder() {
    const builder = this.builderUrl;
    if (!builder) {
      this._log.error('No builder configured (services.builder.modelerUrl)');
      return;
    }

    // The window has to be opened HERE, inside the click handler. Opening it in
    // the subscribe callback below is an asynchronous popup and browsers block
    // it; the tab is opened empty now and pointed at the builder once the link
    // is back.
    const tab = window.open('', '_blank');

    this._http.get<ModelLink>(location.origin + '/api/v2/model-link/' + this.workflow.stringId)
      .subscribe(link => {
        // The backend returns a path, not an absolute URL: behind the reverse
        // proxy it cannot know the port the browser used. We can.
        const modelUrl = location.origin + link.path;
        const target = builder + '?modelUrl=' + encodeURIComponent(modelUrl);
        if (tab) {
          tab.location.href = target;
        } else {
          window.location.href = target;
        }
        this.warnIfBuilderCannotReachUs(builder);
      }, error => {
        this._log.error(`Could not mint a model link for ${this.workflow.identifier}`, error);
        if (tab) {
          tab.close();
        }
        this._snackbar.openErrorSnackBar(this._translate.instant('snackbar.builderLinkFailed'));
      });
  }

  /**
   * An HTTPS builder fetching an HTTP link may be blocked by the browser, and
   * when it is, the builder shows an empty canvas with no error anywhere -
   * nothing on our side can detect it. Chrome does treat http://localhost as a
   * trustworthy origin, so this often works; the warning is deliberately "may",
   * because the alternative is letting the admin conclude the button is broken.
   */
  private warnIfBuilderCannotReachUs(builder: string) {
    if (location.protocol === 'http:' && builder.startsWith('https:')) {
      this._snackbar.openWarningSnackBar(this._translate.instant('snackbar.builderInsecureContext'));
    }
  }

}
