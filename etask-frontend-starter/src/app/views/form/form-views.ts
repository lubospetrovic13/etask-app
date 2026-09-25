import {Case} from '@netgrif/components-core';
import config from '../../../assets/custom_views.json';

/**
 * What the dashboard and the "form" menu items are made of - one file,
 * `assets/custom_views.json`, so that an app changes them without code:
 *
 * `dashboard`       menu item identifiers shown as dashboard cards, in this order.
 *                   A card appears only if the person may open that view.
 * `dashboardNodes`  URI nodes whose menu items are looked up for those cards
 *                   (the root is always searched).
 * `forms`           menu items that do not open their list but a FORM: a new
 *                   case of `process` is created and its `transition` task is
 *                   shown on its own. After it is finished the person lands in
 *                   the `then` menu item. Leaving without finishing releases the
 *                   task (cancel); what that means is up to the net - sd_ticket
 *                   deletes the draft.
 *
 * Why a form is not a menu item type: the menu knows only `Case` and `Task`
 * views. A Task view narrowed to one transition shows a one-row LIST, not the
 * form, and for a case that does not exist yet there is nothing to narrow to.
 */
export interface FormView {
  process: string;
  transition: string;
  then?: string;
}

interface CustomViewsConfig {
  dashboard: Array<string>;
  dashboardNodes: Array<string>;
  forms: { [menuItemIdentifier: string]: FormView };
}

const CONFIG = config as CustomViewsConfig;

export const DASHBOARD_VIEWS: Array<string> = CONFIG.dashboard ?? [];
export const DASHBOARD_NODES: Array<string> = CONFIG.dashboardNodes ?? [];

export function formView(menuItemIdentifier: string | undefined): FormView | undefined {
  return menuItemIdentifier ? CONFIG.forms?.[menuItemIdentifier] : undefined;
}

/** Route of the form launcher - a child of `portal`, so the side menu stays. */
export function formRoute(menuItemIdentifier: string): string {
  return `/portal/form/${menuItemIdentifier}`;
}

export function menuItemIdentifier(filterCase: Case): string | undefined {
  return filterCase?.immediateData?.find(f => f.stringId === 'menu_item_identifier')?.value;
}
