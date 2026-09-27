import {Pipe, PipeTransform} from '@angular/core';
import {TranslateService} from '@ngx-translate/core';

/** `uriNode.` + this, normalised the same way `uriNodeIcons.json` keys are. */
export function uriNodeKey(name: string): string {
  return (name ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/_/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_');
}

/** Title case of every word, so `service_desk` reads as `Service Desk`. */
export function beautifyUriNodeName(name: string): string {
  return (name ?? '')
    .replace(/_/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(word => word.length > 0)
    .map(word => word.charAt(0).toLocaleUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Display name of a URI node - the folder cards and the drawer tree - in the current
 * language.
 *
 * A URI node has **no** translatable name. `UriService` builds it from the process
 * identifier and stores a plain `String`:
 *
 *     uriNode.setName(uriComponents[i]);   // UriService.java:200
 *
 * Unlike a net title, a task label or a field title, it is not an `I18nString`, so no
 * `<i18n>` block in any net can reach it and no `Accept-Language` header changes it.
 * The name is therefore translated on this side, and it has to be: the folder names are
 * the first thing on the dashboard, and leaving them in one language while everything
 * else switches is the kind of half-translated screen that reads as broken.
 *
 * The key is `uriNode.<segment>` in `assets/i18n/*.json`, normalised like the icon map
 * so `service_desk`, `Service Desk` and `SERVICE_DESK` land on the same entry. A node
 * with no entry falls back to the beautified segment, which is exactly what was shown
 * before this pipe existed - so an app that adds a folder and forgets the translation
 * looks the same as it used to rather than showing a raw key.
 */
@Pipe({name: 'uriNodeTitle', pure: false})
export class UriNodeTitlePipe implements PipeTransform {

  constructor(private _translate: TranslateService) {
  }

  public transform(name: string): string {
    const key = 'uriNode.' + uriNodeKey(name);
    const translated = this._translate.instant(key);
    // `instant` returns the key itself when there is no entry for it.
    return translated === key ? beautifyUriNodeName(name) : translated;
  }
}
