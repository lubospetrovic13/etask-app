package com.netgrif.etask.startup

import com.netgrif.application.engine.auth.domain.IUser
import com.netgrif.application.engine.auth.service.interfaces.IUserService
import com.netgrif.application.engine.petrinet.domain.PetriNet
import com.netgrif.application.engine.petrinet.service.interfaces.IPetriNetService
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
 * Co znamena "uz je", zavisi od polozky manifestu. `{"net": "...",
 * "rebuildOnNewVersion": true}` znamena jeden case NA VERZIU siete - to je pre
 * siete stavajuce menu, ktorych akcia je v udalosti `create` a bez noveho casu
 * by sa po re-importe nespustila. Obycajny identifikator znamena jeden case
 * navzdy - to je pre pracujuce singletony (pult, pocitadlo), kde druhy case
 * znamena druhu trvale otvorenu ulohu.
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

    @Override
    void run(String... args) throws Exception {
        log.info("Calling bootstrap case runner")
        manifest.bootstrapCases().each { String identifier, boolean perVersion ->
            bootstrap(identifier, perVersion)
        }
    }

    private void bootstrap(String identifier, boolean perVersion) {
        PetriNet net = petriNetService.getNewestVersionByIdentifier(identifier)
        if (net == null) {
            // NetRunner ju nenaimportoval (alebo import zlyhal). Nie je z coho
            // case zalozit a hadanie by len zakrylo skutocny problem.
            log.warn("Siet ${identifier} nie je naimportovana, bootstrap case sa nezaklada")
            return
        }

        // `perVersion` rozhoduje, ci sa hlada case pre TUTO VERZIU alebo
        // hocijaky. Preco to nemoze byt jedno pravidlo pre vsetkych, je
        // v `ProcessManifest.bootstrapCases`.
        //
        // Historia: chvilu tu bolo `perVersion` pre vsetkych a hned to zhodilo
        // invariant zakladacej siete pouzivatelov - "presne jeden case" - lebo
        // tá je pult, nie artefakt buildu, a druhy case znamena druhu trvale
        // otvorenu ulohu, teda dva riadky v zozname tam, kde ma byt jeden.
        // Zachytil to `pucheck.py`, nie clovek.
        //
        // Stare casy sa zamerne nemazu ani v `perVersion` rezime. Mazanie casu
        // je nevratne a runner na starte nie je miesto, kde to robit; siete
        // stavajuce menu su idempotentne (polozku s existujucim identifikatorom
        // preskocia alebo prepisu), takze druhy case menu nepokazi - a jeho
        // nazov je zhrnutie buildu, takze zopar starych je citatelna historia.
        def query = QCase.case$.processIdentifier.eq(identifier)
        if (perVersion) {
            query = query.and(QCase.case$.petriNetObjectId.eq(net.getObjectId()))
        }
        if (workflowService.searchAll(query).totalElements > 0) {
            log.debug("Bootstrap case pre ${identifier}" +
                    (perVersion ? " v${net.version}" : "") + " uz existuje")
            return
        }

        IUser author = userService.getSystem()
        workflowService.createCase(net.stringId, net.title?.defaultValue ?: identifier,
                null, author.transformToLoggedUser())
        log.info("Bootstrap case pre ${identifier} v${net.version} vytvoreny")
    }
}
