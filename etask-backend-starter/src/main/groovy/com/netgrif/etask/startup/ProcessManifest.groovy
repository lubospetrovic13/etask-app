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

    /** Jeden case navzdy - pracujuci singleton. */
    static final String ONCE = "once"
    /** Jeden case na verziu siete - artefakt buildu, typicky menu appky. */
    static final String REBUILD_ON_NEW_VERSION = "version"
    /** Novy case, ked sa zmeni mnozina nasadenych sieti - katalogove zobrazenia. */
    static final String REBUILD_ON_PROCESS_CHANGE = "processes"

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
    /**
     * Siete, ktorych ma pri starte existovat bootstrap case.
     *
     * Polozka je bud identifikator, alebo objekt
     * `{"net": "...", "rebuildOnNewVersion": true}`. Vracia sa
     * `[identifikator: rebuildOnNewVersion]`.
     *
     * To rozlisenie nie je kozmetika - su to dva rozne druhy bootstrap casu:
     *
     *   * **Singleton, ktory pracuje** (pult, pocitadlo, konfiguracia). Ma
     *     existovat presne jeden, navzdy. Druhy case znamena druhu trvale
     *     otvorenu ulohu, teda dva riadky v zozname tam, kde ma byt jeden.
     *   * **Artefakt buildu** (siet stavajuca menu). Jeho jedina uloha je
     *     spustit akciu z udalosti `create`. Akcia bezi RAZ ZA CASE a case si
     *     drzi verziu siete, takze po re-importe menu siete sa nova verzia
     *     akcie nespusti, kym nevznikne novy case - zmena zobrazeni sa v
     *     nasadenej instancii neprejavi a nikde sa to neohlasi.
     *   * **Katalog** (`rebuildOnProcessChange`). Siet, ktorej vystup zavisi od
     *     TOHO, KTORE SIETE su nasadene - typicky zobrazenie "vsetky pripady",
     *     ktoreho `allowedNets` musi obsahovat kazdu appku, inak tlacidlo "+"
     *     nema co ponuknut a vrati "Ziadne povolene siete". Verzia takej siete
     *     sa pridanim appky nezmeni, takze `rebuildOnNewVersion` by ju nechal
     *     zastaranu; preto sa porovnava zoznam sieti, nie verzia.
     */
    Map<String, String> bootstrapCases() {
        return (manifest()["bootstrapCase"] ?: []).collectEntries { entry ->
            if (entry instanceof Map) {
                if (entry["rebuildOnProcessChange"]) {
                    return [(entry["net"] as String), REBUILD_ON_PROCESS_CHANGE]
                }
                if (entry["rebuildOnNewVersion"]) {
                    return [(entry["net"] as String), REBUILD_ON_NEW_VERSION]
                }
                return [(entry["net"] as String), ONCE]
            }
            return [(entry as String), ONCE]
        } as Map<String, String>
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
