import {AsyncPipe} from '@angular/common';
import {AfterViewInit, Component, OnDestroy, ViewChild} from '@angular/core';
import {ActivatedRoute, Router} from '@angular/router';
import {HeaderComponent} from '@netgrif/components';
import {
  AbstractSingleTaskViewComponent,
  AllowedNetsService,
  AllowedNetsServiceFactory,
  CaseResourceService,
  ChangedFieldsService,
  FilterType,
  FinishTaskService,
  LoggerService,
  NAE_BASE_FILTER,
  NAE_TASK_OPERATIONS,
  NAE_VIEW_ID_SEGMENT,
  SearchService,
  SimpleFilter,
  SingleTaskContentService,
  SnackBarService,
  SubjectTaskOperations,
  TaskContentService,
  TaskDataService,
  TaskEvent,
  TaskEventNotification,
  TaskEventService,
  TaskRequestStateService,
  TaskResourceService,
  TaskViewService,
  ViewIdService,
} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';
import {Subscription} from 'rxjs';
import {ViewNavigationResolverService} from '../side-nav/view-navigation-resolver.service';
import {formView, menuItemIdentifier} from './form-views';

/** Exactly one task: the form's transition in the case from the route. */
const formBaseFilterFactory = (route: ActivatedRoute) => {
  return {
    filter: new SimpleFilter('', FilterType.TASK, {
      case: {id: route.snapshot.paramMap.get('caseId')},
      transitionId: route.snapshot.paramMap.get('transitionId'),
    }),
  };
};

const formAllowedNetsFactory = (factory: AllowedNetsServiceFactory, route: ActivatedRoute) => {
  const form = formView(route.snapshot.paramMap.get('view'));
  return factory.createFromArray(form ? [form.process] : []);
};

/**
 * `portal/form/:view/:caseId/:transitionId` - one task of one case, shown as a
 * form, for a SIGNED-IN person. The public single task view does the same for
 * anonymous visitors; this is its private twin (normal resource services, no
 * anonymous session).
 *
 * Finished -> the person lands in the form's `then` menu item.
 * Left without finishing -> the task is released (cancel). The net decides
 * what that means; sd_ticket deletes the draft, so an abandoned form leaves
 * nothing behind in "My Tickets".
 */
@Component({
  selector: 'app-form-task-view',
  templateUrl: './form-task-view.component.html',
  styleUrls: ['./form-task-view.component.scss'],
  providers: [
    TaskViewService,
    SearchService,
    ChangedFieldsService,
    {provide: NAE_BASE_FILTER, useFactory: formBaseFilterFactory, deps: [ActivatedRoute]},
    {provide: AllowedNetsService, useFactory: formAllowedNetsFactory, deps: [AllowedNetsServiceFactory, ActivatedRoute]},
    {provide: NAE_VIEW_ID_SEGMENT, useValue: 'form'},
    ViewIdService,
    {provide: TaskContentService, useClass: SingleTaskContentService},
    TaskDataService,
    FinishTaskService,
    TaskRequestStateService,
    TaskEventService,
    {provide: NAE_TASK_OPERATIONS, useClass: SubjectTaskOperations},
    AsyncPipe,
  ],
})
export class FormTaskViewComponent extends AbstractSingleTaskViewComponent implements AfterViewInit, OnDestroy {

  @ViewChild('header') public taskHeaderComponent: HeaderComponent;

  private _taskId: string;
  private _caseTitle: string;
  private _finished = false;
  private _taskSub: Subscription;

  constructor(taskViewService: TaskViewService,
              activatedRoute: ActivatedRoute,
              async: AsyncPipe,
              private _router: Router,
              private _tasks: TaskResourceService,
              private _cases: CaseResourceService,
              private _resolver: ViewNavigationResolverService,
              private _snack: SnackBarService,
              private _translate: TranslateService,
              private _log: LoggerService) {
    super(taskViewService, activatedRoute, async);
    this._taskSub = this.task$.subscribe(data => {
      if (data?.task) {
        this._taskId = data.task.stringId;
        this._caseTitle = data.task.caseTitle;
      }
    });
  }

  ngAfterViewInit(): void {
    this.initializeHeader(this.taskHeaderComponent);
  }

  public onTaskEvent(event: TaskEventNotification): void {
    if (event?.event === TaskEvent.FINISH && event.success) {
      this._finished = true;
      this._snack.openSuccessSnackBar(this._translate.instant('form.submitted', {title: this._caseTitle ?? ''}));
      this.goToThen();
    }
  }

  public discard(): void {
    // Release happens in ngOnDestroy - one place for Back, menu and this button.
    this._router.navigate(['dashboard']);
  }

  private goToThen(): void {
    const then = formView(this._activatedRoute.snapshot.paramMap.get('view'))?.then;
    if (!then) {
      this._router.navigate(['dashboard']);
      return;
    }
    const filter = new SimpleFilter('', FilterType.CASE, {
      process: {identifier: 'preference_filter_item'},
      query: `dataSet.menu_item_identifier.textValue:"${then}"`,
    });
    this._cases.searchCases(filter).subscribe(page => {
      const list = Array.isArray(page?.content) ? page.content : [];
      const item = list.find(c => menuItemIdentifier(c) === then);
      const view = item ? this._resolver.resolve(item) : undefined;
      this._router.navigate([view ? view.routing.path : 'dashboard']);
    }, () => this._router.navigate(['dashboard']));
  }

  ngOnDestroy(): void {
    if (!this._finished && this._taskId) {
      this._tasks.cancelTask(this._taskId).subscribe(
        () => undefined,
        err => this._log.warn('Releasing the unfinished form failed', err));
    }
    this._taskSub?.unsubscribe();
    super.ngOnDestroy();
  }
}
