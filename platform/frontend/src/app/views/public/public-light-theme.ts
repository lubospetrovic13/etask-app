/**
 * Verejny formular je VZDY svetly, bez ohladu na temu portalu.
 *
 * Preco: tmava tema je nastavenie cloveka, ktory v portali pracuje kazdy den.
 * Verejny formular je jedna obrazovka pre niekoho cudzieho, kto prisiel
 * z odkazu a viac ju neuvidi - a ten by tmavy formular precital ako chybu,
 * nie ako rozhodnutie. Navyse by temu zdedil po nahodnom nastaveni prehliadaca
 * niekoho ineho, co nedava zmysel ani ako default.
 *
 * Ako: `ThemeService` drzi tmavu temu ako triedu `app-dark` na <html> (svetla
 * je neoscopovana, viz `theme.service.ts`). Staci ju teda na cas zobrazenia
 * odobrat - a pri odchode vratit, inak by verejny formular ticho prepol temu
 * celeho portalu tomu, kto sa nan len pozrel.
 */
export class PublicLightTheme {

  private static readonly DARK_CLASS = 'app-dark';

  private wasDark = false;

  /** Zavolaj v `ngOnInit`. */
  public apply(): void {
    const root = document.documentElement;
    this.wasDark = root.classList.contains(PublicLightTheme.DARK_CLASS);
    if (this.wasDark) {
      root.classList.remove(PublicLightTheme.DARK_CLASS);
    }
  }

  /** Zavolaj v `ngOnDestroy`. */
  public restore(): void {
    if (this.wasDark) {
      document.documentElement.classList.add(PublicLightTheme.DARK_CLASS);
    }
  }
}
