import {Injectable} from '@angular/core';
import {
  ActiveGroupService,
  CaseResourceService,
  LoggerService,
  UriNodeResource,
  UriService,
  UserService,
} from '@netgrif/components-core';
import {Observable, Subject} from 'rxjs';
import {filter, take} from 'rxjs/operators';
import {ETaskUriNodeResource, EtaskUriResourceService} from './etask-uri-resource.service';

@Injectable({
  providedIn: 'root',
})
export class EtaskUriService extends UriService {

  protected _counters: Map<string, number>;

  private _lastUserId: string;

  constructor(_logger: LoggerService,
              _resourceService: EtaskUriResourceService,
              _caseResourceService: CaseResourceService,
              _activeGroupService: ActiveGroupService,
              _users: UserService) {
    // TODO load page size from injection token
    super(_logger, _resourceService, _caseResourceService, _activeGroupService, 100);
    this._counters = new Map<string, number>();

    // Koreň sa načíta znova, keď sa zmení prihlásený človek.
    //
    // `UriService` volá `loadRoot()` v konštruktore, teda RAZ za beh
    // aplikácie - a služba je `providedIn: 'root'`, takže odhlásenie ju
    // nezhodí. Bez tohto zostane po prihlásení iného účtu v pamäti strom
    // PREDOŠLÉHO človeka: dashboard číta `root.children` a bočné menu visí
    // na `activeNode`, takže obe ukazujú cudzí obsah.
    //
    // Nevyzerá to ako zaseknutá appka, ale ako zle nastavené práva. Uzly
    // filtruje server podľa oprávnení, takže kto sa prihlási po niekom
    // s menej právami, vidí jeho prázdnejšie menu a naopak. Nič sa pritom
    // neohlási - zoznam sa načítal úspešne, len pre iný účet. Pomôže až
    // tvrdý refresh, ktorý zhodí celý stav služieb.
    //
    // `user$` je `ReplaySubject(1)`, takže prvou hodnotou je už prihlásený
    // človek. Tú treba preskočiť: koreň preň načítal konštruktor predka
    // a druhé načítanie by bolo len requestom navyše.
    _users.user$.subscribe(user => {
      const id = (user?.id ?? '') as string;
      if (id === this._lastUserId) {
        return;
      }
      const prvy = this._lastUserId === undefined;
      this._lastUserId = id;
      // Odhlásenie (prázdne id) necháme tak - appka ide na prihlásenie
      // a strom pre nikoho nemá zmysel stavať.
      if (prvy || !id) {
        return;
      }
      this._counters.clear();
      // `loadRoot()` je v knižnici deklarovaný ako `private`, hoci koreň je
      // presne to, čo podtrieda potrebuje znova načítať. `private` je len
      // kontrola prekladača, metóda na prototype je - preto pretyp, a nie
      // `any`: takto je v type napísané, čo sa volá, a preklep by prešiel
      // rovnako ako pri `any`.
      (this as unknown as { loadRoot(): void }).loadRoot();
      // Aktívny uzol sa prepína AŽ po načítaní, a na nový koreň, nikdy na
      // `undefined`. Zhodiť ho na `undefined` vyzerá lákavo (`loadRoot()`
      // nastaví koreň ako aktívny len keď žiadny nie je), ale odberatelia
      // `activeNode$` s prázdnou hodnotou nepočítajú a padne to na
      // `Cannot read properties of undefined (reading 'parentId')`. Výnimka
      // pritom zhodí celý tento blok, takže sa ani nenačíta koreň - a jediné,
      // čo z toho vidno, je že sa nič nezmenilo.
      //
      // `loadRoot()` zapne `rootLoaded$` synchrónne, takže odber až za ním
      // čaká na dokončenie, nie na aktuálnu hodnotu.
      this.rootLoaded$.pipe(filter(nacitava => !nacitava), take(1))
        .subscribe(() => this.reset());
    });
  }

  public getCountForNodes(nodes: Array<UriNodeResource>): Observable<boolean> {
    if (!nodes) {
      return;
    }
    const stream$ = new Subject<boolean>();
    const menuItemIdentifiersBody = {};
    const legacyQueriesBody = {};
    nodes.forEach(node => {
      const menuItemIdentifiers = (node as ETaskUriNodeResource)?.menuItemIdentifiers;
      if (menuItemIdentifiers) {
        menuItemIdentifiersBody[node.uriPath] = menuItemIdentifiers;
      } else {
        legacyQueriesBody[node.name] = node.id;
      }
    });
    (this._resourceService as EtaskUriResourceService).getNodesCount({
      menuItemIdentifiersQueries: menuItemIdentifiersBody,
      legacyQueries: legacyQueriesBody,
    }).subscribe(count => {
      if (count && count.counts) {
        Object.keys(count.counts).forEach((counter) => {
          this._counters.set(counter, count.counts[counter] ? count.counts[counter] : 0);
        });
        stream$.next(true);
      } else {
        stream$.next(false);
      }
      stream$.complete();
    }, error => {
      this._logger.error(error);
      stream$.next(false);
      stream$.complete();
    });
    return stream$.asObservable();
  }

  public getCachedNodeCount(name: string): number {
    return this._counters.has(name) ? this._counters.get(name) : 0;
  }
}
