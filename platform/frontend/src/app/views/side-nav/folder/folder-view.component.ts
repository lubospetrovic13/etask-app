import {Component, OnDestroy} from '@angular/core';
import {Router} from '@angular/router';
import {
  FILTER_IDENTIFIERS,
  LoggerService,
  NAE_VIEW_ID_SEGMENT,
  UriNodeResource,
  UriService,
  ViewIdService,
  ViewNavigationItem,
} from '@netgrif/components-core';
import {forkJoin, of, Subscription} from 'rxjs';
import {catchError, switchMap, tap} from 'rxjs/operators';
import icons from '../../../../assets/uriNodeIcons.json';
import {ETaskUriNodeResource} from '../../dashboard/service/etask-uri-resource.service';
import {ViewNavigationResolverService} from '../view-navigation-resolver.service';

/**
 * Čo vidí človek, ktorý klikol na PRIEČINOK - nie na zobrazenie.
 *
 * Predtým klik na priečinok otvoril prvé zobrazenie, ktoré sa v ňom (alebo
 * v jeho podpriečinkoch) našlo. Bolo to tak preto, že `portal` sám osebe je
 * prázdna obrazovka, takže priečinok bez tohto komponentu vyzeral ako
 * rozbitá karta - lenže dôsledok bol horší než choroba: klik na „Financie"
 * hodil človeka do konkrétneho zobrazenia kdesi o dve úrovne nižšie a nedalo
 * sa z toho prečítať, kde vlastne je.
 *
 * Tu sa teda neháda, ktoré zobrazenie mal na mysli: ukáže sa obsah priečinka
 * a vyberie si sám. Žiadne zobrazenie nie je otvorené.
 *
 * Zdroj pravdy o tom, KTORÝ priečinok to je, je `UriService.activeNode` -
 * ten istý, ktorý hýbe stromom v ľavom paneli aj breadcrumbami. Vďaka tomu
 * sa obsah prekreslí aj vtedy, keď človek klikne na priečinok v strome
 * a teda sa nikam nenaroutuje.
 */
@Component({
  selector: 'app-folder-view',
  templateUrl: './folder-view.component.html',
  styleUrls: ['./folder-view.component.scss'],
  providers: [
    {
      provide: NAE_VIEW_ID_SEGMENT,
      useValue: 'folder',
    },
    ViewIdService,
  ],
})
export class FolderViewComponent implements OnDestroy {

  public node: UriNodeResource;
  public folders: Array<ETaskUriNodeResource> = [];
  public views: Array<ViewNavigationItem> = [];
  public loading = true;

  private _sub: Subscription;

  constructor(private _uri: UriService,
              private _router: Router,
              private _resolver: ViewNavigationResolverService,
              private _log: LoggerService) {
    // `switchMap`, nie subscribe s dvoma nezávislými requestami vnútri.
    //
    // Pôvodná verzia strieľala pri každom uzle dva samostatné requesty a
    // nerušila tie predošlé. Keď človek preklikal Financie → Faktúry, odpoveď
    // pre Financie dorazila neskôr a prepísala zoznam priečinkov - výsledok
    // bol priečinok „Faktúry", ktorý ukazoval súrodencov Faktúr, teda
    // priečinky, čo v ňom nie sú. `switchMap` request predošlého uzla zruší.
    //
    // `forkJoin` drží obe polovice pokope, takže sa nestane, že priečinky už
    // patria novému uzlu a zobrazenia ešte starému.
    this._sub = this._uri.activeNode$.pipe(
      tap(node => {
        this.node = node;
        this.loading = true;
      }),
      switchMap(node => !node
        ? of({folders: [] as Array<unknown>, cases: null})
        : forkJoin({
          folders: this._uri.getChildNodes(node).pipe(catchError(error => {
            this._log.error('Nepodarilo sa načítať podpriečinky', error);
            return of([]);
          })),
          cases: this._uri.getCasesOfNode(node, FILTER_IDENTIFIERS).pipe(catchError(error => {
            this._log.error('Nepodarilo sa načítať zobrazenia priečinka', error);
            return of(null);
          })),
        })),
    ).subscribe(({folders, cases}) => {
      // `Array.isArray`, nie `?? []`. Na priečinku BEZ podpriečinkov nevráti
      // `getChildNodes` prázdne pole, ale surový HAL objekt - knižnica sa
      // proti tomu sama chráni (`capitalizeNames` má `if (!(nodes instanceof
      // Array)) return`), takže to nie je výnimka, ale bežný stav.
      //
      // `?? []` ho nechytí (objekt je truthy) a `.filter` padne na
      // "filter is not a function". Chyba zhodí celý stream, takže spinner
      // sa točí navždy a v UI to vyzerá ako pomalý server.
      this.folders = (Array.isArray(folders) ? folders as Array<ETaskUriNodeResource> : [])
        .filter(child => !child.hidden && !child.section)
        .sort((a, b) => (a.name ?? '').localeCompare(b.name ?? ''));
      this.views = this._resolver.resolveAll((cases as { content?: unknown })?.content);
      this.loading = false;
    }, error => {
      // Bez tejto vetvy zhodí akákoľvek výnimka celý stream a spinner sa točí
      // navždy - obrazovka potom vyzerá ako pomalý server, nie ako chyba.
      this._log.error('Obsah priečinka sa nepodarilo zobraziť', error);
      this.loading = false;
    });
  }

  public get title(): string {
    return this.node?.name ?? '';
  }

  public isEmpty(): boolean {
    return !this.loading && !this.folders.length && !this.views.length;
  }

  public folderIcon(node: ETaskUriNodeResource): string {
    return icons[node?.name] ?? 'folder';
  }

  public viewIcon(view: ViewNavigationItem): string {
    return this._resolver.icon(view);
  }

  public viewTitle(view: ViewNavigationItem): string {
    return this._resolver.title(view);
  }

  public openFolder(node: UriNodeResource): void {
    // Len prepnutie uzla - routa zostáva tá istá, lebo tento komponent je
    // naviazaný na `activeNode$` a prekreslí sa sám.
    this._uri.activeNode = node;
  }

  public openView(view: ViewNavigationItem): void {
    this._router.navigate([view.routing.path]);
  }

  ngOnDestroy(): void {
    this._sub?.unsubscribe();
  }
}
