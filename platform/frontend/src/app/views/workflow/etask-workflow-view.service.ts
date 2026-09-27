import {Inject, Injectable, Optional} from '@angular/core';
import {
  DialogService,
  LoggerService,
  NAE_WORKFLOW_SERVICE_CONFIRM_DELETE,
  NAE_WORKFLOW_SERVICE_FILTER,
  PetriNetRequestBody,
  PetriNetResourceService,
  SearchIndexResolverService,
  SnackBarService,
  WorkflowViewService,
} from '@netgrif/components-core';
import {TranslateService} from '@ngx-translate/core';

/**
 * Pole, podľa ktorého sa v zozname procesov hľadá.
 *
 * `title` tu zámerne NIE JE, hoci ho engine v tej istej vetve spomína: názov
 * procesu je v Mongu `I18nString` (`{defaultValue, translations}`), nie
 * reťazec, takže regex nad kľúčom `title` nenájde nikdy nič - HTTP 200,
 * prázdny zoznam, žiadna chyba. Namerané a nahlásené ako `ENGINE_ISSUES` E21.
 * Ponúknuť „Názov" by znamenalo pole, ktoré vždy mlčí.
 */
export type WorkflowSearchField = 'identifier' | 'initials';

export const WORKFLOW_SEARCH_FIELDS: Array<WorkflowSearchField> = ['identifier', 'initials'];

/**
 * `WorkflowViewService`, ktorý vie zúžiť zoznam procesov.
 *
 * Knižničná verzia berie filter raz, cez `NAE_WORKFLOW_SERVICE_FILTER`, a ďalej
 * ho nemení - v jej zdroji je na to aj TODO ("workflow sorting and searching").
 * Filter je pritom obyčajné telo požiadavky na `POST /api/petrinet/search`,
 * takže stačí ho prepísať a zavolať `reload()`, ktorý vynuluje stránkovanie.
 *
 * Čo engine s tým telom robí (`PetriNetService.search`), určuje, čo sa dá:
 *
 *   * `title`, `identifier` a `initials` porovnáva ako **regex, case-insensitive**
 *     - teda hľadanie podreťazca, presne to, čo od vyhľadávacieho poľa čakáme,
 *   * každý iný kľúč porovnáva na **presnú zhodu**,
 *   * a jednotlivé kritériá **spája cez AND**.
 *
 * To posledné je dôvod, prečo je tu prepínač poľa a nie jedno políčko, ktoré by
 * hľadalo "v názve ALEBO v identifikátore": OR sa cez toto API vyjadriť nedá
 * a dve kritériá naraz by zoznam nezúžili, ale vyprázdnili.
 */
@Injectable()
export class EtaskWorkflowViewService extends WorkflowViewService {

  constructor(petriNetResource: PetriNetResourceService,
              log: LoggerService,
              dialogService: DialogService,
              snackBarService: SnackBarService,
              translate: TranslateService,
              resolver: SearchIndexResolverService,
              @Optional() @Inject(NAE_WORKFLOW_SERVICE_FILTER) injectedBaseFilter: PetriNetRequestBody,
              @Optional() @Inject(NAE_WORKFLOW_SERVICE_CONFIRM_DELETE) confirmDelete: boolean) {
    super(petriNetResource, log, dialogService, snackBarService, translate, resolver,
      injectedBaseFilter, confirmDelete);
  }

  /**
   * Zúži zoznam na procesy, ktorých `field` obsahuje `term`. Prázdny `term`
   * filter zruší.
   */
  public applySearch(field: WorkflowSearchField, term: string): void {
    const trimmed = (term ?? '').trim();
    this._baseFilter = trimmed ? {[field]: EtaskWorkflowViewService.escapeRegex(trimmed)} : {};
    this.reload();
  }

  /**
   * Hodnota ide do Mongo regexu, nie do rovnosti.
   *
   * Bez tohto by „(" alebo „[" v hľadanom texte bol neplatný regex a engine by
   * vrátil chybu namiesto prázdneho výsledku, „." by hľadala hocijaký znak,
   * a vzor typu `(a+)+` by sa dal použiť na zahltenie servera.
   */
  private static escapeRegex(value: string): string {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }
}
