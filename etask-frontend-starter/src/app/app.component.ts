import {Component} from '@angular/core';
import {AuthenticationService, LanguageService, RoutingBuilderService} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';
import en from '../assets/i18n/en.json';
import sk from '../assets/i18n/sk.json';

/** Language a first-time visitor gets. Slovak, because that is the primary audience. */
const DEFAULT_LANGUAGE = 'sk-SK';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent {
  title = 'etask';

  constructor(private _languageService: LanguageService, private routingBuilder: RoutingBuilderService,
              private auth: AuthenticationService,
              private _translate: TranslateService) {

    this._translate.setTranslation('sk-SK', sk, true);
    this._translate.setTranslation('en-US', en, true);

    // Set the default only when nothing has been chosen yet.
    //
    // This used to be an unconditional `setLanguage('sk-SK')`, and that quietly broke
    // the whole language switcher: `LanguageService` restores the remembered language
    // in its own constructor - from `localStorage['Language']`, falling back to the
    // browser's - and this line then ran afterwards and overwrote it. Switching to
    // English worked for exactly as long as the tab stayed open; the next reload was
    // Slovak again, with no error anywhere to connect it to.
    //
    // Reading localStorage directly is deliberate: `LanguageService` exposes only
    // `getLanguage()`, which by then already reports its own fallback, so it cannot
    // answer "did the user ever choose?". The key is the library's own.
    let chosen: string | null = null;
    try {
      chosen = localStorage.getItem('Language');
    } catch {
      // Private mode or blocked site data. Falls through to the default.
    }
    if (!chosen) {
      this._languageService.setLanguage(DEFAULT_LANGUAGE);
    }
  }

  isAuthenticated(): boolean {
    return this.auth.isAuthenticated;
  }
}
