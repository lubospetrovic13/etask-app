import {Component} from '@angular/core';
import {LanguageSelectorComponent} from '@netgrif/components';
import {LanguageService} from '@netgrif/components-core';

/** The two languages this portal is actually translated into. */
export const ETASK_LANGUAGES = [
  {key: 'en-US', value: 'en', flag: 'gb'},
  {key: 'sk-SK', value: 'sk'},
];

/**
 * localStorage key holding the language the visitor picked in this switcher.
 * `LanguageService` writes its own `Language` key during construction, so that one
 * cannot tell an explicit choice from a guess; this one only the switcher writes.
 */
export const ETASK_LANGUAGE_CHOSEN = 'etask.languageChosen';

/**
 * Language switcher offering Slovak and English, and nothing else.
 *
 * The library's `nc-language-selector` offers three: sk-SK, de-DE, en-US. That list is
 * a plain property on `AbstractLanguageSelectorComponent`, not an `@Input`, so the only
 * way to change it is a subclass - which is why this file exists rather than a binding
 * in the drawer template.
 *
 * Why narrow it at all. German would not give a German portal, it would give a half
 * German one: the library ships de translations for its own 325 keys and we ship de for
 * our 20, but every string that comes out of a Petriflow net - net titles, task labels,
 * field titles, options - has only the `sk` and `en` blocks the nets declare. Picking
 * German therefore produces English chrome around Slovak content, which reads as a bug
 * and is one. Offering a language is a promise that the whole screen is in it.
 *
 * It extends the concrete `LanguageSelectorComponent`, not the abstract one, because
 * `getFlag()` and the base64 flags live on the concrete class; from the abstract class
 * the template would compile and then render broken images at runtime.
 */
@Component({
  selector: 'app-etask-language-selector',
  templateUrl: './etask-language-selector.component.html',
  styleUrls: ['./etask-language-selector.component.scss'],
})
export class EtaskLanguageSelectorComponent extends LanguageSelectorComponent {

  constructor(languageService: LanguageService) {
    super(languageService);
    this.langMenuItems = ETASK_LANGUAGES;
  }

  setLang(lang: string) {
    super.setLang(lang);
    try {
      localStorage.setItem(ETASK_LANGUAGE_CHOSEN, lang);
    } catch {
      // Private mode or blocked site data: the choice lasts for this tab only.
    }
  }
}
