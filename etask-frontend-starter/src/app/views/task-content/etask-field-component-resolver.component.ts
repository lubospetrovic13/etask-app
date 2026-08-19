import {Component, Input, Type} from '@angular/core';
import {AbstractFieldComponentResolverComponent, TaskContentService} from '@netgrif/components-core';

/**
 * Application copy of @netgrif/components' FieldComponentResolverComponent.
 *
 * The library resolver dispatches field types through a hardcoded `ngSwitch` with
 * no registry or injection token, so replacing the component for a single field
 * type means owning the template. This copy differs from the library's in exactly
 * one place: BUTTON resolves to {@link EtaskButtonFieldComponent}.
 *
 * Maintenance note: field types and component variants added by a future
 * @netgrif/components release will not appear here until this template is
 * re-synced with node_modules/@netgrif/components/esm2020/lib/task-content/
 * field-component-resolver/.
 */
@Component({
  selector: 'app-etask-field-component-resolver',
  templateUrl: './etask-field-component-resolver.component.html',
  styleUrls: ['./etask-field-component-resolver.component.scss'],
})
export class EtaskFieldComponentResolverComponent extends AbstractFieldComponentResolverComponent {

  @Input() taskContentComponentClassReference: Type<any>;

  constructor(taskContentService: TaskContentService) {
    super(taskContentService);
  }
}
