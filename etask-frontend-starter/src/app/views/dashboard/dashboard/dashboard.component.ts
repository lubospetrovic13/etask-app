import {Component, OnDestroy, OnInit} from '@angular/core';
import {Router} from '@angular/router';
import {
  Case,
  CaseResourceService,
  FILTER_IDENTIFIERS,
  FILTER_VIEW_TASK_TRANSITION_ID,
  FilterExtractionService,
  FilterType,
  LoadingEmitter,
  TaskResourceService,
  User,
  UserService,
  ViewNavigationItem,
} from '@netgrif/components-core';
import {forkJoin, Observable, of, Subscription} from 'rxjs';
import {catchError, map, switchMap} from 'rxjs/operators';
import {DASHBOARD_NODES, DASHBOARD_VIEWS, formView, menuItemIdentifier} from '../../form/form-views';
import {UriNodeTitlePipe} from '../../side-nav/uri-node-title.pipe';
import icons from '../../../../assets/uriNodeIcons.json';
import {ETaskUriNodeResource} from '../service/etask-uri-resource.service';
import {EtaskUriService} from '../service/etask-uri.service';
import {ViewNavigationResolverService} from '../../side-nav/view-navigation-resolver.service';


@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss'],
  providers: [UriNodeTitlePipe],
})
export class DashboardComponent implements OnInit, OnDestroy {
  public nodes: Array<ETaskUriNodeResource> = [];

  public customViews: Array<ViewNavigationItem> = [];
  protected _counters: Map<string, number> = new Map<string, number>();
  protected _counterKinds: Map<string, string> = new Map<string, string>();
  /** Folder cards only for someone who has no view cards - see ngOnInit. */
  public showFolders = false;

  private _sub: Subscription;
  private _loading: LoadingEmitter;

  constructor(
    private _user: UserService,
    private _uri: EtaskUriService,
    private _taskResource: TaskResourceService,
    private _caseResource: CaseResourceService,
    private _router: Router,
    private _filterExtraction: FilterExtractionService,
    private _nodeTitle: UriNodeTitlePipe,
    private _viewResolver: ViewNavigationResolverService,
  ) {
    this._loading = new LoadingEmitter();
  }

  ngOnInit(): void {
    this._sub = this._uri.rootLoaded$.subscribe(() => {
      if (this._uri.root) {
        // Zoznam sa stavia odznova, nie sa dopĺňa: koreň sa načíta aj po
        // prihlásení iného človeka (`EtaskUriService`), a bez tohto by sa
        // karty priečinkov pri každom takom načítaní zdvojili.
        this.nodes = [];
        this._uri.root.children.forEach(c => this.nodes.push(c as ETaskUriNodeResource));
        // Bez filtrovania podľa rolí: uzly prichádzajú už prefiltrované zo
        // servera (EtaskUriController). Druhý filter v prehliadači vedel len
        // ubrať uzly, na ktoré užívateľ právo má — porovnával totiž stringId
        // rolí, ktoré sa razia per verziu siete a po re-importe boli neplatné.
        this.nodes = this.nodes.filter(n => !n.section);
        this.nodes.sort((a, b) => a.name.localeCompare(b.name));
        this._loading.on();
        this._uri.getCountForNodes(this.nodes).subscribe(() => {
          this._loading.off();
        });

        // Karty zobrazeni: polozky menu z korena a z uzlov v `dashboardNodes`
        // (custom_views.json), v poradi zo zoznamu `dashboard`. Kto aspon jednu
        // ma, nevidi karty priecinkov - appka ma byt zoznam toho, co clovek
        // robi, nie strom. Priecinky zostavaju v bocnom menu.
        this.loadViewCases().subscribe(cases => {
          const seen = new Set<string>();
          const views = cases
            .filter(c => DASHBOARD_VIEWS.includes(menuItemIdentifier(c)))
            .filter(c => !seen.has(c.stringId) && !!seen.add(c.stringId))
            .sort((a, b) => this.getViewOrder(a) - this.getViewOrder(b))
            .map(c => this._viewResolver.resolve(c))
            .filter(v => !!v);
          this.customViews = views;
          this.showFolders = views.length === 0;
          this.getCountForViews(this.customViews);
        });
      }
    });
  }

  private loadViewCases(): Observable<Array<Case>> {
    // `cases.content` NIE JE pole, ked dopyt nevrati nic - kniznicny
    // `changeType()` vtedy vrati cely surovy HAL objekt, preto Array.isArray.
    const casesOf = node => !node ? of([]) : this._uri.getCasesOfNode(node, FILTER_IDENTIFIERS, 0, 100).pipe(
      map(page => (Array.isArray(page?.content) ? page.content : []) as Array<Case>),
      catchError(() => of([] as Array<Case>)),
    );
    const nodes$ = DASHBOARD_NODES.map(path => this._uri.getNodeByPath(path).pipe(
      catchError(() => of(undefined)),
      switchMap(node => casesOf(node)),
    ));
    return forkJoin([casesOf(this._uri.root), ...nodes$]).pipe(
      map(lists => ([] as Array<Case>).concat(...lists)),
    );
  }

  /* Uri node */
  public count(name: string): number {
    return this._uri.getCachedNodeCount(name);
  }

  /**
   * Klik na kartu = vstup DO PRIEČINKA, nie do zobrazenia.
   *
   * Predtým tu bol `entryFor`, ktorý zostupoval do podpriečinkov a otvoril
   * prvé zobrazenie, ktoré našiel. Vzniklo to ako oprava toho, že `portal`
   * bola prázdna obrazovka, takže karta priečinka „nič nerobila" - lenže
   * dôsledok bol, že klik na „Financie" hodil človeka do konkrétneho
   * zobrazenia o dve úrovne nižšie a nedalo sa z toho prečítať, kde je.
   *
   * Prázdnu obrazovku rieši `FolderViewComponent`, takže hádať sa už nemusí.
   */
  public openNode(node: ETaskUriNodeResource) {
    this._uri.activeNode = node;
    this._router.navigate(['portal', 'folder']);
  }

  /**
   * Icon for a node's dashboard card and menu entry.
   *
   * The lookup used to be an exact match on the node name, so a single differing
   * character - case, an underscore instead of a space, or a diacritic - fell through to
   * the generic folder. Node names come from the URI tree and are not written with the
   * icon map in mind, so the key is normalised on both sides instead.
   */
  public getNodeIcon(node: ETaskUriNodeResource): string {
    return icons[DashboardComponent.iconKey(node?.name)] ?? 'folder';
  }

  /**
   * Human-readable node title: underscores out, every word capitalised.
   *
   * Each word, not just the first: a URI node comes from the process
   * identifier, so `service_desk` has to read as "Service Desk" - which is also
   * how the drawer renders it. Capitalising only the first letter left the
   * dashboard saying "Service desk" while the menu right next to it said
   * "Service Desk".
   */
  public getNodeTitle(node: ETaskUriNodeResource): string {
    return this._nodeTitle.transform(node?.name);
  }

  private static iconKey(name: string): string {
    return (name ?? '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/_/g, ' ')
      .trim()
      .toLowerCase();
  }

  /* custom views */
  public countView(view: ViewNavigationItem) {
    return this.isCountLoaded(view) ? this._counters.get(view.id) : 0;
  }

  public isCountLoaded(view: ViewNavigationItem) {
    return this._counters.has(view.id);
  }

  public areCountersLoaded(): boolean {
    return !this._loading.getValue();
  }

  public getCountForViews(customViews: Array<ViewNavigationItem>) {
    if (!customViews) {
      return;
    }
    customViews.forEach(view => {
      // Formular nema co pocitat - karta je tlacidlo.
      if (formView(menuItemIdentifier(view.resource))) {
        return;
      }
      const taskId = view.resource.tasks.find(taskPair => taskPair.transition === FILTER_VIEW_TASK_TRANSITION_ID).task;
      this._taskResource.getData(taskId).subscribe(taskData => {
        const filter = this._filterExtraction.extractCompleteFilterFromData(taskData);
        if (!filter) {
          return;
        }
        // Case zobrazenie sa pocita v pripadoch, Task v ulohach. Predtym sa
        // vsetko pocitalo ako ulohy, co pri case filtri vracia nezmysel.
        const isCase = filter.type === FilterType.CASE;
        const count$ = isCase ? this._caseResource.count(filter) : this._taskResource.count(filter);
        count$.subscribe(count => {
          this._counterKinds.set(view.id, isCase ? 'dashboard.cases' : 'dashboard.tasks');
          this._counters.set(view.id, count.count);
        });
      });
    });
  }

  public isForm(view: ViewNavigationItem): boolean {
    return !!formView(menuItemIdentifier(view.resource));
  }

  public countLabel(view: ViewNavigationItem): string {
    return this._counterKinds.get(view.id) ?? 'dashboard.tasks';
  }

  public openView(view: ViewNavigationItem) {
    this._uri.activeNode = this._uri.root;
    this._router.navigate([view.routing.path]);
  }

  /* user session */
  public logout(): void {
    this._user.logout().subscribe(() => {
      this._router.navigate(['login']);
    });
  }

  public get loggedUser(): User {
    return this._user.user;
  }

  public isImpersonating(): boolean {
    return this.loggedUser.isImpersonating();
  }

  /* util */
  private getViewOrder(aCase: Case) {
    return DASHBOARD_VIEWS.indexOf(menuItemIdentifier(aCase));
  }

  ngOnDestroy(): void {
    this._sub.unsubscribe();
  }
}
