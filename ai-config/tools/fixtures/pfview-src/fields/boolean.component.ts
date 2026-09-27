// Stand-in za app-etask-boolean-field. Bez neho by fixture nedokázal to, na čo
// je: `toggle` by vyzeral ako neznáme meno a preklep v `key` by sa overoval
// proti knižnici namiesto proti tomuto súboru. S ním prejde presne tá istá
// vetva pfview ako nad skutočným frontendom.
@Component({
  selector: 'app-etask-boolean-field',
  templateUrl: './boolean.component.html',
})
export class BooleanComponent {
  public variant = 'toggle';

  ngOnInit(): void {
    const properties = this.dataField?.component?.properties;
    if (properties?.variant) {
      this.variant = properties.variant;
    }
  }
}
