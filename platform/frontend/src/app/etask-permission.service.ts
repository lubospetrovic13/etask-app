import {Injectable} from '@angular/core';
import {
  Case,
  PermissionService,
  PetriNetReferenceWithPermissions,
  UserComparatorService,
  UserService,
} from '@netgrif/components-core';

/**
 * `PermissionService`, ktorý vie o systémových rolách.
 *
 * Knižničná verzia pozerá výhradne na `net.permissions[procesná rola]`, takže
 * admin bez procesnej roly z nej vyjde ako niekto, kto nesmie nič - a to
 * NESEDÍ S ENGINOM. Overené proti bežiacemu enginu: účet s `ROLE_ADMIN` a bez
 * roly `manager` založil prípad `service_desk/sd_customer` (HTTP 200), bežný
 * používateľ na tom istom mieste dostal 403.
 *
 * Dôsledok toho rozdielu nebol "admin dostane 403" - to by sa aspoň ohlásilo -
 * ale že tlačidlo „+" adminovi ponúkne prázdny zoznam sietí, alebo sa
 * nezobrazí vôbec. Klient teda zakazoval to, čo server povoľuje, a vyzeralo to
 * ako pokazená appka.
 *
 * `ROLE_SYSTEMADMIN` je tu z toho istého dôvodu ako v `UriNodeVisibilityService`
 * na backende: je to účet, ktorý má vedieť opraviť zle nastavenú inštanciu,
 * takže nesmie byť zamknutý mimo obrazoviek, ktorými sa to robí.
 */
@Injectable({
  providedIn: 'root',
})
export class EtaskPermissionService extends PermissionService {

  private static readonly ADMIN_AUTHORITIES = ['ROLE_ADMIN', 'ROLE_SYSTEMADMIN'];

  constructor(userComparator: UserComparatorService, private _users: UserService) {
    super(userComparator, _users);
  }

  public hasNetPermission(action: string, net: PetriNetReferenceWithPermissions): boolean {
    if (this.isAdmin()) {
      return true;
    }
    return super.hasNetPermission(action, net);
  }

  /**
   * To isté pre prípad, a stojí za tým konkrétny prejav: po stlačení „+“ sa
   * nový prípad založil, ale appka doň neprelinkovala - zostala v zozname.
   *
   * `nc-create-case-button` emituje `caseCreatedEvent` (a tým otvorí tab
   * s novým prípadom) LEN keď `CaseViewService.viewEnabled(case)` vráti true,
   * a to je presne `hasCasePermission(case, VIEW)`. Knižničná verzia pozerá
   * výhradne na `case.permissions[procesná rola]` a `case.users`, takže admin
   * bez procesnej roly z nej vyjde ako niekto, kto prípad nesmie vidieť -
   * hoci ho práve založil a engine mu ho ukáže. Nič sa pritom neohlási:
   * prípad v zozname je, len sa neotvorí.
   *
   * Je to tá istá nezrovnalosť s enginom ako pri `hasNetPermission` vyššie
   * a rieši sa rovnako.
   */
  public hasCasePermission(aCase: Case | undefined, permission: string): boolean {
    if (this.isAdmin()) {
      return true;
    }
    return super.hasCasePermission(aCase, permission);
  }

  private isAdmin(): boolean {
    return EtaskPermissionService.ADMIN_AUTHORITIES.some(a => this._users.hasAuthority(a));
  }
}
