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
 * Idempotentne dvojmo: preskoci siet, ktorej case pre TUTO VERZIU uz je, a siete
 * samotne preskakuju polozky menu s uz existujucim identifikatorom. Per verzia,
 * nie per identifikator - dovod je v tele metody.
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
        manifest.bootstrapCases().each { String identifier -> bootstrap(identifier) }
    }

    private void bootstrap(String identifier) {
        PetriNet net = petriNetService.getNewestVersionByIdentifier(identifier)
        if (net == null) {
            // NetRunner ju nenaimportoval (alebo import zlyhal). Nie je z coho
            // case zalozit a hadanie by len zakrylo skutocny problem.
            log.warn("Siet ${identifier} nie je naimportovana, bootstrap case sa nezaklada")
            return
        }

        // Case sa hlada pre TUTO VERZIU siete, nie len pre identifikator.
        //
        // Predtym tu stalo `processIdentifier.eq(identifier)`, teda "existuje
        // aspon jeden case?", a to malo tichy dosledok: case si drzi verziu
        // siete, v ktorej vznikol, a akcia stavajuca menu je v udalosti
        // `create` - teda bezi presne raz za case. Po re-importe menu siete
        // teda runner nasiel stary case, preskocil - a NOVA verzia akcie sa
        // nespustila nikdy. Zmena zobrazeni v menu sa v nasadenej instancii
        // neprejavila a nikde sa to neohlasilo; vyzeralo to, ze re-import
        // nefunguje.
        //
        // Prejavilo sa to az pri prekladoch: siet zacala nazvy zobrazeni
        // posielat dvojjazycne, import presiel, a v menu bola dalej
        // jednojazycna verzia z casu, ktory vznikol pred tou zmenou.
        //
        // Stare casy sa zamerne nemazu. Su to artefakty buildu menu, ale
        // mazanie casu je nevratne a runner na starte nie je miesto, kde to
        // robit; siete samotne su idempotentne (polozku s existujucim
        // identifikatorom preskocia alebo ju prepisu), takze druhy case
        // menu nepokazi.
        long existing = workflowService.searchAll(
                QCase.case$.processIdentifier.eq(identifier)
                        .and(QCase.case$.petriNetObjectId.eq(net.getObjectId()))).totalElements
        if (existing > 0) {
            log.debug("Bootstrap case pre ${identifier} v${net.version} uz existuje")
            return
        }

        IUser author = userService.getSystem()
        workflowService.createCase(net.stringId, net.title?.defaultValue ?: identifier,
                null, author.transformToLoggedUser())
        log.info("Bootstrap case pre ${identifier} v${net.version} vytvoreny")
    }
}
