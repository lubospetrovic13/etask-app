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
 * differs, and it leaves nodes it does not know about alone.
 */
@Component
class UriNodeDataRunner extends AbstractOrderedCommandLineRunner {

    private static Logger log = LoggerFactory.getLogger(UriNodeDataRunner.class)

    @Autowired
    private IUriService uriService

    @Autowired
    private UriNodeDataRepository repository

    /**
     * uriPath -> configuration.
     *
     * requiredProcessRoles holds Petriflow import ids, not role string ids: a
     * role's string id is minted per net version, so a re-import of the process
     * would mint new ones and silently empty the list.
     */
    private static final Map<String, Map> NODES = [
            "general"     : [
                    icon                : "widgets",
                    requiredAuthorities : ["ROLE_ADMIN"] as Set,
                    requiredProcessRoles: [] as Set,
            ],
            "service_desk": [
                    icon                : "support_agent",
                    requiredAuthorities : [] as Set,
                    requiredProcessRoles: ["agent", "specialist", "manager"] as Set,
            ],
    ]

    @Override
    void run(String... args) throws Exception {
        log.info("Calling uri node data runner")
        migrateLegacyRoleIds()
        NODES.each { String uriPath, Map config ->
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
        UriNodeData data = repository.findByUriNodeId(node.getId()).orElse(null)
        boolean isNew = data == null
        if (isNew) {
            data = new UriNodeData()
            data.setUriNodeId(node.getId())
        }

        boolean changed = isNew
        if (data.getIcon() != config.icon) {
            data.setIcon(config.icon as String)
            changed = true
        }
        if (data.getRequiredAuthorities() != config.requiredAuthorities) {
            data.setRequiredAuthorities(config.requiredAuthorities as Set<String>)
            changed = true
        }
        if (data.getRequiredProcessRoles() != config.requiredProcessRoles) {
            data.setRequiredProcessRoles(config.requiredProcessRoles as Set<String>)
            changed = true
        }

        if (!changed) {
            log.debug("Uri node ${uriPath} already configured")
            return
        }
        repository.save(data)
        log.info("Uri node ${uriPath}: icon=${config.icon}, " +
                "authorities=${config.requiredAuthorities}, roles=${config.requiredProcessRoles}")
    }
}
