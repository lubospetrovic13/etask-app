package com.netgrif.etask.startup

import com.netgrif.application.engine.auth.domain.IUser
import com.netgrif.application.engine.auth.service.interfaces.IUserService
import com.netgrif.application.engine.petrinet.domain.PetriNet
import com.netgrif.application.engine.petrinet.service.interfaces.IPetriNetService
import com.netgrif.application.engine.workflow.domain.Case
import com.netgrif.application.engine.workflow.domain.QCase
import com.netgrif.application.engine.workflow.service.interfaces.IWorkflowService
import com.netgrif.application.engine.startup.AbstractOrderedCommandLineRunner
import org.slf4j.Logger
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.stereotype.Component

/**
 * Zaklada jeden case pre kazdu siet uvedenu v `bootstrapCase` v processes.json.
 *
 * Preco to vobec treba: uzol URI sam o sebe ziadne zobrazenia nenesie - to, co
 * bocne menu pod uzlom vypisuje, su casy procesov `filter`
 * a `preference_filter_item`. Bez nich existuje karta appky, ale vedie do
 * prazdneho panelu. Zobrazenia stavia sama siet, lebo menu API enginu
 * (`createFilterInMenu`) je na action delegate a z runnera sa zavolat neda.
 * Runner teda len zabezpeci, ze existuje case, z ktoreho sa akcia spusti.
 *
 * Idempotentne dvojmo: preskoci siet, ktorej case uz je, a siete samotne
 * preskakuju polozky menu s uz existujucim identifikatorom.
 *
 * Co znamena "uz je", zavisi od polozky manifestu - su tri rezimy:
 *
 *   * obycajny identifikator: jeden case NAVZDY. Pracujuci singleton (pult,
 *     pocitadlo), kde druhy case znamena druhu trvale otvorenu ulohu.
 *   * `rebuildOnNewVersion`: jeden case NA VERZIU siete. Siete stavajuce menu,
 *     ktorych akcia je v udalosti `create` a bez noveho casu by sa po
 *     re-importe nespustila.
 *   * `rebuildOnProcessChange`: novy case, ked sa zmeni MNOZINA NASADENYCH
 *     SIETI. Katalogove zobrazenia ("vsetky pripady"), ktorych obsah zavisi od
 *     toho, ktore appky su nasadene - a to sa deje bez zmeny ich vlastnej
 *     verzie.
 *
 * Zamerne to nevie meno konkretnej aplikacie: ked bol tento runner
 * `SdMenuRunner` s natvrdo zapisanym `service_desk/sd_menu`, znamenala nova
 * appka s menu zasah do Javy.
 */
@Component
class BootstrapCaseRunner extends AbstractOrderedCommandLineRunner {

    private static Logger log = LoggerFactory.getLogger(BootstrapCaseRunner.class)

    @Autowired
    private IPetriNetService petriNetService

    @Autowired
    private IWorkflowService workflowService

    @Autowired
    private IUserService userService

    @Autowired
    private ProcessManifest manifest

    /**
     * Pole, do ktoreho si katalogova siet zapisuje zoznam sieti, s ktorym
     * naposledy stavala zobrazenia. Musi sedet s id pola v tej sieti; ked ho
     * niekto premenuje, katalog sa bude prestavovat pri kazdom starte - co je
     * hlucne, ale nie nebezpecne.
     */
    private static final String APPLIED_PROCESSES_FIELD = "tiles_applied_processes"

    @Override
    void run(String... args) throws Exception {
        log.info("Calling bootstrap case runner")
        manifest.bootstrapCases().each { String identifier, String mode ->
            bootstrap(identifier, mode)
        }
    }

    private void bootstrap(String identifier, String mode) {
        PetriNet net = petriNetService.getNewestVersionByIdentifier(identifier)
        if (net == null) {
            // NetRunner ju nenaimportoval (alebo import zlyhal). Nie je z coho
            // case zalozit a hadanie by len zakrylo skutocny problem.
            log.warn("Siet ${identifier} nie je naimportovana, bootstrap case sa nezaklada")
            return
        }

        // Rezim rozhoduje, ci sa hlada case pre TUTO VERZIU alebo hocijaky.
        // Preco to nemoze byt jedno pravidlo pre vsetkych, je
        // v `ProcessManifest.bootstrapCases`.
        //
        // Historia: chvilu tu bolo `perVersion` pre vsetkych a hned to zhodilo
        // invariant zakladacej siete pouzivatelov - "presne jeden case" - lebo
        // tá je pult, nie artefakt buildu, a druhy case znamena druhu trvale
        // otvorenu ulohu, teda dva riadky v zozname tam, kde ma byt jeden.
        // Zachytil to `pucheck.py`, nie clovek.
        //
        // Stare casy sa zamerne nemazu ani v prestavovacich rezimoch. Mazanie casu
        // je nevratne a runner na starte nie je miesto, kde to robit; siete
        // stavajuce menu su idempotentne (polozku s existujucim identifikatorom
        // preskocia alebo prepisu), takze druhy case menu nepokazi - a jeho
        // nazov je zhrnutie buildu, takze zopar starych je citatelna historia.
        def query = QCase.case$.processIdentifier.eq(identifier)
        if (mode == ProcessManifest.REBUILD_ON_NEW_VERSION) {
            query = query.and(QCase.case$.petriNetObjectId.eq(net.getObjectId()))
        }
        def existing = workflowService.searchAll(query)
        if (existing.totalElements > 0 && !processSetChanged(mode, existing.content)) {
            log.debug("Bootstrap case pre ${identifier}" +
                    (mode == ProcessManifest.REBUILD_ON_NEW_VERSION ? " v${net.version}" : "") + " uz existuje")
            return
        }

        IUser author = userService.getSystem()
        workflowService.createCase(net.stringId, net.title?.defaultValue ?: identifier,
                null, author.transformToLoggedUser())
        log.info("Bootstrap case pre ${identifier} v${net.version} vytvoreny")
    }

    /**
     * Ci sa od posledneho casu zmenila mnozina nasadenych sieti.
     *
     * Toto je cely dovod, preco `rebuildOnNewVersion` na katalogove zobrazenia
     * nestaci: "vsetky pripady" musi mat v `allowedNets` kazdu nasadenu appku,
     * inak jeho "+" vrati "Ziadne povolene siete" - ale pridanim appky sa
     * verzia katalogovej siete NEZMENI, takze by sa jej akcia uz nikdy
     * nespustila a zoznam by ostal taky, aky bol pri prvom starte. Nikde by sa
     * to neohlasilo; prejavilo by sa to len tym, ze nova appka v "+" chyba.
     *
     * Porovnava sa proti tomu, co si akcia pri poslednom behu SAMA zapisala do
     * {@link #APPLIED_PROCESSES_FIELD} - nie proti verzii a nie proti poctu.
     * Ked to pole chyba (siet ho nema, alebo akcia spadla skor, nez ho
     * zapisala), berie sa to ako zmena: radsej case navyse nez katalog, ktory
     * ticho nesedi.
     */
    private boolean processSetChanged(String mode, List<Case> cases) {
        if (mode != ProcessManifest.REBUILD_ON_PROCESS_CHANGE) {
            return false
        }
        String current = currentProcessSet()
        String applied = cases
                .collect { it.dataSet?.get(APPLIED_PROCESSES_FIELD)?.value as String }
                .findAll { it != null }
                .max { it == current ? 1 : 0 }
        if (applied == current) {
            log.debug("Katalog ${cases.first().processIdentifier} sedi s nasadenymi sietami")
            return false
        }
        log.info("Mnozina nasadenych sieti sa zmenila, katalog sa prestavuje")
        return true
    }

    /** Identifikatory vsetkych nasadenych sieti, zoradene - porovnatelny retazec. */
    private String currentProcessSet() {
        return petriNetService.getAll()
                .collect { it.identifier as String }
                .unique()
                .sort()
                .join(",")
    }
}
