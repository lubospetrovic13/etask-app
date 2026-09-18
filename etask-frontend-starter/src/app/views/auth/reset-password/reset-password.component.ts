import {Component} from '@angular/core';
import {Router} from '@angular/router';
import {
  FormSubmitEvent,
  LanguageService,
  LoggerService,
  NAE_VIEW_ID_SEGMENT,
  SignUpService,
  SnackBarService,
  ViewIdService,
} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';
import {take} from 'rxjs/operators';

/**
 * "Zabudnute heslo" - zadanie adresy, na ktoru ma prist odkaz na obnovu.
 *
 * Endpoint `/api/auth/reset` VZDY odpovie `success`, aj ked ucet s tou adresou
 * neexistuje alebo je zablokovany mailovym limitom. Je to zamerne: opacna
 * odpoved by z prihlasovacej obrazovky spravila nastroj na zistovanie, kto
 * v instancii ucet ma. Preto je aj hlaska tu formulovana tak, aby neprezradila
 * viac nez endpoint - "ak ucet existuje, odkaz je na ceste".
 */
@Component({
  selector: 'app-reset-password',
  templateUrl: './reset-password.component.html',
  styleUrls: ['./reset-password.component.scss'],
  providers: [
    {
      provide: NAE_VIEW_ID_SEGMENT,
      useValue: 'reset',
    },
    ViewIdService,
  ],
})
export class ResetPasswordComponent {

  /** Po odoslani sa formular skryje - opakovane odoslanie narazi na limit 2 maily/den. */
  public sent = false;

  constructor(private _signUpService: SignUpService,
              private _router: Router,
              private _snackbar: SnackBarService,
              private _translate: TranslateService,
              private _language: LanguageService,
              private _log: LoggerService) {
  }

  public get currentLanguage(): string {
    return this._language.getLanguage();
  }

  /**
   * `nc-email-submission-form` posiela `{email, loading}` - `loading` je jeho
   * vlastny spinner a treba ho vypnut aj na chybovej vetve, inak sa tocí dalej
   * a formular vyzera zaseknuto.
   */
  public onSubmit(event: FormSubmitEvent): void {
    const email = event.email as string;
    const loading = event.loading;
    loading?.on();
    this._signUpService.resetPassword(email).pipe(take(1)).subscribe(() => {
      loading?.off();
      this.sent = true;
      this._snackbar.openSuccessSnackBar(this._translate.instant('auth.reset.sent'));
    }, error => {
      loading?.off();
      this._log.error('Password reset request failed', error);
      this._snackbar.openErrorSnackBar(this._translate.instant('auth.reset.failed'));
    });
  }

  public toLogin(): void {
    this._router.navigate(['/login']);
  }
}
