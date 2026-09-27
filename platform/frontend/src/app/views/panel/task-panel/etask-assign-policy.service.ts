import {Injectable} from '@angular/core';
import {
  AfterAction,
  AssignPolicyService,
  PermissionType,
} from '@netgrif/components-core';

/**
 * Opening a task takes it.
 *
 * Petriflow's `assignPolicy` conflates two different moments:
 *
 *   * `auto`   - the ENGINE assigns the task the moment it is created, to
 *                whoever created it. On a `bootstrapCase` that is
 *                `engine@netgrif.com`, so everyone else then gets
 *                "User that is not assigned tried to finish task". On a task
 *                created by one admin's action, it is that admin, and the rest
 *                of the team is locked out of a queue that is supposed to be
 *                shared.
 *   * `manual` - nobody is assigned on creation (good), but opening the panel
 *                only loads the data, so the user has to notice and press
 *                "Priradiť" before anything can be filled in.
 *
 * Neither is what a shared queue wants. What it wants is: nobody holds the task
 * until someone opens it, and opening it is enough.
 *
 * So the nets declare `manual` - which is about task CREATION and stays correct
 * - and this service decides the OPENING separately: an unassigned task the
 * user is allowed to take is taken. Anything else keeps the library's
 * behaviour, including a task somebody else already holds, which must stay
 * theirs until they release it.
 *
 * Why layer 3: the split does not exist in the model at all. `assignPolicy` is
 * a single value covering both moments, so there is no Petriflow primitive to
 * express "assign on open but not on create".
 */
@Injectable()
export class EtaskAssignPolicyService extends AssignPolicyService {

  public performAssignPolicy(taskOpened: boolean, afterAction: AfterAction = new AfterAction()): void {
    const task = this._safeTask;
    const unassigned = !task?.user;
    const mayAssign = !!task && this._permissionService.hasTaskPermission(task, PermissionType.ASSIGN);

    if (taskOpened && unassigned && mayAssign) {
      this.autoAssignPolicy(true, afterAction);
      return;
    }
    super.performAssignPolicy(taskOpened, afterAction);
  }
}
