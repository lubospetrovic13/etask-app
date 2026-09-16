import {Component} from '@angular/core';
import {Router} from '@angular/router';
import {UriNodeResource, UriService} from '@netgrif/components-core';
import {Observable} from 'rxjs';
import {map} from 'rxjs/operators';

export interface Breadcrumb {
  name: string;
  path: string;
}

/**
 * "Where am I": the drawer already lets you drill into a folder, but nothing on
 * screen named the folder you ended up in - the only place it showed up was as
 * the raw, untranslated `menu.folders` label in the drawer header. This reads
 * the same `UriService.activeNode` the drawer uses, so it always matches the tree.
 *
 * `splitNodePath` returns raw URI segments (`financie`, not `Financie`) - the
 * library keeps `UriNodeResource.name` untranslated, same reason `uriNodeTitle`
 * exists for the drawer tree. Each crumb goes through the same pipe.
 */
@Component({
  selector: 'app-e-task-breadcrumbs',
  templateUrl: './e-task-breadcrumbs.component.html',
  styleUrls: ['./e-task-breadcrumbs.component.scss'],
})
export class ETaskBreadcrumbsComponent {

  public crumbs$: Observable<Array<Breadcrumb>>;

  constructor(private _uri: UriService, private _router: Router) {
    this.crumbs$ = this._uri.activeNode$.pipe(
      map(node => this.buildCrumbs(node)),
    );
  }

  private buildCrumbs(node: UriNodeResource): Array<Breadcrumb> {
    const segments = this._uri.splitNodePath(node) ?? [];
    const acc: Array<string> = [];
    return segments.map(name => {
      acc.push(name);
      return {name, path: acc.join('/')};
    });
  }

  public goHome(): void {
    this._uri.reset();
    this._router.navigate(['dashboard']);
  }

  /**
   * Same fallback the dashboard uses for a folder it can't drop you straight
   * into a view for: point the tree at it and land on `portal`, so the drawer's
   * own folder/view list becomes the next thing to click - it does not guess
   * which of the folder's views you meant.
   */
  public goToNode(path: string): void {
    this._uri.getNodeByPath(path).subscribe(node => {
      this._uri.activeNode = node;
      this._router.navigate(['portal']);
    });
  }
}
