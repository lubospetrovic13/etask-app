package com.netgrif.etask.startup

import com.netgrif.application.engine.petrinet.domain.UriNode
import com.netgrif.application.engine.petrinet.service.interfaces.IUriService
import com.netgrif.application.engine.startup.AbstractOrderedCommandLineRunner
import com.netgrif.etask.petrinet.domain.UriNodeData
import com.netgrif.etask.petrinet.domain.UriNodeDataRepository
import org.slf4j.Logger
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.stereotype.Component

/**
 * Configures who sees which menu node, and with what icon.
 *
 * A UriNode itself carries no permissions - the engine's document has no roles
 * field and its URI endpoints take no user - so without this every
 * authenticated user saw the whole menu tree regardless of what they could
 * open. EtaskUriController now filters on UriNodeData; this runner is where
 * that data comes from, so the rules live in the repository rather than in
 * someone's mongo shell history.
 *
 * Runs on every boot and is idempotent: it only writes when something actually
 * differs, and it leaves nodes the manifest does not mention alone.
 *
 * The rules themselves live in `uriNodes` in etask-configuration/processes.json,
 * not here: an app that ships its own menu card would otherwise mean editing
 * Java to register it. requiredProcessRoles there are Petriflow import ids, not
 * role string ids - a role's string id is minted per net version, so a re-import
 * of the process would mint new ones and silently empty the list.
 */
@Component
class UriNodeDataRunner extends AbstractOrderedCommandLineRunner {

    private static Logger log = LoggerFactory.getLogger(UriNodeDataRunner.class)

    @Autowired
    private IUriService uriService

    @Autowired
    private UriNodeDataRepository repository

    @Autowired
    private ProcessManifest manifest

    @Override
    void run(String... args) throws Exception {
        log.info("Calling uri node data runner")
        migrateLegacyRoleIds()
        manifest.uriNodes().each { String uriPath, Map config ->
            UriNode node = uriService.findByUri(uriPath)
            if (node == null) {
                // Nodes appear when a process whose identifier carries the path
                // is imported. Nothing to configure until then.
                log.info("Uri node ${uriPath} does not exist yet, skipping")
                return
            }
            applyTo(node, uriPath, config)
        }
    }

    /**
     * Zahodi stare pole processRolesIds.
     *
     * Drzalo stringId roli, ktore sa razia per verziu siete, takze po kazdom
     * re-importe bolo neplatne - a jediny konzument bol klientsky filter nad
     * zoznamom, ktory server uz prefiltroval. Prevod na importId sa tu nedela
     * zamerne: zo stringId neexistujuceho (pretoceneho) roleu sa importId
     * spolahlivo odvodit neda, a hadat ho by znamenalo tichu zmenu opravneni.
     * Cielovy stav uzlov je deklarovany v NODES nizsie a runner ho aj tak nastavi.
     */
    private void migrateLegacyRoleIds() {
        def stale = repository.findAll().findAll { it.legacyProcessRolesIds }
        if (!stale) {
            return
        }
        stale.each { data ->
            log.info("Uri node data ${data.uriNodeId}: zahadzujem stare processRolesIds " +
                    "(${data.legacyProcessRolesIds.size()} stringId roli)")
            data.legacyProcessRolesIds = null
            repository.save(data)
        }
    }

    private void applyTo(UriNode node, String uriPath, Map config) {
        String icon = config.icon as String
        // Z JSON pridu zoznamy, v dokumente su mnoziny. Bez tohto prevodu by
        // porovnanie nizsie nikdy nesedelo a runner by zapisoval pri kazdom
        // starte - "idempotentny" len na papieri.
        Set<String> authorities = asStringSet(config.requiredAuthorities)
        Set<String> roles = asStringSet(config.requiredProcessRoles)

        UriNodeData data = repository.findByUriNodeId(node.getId()).orElse(null)
        boolean isNew = data == null
        if (isNew) {
            data = new UriNodeData()
            data.setUriNodeId(node.getId())
        }

        boolean changed = isNew
        if (data.getIcon() != icon) {
            data.setIcon(icon)
            changed = true
        }
        if (asStringSet(data.getRequiredAuthorities()) != authorities) {
            data.setRequiredAuthorities(authorities)
            changed = true
        }
        if (asStringSet(data.getRequiredProcessRoles()) != roles) {
            data.setRequiredProcessRoles(roles)
            changed = true
        }

        if (!changed) {
            log.debug("Uri node ${uriPath} already configured")
            return
        }
        repository.save(data)
        log.info("Uri node ${uriPath}: icon=${icon}, " +
                "authorities=${authorities}, roles=${roles}")
    }

    private static Set<String> asStringSet(Object value) {
        if (value == null) {
            return [] as Set<String>
        }
        return (value as Collection).collect { it as String } as Set<String>
    }
}
