import {AfterViewInit, Component, Inject, Optional, ViewChild} from '@angular/core';
import {
  filterCaseTabbedDataAllowedNetsServiceFactory,
  filterCaseTabbedDataFilterFactory,
  filterCaseTabbedDataSearchCategoriesFactory,
  HeaderComponent,
} from '@netgrif/components';
import {
  AbstractTabbedCaseViewComponent,
  AllowedNetsService,
  AllowedNetsServiceFactory,
  BaseAllowedNetsService,
  CaseViewService,
  CategoryFactory,
  CategoryResolverService,
  FilterExtractionService,
  InjectedTabbedCaseViewData,
  LoggerService,
  NAE_AUTOSWITCH_TAB_TOKEN,
  NAE_BASE_FILTER,
  NAE_DEFAULT_CASE_SEARCH_CATEGORIES,
  NAE_DEFAULT_TASK_SEARCH_CATEGORIES,
  NAE_OPEN_EXISTING_TAB,
  NAE_SEARCH_CATEGORIES,
  NAE_TAB_DATA,
  OverflowService,
  SearchService,
  ViewIdService,
} from '@netgrif/components-core';

/**
 * Stand-in for the library's `nc-default-tabbed-case-view` (`DefaultTabbedCaseViewComponent`),
 * used by `EtaskTabViewComponent` for every drawer menu-item tab - i.e. every case-list view
 * reached through the side menu.
 *
 * The library's own component hardcodes `undefined` for `_overflowService` in its constructor
 * (see its compiled `super(caseViewService, loggerService, injectedTabData, undefined, ...)`),
 * so `AbstractCaseViewComponent.getWidth()`/`getOverflowStatus()` can never see a real
 * `OverflowService` there even if one is added to `providers` - only `nc-header`'s own,
 * separately-injected copy would notice it, which is enough to show the "Table mode" toggle
 * but not enough to actually widen the header/case-list when it is switched on. This copy
 * threads the injected instance through instead, the same way `SideNavCasesCaseViewComponent`
 * (used for the non-tabbed case list) already does.
 */
@Component({
  selector: 'app-etask-tabbed-case-view',
  templateUrl: './etask-tabbed-case-view.component.html',
  styleUrls: ['./etask-tabbed-case-view.component.scss'],
  // Same list `DefaultTabbedCaseViewComponent` provides for itself (this is what actually
  // resolves the menu item's filter/allowed nets/search categories from `NAE_TAB_DATA` -
  // without it the case list has no idea which cases or fields belong to this view), plus
  // `OverflowService` for table mode.
  providers: [
    CategoryFactory,
    CaseViewService,
    SearchService,
    ViewIdService,
    OverflowService,
    {
      provide: NAE_BASE_FILTER,
      useFactory: filterCaseTabbedDataFilterFactory,
      deps: [FilterExtractionService, NAE_TAB_DATA],
    },
    {
      provide: AllowedNetsService,
      useFactory: filterCaseTabbedDataAllowedNetsServiceFactory,
      deps: [AllowedNetsServiceFactory, BaseAllowedNetsService, NAE_TAB_DATA],
    },
    {
      provide: NAE_SEARCH_CATEGORIES,
      useFactory: filterCaseTabbedDataSearchCategoriesFactory,
      deps: [CategoryResolverService, NAE_TAB_DATA, NAE_DEFAULT_CASE_SEARCH_CATEGORIES, NAE_DEFAULT_TASK_SEARCH_CATEGORIES],
    },
  ],
})
export class EtaskTabbedCaseViewComponent extends AbstractTabbedCaseViewComponent implements AfterViewInit {

  @ViewChild('header') public caseHeaderComponent: HeaderComponent;

  constructor(caseViewService: CaseViewService,
              loggerService: LoggerService,
              @Inject(NAE_TAB_DATA) injectedTabData: InjectedTabbedCaseViewData,
              overflowService: OverflowService,
              @Optional() @Inject(NAE_AUTOSWITCH_TAB_TOKEN) autoswitchToTaskTab: boolean,
              @Optional() @Inject(NAE_OPEN_EXISTING_TAB) openExistingTab: boolean) {
    super(caseViewService, loggerService, injectedTabData, overflowService, autoswitchToTaskTab, openExistingTab,
      (injectedTabData as any).newCaseButtonConfiguration);
  }

  ngAfterViewInit(): void {
    this.initializeHeader(this.caseHeaderComponent);
  }

  /**
   * Opens a filter picked from `nc-search` in a new tab of this same type - mirrors the
   * library's own `loadFilter`, just pointing the new tab at this class instead of at
   * `DefaultTabbedCaseViewComponent`, so table mode survives switching filters.
   */
  public loadFilter(filterData: { filter: { title: string }, filterCase: unknown }): void {
    this._injectedTabData.tabViewRef.openTab({
      label: {
        text: filterData.filter.title,
      },
      canBeClosed: true,
      tabContentComponent: EtaskTabbedCaseViewComponent,
      injectedObject: {...this._injectedTabData, filterCase: filterData.filterCase},
      order: this._injectedTabData.tabViewOrder,
      parentUniqueId: this._injectedTabData.tabUniqueId,
    }, this._autoswitchToTaskTab, this._openExistingTab);
  }

}
