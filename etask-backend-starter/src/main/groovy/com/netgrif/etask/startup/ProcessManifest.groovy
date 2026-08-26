package com.netgrif.etask.startup

import groovy.json.JsonSlurper
import org.slf4j.Logger
import org.slf4j.LoggerFactory
import org.springframework.core.io.ClassPathResource
import org.springframework.stereotype.Component

/**
 * Cita etask-configuration/processes.json - jediny zoznam toho, co runtime robi
 * so sietami.
 *
 * Preco manifest a nie Java: pridanie aplikacie ma byt "hod XML do processes/
 * a dopis riadok". Kym boli zoznam sieti, bootstrap casy aj konfiguracia uzlov
 * URI zadrotovane v runneroch, znamenalo pridanie appky zasah do Javy - teda
 * presne to, comu sa tento stack snazi zabranit. Sablona, ktora na pridanie
 * aplikacie vyzaduje editovat framework, nie je sablona.
 *
 * Manifest sa cita raz pri prvom pouziti; runnery bezia pri starte, takze
 * opakovane citanie by len viackrat zalogovalo tu istu chybu.
 */
@Component
class ProcessManifest {

    private static Logger log = LoggerFactory.getLogger(ProcessManifest.class)

    static final String PATH = "petriNets/processes.json"

    private Map parsed = null

    /** Subory sieti na import, v poradi, v akom sa maju importovat. */
    List<String> imports() {
        return (manifest()["import"] ?: []).collect { it as String }
    }

    /**
     * Identifikatory sieti, ktorych ma pri starte existovat prave jeden case.
     *
     * Typicky siet, ktora stavia zobrazenia menu: uzol URI sam o sebe ziadne
     * zobrazenia nenesie a menu API enginu (`createFilterInMenu`) je na action
     * delegate, teda dosiahnutelne len z akcie - a akcia potrebuje case.
     */
    List<String> bootstrapCases() {
        return (manifest()["bootstrapCase"] ?: []).collect { it as String }
    }

    /** uriPath -> {icon, requiredAuthorities, requiredProcessRoles}. */
    Map<String, Map> uriNodes() {
        def nodes = manifest()["uriNodes"]
        if (!(nodes instanceof Map)) {
            return [:]
        }
        return nodes.collectEntries { key, value -> [(key as String), (value as Map)] } as Map<String, Map>
    }

    private synchronized Map manifest() {
        if (parsed != null) {
            return parsed
        }
        parsed = read()
        return parsed
    }

    private Map read() {
        ClassPathResource resource = new ClassPathResource(PATH)
        if (!resource.exists()) {
            log.warn("${PATH} nie je na classpath - ziadne siete sa nenaimportuju. " +
                    "Ocakava sa etask-configuration/processes.json (kopiruje ho pom.xml).")
            return [:]
        }
        try {
            def json = resource.inputStream.withCloseable { new JsonSlurper().parse(it, "UTF-8") }
            return (json instanceof Map) ? json : [:]
        } catch (Exception e) {
            log.error("${PATH} sa neda precitat: ${e.message}")
            return [:]
        }
    }
}
