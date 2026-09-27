import {Injectable} from '@angular/core';
import {
  AccessService,
  Case,
  DynamicNavigationRouteProviderService,
  FILTER_VIEW_TASK_TRANSITION_ID,
  LanguageService,
  RoleAccess,
  ViewNavigationItem,
} from '@netgrif/components-core';
import {localisedViewTitle} from './view-title';

/**
 * Prípad `preference_filter_item` → položka menu, ktorú sa dá otvoriť.
 *
 * Je to kód `AbstractNavigationDoubleDrawerComponent`-u, ktorý knižnica drží
 * ako `protected` metódy komponentu, takže sa z ničoho iného zavolať nedá.
 * Dashboard si ho preto skopíroval; odkedy má zobrazenia priečinka vykresliť
 * aj `FolderViewComponent`, boli by kópie dve - a druhá kópia je presne to
 * miesto, kde sa raz stratí `canAccessView` a zo zobrazenia, ktoré človek
 * otvoriť nesmie, sa stane položka, ktorá pri kliknutí vráti 403.
 *
 * `canAccessView` teda zostáva TU, na jednom mieste, a obaja volajúci
 * dostanú buď položku, ktorú smú ukázať, alebo `undefined`.
 */
@Injectable({
  providedIn: 'root',
})
export class ViewNavigationResolverService {

  constructor(private _accessService: AccessService,
              private _dynamicRoutingService: DynamicNavigationRouteProviderService,
              private _language: LanguageService) {
  }

  public resolve(filter: Case): ViewNavigationItem | undefined {
    const item: ViewNavigationItem = {
      access: {},
      navigation: {
        icon: filter.immediateData.find(f => f.stringId === 'icon_name')?.value,
        title: localisedViewTitle(filter, this._language.getLanguage()),
      },
      routing: {
        path: this.routingPath(filter),
      },
      id: filter.stringId,
      resource: filter,
    };
    const resolvedRoles = this.accessRoles(filter, 'allowed_roles');
    const resolvedBannedRoles = this.accessRoles(filter, 'banned_roles');
    if (!!resolvedRoles) item.access['role'] = resolvedRoles;
    if (!!resolvedBannedRoles) item.access['bannedRole'] = resolvedBannedRoles;
    if (!this._accessService.canAccessView(item, item.routingPath)) return;
    return item;
  }

  /**
   * Zoznam prípadov → zobrazenia, ktoré tento človek smie otvoriť, zoradené
   * podľa názvu. Poradie je tu zámerne: server ich vracia v poradí, v akom
   * ich našiel, takže bez toho by ten istý priečinok vyzeral zakaždým inak.
   */
  public resolveAll(cases: Array<Case> | unknown): Array<ViewNavigationItem> {
    // Na nula výsledkoch je `page.content` surový HAL objekt, nie `[]` -
    // `?? []` ho nechytí a `.map` padne. Tá pasca stála jeden celý priečinok,
    // ktorý „nemal žiadne zobrazenia".
    const list = Array.isArray(cases) ? (cases as Array<Case>) : [];
    return list
      .map(c => this.resolve(c))
      .filter(v => !!v)
      .sort((a, b) => this.title(a).localeCompare(this.title(b)));
  }

  public title(view: ViewNavigationItem): string {
    // `navigation` je v type `boolean | {title?, icon?, ...}` - bez tejto
    // stráže build neprejde.
    return (typeof view.navigation === 'object' && !!view.navigation
      ? (view.navigation.title ?? '') : '');
  }

  public icon(view: ViewNavigationItem): string {
    return (typeof view.navigation === 'object' && !!view.navigation
      ? (view.navigation.icon ?? 'list') : 'list');
  }

  private routingPath(filterCase: Case): string {
    const viewTaskId = filterCase.tasks
      .find(taskPair => taskPair.transition === FILTER_VIEW_TASK_TRANSITION_ID).task;
    const url = this._dynamicRoutingService.route;
    return `/${url}/${viewTaskId}`;
  }

  private accessRoles(filter: Case, roleType: string): Array<RoleAccess> | undefined {
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
}
