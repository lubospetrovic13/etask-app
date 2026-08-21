package com.netgrif.etask.startup


import com.netgrif.application.engine.auth.service.interfaces.IUserService
import com.netgrif.application.engine.petrinet.service.interfaces.IPetriNetService
import com.netgrif.application.engine.startup.AbstractOrderedCommandLineRunner
import com.netgrif.application.engine.workflow.service.interfaces.IWorkflowService
import org.slf4j.Logger
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component

/**
 * Kontrola bezpecnostnej pozicie pri starte.
 *
 * Tento repozitar je sablona - niekto si ho naklonuje a nasadi. Preto nesmie byt
 * mozne, aby bezal s defaultnymi pristupmi TICHO. Kazda z veci nizsie bola
 * v tomto repozitari realne pritomna:
 *
 *   - nae.admin.password mal default "password", compose ho neposielal, takze
 *     systemovy admin na verejnej adrese mal heslo "password";
 *   - styri testovacie ucty vratane ROLE_ADMIN mali default "test1234";
 *   - JWT kluc je gitignored, takze po ciastom checkoute engine nepodpise
 *     anonymnu session a verejne formulare vratia 401 - bez chybovej spravy,
 *     ktora by to spojila s klucom.
 *
 * Runner nic nemeni a nic nezhodi. Len to napise tak, aby sa to neprehliadlo.
 */
@Component
class EtaskRunner extends AbstractOrderedCommandLineRunner {

    private static Logger log = LoggerFactory.getLogger(EtaskRunner.class)

    private static final String DEFAULT_ADMIN_PASSWORD = "password"

    @Autowired
    private IWorkflowService workflowService

    @Autowired
    private IUserService userService

    @Autowired
    private IPetriNetService petriNetService

    @Value('${nae.admin.password:}')
    private String adminPassword

    @Value('${nae.security.jwt.private-key:}')
    private String jwtKey

    @Value('${etask.users.testadmin.password:}')
    private String testPassword

    @Override
    void run(String... args) throws Exception {
        log.info("Calling EtaskRunner runner")
        List<String> problems = []

        if (adminPassword == DEFAULT_ADMIN_PASSWORD) {
            problems << "nae.admin.password je stale '${DEFAULT_ADMIN_PASSWORD}' - " +
                    "nastav premennu ADMIN_PASSWORD"
        }
        if (testPassword) {
            problems << "testovacie ucty (admin@test.local a spol.) su VYTVORENE, " +
                    "jeden z nich ma ROLE_ADMIN - nenechavaj ETASK_TEST_PASSWORD " +
                    "nastavene na verejnej instancii"
        }
        if (!jwtKeyPresent()) {
            problems << "JWT podpisovy kluc sa neda precitat (${jwtKey ?: 'nenastaveny'}) - " +
                    "anonymne prihlasenie zlyha a VEREJNE FORMULARE budu vracat 401. " +
                    "Vygeneruj ho: etask-configuration/tools/bootstrap.sh"
        }

        if (problems.isEmpty()) {
            log.info("Bezpecnostna kontrola: v poriadku")
            return
        }
        log.warn("=".multiply(72))
        log.warn("BEZPECNOSTNA KONTROLA - {} zjisteni:", problems.size())
        problems.eachWithIndex { String problem, int i ->
            log.warn("  {}. {}", i + 1, problem)
        }
        log.warn("=".multiply(72))
    }

    private boolean jwtKeyPresent() {
        if (!jwtKey) {
            return false
        }
        String path = jwtKey.startsWith("file:") ? jwtKey.substring("file:".length()) : jwtKey
        if (path.startsWith("classpath:")) {
            // Kluc zabaleny v jare - overit sa da len tym, ze resource existuje.
            String resource = path.substring("classpath:".length())
            return getClass().getClassLoader().getResource(resource) != null
        }
        File file = new File(path)
        return file.isFile() && file.length() > 0
    }
}
