import {Component, Inject} from '@angular/core';
import {ActivatedRoute} from '@angular/router';
import {
  DataGroup,
  extractIconAndTitle,
  groupNavigationViewIdSegmentFactory,
  NAE_NAVIGATION_ITEM_TASK_DATA,
  NAE_VIEW_ID_SEGMENT,
  NewCaseCreationConfigurationData,
  TabContent,
  ViewIdService,
} from '@netgrif/components-core';
import {EtaskTabbedCaseViewComponent} from '../cases/etask-tabbed-case-view.component';
import {EtaskTabbedTaskViewComponent} from '../../task-view/etask-tabbed-task-view.component';


@Component({
  selector: 'app-etask-tab-view',
  templateUrl: './etask-tab-view.component.html',
  styleUrls: ['./etask-tab-view.component.scss'],
  providers: [
    ViewIdService,
    {provide: NAE_VIEW_ID_SEGMENT, useFactory: groupNavigationViewIdSegmentFactory, deps: [ActivatedRoute]},
  ],
})
export class EtaskTabViewComponent {


  tabs: Array<TabContent>;

  constructor(
    @Inject(NAE_NAVIGATION_ITEM_TASK_DATA) protected _navigationItemTaskData: Array<DataGroup>,
    @Inject(NAE_VIEW_ID_SEGMENT) protected _viewIdSegment: string) {
    const labelData = extractIconAndTitle(this._navigationItemTaskData);
    const createCaseButtonTitle: string = _navigationItemTaskData[0]?.fields
      .find(field => field.stringId === 'create_case_button_title')?.value;
    const createCaseButtonIcon: string = _navigationItemTaskData[0].fields
      .find(field => field.stringId === 'create_case_button_icon')?.value;
    const enableCaseTitle: boolean = _navigationItemTaskData[0].fields
      .find(field => field.stringId === 'enable_case_title')?.value;
    const caseRequireTitleInCreation: boolean = _navigationItemTaskData[0].fields
      .find(field => field.stringId === 'case_require_title_in_creation')?.value;
    const newCaseButtonConfig: NewCaseCreationConfigurationData = {
      enableCaseTitle: enableCaseTitle,
      isCaseTitleRequired: caseRequireTitleInCreation,
      newCaseButtonConfig: {
        createCaseButtonTitle,
        createCaseButtonIcon,
      },
    };

    const caseIndexContext = {
      menuItemViewId: this._viewIdSegment,
    };
    this.tabs = [
      {
        label: {text: labelData.name, icon: labelData.icon},
        canBeClosed: false,
        // `EtaskTabbedCaseViewComponent`, not the library's own `DefaultTabbedCaseViewComponent` -
        // see its own doc comment for why: the library's version hardcodes `_overflowService` to
        // `undefined` in its constructor, which silently breaks "table mode" for every case list
        // reached from the drawer.
        tabContentComponent: EtaskTabbedCaseViewComponent,
        injectedObject: {
          tabViewComponent: EtaskTabbedTaskViewComponent,
          tabViewOrder: 0,
          navigationItemTaskData: this._navigationItemTaskData,
          newCaseButtonConfiguration: newCaseButtonConfig,
          caseIndexContext: caseIndexContext,
        },
      },
    ];
  }

}

