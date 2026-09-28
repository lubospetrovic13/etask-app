import {Component} from '@angular/core';
import {AuthenticationService, LanguageService, RoutingBuilderService} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';
import {LANGUAGE_CHOSEN_KEY} from './views/side-nav/etask-language-selector/etask-language-selector.component';
import en from '../assets/i18n/en.json';
import sk from '../assets/i18n/sk.json';

/** What everyone gets until they pick a language in the switcher. */
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

    // English for everyone who has not picked a language.
    //
    // The portal is for people outside Slovakia first, so the browser language is not
    // a good enough signal: a Slovak browser used to get Slovak automatically, and the
    // first thing a reviewer saw was a Slovak portal. Slovak stays one click away in
    // the switcher, and that click is remembered (LANGUAGE_CHOSEN_KEY). Once logged in,
    // `UserPreferenceService` holds the choice and wins - the switcher saves it with
    // `setLanguage(lang, true)`.
    //
    // History, because it bit twice: an unconditional `setLanguage(...)` here broke the
    // switcher (it overwrote the remembered language on every reload), and "only when
    // nothing is stored" was dead code, because the service stores a value during its
    // own construction. Hence the separate flag.
    let chosen = false;
    try {
      chosen = localStorage.getItem(LANGUAGE_CHOSEN_KEY) === '1';
    } catch {
      // Private mode or blocked site data: nobody can have chosen, English it is.
    }
    if (!chosen) {
      this._languageService.setLanguage(DEFAULT_LANGUAGE);
    }
  }

  isAuthenticated(): boolean {
    return this.auth.isAuthenticated;
  }
}
