import {animate, state, style, transition, trigger} from '@angular/animations';
import {BreakpointObserver} from '@angular/cdk/layout';
import {Component} from '@angular/core';
import {ActivatedRoute, Router} from '@angular/router';
import {NavigationDoubleDrawerComponent} from '@netgrif/components';
import {
  AccessService,
  Case,
  ConfigurationService,
  DynamicNavigationRouteProviderService,
  FILTER_IDENTIFIERS,
  ImpersonationService,
  ImpersonationUserSelectService,
  LanguageService,
  LoggerService,
  UriNodeResource,
  UriService,
  UserService,
  ViewNavigationItem,
} from '@netgrif/components-core';
import {forkJoin, of, Subscription} from 'rxjs';
import {map} from 'rxjs/operators';
import icons from '../../../../assets/uriNodeIcons.json';
import {ETaskUriNodeResource} from '../../dashboard/service/etask-uri-resource.service';
import {ThemeService} from '../../../theme.service';
import {localisedViewTitle} from '../view-title';

@Component({
  selector: 'app-e-task-double-drawer',
  templateUrl: './e-task-double-drawer.component.html',
  styleUrls: ['./e-task-double-drawer.component.scss'],
  animations: [
    trigger('sectionExpansion', [
      state('expanded, void', style({
        height: '*',
        visibility: 'visible',
      })),
      state('collapsed', style({
        height: '0px',
        visibility: 'hidden',
      })),
      transition('expanded <=> collapsed, void => expanded', [
        animate('225ms cubic-bezier(0.4,0.0,0.2,1)'),
      ]),
    ]),
    trigger('indicatorRotate', [
      state('expanded, void', style({
        transform: 'rotate(180deg)',
      })),
      state('collapsed', style({
        transform: 'rotate(0deg)',
      })),
      transition('expanded <=> collapsed, void => expanded', [
        animate('225ms cubic-bezier(0.4,0.0,0.2,1)'),
      ]),
    ]),
  ],
})
export class ETaskDoubleDrawerComponent extends NavigationDoubleDrawerComponent {

  static readonly SETTINGS_SECTION = 'settings';
  public isSectionOpen: {
    folders: boolean;
    views: boolean;
    settings: boolean;
  };
  public settingsNodes: Array<UriNodeResource>;
  public settingsViews: Array<ViewNavigationItem>;
  private _languageSub: Subscription;

  constructor(router: Router,
              activatedRoute: ActivatedRoute,
              breakpoint: BreakpointObserver,
              languageService: LanguageService,
              userService: UserService,
              accessService: AccessService,
              log: LoggerService,
              config: ConfigurationService,
              uriService: UriService,
              impersonationUserSelect: ImpersonationUserSelectService,
              impersonation: ImpersonationService,
              public themeService: ThemeService,
              dynamicRouteProviderService: DynamicNavigationRouteProviderService) {
    super(router, activatedRoute, breakpoint, languageService, userService, accessService, log, config, uriService,
      impersonationUserSelect, impersonation, dynamicRouteProviderService);
    this._impersonation.impersonating$.subscribe(() => {
      this._router.navigate(['dashboard']);
    });
    // Rebuild the tree when the language changes.
    //
    // View names are resolved once, when the right side loads, so without this the
    // menu keeps the names from whichever language was active at load time - the
    // library's own labels ("Views", "Settings") switch immediately through the
    // translate pipe and the app's own view names do not, which looks like the
    // translations are missing rather than stale. Folder names go through a pipe and
    // are fine either way.
    this._languageSub = languageService.getLangChange$().subscribe(() => {
      // The node guard matters: the language can change before the drawer has one
      // (the app sets a default in its own constructor), and `loadRightSide` reads
      // `currentNode.uriPath` straight away.
      if (this.currentNode) this.loadRightSide();
    });
    this.isSectionOpen.settings = false;
    this.settingsViews = [];
    this.settingsNodes = [];
  }

  protected loadLeftSide() {
    if (this._uriService.isRoot(this.currentNode)) {
      this.leftNodes = [];
      return;
    }
    this.leftLoading$.on();
    this._leftNodesSubscription = this._uriService.getSiblingsOfNode(this.currentNode).subscribe(nodes => {
      // Uzly su uz prefiltrovane serverom, druhy filter tu nema co robit.
      const allNodes = (nodes instanceof Array ? nodes : []) as Array<ETaskUriNodeResource>;
      this.leftNodes = [];
      allNodes.forEach(node => {
        if (node.hidden) return;
        if (!node.section) {
          this.leftNodes.push(node);
        }
      });

      this.leftNodes.sort((a, b) => this.compareStrings(a.name, b.name));
      this.leftLoading$.off();
    }, error => {
      this._log.error(error);
      this.leftNodes = [];
      this.leftLoading$.off();
    });
  }

  protected loadRightSide() {
    this.rightLoading$.on();
    this._uriService.getCasesOfNode(this.currentNode, FILTER_IDENTIFIERS, 0, 1).subscribe(page => {
      this._log.debug('Number of filters for uri ' + this.currentNode.uriPath + ': ' + page?.pagination?.totalElements);
      forkJoin({
        folders: this._uriService.getChildNodes(this.currentNode),
        filters: page?.pagination?.totalElements === 0 ? of([]) : this._uriService.getCasesOfNode(this.currentNode, FILTER_IDENTIFIERS, 0, page.pagination.totalElements).pipe(
          map(p => p.content),
        ),
      }).subscribe(result => {
        const allNodes = ((result.folders instanceof Array ? result.folders : []) as Array<ETaskUriNodeResource>)
          .sort((a, b) => this.compareStrings(a.name, b.name));
        this.rightNodes = [];
        this.views = [];
        this.settingsNodes = [];
        this.settingsViews = [];
        this.isSectionOpen.views = true;
        this.isSectionOpen.folders = true;
        allNodes.forEach(node => {
          if (node.hidden) return;
          if (node.section === ETaskDoubleDrawerComponent.SETTINGS_SECTION) {
            this.settingsNodes.push(node);
          } else {
            // Sekcia Archív je z menu odobraná - uzol, ktorý sa do nej hlásil,
            // patrí medzi bežné priečinky. Zahodiť ho by znamenalo, že zmizne
            // z menu a nikde sa to nedozvieš.
            this.rightNodes.push(node);
          }
        });
        const allViewsFilters = (result.filters instanceof Array ? result.filters : []);
        allViewsFilters.forEach(vf => {
          const convertedViewItem = this.resolveFilterCaseToViewNavigationItem(vf);
          if (!convertedViewItem) return;
          const sectionImmediate = vf.immediateData.find(f => f.stringId === 'custom_drawer_section')?.value;
          if (sectionImmediate === ETaskDoubleDrawerComponent.SETTINGS_SECTION) {
            this.settingsViews.push(convertedViewItem);
          } else {
            // Všetko ostatné (vrátane neznámej sekcie) ide do bežných
            // zobrazení. Predtým tu bola vetva do Archívu, takže zobrazenie
            // s preklepom v `custom_drawer_section` sa ticho stratilo v sekcii,
            // ktorú nikto neotvára.
            this.views.push(convertedViewItem);
          }
        });
        if (!!this._childCustomViews[this.currentNode.uriPath]) {
          this.views.push(...Object.values(this._childCustomViews[this.currentNode.uriPath]));
        }
        // @ts-ignore
        this.views.sort((a, b) => this.compareStrings(a?.navigation?.title, b?.navigation?.title));
        this.rightLoading$.off();
      }, error => {
        this._log.error(error);
        this.rightNodes = [];
        this.views = [];
        this.rightLoading$.off();
      });
    }, error => {
      this._log.error(error);
      this.rightNodes = [];
      this.views = [];
      this.rightLoading$.off();
    });
  }

  /**
   * Je sekcia Nastavenia prázdna?
   *
   * Pozor na to, čo tu stálo predtým: `!this.settingsNodes && !this.settingsViews`
   * je **vždy false** - prázdne pole je v JS truthy. Nadpis sekcie sa preto
   * zobrazoval aj nad ničím, a presne tak vznikol prázdny „Archív" v menu.
   */
  public isSettingsEmpty(): boolean {
    return !this.settingsNodes?.length && !this.settingsViews?.length;
  }

  public getLeftNodeIcon(node: UriNodeResource): string {
    const cNode = node as ETaskUriNodeResource;
    if (cNode.icon) {
      return cNode.icon;
    }
    if (icons[node.name]) {
      return icons[node.name];
    }
    return node.id === this.currentNode.id ? this.openedFolderIcon : this.folderIcon;
  }

  public getRightFolderIcon(node: UriNodeResource): string {
    const cNode = node as ETaskUriNodeResource;
    if (cNode.icon) {
      return cNode.icon;
    }
    if (icons[node.name]) {
      return icons[node.name];
    }
    return this.folderIcon;
  }

  /**
   * Log out.
   *
   * `UserService.logout()` returns an `Observable<object>` and an HTTP observable
   * is cold: without a subscriber nothing is sent and nothing happens. This used
   * to be a bare `this._userService.logout()`, so the item in the left menu did
   * literally nothing - no request, no redirect, no error. The dashboard's own
   * logout button subscribes, which is why one of them worked and the other
   * didn't.
   *
   * The redirect is part of logging out: the guard would eventually bounce the
   * user, but only on the next navigation, so without it the app keeps showing
   * a session that no longer exists.
   */
  public logout(): void {
    this._userService.logout().subscribe(
      () => this._router.navigate(['login']),
      error => {
        this._log.error('Logout failed', error);
        this._router.navigate(['login']);
      });
  }

  public isRoot(): boolean {
    return this.currentNode.name === 'root';
  }

  /**
   * Same as the library's, except the view name follows the portal's language.
   *
   * The library takes `entry_name.value.defaultValue` and therefore always shows the
   * language the menu item was created in. `localisedViewTitle` prefers the matching
   * entry in `translations` and keeps the same fallbacks, so a menu item created with
   * a plain string is unaffected. Why it matters and what the payload looks like is
   * in `view-title.ts`.
   *
   * Only the title is touched; everything else, the access check included, comes from
   * `super`. Copying the library's body instead would have meant carrying its access
   * check along by hand, and a copy that loses it turns a view somebody may not open
   * into a visible menu entry that 403s on click.
   */
  public ngOnDestroy(): void {
    super.ngOnDestroy();
    this._languageSub?.unsubscribe();
  }

  protected resolveFilterCaseToViewNavigationItem(filter: Case): ViewNavigationItem | undefined {
    const item = super.resolveFilterCaseToViewNavigationItem(filter);
    // `navigation` is typed `boolean | {title?, icon?, ...}` - the boolean form means
    // "no navigation entry", and writing a title into that would be meaningless.
    if (!item || typeof item.navigation !== 'object' || !item.navigation) return item;
    item.navigation.title = localisedViewTitle(filter, this.getLang());
    return item;
  }
}
