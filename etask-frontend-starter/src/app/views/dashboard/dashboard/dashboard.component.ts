import {Component, OnDestroy, OnInit} from '@angular/core';
import {Router} from '@angular/router';
import {
  Case,
  FILTER_IDENTIFIERS,
  FILTER_VIEW_TASK_TRANSITION_ID,
  FilterExtractionService,
  LoadingEmitter,
  TaskResourceService,
  User,
  UserService,
  ViewNavigationItem,
} from '@netgrif/components-core';
import {Subscription} from 'rxjs';
import {map} from 'rxjs/operators';
import custom_views from '../../../../assets/custom_views.json';
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

  private _sub: Subscription;
  private _loading: LoadingEmitter;

  constructor(
    private _user: UserService,
    private _uri: EtaskUriService,
    private _taskResource: TaskResourceService,
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

        this._uri.getCasesOfNode(this._uri.root, FILTER_IDENTIFIERS).pipe(
          map(cases => {
            // `cases.content` NIE JE `undefined`, ked dopyt nevrati ziadny vysledok -
            // kniznicny `changeType()` (netgrif-components-core) vtedy vrati CELY
            // surovy HAL response objekt (HAL odpoved bez `_embedded` je pre 0
            // zaznamov normalna), nie `[]` ani `undefined`. `?? []` teda nechrani -
            // `content` je definovany (truthy), len nie je pole, a `.filter` na
            // objekte padne presne na "content.filter is not a function". Treba
            // teda overit typ, nie len null/undefined.
            const filteredViews = (Array.isArray(cases.content) ? cases.content : []).filter(it => custom_views.includes(it.immediateData.find(f => f.stringId === 'menu_item_identifier')?.value))
              .sort((a, b) => this.getViewOrder(a) - this.getViewOrder(b));
            return filteredViews.map(it => this._viewResolver.resolve(it)).filter(it => !!it);
          }),
        ).subscribe(views => {
          this.customViews = views;
          this.getCountForViews(this.customViews);
        });
      }
    });
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
      const taskId = view.resource.tasks.find(taskPair => taskPair.transition === FILTER_VIEW_TASK_TRANSITION_ID).task;
      this._taskResource.getData(taskId).subscribe(taskData => {
        const filter = this._filterExtraction.extractCompleteFilterFromData(taskData);
        this._taskResource.count(filter).subscribe(count => {
          this._counters.set(view.id, count.count);
        });
      });
    });
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
    return custom_views.indexOf(aCase.immediateData.find(f => f.stringId === 'menu_item_identifier')?.value);
  }

  ngOnDestroy(): void {
    this._sub.unsubscribe();
  }
}
