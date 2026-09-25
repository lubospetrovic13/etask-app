import {Component, OnInit} from '@angular/core';
import {ActivatedRoute, Router} from '@angular/router';
import {CaseResourceService, LoggerService, PetriNetResourceService} from '@netgrif/components-core';
import {switchMap} from 'rxjs/operators';
import {formView} from './form-views';

/**
 * `portal/form/:view` - creates a new case of the form's process and moves on
 * to its task: `portal/form/:view/:caseId/:transitionId`.
 *
 * Two routes, not one, because the single task view reads the case and the
 * transition from the route when it is constructed (`NAE_BASE_FILTER`). The
 * case does not exist yet when this route is entered, and it must not be
 * created twice on a reload - so this step is `replaceUrl`: Back from the form
 * does not come here and create another one.
 */
@Component({
  selector: 'app-form-launch',
  template: `
    <div class="form-launch" fxLayout="column" fxLayoutAlign="center center">
      <mat-spinner *ngIf="!error" diameter="40"></mat-spinner>
      <div *ngIf="error" class="form-launch-error">{{ error }}</div>
    </div>`,
  styles: ['.form-launch { height: 100%; padding: 48px 16px; } .form-launch-error { max-width: 480px; text-align: center; }'],
})
export class FormLaunchComponent implements OnInit {

  public error: string;

  constructor(private _route: ActivatedRoute,
              private _router: Router,
              private _nets: PetriNetResourceService,
              private _cases: CaseResourceService,
              private _log: LoggerService) {
  }

  ngOnInit(): void {
    const id = this._route.snapshot.paramMap.get('view');
    const form = formView(id);
    if (!form) {
      this.error = `"${id}" is not a form view.`;
      return;
    }
    // '^' = the newest version of the net: the one new cases come from.
    this._nets.getOne(form.process, '^').pipe(
      switchMap(net => this._cases.createCase({title: null, color: '', netId: net.stringId})),
    ).subscribe(outcome => {
      const caseId = outcome?.outcome?.['aCase']?.stringId;
      if (!caseId) {
        this.error = outcome?.error ?? 'The form could not be opened.';
        return;
      }
      this._router.navigate(['portal', 'form', id, caseId, form.transition], {replaceUrl: true});
    }, err => {
      this._log.error('Form launch failed', err);
      this.error = 'The form could not be opened. You may not be allowed to create it - try signing out and in again.';
    });
  }
}
