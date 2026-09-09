import {Component} from '@angular/core';
import {AuthenticationService, LanguageService, RoutingBuilderService} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';
import {ETASK_LANGUAGES} from './views/side-nav/etask-language-selector/etask-language-selector.component';
import en from '../assets/i18n/en.json';
import sk from '../assets/i18n/sk.json';

/** What a visitor gets when their browser asks for a language we do not offer. */
const DEFAULT_LANGUAGE = 'sk-SK';

/** `LanguageService._DEFAULT_LANG` - what the library picks when it cannot match. */
const LIBRARY_FALLBACK = 'en-US';

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

    // Slovak for anyone whose browser asks for a language we do not offer.
    //
    // What this is NOT any more: an unconditional `setLanguage('sk-SK')`. That quietly
    // broke the whole switcher. `LanguageService` restores the remembered language in
    // its own constructor - from `localStorage['Language']`, falling back to the
    // browser's, falling back to `en-US` - and this line ran afterwards and overwrote
    // it. Switching to English worked for exactly as long as the tab stayed open; the
    // next reload was Slovak again, with no error to connect it to.
    //
    // The first repair was "set the default only when nothing is stored", and that was
    // dead code: the service writes localStorage during its own construction, so by the
    // time this runs something is always stored. Measured - browser `en-US`, cleared
    // storage, and `localStorage['Language']` was already `en-US` here.
    //
    // So the rule is about the BROWSER language, which is the only signal available
    // this early. `sk` or `en` browser gets its own language; anything else would get
    // the library's `en-US`, and for a Slovak-primary product Slovak is the better
    // guess. A stored value is respected unless it is exactly that `en-US` fallback.
    //
    // Residual case, stated because it is real: someone with, say, a German browser who
    // deliberately picks English gets Slovak again on the next reload while logged out.
    // Once logged in, `UserPreferenceService` holds their choice and wins - the
    // switcher saves it with `setLanguage(lang, true)`.
    const browser = (this._translate.getBrowserLang() ?? '').toLowerCase();
    const offered = ETASK_LANGUAGES.some(l => l.value === browser);
    let stored: string | null = null;
    try {
      stored = localStorage.getItem('Language');
    } catch {
      // Private mode or blocked site data.
    }
    if (!offered && (!stored || stored === LIBRARY_FALLBACK)) {
      this._languageService.setLanguage(DEFAULT_LANGUAGE);
    }
  }

  isAuthenticated(): boolean {
    return this.auth.isAuthenticated;
  }
}
