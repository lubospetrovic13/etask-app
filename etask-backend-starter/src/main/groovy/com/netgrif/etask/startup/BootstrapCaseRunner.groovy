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
 * Idempotentne dvojmo: preskoci siet, ktorej case uz je, a sieti samotne
 * preskakuju polozky menu s uz existujucim identifikatorom.
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

        long existing = workflowService.searchAll(
                QCase.case$.processIdentifier.eq(identifier)).totalElements
        if (existing > 0) {
            log.debug("Bootstrap case pre ${identifier} uz existuje")
            return
        }

        IUser author = userService.getSystem()
        workflowService.createCase(net.stringId, net.title?.defaultValue ?: identifier,
                null, author.transformToLoggedUser())
        log.info("Bootstrap case pre ${identifier} vytvoreny")
    }
}
