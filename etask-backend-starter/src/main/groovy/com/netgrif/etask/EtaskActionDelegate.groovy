package com.netgrif.etask

import com.netgrif.application.engine.auth.domain.Authority
import com.netgrif.application.engine.auth.domain.IUser
import com.netgrif.application.engine.auth.domain.User
import com.netgrif.application.engine.auth.domain.UserState
import com.netgrif.application.engine.petrinet.domain.I18nString
import com.netgrif.application.engine.petrinet.domain.PetriNet
import com.netgrif.application.engine.petrinet.domain.UriContentType
import com.netgrif.application.engine.petrinet.domain.UriNode
import com.netgrif.application.engine.petrinet.domain.dataset.logic.action.ActionDelegate
import com.netgrif.application.engine.petrinet.domain.roles.ProcessRole
import com.netgrif.application.engine.workflow.domain.Case
import com.netgrif.etask.ai.AiCallService
import com.netgrif.etask.petrinet.domain.UriNodeData
import com.netgrif.etask.petrinet.domain.UriNodeDataRepository
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.stereotype.Component

@Component
class EtaskActionDelegate extends ActionDelegate {

    @Autowired
    private UriNodeDataRepository uriNodeDataRepository

    @Autowired
    private AiCallService aiCallService

    /**
     * create or update menu item of specified type
     * @param id
     * @param uri
     * @param type
     * @param query
     * @param icon
     * @param title
     * @param allowedNets
     * @param roles
     * @param bannedRoles
     * @return
     */
    Case createOrUpdateMenuItem(String id, String uri, String type, String query, String icon, String title, List<String> allowedNets, Map<String, String> roles = [:], Map<String, String> bannedRoles = [:]) {
        collectRolesForPreferenceItem(roles)
        Case menuItem = findMenuItem(id)
        if (!menuItem) {
            Case filter = createFilter(title, query, type, allowedNets, icon, "private", null)
            createUri(uri, UriContentType.DEFAULT)
            return createMenuItem(uri, id, filter, roles, bannedRoles)
        } else {
            Case filter = getFilterFromMenuItem(menuItem)
            changeFilter filter query { query }
            changeFilter filter allowedNets { allowedNets }
            changeFilter filter title { title }
            changeFilter filter icon { icon }
            changeMenuItem menuItem allowedRoles { roles }
            changeMenuItem menuItem bannedRoles { bannedRoles }
            changeMenuItem menuItem uri { uri }
            changeMenuItem menuItem filter { filter }
            return workflowService.findOne(menuItem.stringId)
        }
    }

    private Map<String, I18nString> collectRolesForPreferenceItem(Map<String, String> roles) {
        Map<String, PetriNet> temp = [:]
        return roles.collectEntries { entry ->
            if (!temp.containsKey(entry.value)) {
                temp.put(entry.value, petriNetService.getNewestVersionByIdentifier(entry.value))
            }
            PetriNet net = temp[entry.value]
            def foundEntry = net.roles.find { it.value.importId == entry.key }
            if (!foundEntry) {
                throw new IllegalArgumentException("No role $entry.key $net.identifier")
            }
            ProcessRole role = foundEntry.value
            return [(role.importId + ":" + net.identifier), ("$role.name ($net.title)" as String)]
        } as Map<String, I18nString>
    }

    /**
     * update menu item property
     * @param id
     * @param section to put this item in instead of default (currently only "settings" supported)
     * @return menu item
     */
    Case updateMenuItemSection(String id, String section = "settings") {
        Case menuItem = findMenuItem(id)
        if (!menuItem) {
            return null
        }
        return updateMenuItemSection(menuItem, section)
    }

    Case updateMenuItemSection(Case menuItem, String section = "settings") {
        menuItem.dataSet["custom_drawer_section"].value = section
        return workflowService.save(menuItem)
    }

    /**
     * set roles to uri node based on uriPaths
     * all roles of all processes from provided uriPaths will be able to see the node
     * @param uri
     * @param uriPaths
     */
    void setUriNodeDataRolesByPaths(String uri, List<String> uriPaths) {
        List<PetriNet> nets = uriPaths.collect {
            UriNode node = getUri(it) as UriNode
            if (!node) return null
            return petriNetService.findAllByUri(node.id)
        }.findAll { it != null }.flatten() as List<PetriNet>
        List<String> roleIds = nets.collect { it.roles.keySet() as List }.flatten() as List<String>
        setUriNodeDataRoles(uri, roleIds)
    }

    /**
     * set roles to uri node
     * @param uri
     * @param netRoles [net_identifier: [admin, system, ...]
     */
    void setUriNodeDataRoles(String uri, Map<String, List<String>> netRoles) {
        List<ProcessRole> roles = netRoles.collect { entry ->
            def net = petriNetService.getNewestVersionByIdentifier(entry.key)
            return net.roles.values().findAll { role -> entry.value.any { roleImportId -> roleImportId == role.importId } }
        }.flatten() as List<ProcessRole>
        setUriNodeDataRoles(uri, roles.stringId as List)
    }

    /**
     * set filters to uri node
     * @param uri
     * @param menu item identifiers
     */
    void setUriNodeDataFilters(String uri, List<String> menuItemIdentifiers) {
        UriNode uriNode = getUri(uri) as UriNode
        uriNodeDataRepository.findByUriNodeId(uriNode.getId()).ifPresentOrElse(data -> {
            data.setMenuItemIdentifiers(menuItemIdentifiers)
            uriNodeDataRepository.save(data)
        }, () -> {
            uriNodeDataRepository.save(new UriNodeData(uriNode.getId(), null, null, false, false, null, menuItemIdentifiers))
        })
    }

    /**
     * set roles to uri node for counters
     * @param uri
     * @param roleIds role stringIds
     */
    void setUriNodeDataRoles(String uri, List<String> roleIds) {
        UriNode uriNode = getUri(uri) as UriNode
        uriNodeDataRepository.findByUriNodeId(uriNode.getId()).ifPresentOrElse(data -> {
            data.setProcessRolesIds(roleIds as Set)
            uriNodeDataRepository.save(data)
        }, () -> {
            uriNodeDataRepository.save(new UriNodeData(uriNode.getId(), null, null, false, false, roleIds as Set, null))
        })
    }

    /**
     * set custom uri node data
     * @param uri
     * @param title
     * @param section - "settings" or "archive" if root, else null
     * @param icon
     * @param isSvgIcon
     * @param isHidden
     * @param roleIds - if null, no restriction
     */
    void setUriNodeData(String uri, String title, String section, String icon, boolean isSvgIcon = false, boolean isHidden = false, List<String> roleIds = null) {
        UriNode uriNode = getUri(uri) as UriNode
        uriNode.setName(title)
        uriService.save(uriNode)
        uriNodeDataRepository.findByUriNodeId(uriNode.getId()).ifPresentOrElse(data -> {
            data.setIcon(icon)
            data.setSection(section)
            data.setIconSvg(isSvgIcon)
            data.setProcessRolesIds(roleIds as Set)
            data.setHidden(isHidden)
            uriNodeDataRepository.save(data)
        }, () -> {
            uriNodeDataRepository.save(new UriNodeData(uriNode.getId(), section, icon, isSvgIcon, isHidden, roleIds as Set, null))
        })
    }

    boolean canUserAccessMenuItem(Case menuItem, IUser user) {
        Map<String, I18nString> allowedRoles = menuItem.getDataField("allowed_roles").options
        Map<String, I18nString> bannedRoles = menuItem.getDataField("banned_roles").options
        boolean hasAllowedRole = !allowedRoles || allowedRoles.keySet().any { encoded ->
            def importIdToNet = parseRoleFromMenuItemRoles(encoded)
            def net = petriNetService.getNewestVersionByIdentifier(importIdToNet.values()[0])
            return user.processRoles.any { it.importId == importIdToNet.keySet()[0] && it.netId == net.stringId }
        }
        boolean hasBannedRole = bannedRoles && bannedRoles.keySet().any { encoded ->
            def importIdToNet = parseRoleFromMenuItemRoles(encoded)
            def net = petriNetService.getNewestVersionByIdentifier(importIdToNet.values()[0])
            return user.processRoles.any { it.importId == importIdToNet.keySet()[0] && it.netId == net.stringId }
        }
        return hasAllowedRole && !hasBannedRole
    }

    protected static Map<String, String> parseRoleFromMenuItemRoles(String encoded) {
        def split = encoded.split(":")
        return [(split[0]): split[1]]
    }

    // ==================================================================
    // Opravnenia: prienik roly a prislusnosti
    //
    // Petriflow `roleRef` a `userRef` sa ZJEDNOCUJU, nie prienikaju. "Rola X
    // a zaroven v zozname Y" sa deklarativne napisat neda, a to je pri
    // multi-tenant aplikacii zakladna poziadavka: operator zakaznika A nema
    // vidiet tikety zakaznika B, aj keby rolu operatora mal.
    //
    // Obchadza sa to tak, ze sa prienik vypocita do datoveho pola typu
    // userList a transition potom pouzije `userRef` na to pole. Fungovalo to
    // uz predtym, ale kazdy pripad si to pisal sam - vratane extrakcie id
    // z UserListFieldValue, kde `u?._id` vyhodi MissingPropertyException
    // a zhodi celu akciu. Toto z toho robi jeden volatelny primitiv.
    // ==================================================================

    /**
     * Vytiahne id uzivatelov z hodnoty userList pola.
     *
     * Hodnota je UserListFieldValue s userValues, nie zoznam id. Pozor:
     * `u?._id` NEFUNGUJE - Groovy `?.` chrani pred null, nie pred chybajucou
     * property, takze na UserFieldValue vyhodi MissingPropertyException
     * a zhodi celu akciu v strede.
     *
     * @param value hodnota userList pola, alebo zoznam id
     * @return zoznam id, nikdy null
     */
    List<String> userIdsOf(Object value) {
        if (value == null) {
            return []
        }
        def users = value.hasProperty("userValues") ? value.userValues
                : (value instanceof List ? value : null)
        if (!users) {
            return []
        }
        return users.collect { u ->
            if (u == null) return null
            if (u instanceof String) return u
            if (u instanceof Map) return (u["_id"] ?: u["id"])
            return u.hasProperty("id") ? u.id : null
        }.findAll { it != null }.collect { it as String }
    }

    /**
     * Ci uzivatel drzi procesnu rolu s danym importId.
     *
     * @param netIdentifier ak nie je null, rola musi byt z tejto siete
     */
    boolean hasProcessRole(IUser user, String roleImportId, String netIdentifier = null) {
        if (user == null || !roleImportId) {
            return false
        }
        return (user.processRoles ?: []).any { ProcessRole role ->
            if (role.importId != roleImportId) {
                return false
            }
            if (!netIdentifier) {
                return true
            }
            // Rola sa razi per verziu siete, takze porovnavame netId roly
            // s KTOROUKOLVEK verziou daneho identifikatora, nie len najnovsou -
            // inak by po re-importe prestal prienik platit pre stare casy.
            return petriNetService.getByIdentifier(netIdentifier)
                    .any { it.stringId == role.netId }
        }
    }

    /**
     * Prienik: z uzivatelov v `source` vrati tych, ktori drzia rolu `roleImportId`.
     *
     * Presne to, co `roleRef` a `userRef` spolu vyjadrit nevedia. Rola zostava
     * autoritativna - ked niekoho niekto do zoznamu prida omylom a rolu nema,
     * pristup nedostane.
     *
     * @param source hodnota userList pola (napr. tym zakaznika)
     * @param roleImportId importId roly, napr. "agent"
     * @param netIdentifier volitelne zuzenie na konkretnu siet
     * @return zoznam id vhodny priamo pre `change <pole> value { ... }`
     */
    List<String> usersWithRole(Object source, String roleImportId, String netIdentifier = null) {
        return userIdsOf(source).findAll { String id ->
            hasProcessRole(findUserById(id), roleImportId, netIdentifier)
        }
    }

    def createNewUser(String name, String surname, String email, String password) {
        if (userService.findByEmail(email, true) != null) {
            throw new IllegalArgumentException("Používateľ s rovnakým emailom už bol vytvorený")
        }
        userService.saveNew(new User(
                name: name,
                surname: surname,
                email: email,
                password: password,
                state: UserState.ACTIVE,
                authorities: [] as Set<Authority>,
                processRoles: [] as Set<ProcessRole>))
    }

    // ==================================================================
    // AI konfigurácia
    //
    // Volá sa priamo z Petriflow akcie procesu ai_config, task "Test volania":
    //     def res = callAIToolByConfig(params)
    //
    // Samotná logika je v com.netgrif.etask.ai, delegát len presmeruje.
    // ==================================================================

    /**
     * Zavolá LLM podľa aktívnej AI konfigurácie a vráti čitateľný report.
     *
     * @param params caseId, modelKey, provider, origin, systemPrompt, userPrompt,
     *               temperature, maxTokens, inputMode, mailFrom, mailTo, mailSubject,
     *               mailBody, mailAttachments, mailJson, zipFieldId
     */
    String callAIToolByConfig(Map params) {
        return aiCallService.callByConfig(params)
    }

}
