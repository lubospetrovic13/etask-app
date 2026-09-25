import {Component} from '@angular/core';
import {AuthenticationService, LanguageService, RoutingBuilderService} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';
import {
  ETASK_LANGUAGE_CHOSEN,
  ETASK_LANGUAGES,
} from './views/side-nav/etask-language-selector/etask-language-selector.component';
import en from '../assets/i18n/en.json';
import sk from '../assets/i18n/sk.json';

/** What a visitor gets until they pick a language in the switcher. */
const DEFAULT_LANGUAGE = 'en-US';

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

    // English for everyone who has not picked a language in the switcher.
    //
    // `LanguageService` restores a language in its own constructor - from
    // `localStorage['Language']`, else the browser's - and writes that key while doing
    // so, so by now `Language` is always set and cannot tell a choice from a guess.
    // A Slovak browser would therefore always land in Slovak. The switcher writes its
    // own key (`ETASK_LANGUAGE_CHOSEN`) and only that one counts as a choice.
    //
    // Not an unconditional `setLanguage`: that once overwrote the remembered choice on
    // every reload. Once logged in, `UserPreferenceService` holds the choice and wins.
    let chosen: string | null = null;
    try {
      chosen = localStorage.getItem(ETASK_LANGUAGE_CHOSEN);
    } catch {
      // Private mode or blocked site data.
    }
    const valid = ETASK_LANGUAGES.some(l => l.key === chosen);
    this._languageService.setLanguage(valid ? chosen as string : DEFAULT_LANGUAGE);
  }

  isAuthenticated(): boolean {
    return this.auth.isAuthenticated;
  }
}
