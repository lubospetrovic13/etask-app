package com.netgrif.etask.startup

import com.netgrif.application.engine.petrinet.service.interfaces.IPetriNetService
import com.netgrif.application.engine.startup.AbstractOrderedCommandLineRunner
import com.netgrif.application.engine.startup.ImportHelper
import org.slf4j.Logger
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.core.io.ClassPathResource
import org.springframework.stereotype.Component

import java.util.regex.Pattern

/**
 * Importuje siete pri starte podla `import` v processes.json.
 *
 * Identifikator siete sa v manifeste NEUVADZA - cita sa z <id> v samotnom XML,
 * takze sa nemoze rozist so sietou.
 *
 * Poradie v manifeste zalezi: uzol URI vznikne az importom prvej siete, ktorej
 * identifikator tu cestu nesie, takze siet odkazujuca na uzol musi byt za nou.
 */
@Component
class NetRunner extends AbstractOrderedCommandLineRunner {

    private static Logger log = LoggerFactory.getLogger(NetRunner.class)

    private static final Pattern NET_ID = ~/(?s)<document\b.*?<id>\s*([^<\s][^<]*?)\s*<\/id>/

    @Autowired
    private IPetriNetService petriNetService

    @Autowired
    private ImportHelper helper

    @Autowired
    private ProcessManifest manifest

    @Override
    void run(String... args) throws Exception {
        log.info("Calling net runner")
        List<String> files = manifest.imports()
        if (files.isEmpty()) {
            log.warn("${ProcessManifest.PATH}: ziadne siete na import")
            return
        }
        files.each { String file -> importNet(file) }
    }

    /** Naimportuje siet, ak v databaze este nie je. */
    void importNet(String file, boolean reimport = false) {
        String identifier = identifierOf(file)
        if (identifier == null) {
            log.error("${file}: nepodarilo sa precitat <id> siete, preskakujem")
            return
        }
        if (!reimport && petriNetService.getNewestVersionByIdentifier(identifier)) {
            return
        }
        log.info("Importujem siet ${identifier} (${file})")
        helper.createNet(file)
    }

    /**
     * Identifikator z <id> v XML. Zamerne regexom a nie XML parserom: staci
     * prvy vyskyt a nechceme, aby sa runner zasekol na sieti, ktora ma
     * v CDATA nieco, co parser nema rad.
     */
    private String identifierOf(String file) {
        ClassPathResource resource = new ClassPathResource("petriNets/${file}")
        if (!resource.exists()) {
            log.error("petriNets/${file} nie je na classpath")
            return null
        }
        String xml = resource.inputStream.withCloseable { it.getText("UTF-8") }
        def matcher = NET_ID.matcher(xml)
        return matcher.find() ? matcher.group(1) : null
    }
}
