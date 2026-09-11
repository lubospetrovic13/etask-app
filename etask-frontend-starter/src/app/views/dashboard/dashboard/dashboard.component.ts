import {Component, OnDestroy, OnInit} from '@angular/core';
import {Router} from '@angular/router';
import {
  AccessService,
  Case,
  DynamicNavigationRouteProviderService,
  FILTER_IDENTIFIERS,
  FILTER_VIEW_TASK_TRANSITION_ID,
  FilterExtractionService,
  LanguageService,
  LoadingEmitter,
  LoggerService,
  RoleAccess,
  TaskResourceService,
  User,
  UserService,
  ViewNavigationItem,
} from '@netgrif/components-core';
import {Observable, Subscription, from, of} from 'rxjs';
import {concatMap, first, map, switchMap} from 'rxjs/operators';
import custom_views from '../../../../assets/custom_views.json';
import {UriNodeTitlePipe} from '../../side-nav/uri-node-title.pipe';
import {localisedViewTitle} from '../../side-nav/view-title';
import icons from '../../../../assets/uriNodeIcons.json';
import {ETaskUriNodeResource} from '../service/etask-uri-resource.service';
import {EtaskUriService} from '../service/etask-uri.service';


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
    private _dynamicRoutingService: DynamicNavigationRouteProviderService,
    private _accessService: AccessService,
    private _nodeTitle: UriNodeTitlePipe,
    private _language: LanguageService,
    private _log: LoggerService,
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
            const filteredViews = cases
              .content.filter(it => custom_views.includes(it.immediateData.find(f => f.stringId === 'menu_item_identifier')?.value))
              .sort((a, b) => this.getViewOrder(a) - this.getViewOrder(b));
            return filteredViews.map(it => this.resolveFilterCaseToViewNavigationItem(it)).filter(it => !!it);
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
   * Open a dashboard card: land on the first view the folder can offer.
   *
   * This used to be `activeNode = node` + `navigate(['portal'])`, and it left
   * the user at the root of the tree - measured: the drawer's `currentNode` was
   * `root` right after the click. Two things were wrong and both are fixed:
   *
   *   1. `activeNode` was written into a *different instance* of the service.
   *      `EtaskUriService` and the library's `UriService` were two tokens, so
   *      Angular built two objects, each with its own `_activeNode$`. The
   *      drawer listened to the other one. `app.module.ts` now aliases them
   *      (`useExisting`), so setting `activeNode` really does move the drawer.
   *   2. A folder that only holds other folders has no views of its own, so
   *      `firstViewPath` fell back to `portal` - a valid route with an empty
   *      content area. The card "worked" and looked like it did nothing.
   *      Hence `entryFor`: descend into child folders and open the first view
   *      that actually exists.
   *
   * `activeNode` is set to the node that OWNS the opened view, because that is
   * what it means in the library - the folder the open view belongs to - and
   * that is what the drawer shows.
   */
  public openNode(node: ETaskUriNodeResource) {
    this.entryFor(node).subscribe(
      entry => {
        if (!entry) {
          // Priecinok bez zobrazeni a bez deti: otvorit sa nema co. Aspon
          // prepneme strom na neho, aby bolo vidno, ze je prazdny.
          this._uri.activeNode = node;
          this._router.navigate(['portal']);
          return;
        }
        this._uri.activeNode = entry.node;
        this._router.navigate([entry.path]);
      },
      error => {
        this._log.error('Nepodarilo sa načítať zobrazenia priečinka', error);
        this._router.navigate(['portal']);
      });
  }

  /**
   * First openable view in this folder, or in its subfolders.
   *
   * Depth is capped: the URI tree is a tree, and a bug in the data (a node
   * whose child is its own ancestor) would otherwise turn this into an
   * infinite walk instead of a wrong answer.
   */
  private entryFor(node: ETaskUriNodeResource, depth: number = 0):
    Observable<{ node: ETaskUriNodeResource, path: string } | undefined> {
    return this._uri.getCasesOfNode(node, FILTER_IDENTIFIERS).pipe(
      switchMap(page => {
        const path = this.firstViewPath(page?.content ?? []);
        if (path !== 'portal') {
          return of({node, path});
        }
        if (depth >= 3) {
          return of(undefined);
        }
        return this._uri.getChildNodes(node).pipe(
          switchMap(children => {
            const sorted = ((children ?? []) as Array<ETaskUriNodeResource>)
              .filter(child => !child.hidden)
              .sort((a, b) => (a.name ?? '').localeCompare(b.name ?? ''));
            if (!sorted.length) {
              return of(undefined);
            }
            // `concatMap` a nie `mergeMap`: priecinky sa maju prehladat
            // v poradi, v akom ich vidi clovek, nie v poradi, v akom stihne
            // odpovedat server - inak by ta karta otvarala raz Faktury,
            // raz Objednavky.
            return from(sorted).pipe(
              concatMap(child => this.entryFor(child, depth + 1)),
              first(entry => !!entry, undefined),
            );
          }),
        );
      }),
    );
  }

  /**
   * Path of the alphabetically first view the user may open, or `portal`.
   *
   * Sorted by title so the card is predictable: the same folder opens the same
   * view every time, regardless of the order the server happened to return.
   */
  private firstViewPath(cases: Array<Case>): string {
    // `navigation` je v type `boolean | {title?, icon?, ...}` - bez tejto
    // stráže build neprejde.
    const title = (v: ViewNavigationItem): string =>
      (typeof v.navigation === 'object' && !!v.navigation ? (v.navigation.title ?? '') : '');
    const views = cases
      .map(c => this.resolveFilterCaseToViewNavigationItem(c))
      .filter(v => !!v)
      .sort((a, b) => title(a).localeCompare(title(b)));
    return views.length ? views[0].routing.path : 'portal';
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

  /* from AbstractNavigationDoubleDrawerComponent */
  protected resolveFilterCaseToViewNavigationItem(filter: Case): ViewNavigationItem | undefined {
    const item: ViewNavigationItem = {
      access: {},
      navigation: {
        icon: filter.immediateData.find(f => f.stringId === 'icon_name')?.value,
        title: localisedViewTitle(filter, this._language.getLanguage()),
      },
      routing: {
        path: this.getFilterRoutingPath(filter),
      },
      id: filter.stringId,
      resource: filter,
    };
    const resolvedRoles = this.resolveAccessRoles(filter, 'allowed_roles');
    const resolvedBannedRoles = this.resolveAccessRoles(filter, 'banned_roles');
    if (!!resolvedRoles) item.access['role'] = resolvedRoles;
    if (!!resolvedBannedRoles) item.access['bannedRole'] = resolvedBannedRoles;
    if (!this._accessService.canAccessView(item, item.routingPath)) return;
    return item;
  }

  /* from AbstractNavigationDoubleDrawerComponent */
  protected getFilterRoutingPath(filterCase: Case) {
    const viewTaskId = filterCase.tasks.find(taskPair => taskPair.transition === FILTER_VIEW_TASK_TRANSITION_ID).task;
    const url = this._dynamicRoutingService.route;
    return `/${url}/${viewTaskId}`;
  }

  /* from AbstractNavigationDoubleDrawerComponent */
  protected resolveAccessRoles(filter: Case, roleType: string): Array<RoleAccess> | undefined {
    const allowedRoles = filter.immediateData.find(f => f.stringId === roleType)?.options;
    if (!allowedRoles || Object.keys(allowedRoles).length === 0) return undefined;
    const roles = [];
    Object.keys(allowedRoles).forEach(combined => {
      const parts = combined.split(':');
      roles.push({
        processId: parts[1],
        roleId: parts[0],
      });
    });
    return roles;
  }

  ngOnDestroy(): void {
    this._sub.unsubscribe();
  }
}
