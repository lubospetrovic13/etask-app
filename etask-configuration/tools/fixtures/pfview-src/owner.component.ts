// Vlastný komponent, ktorý má bypass.component.html obchádzať. Leží v tomto
// priečinku; bypass leží v inom, takže výnimka na obalenie sa neuplatní.
@Component({
  selector: 'app-etask-task-list',
  templateUrl: './owner.component.html',
})
export class OwnerComponent {}
