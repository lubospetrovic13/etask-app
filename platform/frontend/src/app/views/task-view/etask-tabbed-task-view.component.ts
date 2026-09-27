import {AfterViewInit, Component, Inject, ViewChild} from '@angular/core';
import {HeaderComponent} from '@netgrif/components';
import {
  AbstractTabbedTaskViewComponent,
  AllowedNetsService,
  AllowedNetsServiceFactory,
  CategoryFactory,
  ChangedFieldsService,
  InjectedTabbedTaskViewData,
  NAE_BASE_FILTER,
  NAE_DEFAULT_HEADERS,
  NAE_TAB_DATA,
  NAE_TASK_VIEW_CONFIGURATION,
  SearchService,
  tabbedAllowedNetsServiceFactory,
  tabbedTaskViewConfigurationFactory,
  TaskViewService,
  ViewIdService,
} from '@netgrif/components-core';

export function baseFilterFactory(injectedTabData: InjectedTabbedTaskViewData) {
  return {
    filter: injectedTabData.baseFilter,
  };
}

/**
 * The library default minus `meta-priority`. Values are `HeaderColumn.uniqueId`,
 * which for meta columns is `meta-<TaskMetaField>`.
 *
 * Kept at module level rather than as a static on the component: the component
 * decorator references it, and a class referring to its own static from its own
 * decorator is not statically analysable for the AOT compiler.
 */
export const ETASK_TASK_HEADERS = [
  'meta-caseTitleSortable',
  'meta-title',
  'meta-user',
  'meta-assign-date',
];

/**
 * Task list shown inside an opened case tab, replacing
 * @netgrif/components' DefaultTabbedTaskViewComponent.
 *
 * Two reasons to own it:
 *
 * 1. **Column set.** The priority column comes from TaskHeaderService's meta
 *    headers, which default to case / title / priority / user / assign date.
 *    {@link NAE_DEFAULT_HEADERS} replaces that list. TaskHeaderService is provided
 *    on `nc-header` itself, so a provider here reaches it - and only it, leaving the
 *    case list's own header untouched. The token takes `HeaderColumn.uniqueId`
 *    values, which for meta columns are `meta-<TaskMetaField>`.
 *
 * 2. **Density.** The library template surrounds the search card and the header bar
 *    with 20px paddings and a 16px mat-card padding, costing about 90px of vertical
 *    space before the first row. Owning the template tightens that without having to
 *    fight component-scoped styles with `!important` from the global stylesheet.
 *
 * Everything else - the provider list, the base filter factory - is carried over
 * from the library component unchanged.
 */
@Component({
  selector: 'app-etask-tabbed-task-view',
  templateUrl: './etask-tabbed-task-view.component.html',
  styleUrls: ['./etask-tabbed-task-view.component.scss'],
  providers: [
    CategoryFactory,
    TaskViewService,
    SearchService,
    ChangedFieldsService,
    {provide: ViewIdService, useValue: null},
    {
      provide: NAE_BASE_FILTER,
      useFactory: baseFilterFactory,
      deps: [NAE_TAB_DATA],
    },
    {
      provide: AllowedNetsService,
      useFactory: tabbedAllowedNetsServiceFactory,
      deps: [AllowedNetsServiceFactory, NAE_TAB_DATA],
    },
    {
      provide: NAE_TASK_VIEW_CONFIGURATION,
      useFactory: tabbedTaskViewConfigurationFactory,
      deps: [NAE_TAB_DATA],
    },
    {
      provide: NAE_DEFAULT_HEADERS,
      useValue: ETASK_TASK_HEADERS,
    },
  ],
})
export class EtaskTabbedTaskViewComponent extends AbstractTabbedTaskViewComponent implements AfterViewInit {

  /**
   * Bound to `nc-header`'s `maxHeaderColumns`. Must match the length of
   * {@link ETASK_TASK_HEADERS} - the header pads any difference with empty columns.
   */
  public readonly headerColumns = ETASK_TASK_HEADERS.length;

  @ViewChild('header') public taskHeaderComponent: HeaderComponent;

  constructor(taskViewService: TaskViewService,
              @Inject(NAE_TAB_DATA) injectedTabData: InjectedTabbedTaskViewData) {
    super(taskViewService, injectedTabData);
  }

  ngAfterViewInit(): void {
    this.initializeHeader(this.taskHeaderComponent);
  }
}
