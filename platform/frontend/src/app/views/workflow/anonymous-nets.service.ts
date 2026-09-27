import {Injectable} from '@angular/core';
import {AbstractResourceService, ConfigurationService, ResourceProvider} from '@netgrif/components-core';
import {Observable, of} from 'rxjs';
import {catchError, map, shareReplay} from 'rxjs/operators';

/**
 * Ktore procesy maju verejny (anonymny) formular.
 *
 * Engine to v referencii siete nevracia (vid `AnonymousNetsController`
 * v backende), takze sa pytame vlastneho endpointu.
 *
 * Adresa sa berie cez `AbstractResourceService`, nie z `HttpClient` a rucne
 * zlozenej URL. Dva dovody, oba zistene tym, ze prva verzia nefungovala:
 *
 *   1. `getServicesConfiguration().backend` v tejto konfiguracii NEEXISTUJE -
 *      adresa je v `providers.auth.address` (`etask-frontend-configuration.service.ts`
 *      ju stava ako `location.origin + '/api'`). Cítanie `.address` z undefined
 *      vyhodilo vynimku este pred odoslanim requestu, takze odznak sa nikdy
 *      neobjavil a v konzole nebolo nic, co by na to ukazalo.
 *   2. `ResourceProvider` prida autorizacnu hlavicku. Holy `HttpClient` ju
 *      neprida, takze by endpoint vratil 401 a `catchError` by to zahladil
 *      do prazdneho zoznamu - zase ticho.
 *
 * `shareReplay` je tu preto, ze panel vznika pre kazdy riadok zoznamu. Bez
 * neho by sa ten dopyt poslal tolkokrat, kolko je procesov.
 */
@Injectable({
  providedIn: 'root',
})
export class AnonymousNetsService extends AbstractResourceService {

  private _identifiers$: Observable<Set<string>>;

  constructor(provider: ResourceProvider, config: ConfigurationService) {
    super('petrinet', provider, config);
  }

  public identifiers$(): Observable<Set<string>> {
    if (!this._identifiers$) {
      this._identifiers$ = this._resourceProvider
        .get$('etask/petrinet/anonymous', this.SERVER_URL)
        .pipe(
          // Odpoved je holé pole reťazcov, ale `ResourceProvider` vracia
          // `Object` a pri prázdnom výsledku môže prísť HAL obal namiesto `[]`
          // (tá istá pasca ako `page.content` inde v tejto appke). Preto sa
          // typ overuje, nie predpokladá.
          map(response => new Set<string>(Array.isArray(response) ? response as Array<string> : [])),
          // Ked endpoint nie je (starsi backend), zoznam je prazdny a panel sa
          // chova ako predtym. Rozbit zoznam procesov kvoli odznaku by bolo horsie.
          catchError(() => of(new Set<string>())),
          shareReplay(1),
        );
    }
    return this._identifiers$;
  }
}
