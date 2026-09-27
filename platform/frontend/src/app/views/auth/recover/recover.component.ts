import {Component, OnInit} from '@angular/core';
import {ActivatedRoute, Router} from '@angular/router';
import {
  LanguageService,
  LoggerService,
  MessageResource,
  NAE_VIEW_ID_SEGMENT,
  SnackBarService,
  ViewIdService,
} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';

/**
 * Nastavenie noveho hesla z odkazu, ktory prisiel mailom po ziadosti o obnovu.
 *
 * Dvojica k `ResetPasswordComponent`: tam clovek zada adresu, sem sa dostane
 * z mailu. Formular je kniznicny (`nc-forgotten-password-form`), tento
 * komponent riesi len token v URL a to, co sa stane po odoslani.
 *
 * Token je v `?token=` z toho isteho dovodu ako pri pozvanke - standardne
 * Base64 z enginu obsahuje `/`, ktory by cestu rozbil. Varianta `/:token`
 * zostava pre odkazy z povodnych sablon enginu.
 *
 * Co treba vediet pri ladeni: `/api/auth/reset` ucet prepne do stavu BLOCKED
 * a zmaze mu heslo. Kym sa novo nenastavi, NEPRIHLASI SA ani tym povodnym -
 * a zo samotneho "nespravne prihlasovacie udaje" sa to nedozvie nikto.
 */
@Component({
  selector: 'app-recover',
  templateUrl: './recover.component.html',
  styleUrls: ['./recover.component.scss'],
  providers: [
    {
      provide: NAE_VIEW_ID_SEGMENT,
      useValue: 'recover',
    },
    ViewIdService,
  ],
})
export class RecoverComponent implements OnInit {

  public token: string;
  public tokenInvalid = false;
  public done = false;

  constructor(private _route: ActivatedRoute,
              private _router: Router,
              private _snackbar: SnackBarService,
              private _translate: TranslateService,
              private _language: LanguageService,
              private _log: LoggerService) {
  }

  public get currentLanguage(): string {
    return this._language.getLanguage();
  }

  public get tokenMissing(): boolean {
    return !this.token;
  }

  ngOnInit(): void {
    this.token = this._route.snapshot.queryParamMap.get('token')
      ?? this._route.snapshot.paramMap.get('token')
      ?? '';
    if (!this.token) {
      this._log.warn('Recover view opened without a token');
    }
  }

  public onRecover(message: MessageResource): void {
    if (message && message.error) {
      this._log.error('Password recovery failed: ' + message.error);
      this._snackbar.openErrorSnackBar(this._translate.instant('auth.recover.failed'));
      return;
    }
    this.done = true;
    this._snackbar.openSuccessSnackBar(this._translate.instant('auth.recover.done'));
    this._router.navigate(['/login']).then(value => this._log.debug('Routed to ' + value));
  }

  public onInvalidToken(): void {
    this.tokenInvalid = true;
  }

  public toLogin(): void {
    this._router.navigate(['/login']);
  }

  public toReset(): void {
    this._router.navigate(['/reset']);
  }
}
