import {Injectable} from '@angular/core';
import {BehaviorSubject, Observable} from 'rxjs';

export type AppTheme = 'light' | 'dark';

/**
 * Light/dark mode switch.
 *
 * Angular Material 13 is pre-MDC, so its themes are static CSS and cannot be
 * recoloured at runtime through custom properties. Both themes are therefore
 * compiled into styles.css - light unscoped, dark under `.app-dark` - and
 * switching is a matter of toggling that one class. See
 * src/styles/themes/custom-themes.scss.
 *
 * The class goes on <html> rather than <body> so that the inline script in
 * index.html can set it before the first paint, which is what keeps the app from
 * flashing light on load. That script duplicates {@link STORAGE_KEY} and the
 * prefers-color-scheme fallback below - change both together.
 *
 * Persistence uses localStorage under the key `Theme`, mirroring how
 * @netgrif/components-core's LanguageService stores `Language`.
 */
@Injectable({providedIn: 'root'})
export class ThemeService {

  /** Also hardcoded in the pre-boot script in index.html. */
  public static readonly STORAGE_KEY = 'Theme';
  private static readonly DARK_CLASS = 'app-dark';

  private readonly _theme$: BehaviorSubject<AppTheme>;

  constructor() {
    this._theme$ = new BehaviorSubject<AppTheme>(this.resolveInitialTheme());
    this.applyToDocument(this._theme$.value);
  }

  public get theme$(): Observable<AppTheme> {
    return this._theme$.asObservable();
  }

  public get theme(): AppTheme {
    return this._theme$.value;
  }

  public isDark(): boolean {
    return this.theme === 'dark';
  }

  public setTheme(theme: AppTheme): void {
    if (theme === this._theme$.value) {
      return;
    }
    this.applyToDocument(theme);
    this.persist(theme);
    this._theme$.next(theme);
  }

  public toggle(): void {
    this.setTheme(this.isDark() ? 'light' : 'dark');
  }

  /**
   * A stored choice wins. With nothing stored the operating system preference
   * decides, so a first-time visitor on a dark desktop gets dark.
   */
  private resolveInitialTheme(): AppTheme {
    const stored = this.read();
    if (stored !== null) {
      return stored;
    }
    return this.prefersDark() ? 'dark' : 'light';
  }

  private applyToDocument(theme: AppTheme): void {
    const root = document.documentElement.classList;
    if (theme === 'dark') {
      root.add(ThemeService.DARK_CLASS);
    } else {
      root.remove(ThemeService.DARK_CLASS);
    }
  }

  private prefersDark(): boolean {
    return typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  // localStorage throws in private-browsing and sandboxed contexts, so every
  // access is guarded; the theme simply stops being remembered in that case.
  private read(): AppTheme | null {
    try {
      const value = localStorage.getItem(ThemeService.STORAGE_KEY);
      return value === 'light' || value === 'dark' ? value : null;
    } catch (e) {
      return null;
    }
  }

  private persist(theme: AppTheme): void {
    try {
      localStorage.setItem(ThemeService.STORAGE_KEY, theme);
    } catch (e) {
      // ignored - the switch still works for this session
    }
  }
}
