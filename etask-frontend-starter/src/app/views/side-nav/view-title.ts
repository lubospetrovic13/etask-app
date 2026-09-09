import {Case} from '@netgrif/components-core';

/** Immediate data field on `preference_filter_item` that carries the menu entry name. */
const ENTRY_NAME = 'entry_name';

/**
 * Name of a view (an entry in the left menu / a row on a dashboard card) in the
 * current language.
 *
 * The library resolves it as:
 *
 *     title: filter.immediateData.find(f => f.stringId === 'entry_name')?.value?.defaultValue
 *            || filter.title
 *
 * `entry_name` is an `enumeration` field, so its value is an `I18nString` and the
 * payload really does carry the translations - measured on 6.3.1:
 *
 *     "entry_name": {"defaultValue": "Žiadosti o dovolenku", "translations": {"en": "..."}}
 *
 * The server does not localise this one (unlike task titles or field titles, which
 * arrive already translated), so the choice is the client's - and the library always
 * takes `defaultValue`. The result is that every view in the left menu stays in one
 * language no matter what the portal is switched to. Since the menu is the most
 * visible text in the portal, that alone makes the app read as untranslated.
 *
 * This picks the translation for the current language and keeps the library's
 * fallback chain behind it: `translations[lang]` -> `defaultValue` -> case title. A
 * menu item created with a plain `String` therefore behaves exactly as before.
 *
 * `language` is the portal's locale (`sk-SK`), the translations are keyed by the
 * two-letter language (`sk`) - the same asymmetry as in the nets, where the engine
 * stores whatever `<i18n locale>` says but looks it up by `Locale.getLanguage()`.
 */
export function localisedViewTitle(filter: Case, language: string): string {
  const raw: any = filter?.immediateData?.find(f => f.stringId === ENTRY_NAME)?.value;
  const lang = (language ?? '').split('-')[0];
  return (lang && raw?.translations?.[lang]) || raw?.defaultValue || filter?.title;
}
