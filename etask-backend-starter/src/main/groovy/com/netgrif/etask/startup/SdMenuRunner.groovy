package com.netgrif.etask.startup

import com.netgrif.application.engine.auth.domain.IUser
import com.netgrif.application.engine.auth.service.interfaces.IUserService
import com.netgrif.application.engine.petrinet.domain.PetriNet
import com.netgrif.application.engine.petrinet.service.interfaces.IPetriNetService
import com.netgrif.application.engine.startup.AbstractOrderedCommandLineRunner
import com.netgrif.application.engine.workflow.service.interfaces.IWorkflowService
import org.slf4j.Logger
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.stereotype.Component

/**
 * Gives the Service Desk menu node something to open.
 *
 * A URI node on its own carries no views: what the side menu lists under a node
 * are cases of the engine's {@code filter} and {@code preference_filter_item}
 * processes. Without them the Service Desk card existed but led to a blank
 * panel, and an operator or a specialist had no route to their own tickets at
 * all - the only case list in the app was General / All cases, which after the
 * permission work only an admin can see.
 *
 * The views themselves are built by the {@code service_desk/sd_menu} process,
 * because the engine's menu API ({@code createFilterInMenu}) lives on the
 * Petriflow action delegate and is not reachable from a runner. This runner
 * only makes sure one case of that process exists.
 *
 * Idempotent twice over: it skips when a case is already there, and the
 * process itself skips menu items whose identifier already exists.
 */
@Component
class SdMenuRunner extends AbstractOrderedCommandLineRunner {

    private static Logger log = LoggerFactory.getLogger(SdMenuRunner.class)

    private static final String MENU_NET_IDENTIFIER = "service_desk/sd_menu"

    @Autowired
    private IPetriNetService petriNetService

    @Autowired
    private IWorkflowService workflowService

    @Autowired
    private IUserService userService

    @Override
    void run(String... args) throws Exception {
        log.info("Calling sd menu runner")

        PetriNet net = petriNetService.getNewestVersionByIdentifier(MENU_NET_IDENTIFIER)
        if (net == null) {
            // NetRunner has not imported it (or the import failed). Nothing to
            // build views from, and guessing would only hide the real problem.
            log.warn("Process ${MENU_NET_IDENTIFIER} is not imported, Service Desk menu not built")
            return
        }

        long existing = workflowService.searchAll(
                com.netgrif.application.engine.workflow.domain.QCase.case$
                        .processIdentifier.eq(MENU_NET_IDENTIFIER)).totalElements
        if (existing > 0) {
            log.debug("Service Desk menu already built")
            return
        }

        IUser author = userService.getSystem()
        workflowService.createCase(net.stringId, "Menu Service Desku", null, author.transformToLoggedUser())
        log.info("Service Desk menu views created")
    }
}
