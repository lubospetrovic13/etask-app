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
 * Dokoncenie registracie z pozvanky.
 *
 * Kniznica ma cely formular hotovy (`nc-registration-form`) - overi token,
 * vypyta meno, priezvisko a heslo a zavola `/api/auth/signup`. Tento komponent
 * je len obal, ktory:
 *   1. vytiahne token z URL,
 *   2. povie cloveku, ked token chyba alebo uz vyprsal,
 *   3. po uspechu ho posle na prihlasenie.
 *
 * TOKEN SA CITA Z `?token=`, nie z cesty. Engine ho koduje standardnym Base64
 * (`Base64.getEncoder()`), takze bezne obsahuje `/` - a ten by segment cesty
 * rozbil, cize zhruba polovica pozvanok by skoncila na 404. Varianta `/:token`
 * zostava zapojena len pre odkazy z povodnych sablon enginu.
 */
@Component({
  selector: 'app-signup',
  templateUrl: './signup.component.html',
  styleUrls: ['./signup.component.scss'],
  providers: [
    {
      provide: NAE_VIEW_ID_SEGMENT,
      useValue: 'signup',
    },
    ViewIdService,
  ],
})
export class SignupComponent implements OnInit {

  /** Token z URL. Prazdny znamena, ze sa sem clovek dostal inak nez z mailu. */
  public token: string;

  /** Odkaz je neplatny alebo vyprsal - `nc-registration-form` to hlasi cez `invalidToken`. */
  public tokenInvalid = false;

  /** Registracia presla; formular sa skryje, aby sa nedal odoslat druhykrat. */
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

  /** Token chyba uplne - iny pripad nez "token je neplatny", a iná veta pre cloveka. */
  public get tokenMissing(): boolean {
    return !this.token;
  }

  ngOnInit(): void {
    this.token = this._route.snapshot.queryParamMap.get('token')
      ?? this._route.snapshot.paramMap.get('token')
      ?? '';
    if (!this.token) {
      this._log.warn('Signup view opened without a token');
    }
  }

  /**
   * `MessageResource` z enginu: `success` alebo `error`. Pozor - registracia
   * vracia HTTP 200 aj ked zlyhala, dovod je v tele. Test na stavovy kod by
   * taky pripad prehliadol, a rovnako by ho prehliadol aj tento komponent,
   * keby sa spoliehal na chybovu vetvu subscribe.
   */
  public onRegister(message: MessageResource): void {
    if (message && message.error) {
      this._log.error('Registration failed: ' + message.error);
      this._snackbar.openErrorSnackBar(this._translate.instant('auth.signup.failed'));
      return;
    }
    this.done = true;
    this._snackbar.openSuccessSnackBar(this._translate.instant('auth.signup.done'));
    this._router.navigate(['/login']).then(value => this._log.debug('Routed to ' + value));
  }

  public onInvalidToken(): void {
    this.tokenInvalid = true;
  }

  public toLogin(): void {
    this._router.navigate(['/login']);
  }
}
