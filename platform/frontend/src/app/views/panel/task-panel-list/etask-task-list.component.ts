import {Component, Inject, Input, Optional} from '@angular/core';
import {ActivatedRoute} from '@angular/router';
import {TaskListComponent} from '@netgrif/components';
import {InjectedTabData, LoggerService, NAE_TAB_DATA, TaskPanelData, TaskViewService} from '@netgrif/components-core';
import {Observable} from 'rxjs';
import {map} from 'rxjs/operators';

/**
 * Read-only overview of a case: the transition `pfnew` generates as `t_<prefix>_prehlad`
 * (`_overview` in English nets). It hangs on a read arc, so it is enabled in every state.
 */
export const OVERVIEW_TRANSITION = /_(prehlad|overview)$/;

@Component({
  selector: 'app-etask-task-list',
  templateUrl: './etask-task-list.component.html',
  styleUrls: ['./etask-task-list.component.scss'],
})
export class EtaskTaskListComponent extends TaskListComponent {

  /**
   * Na verejnom formulari je uloha jedina a je to cely obsah stranky, takze
   * hlavicka panela ani jeho zbalenie nedavaju zmysel. Kniznicny panel oboje
   * vie vypnut, len to zo zoznamu nemal ako dostat.
   */
  @Input() public preventCollapse = false;
  @Input() public hidePanelHeader = false;

  /**
   * Zoznam bez prehladu case-u, ktory ma v zozname aj inu ulohu. Prehlad je na to,
   * aby clovek videl stav, ked nema co robit; ked ma, stav je v jeho ulohe tiez
   * a dve polozky pre ten isty case len matu (faktura: "Stav faktury" nad
   * "Zapisat fakturu").
   *
   * Vo vrstve 3, lebo sa to tyka toho, co vidi prave tento pouzivatel: engine
   * nema opravnenie "vykonaj, ak nemozes vykonat inu ulohu case-u". Sietou by sa
   * to dalo len negativnym `view` cez `userRef` so zoznamom ludi, ktori su prave
   * na rade - a ten by musela kazda siet v kazdom kroku prepocitavat z roli.
   */
  get visibleTasks$(): Observable<Array<TaskPanelData>> {
    // `tasks$` je vstup - nastavi sa az po konstrukcii a moze sa vymenit.
    const source = this.tasks$;
    if (source !== this._visibleSource) {
      this._visibleSource = source;
      this._visible = source?.pipe(map(tasks => {
        const busy = new Set(tasks
          .filter(t => !OVERVIEW_TRANSITION.test(t.task.transitionId))
          .map(t => t.task.caseId));
        return tasks.filter(t => !OVERVIEW_TRANSITION.test(t.task.transitionId) || !busy.has(t.task.caseId));
      }));
    }
    return this._visible;
  }

  private _visibleSource: Observable<Array<TaskPanelData>>;
  private _visible: Observable<Array<TaskPanelData>>;

  constructor(_taskViewService: TaskViewService,
              _log: LoggerService,
              @Optional() @Inject(NAE_TAB_DATA) injectedTabData: InjectedTabData,
              route?: ActivatedRoute) {
    super(_taskViewService, _log, injectedTabData, route);
  }
}
