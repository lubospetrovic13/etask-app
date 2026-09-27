import {Component, OnDestroy} from '@angular/core';
import {ImportNetComponent} from '@netgrif/components';
import {
  AbstractWorkflowViewComponent,
  LoggerService,
  ProcessService,
  SideMenuService,
  WorkflowViewService,
} from '@netgrif/components-core';
import {Subject} from 'rxjs';
import {debounceTime, distinctUntilChanged, takeUntil} from 'rxjs/operators';
import {
  EtaskWorkflowViewService,
  WORKFLOW_SEARCH_FIELDS,
  WorkflowSearchField,
} from '../etask-workflow-view.service';


@Component({
  selector: 'app-workflow-view',
  templateUrl: './workflow-view.component.html',
  styleUrls: ['./workflow-view.component.scss'],
  // `useExisting`, nie dva samostatné providery: `AbstractWorkflowViewComponent`
  // si pýta `WorkflowViewService`, my potrebujeme tú istú INŠTANCIU aj pod
  // vlastným typom. Dva providery by znamenali dve služby, dve stránkovania
  // a hľadanie by sa prejavilo v zozname, ktorý nikto nevidí.
  providers: [
    EtaskWorkflowViewService,
    {provide: WorkflowViewService, useExisting: EtaskWorkflowViewService},
  ],
})
export class WorkflowViewComponent extends AbstractWorkflowViewComponent implements OnDestroy {

  public readonly searchFields = WORKFLOW_SEARCH_FIELDS;
  public searchField: WorkflowSearchField = 'identifier';
  public searchTerm = '';

  private readonly _searchInput$ = new Subject<string>();
  private readonly _destroy$ = new Subject<void>();

  constructor(protected _sideMenuService: SideMenuService,
              protected _workflowViewService: EtaskWorkflowViewService,
              protected _log: LoggerService,
              protected _processService: ProcessService) {
    super(_sideMenuService, _workflowViewService, _log, _processService);

    // Debounce, lebo každý úder do klávesnice je inak jeden `POST
    // /api/petrinet/search`. `distinctUntilChanged` navyše zahodí prípad, keď
    // sa text po debounci nezmenil (kurzorové klávesy, opravený preklep).
    this._searchInput$.pipe(
      debounceTime(300),
      distinctUntilChanged(),
      takeUntil(this._destroy$),
    ).subscribe(() => this.applySearch());
  }

  public importNet() {
    this.importSidemenuNet(ImportNetComponent);
  }

  /** Zmena textu - prejde cez debounce. */
  public onSearchInput(): void {
    this._searchInput$.next(this.searchTerm);
  }

  /** Zmena poľa - hľadá sa hneď, klik na výber nie je písanie. */
  public onSearchFieldChange(): void {
    if (this.searchTerm.trim()) {
      this.applySearch();
    }
  }

  public clearSearch(): void {
    if (!this.searchTerm) {
      return;
    }
    this.searchTerm = '';
    this.applySearch();
  }

  private applySearch(): void {
    this._workflowViewService.applySearch(this.searchField, this.searchTerm);
  }

  ngOnDestroy(): void {
    this._destroy$.next();
    this._destroy$.complete();
    this._searchInput$.complete();
  }
}
