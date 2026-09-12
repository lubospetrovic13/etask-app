package com.netgrif.etask

import com.netgrif.application.engine.auth.domain.Authority
import com.netgrif.application.engine.auth.domain.IUser
import com.netgrif.application.engine.auth.domain.User
import com.netgrif.application.engine.auth.domain.UserState
import com.netgrif.application.engine.auth.service.interfaces.IAuthorityService
import com.netgrif.application.engine.petrinet.domain.I18nString
import com.netgrif.application.engine.petrinet.domain.PetriNet
import com.netgrif.application.engine.petrinet.domain.UriContentType
import com.netgrif.application.engine.petrinet.domain.UriNode
import com.netgrif.application.engine.petrinet.domain.dataset.logic.action.ActionDelegate
import com.netgrif.application.engine.petrinet.domain.roles.ProcessRole
import com.netgrif.application.engine.petrinet.domain.version.Version
import com.netgrif.application.engine.workflow.domain.Case
import com.netgrif.etask.ai.AiCallService
import com.netgrif.etask.doc.InvoiceReaderService
import com.netgrif.etask.mail.NotifyService
import com.netgrif.etask.petrinet.domain.UriNodeData
import com.netgrif.etask.petrinet.domain.UriNodeDataRepository
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.stereotype.Component

import java.nio.charset.StandardCharsets

@Component
class EtaskActionDelegate extends ActionDelegate {

    @Autowired
    private UriNodeDataRepository uriNodeDataRepository

    @Autowired
    private AiCallService aiCallService

    @Autowired
    private IAuthorityService authorityService

    @Autowired
    private InvoiceReaderService invoiceReaderService

    @Autowired
    private NotifyService notifyService

    // Id poli na `preference_filter_item` a prechod na `filter`, kde sa data
    // zapisuju. V engine su to `private static final` na `ActionDelegate`, takze
    // z podtriedy sa na ne za behu nedostaneme (rovnaky dovod ako pri metodach
    // nizsie) - preto tu stoja ako literaly. Ked ich engine premenuje, prasknu
    // testy `pfcheck`, nie kompilacia; preto su na jednom mieste a s tymto
    // komentarom.
    private static final String MENU_FIELD_ALLOWED_ROLES = "allowed_roles"
    private static final String MENU_FIELD_BANNED_ROLES = "banned_roles"
    private static final String MENU_FIELD_NEW_FILTER_ID = "new_filter_id"
    private static final String FILTER_DETAILS_TRANSITION = "t2"
    private static final String FILTER_FIELD = "filter"
    private static final String FILTER_I18N_TITLE_FIELD = "i18n_filter_name"

    /**
     * Zaloz alebo uprav polozku menu.
     *
     * `title` prijme `String` aj `I18nString` - su na to dve pretazenia (viz
     * komentar pri tom druhom), takze polozka menu sa da mat dvojjazycne:
     * `i18n("Vsetky pripady", ["en": "All cases"])` je metoda delegata
     * a `createFilter` uz `I18nString` zvlada sama. Bez toho by nazov karty
     * v lavom menu zostal jednojazycny aj v appke, ktora ma cely zvysok
     * prelozeny - a to je prvy riadok, ktory clovek v portali vidi.
     *
     * UPDATE CESTA NEIDE CEZ `changeFilter` ANI `changeMenuItem`. Obe volaju
     * metody, ktore su na `ActionDelegate` **private**:
     *
     *     private void updateFilter(Case, Map)                 // ActionDelegate:1884
     *     private void updateMenuItemRoles(Case, Closure, String)  // :1648
     *
     * Uzavery v `changeFilter`/`changeMenuItem` ich volaju dynamicky, takze
     * volanie sa riesi cez metaclass instancie - a tou je nasa podtrieda, ktora
     * private metody predka nevystavuje. Vysledok:
     *
     *     groovy.lang.MissingMethodException: No signature of method:
     *     com.netgrif.etask.EtaskActionDelegate.updateFilter() is applicable
     *     for argument types: (Case, LinkedHashMap)
     *
     * Chyba je v engine (ENGINE_ISSUES E6), ale dotyka sa kazdej appky, ktora si
     * delegata rozsiruje - teda kazdej, lebo rozsirenie delegata je dokumentovany
     * sposob, ako pridat vlastne akcie. Dovtedy sa to obchadza tak, ze sa tie
     * dva zapisy urobia priamo; oba su len `setData` alebo zapis do `dataSet`
     * a `save`, teda presne to, co robia tie private metody.
     *
     * Priznak, ked to niekto vrati na `changeFilter`: prvy import prejde
     * (polozka neexistuje, ide sa create cestou), druhy vrati HTTP 500. V logu
     * je `MissingMethodException`, v odpovedi hole `{"status":500}`.
     */
    Case createOrUpdateMenuItem(String id, String uri, String type, String query, String icon, String title, List<String> allowedNets, Map<String, String> roles = [:], Map<String, String> bannedRoles = [:]) {
        return doCreateOrUpdateMenuItem(id, uri, type, query, icon, title, allowedNets, roles, bannedRoles)
    }

    /**
     * To iste s dvojjazycnym nazvom polozky menu.
     *
     * Musi to byt SAMOSTATNE preťaženie s typom `I18nString`, nie jedna metoda
     * s `def title`. Groovy vybera podla najspecifickejsieho parametra a engine
     * ma vlastne `createOrUpdateMenuItem(..., String title, ...)`; nasa metoda
     * s `def title` je vseobecnejsia, takze pri volani so `String`-om by vyhrala
     * TA ENGINOVA a nase prekrytie by prestalo platit - bez chyby pri kompilacii
     * aj pri importe. Prejavi sa to az druhym importom siete, ktora polozku uz
     * ma: spadne na `MissingMethodException: updateFilter()`, teda presne na tu
     * chybu, ktoru mala nasa metoda obchadzat.
     */
    Case createOrUpdateMenuItem(String id, String uri, String type, String query, String icon, I18nString title, List<String> allowedNets, Map<String, String> roles = [:], Map<String, String> bannedRoles = [:]) {
        return doCreateOrUpdateMenuItem(id, uri, type, query, icon, title, allowedNets, roles, bannedRoles)
    }

    private Case doCreateOrUpdateMenuItem(String id, String uri, String type, String query, String icon, def title, List<String> allowedNets, Map<String, String> roles, Map<String, String> bannedRoles) {
        collectRolesForPreferenceItem(roles)
        Case menuItem = findMenuItem(id)
        if (!menuItem) {
            Case filter = createFilter(title, query, type, allowedNets, icon, "private", null)
            createUri(uri, UriContentType.DEFAULT)
            return createMenuItem(uri, id, filter, roles, bannedRoles)
        }

        Case filter = getFilterFromMenuItem(menuItem)

        // Dopyt a allowedNets naraz. Engine ich ma v dvoch uzaveroch, pricom ta
        // pre `query` zapisuje `"type": "enumeration_map"` a allowedNets
        // zahodi - preto sa tu pise tvar, ktory pouziva `createFilter`.
        setData(FILTER_DETAILS_TRANSITION, filter, [
                (FILTER_FIELD): [
                        "type"       : "filter",
                        "value"      : query,
                        "allowedNets": allowedNets,
                ],
        ])

        filter = workflowService.findOne(filter.stringId)
        filter.setTitle(title as String)
        filter.dataSet[FILTER_I18N_TITLE_FIELD].value =
                (title instanceof I18nString) ? title : new I18nString(title as String)
        filter.setIcon(icon)
        filter = workflowService.save(filter)

        setMenuItemRoles(menuItem, MENU_FIELD_ALLOWED_ROLES, roles)
        setMenuItemRoles(menuItem, MENU_FIELD_BANNED_ROLES, bannedRoles)

        menuItem = workflowService.findOne(menuItem.stringId)
        menuItem.setUriNodeId(uriService.findByUri(uri).id)
        workflowService.save(menuItem)
        setData("change_filter", menuItem, [
                (MENU_FIELD_NEW_FILTER_ID): ["type": "text", "value": filter.stringId],
        ])
        return workflowService.findOne(menuItem.stringId)
    }

    /**
     * Prepoji existujucu polozku menu na URI uzol danej cesty.
     *
     * Preco to je samostatny primitiv: **URI uzly zije Elasticsearch, polozky
     * menu Mongo.** Kazdy uzol ma teda id z ineho ulozista, a ked sa ES index
     * zahodi alebo vymeni (`up.sh --fresh`, prenos na iny stroj, cisty volume
     * v Dockeri), uzly sa vytvoria ZNOVA a s NOVYMI id - kym polozky menu
     * v Mongu drzia stare.
     *
     * Prejavi sa to tak, ze v bocnom paneli je priecinok, ale je PRAZDNY:
     * frontend hlada polozky dopytom `uriNodeId: <id uzla>`
     * (`UriService.getCasesOfNode`), a ten na stare id nesedi. Ziadna chyba,
     * ziadny log - len appka bez zobrazeni.
     *
     * `createOrUpdateMenuItem` uriNodeId dorovnava, ale siete stavajuce menu ho
     * pri NEZMENENEJ polozke vobec nezavolaju (kontroluju dopyt, allowedNets
     * a nazov - a tie sa nezmenili). Preto to musi ist zvlast a lacno.
     *
     * @return true, ked sa uzol naozaj zmenil
     */
    boolean pripoj_do_uzla(Object item, String uri) {
        if (item == null || !uri) {
            return false
        }
        String itemId = (item instanceof Case) ? (item.stringId as String) : (item as String)
        Case menuItem = workflowService.findOne(itemId)
        if (menuItem == null) {
            return false
        }
        UriNode node = uriService.findByUri(uri)
        if (node == null) {
            return false
        }
        String want = node.id as String
        boolean changed = ((menuItem.uriNodeId ?: "") as String) != want
        if (changed) {
            menuItem.setUriNodeId(want)
            menuItem = workflowService.save(menuItem)
        }
        // A to iste v datovom poli. Frontend cita `uriNodeId` z pripadu, ale
        // `parentId` drzi to iste a rozchod dvoch zdrojov tej istej pravdy sa
        // vzdy niekomu vrati.
        // Zapis rovno do dataSetu a save - `setData` by potrebovalo prechod,
        // ktory `parentId` naozaj obsahuje, a to nie je nas kontrakt (rovnaky
        // dovod ako pri `setMenuItemRoles` nizsie).
        def pole = menuItem.dataSet["parentId"]
        if (pole != null && ((pole.value ?: "") as String) != want) {
            pole.value = want
            workflowService.save(menuItem)
            changed = true
        }
        return changed
    }

    /** Nahrada za private `ActionDelegate.updateMenuItemRoles`. */
    private void setMenuItemRoles(Case item, String fieldId, Map<String, String> roles) {
        Case fresh = workflowService.findOne(item.stringId)
        fresh.dataSet[fieldId].options = collectRolesForPreferenceItem(roles)
        workflowService.save(fresh)
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

    // Tri metody, ktore tu boli - `setUriNodeDataRoles(String, List)`,
    // `setUriNodeDataRoles(String, Map)` a `setUriNodeDataRolesByPaths` - su
    // zmazane. Vsetky tri zapisovali do `UriNodeData.processRolesIds`, co je
    // pole, ktore:
    //
    //   * uz sa tak nevola. Bolo premenovane na `legacyProcessRolesIds`
    //     s `@Field("processRolesIds")`, takze Lombok generuje
    //     `setLegacyProcessRolesIds` a povodne volanie padne na
    //     `MissingMethodException: setProcessRolesIds()`. A padne az na DRUHE
    //     volanie: pri prvom sa uzol este nema kam najst, takze sa ide else
    //     vetvou cez konstruktor. Prvy import teda prejde a druhy vrati 500.
    //   * ani predtym nefungovalo. Drzalo `stringId` roly, ktore engine razi
    //     per verzia siete, takze zoznam sa po kazdom re-importe rozpadol.
    //
    // Viditelnost karty v lavom menu urcuje `processes.json` (sekcia
    // `uriNodes`, `requiredAuthorities` a `requiredProcessRoles` cez
    // `UriNodeDataRunner`) - a to je jedno miesto, kde to ma stat. Nastavovat
    // to aj z akcie by znamenalo dva zdroje pravdy, ktore si pri kazdom starte
    // prepisuju vysledok.

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
     * Ikona, sekcia a viditelnost karty uzla URI.
     *
     * Parameter `roleIds` je zmazany. Zapisoval do pola, ktore uz nema setter
     * (viz komentar vyssie), a hlavne: kto uzol vidi, urcuje `processes.json`.
     * Dva zdroje pravdy na tu istu vec sa pri kazdom starte prepisovali.
     *
     * @param section "settings" alebo "archive" pre koren, inak null
     */
    void setUriNodeData(String uri, String title, String section, String icon, boolean isSvgIcon = false, boolean isHidden = false) {
        UriNode uriNode = getUri(uri) as UriNode
        if (uriNode == null) {
            // Bez tejto kontroly to je `NullPointerException: Cannot invoke
            // method setName() on null object` z vnutra Groovy - sprava, ktora
            // NEPOVIE, o ktory uzol islo, a ked to bezi z NetRunnera, zhodi
            // cely start backendu.
            //
            // Uzol vznikne az tym, ze ho niekto vyrobi: bud import siete, ktorej
            // identifikator tu cestu nesie, alebo `createOrUpdateMenuItem`
            // (ten vola `createUri`). Na CISTEJ databaze teda plati poradie -
            // konfigurovat uzol sa da az po tom, co existuje. Tvorit ho tu
            // potichu by znamenalo, ze preklep v ceste vyrobi druhu, prazdnu
            // kartu namiesto chyby.
            throw new IllegalStateException(
                    "Uzol URI '${uri}' neexistuje, nie je co konfigurovat. " +
                    "Vyrob ho najprv importom siete s tymto prefixom alebo " +
                    "volanim createOrUpdateMenuItem(..., '${uri}', ...).")
        }
        uriNode.setName(title)
        uriService.save(uriNode)
        uriNodeDataRepository.findByUriNodeId(uriNode.getId()).ifPresentOrElse(data -> {
            data.setIcon(icon)
            data.setSection(section)
            data.setIconSvg(isSvgIcon)
            data.setHidden(isHidden)
            uriNodeDataRepository.save(data)
        }, () -> {
            uriNodeDataRepository.save(new UriNodeData(uriNode.getId(), section, icon, isSvgIcon, isHidden, null, null))
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
    /**
     * Vsetci skutocni pouzivatelia, ktori maju danu procesnu rolu.
     *
     * `usersWithRole` filtruje ZADANY zoznam; toto je ten druhy pripad -
     * "kto vsetko ma rolu schvalovatela strediska Wellness". Petriflow na to
     * primitiv nema: `roleRef` sa v prechode uvadza staticky a dynamicky sa
     * vybrat neda, takze rola sa musi premietnut do `userList` pola, na ktorom
     * visi `userRef`.
     *
     * Pouzivaju to obe siete appky schvalovania (faktury aj objednavky) -
     * a to je aj dovod, preco to je tu a nie ako process funkcia v jednej
     * z nich.
     */
    List<String> usersWithRoleAll(String roleImportId, String netIdentifier = null) {
        if (!roleImportId) {
            return []
        }
        return userService.findAll(true).findAll { IUser u ->
            isRealUser(u) && hasProcessRole(u, roleImportId, netIdentifier)
        }.collect { IUser u -> u.stringId as String }
    }

    /**
     * Case danej siete, ktory plati - z NAJNOVSEJ verzie siete a z nej ten
     * naposledy zalozeny.
     *
     * Na co to je: konfiguracny case (limity, parametre) sa zaklada
     * `bootstrapCase` s `rebuildOnNewVersion`, takze po kazdom re-importe
     * pribudne novy a stare zostanu ako stopa. Kto by cital "prvy najdeny",
     * cital by po case ten najstarsi a nechapal by, preco sa zmena nastavenia
     * neprejavila.
     *
     * Vracia null, ked siet neexistuje alebo z nej ziadny case nie je -
     * volajuci ma vtedy pouzit svoj default, nie spadnut.
     */
    Case najnovsiCase(String netIdentifier) {
        if (!netIdentifier) {
            return null
        }
        List<PetriNet> nets = petriNetService.getByIdentifier(netIdentifier)
        if (!nets) {
            return null
        }
        // Najnovsiu verziu urcuje ENGINE, nie my.
        //
        // Prva verzia tejto metody hladala maximum sama:
        //     nets.max { versionKey("${n.version.major}.${...}") }
        // `versionKey` vracia `List<Integer>` a Groovy `max` porovnava
        // navratove hodnoty cez `DefaultTypeTransformation.compareTo`, ktore
        // dva `ArrayList`y porovnat ODMIETNE:
        //     Cannot compare java.util.ArrayList with value '[1, 0, 0]'
        //     and java.util.ArrayList with value '[2, 0, 0]'
        // Kym existovala jedna verzia siete, `max` nic neporovnaval a vsetko
        // vyzeralo v poriadku. Po druhom importe zacala akcia, ktora tuto
        // metodu vola, padat - a kedze bola v `create` udalosti konfiguracneho
        // casu, PRESTAL SA ZAKLADAT CELY CASE. V appke to vyzeralo tak, ze
        // "nastavenia nefunguju, nie je tam ziaden pripad".
        PetriNet newest = petriNetService.getNewestVersionByIdentifier(netIdentifier)
        if (newest == null) {
            return null
        }
        List<Case> cases = findCases({ it.processIdentifier.eq(netIdentifier) }) ?: []
        List<Case> fromNewest = cases.findAll { it.petriNetObjectId == newest.objectId }
        List<Case> pool = fromNewest ?: cases
        if (!pool) {
            return null
        }
        return pool.max { Case c -> c.creationDate }
    }

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
        return createNewUser(name, surname, email, password, ["ROLE_USER"])
    }

    /**
     * Vytvori uzivatela aj so systemovymi authorities. Vrati vytvoreneho IUser.
     *
     * Preco varianta s authorities: bez nich sa uzivatel prihlasi a NEVIDI NIC.
     * Pristup k viewom riadi `nae.json` podla authorities (`ROLE_USER`,
     * `ROLE_ADMIN`), nie podla procesnych roli - to su dve oddelene veci, ktore
     * sa lahko pletu. Povodna varianta zakladala uzivatela s prazdnou mnozinou
     * a Petriflow akcia nemala ako to doplnit; prvy uzivatel vytvoreny z procesu
     * sa prihlasil do prazdnej aplikacie a nebolo z coho zistit preco.
     * Bezparametricka varianta preto teraz dava ROLE_USER, co je rozumny default.
     *
     * Authorities sa riesia rovnako ako v EtaskUserCreator (properties):
     * `authorityService.getOrCreate(nazov)`, takze nazov, ktory este neexistuje,
     * sa zalozi.
     */
    IUser createNewUser(String name, String surname, String email, String password,
                        List<String> authorities) {
        if (userService.findByEmail(email, true) != null) {
            throw new IllegalArgumentException("Používateľ s rovnakým emailom už bol vytvorený")
        }
        User user = new User(
                name: name,
                surname: surname,
                email: email,
                password: password,
                state: UserState.ACTIVE,
                authorities: [] as Set<Authority>,
                processRoles: [] as Set<ProcessRole>)
        (authorities ?: []).each { String authority ->
            user.addAuthority(authorityService.getOrCreate(authority))
        }
        return userService.saveNew(user)
    }

    /**
     * Pridel alebo odober procesnu rolu. Tenky adapter nad enginovym
     * `assignRole`/`removeRole` - NIE ich nahrada.
     *
     * Engine uz obe operacie podla importId a identifikatora siete ma, a to
     * v dvoch presne tych variantach, ktore treba:
     *
     *   assignRole(importId, netId, user)            ... VSETKY verzie siete
     *   assignRole(importId, netId, version, user)   ... jedna konkretna verzia
     *
     * (Predchadzajuca verzia tohto suboru mala vlastne `assignRoleByImportId`,
     * ktore duplikovalo tu prvu - a robilo menej: pridelilo rolu len na
     * najnovsej verzii. Presne pripad, pred ktorym varuje CLAUDE.md.)
     *
     * Zostava teda len to, co z Petriflow akcie naozaj nejde:
     *   - `Version` je objekt, akcia ma verziu ako retazec "1.0.0";
     *   - enginova varianta robi `.roles.values().find { ... }.stringId`, takze
     *     pri neznamom importId hodi NullPointerException. Tu sa vrati false.
     *
     * @param version prazdne alebo null = vsetky verzie siete (plosne)
     * @param assign true = pridelit, false = odobrat
     * @return true, ak rola na tej sieti existuje a operacia sa vykonala
     */
    boolean setProcessRole(IUser user, String roleImportId, String netIdentifier,
                           String version, boolean assign) {
        return setProcessRole(user?.stringId as String, roleImportId, netIdentifier,
                              version, assign)
    }

    /**
     * Varianta podla ID uctu - a je to tá, ktorú treba volať.
     *
     * DOVOD, a stálo to jedno ladenie: kazda zmena uctu je `read - mutuj - save`
     * celeho dokumentu. Kto si objekt `IUser` PODRZI a spravi cez neho dve
     * zmeny za sebou, prepise tou druhou vysledok prvej - posledny `save` zapise
     * svoju (uz neaktualnu) kopiu. V praxi to vypadalo tak, ze heslo sa zmenilo,
     * ale meno, authorities aj odobrana rola sa TICHO vratili do povodneho stavu.
     * `finish` pritom vratil `success`.
     *
     * Preto sa ucet nacita znova pred kazdym volanim a pouzije sa objekt, ktory
     * enginova metoda VRATI - nie ten, ktory sme jej dali.
     */
    boolean setProcessRole(String userId, String roleImportId, String netIdentifier,
                           String version, boolean assign) {
        if (!userId || !roleImportId || !netIdentifier) {
            return false
        }
        String v = (version ?: "").trim()
        List<PetriNet> nets = (v.isEmpty() || v == VSETKY_VERZIE)
                ? petriNetService.getByIdentifier(netIdentifier)
                : [petriNetService.getPetriNet(netIdentifier, parseVersion(v))]
        nets = nets.findAll { it != null }
        if (nets.isEmpty()) {
            return false
        }
        boolean done = false
        nets.each { PetriNet net ->
            ProcessRole role = net.roles.values().find { it.importId == roleImportId }
            if (role == null) {
                return
            }
            IUser fresh = userService.findById(userId, false)
            if (fresh == null) {
                return
            }
            if (assign) {
                assignRole(role.stringId, fresh)
            } else {
                // NEPOUZIVAT enginove `removeRole` - v 6.3.1 je rozbite a mlci.
                // `AbstractUserService.removeRole(IUser, String roleStringId)`
                // si rolu vytiahne cez `processRoleService.findByImportId(...)`,
                // teda podla importId - hoci parameter je stringId. Podla
                // stringId tak nenajde NIC, `removeProcessRole(null)` neodoberie
                // nic a `save` ulozi nezmeneny dokument. Bez chyby, bez logu.
                // (`addRole` ten isty parameter riesi spravne cez `findById`,
                // takze pridelenie funguje a odobranie nie - odtial ta asymetria.)
                // Rolu preto odoberame priamo, mame ju ako objekt zo siete.
                fresh.removeProcessRole(role)
                userService.save(fresh)
            }
            done = true
        }
        return done
    }

    /**
     * Zmena hesla podla ID uctu.
     *
     * Existuje preto, aby siet nemusela drzat objekt uctu: `changePassword`
     * z `registrationService` berie `RegisteredUser` a uklada ho cely, takze
     * podrzany objekt by prepisal vsetko, co sa medzitym zmenilo. Viac pri
     * `setProcessRole(String, ...)`.
     *
     * Silu hesla overuje engine (`registrationService.isPasswordSufficient`),
     * nie táto metoda - politika patrí do konfiguracie instancie.
     */
    boolean changeUserPassword(String userId, String newPassword) {
        if (!userId || !newPassword) {
            return false
        }
        IUser user = userService.findById(userId, false)
        if (user == null) {
            return false
        }
        registrationService.changePassword(user, newPassword)
        return true
    }

    /**
     * Roly vsetkych aplikacnych sieti v instancii, ako mapa
     * "importId:identifikatorSiete" -> "Nazov roly (Nazov siete)".
     *
     * Na naplnenie `options` multichoice_map pola z akcie, aby appka na spravu
     * uzivatelov nemusela mat nazvy roli natvrdo - inak by kazda nova appka
     * znamenala zasah do nej.
     *
     * Systemove siete enginu (`filter`, `preference_filter_item`, ...) sa
     * preskakuju: ich identifikator neobsahuje `/`, kym aplikacne siete v tomto
     * repozitari maju tvar `appka/siet`. Vstavane roly `default` a `anonymous`
     * tiez, tie sa neprideluju.
     */
    Map<String, String> processRoleOptions() {
        Map<String, String> out = [:]
        applicationNetIdentifiers().each { String identifier ->
            PetriNet net = petriNetService.getNewestVersionByIdentifier(identifier)
            if (net == null) {
                return
            }
            assignableRoles(net).each { ProcessRole role ->
                out.put(role.importId + ":" + identifier,
                        "${role.name} (${net.title})" as String)
            }
        }
        return out
    }

    /**
     * Roly JEDNEHO procesu, ako mapa importId -> "Nazov roly".
     *
     * Toto je druha polovica vyberu v dvoch krokoch: najprv `processOptions()`
     * da procesy, potom sa touto metodou z vybraneho procesu doplnia jeho roly
     * (`change pole options { ... }` v `set` akcii pola s procesom).
     *
     * Kluc je tu cisty importId, nie "importId:siet" - siet uz je vybrana
     * a drzi ju vlastne pole, takze ju netreba nosit v kluci.
     *
     * @param version prazdne alebo null = najnovsia verzia siete
     */
    Map<String, String> processRoleOptions(String netIdentifier, String version = null) {
        Map<String, String> out = [:]
        PetriNet net = resolveNet(netIdentifier, version)
        if (net == null) {
            return out
        }
        assignableRoles(net).each { ProcessRole role ->
            out.put(role.importId, role.name as String)
        }
        return out
    }

    /**
     * Procesy (aplikacne siete) instancie, ako mapa identifikator -> "Nazov".
     *
     * Prvy krok vyberu roly v dvoch krokoch. Bez neho by pole s rolami muselo
     * ponukat vsetky roly vsetkych sietí naraz - co je pri niekolkych appkach
     * zoznam, v ktorom sa neda nic najst.
     */
    Map<String, String> processOptions() {
        Map<String, String> out = [:]
        applicationNetIdentifiers().each { String identifier ->
            PetriNet net = petriNetService.getNewestVersionByIdentifier(identifier)
            if (net != null) {
                out.put(identifier, net.title as String)
            }
        }
        return out
    }

    /** Volba "vsetky verzie" v `processVersionOptions`. */
    static final String VSETKY_VERZIE = "vsetky"

    /**
     * Verzie jedneho procesu, ako mapa hodnota -> popis.
     *
     * Prvy zaznam je VSETKY_VERZIE a je aj rozumny default: rola ma `stringId`
     * razene per verziu siete, takze pridelenie len na jednej verzii znamena, ze
     * na casoch inej verzie uzivatel pristup NEMA. Konkretna verzia je tu pre
     * pripad, kedy to niekto chce zamerne.
     *
     * KLUCE SU ZASLUGOVANE: "1.0.0" -> "1_0_0". Moznosti nastavene za behu sa
     * ukladaju ako Mongo dokument a Mongo v nazvoch poli zakazuje bodku - kluc
     * s verziou by zhodil ulozenie na "Map key 1.0.0 contains dots but no
     * replacement was configured". (`petriflow_reference.md`, C17.) Popis
     * zostava s bodkami, `setProcessRole` si podtrzniky prelozi spat.
     */
    Map<String, String> processVersionOptions(String netIdentifier) {
        Map<String, String> out = [(VSETKY_VERZIE): "Všetky verzie"]
        List<PetriNet> nets = petriNetService.getByIdentifier(netIdentifier) ?: []
        PetriNet newest = petriNetService.getNewestVersionByIdentifier(netIdentifier)
        String newestVersion = newest?.version?.toString()
        nets.collect { it.version?.toString() }
                .findAll { it != null }
                .unique()
                // `versionSortKey`, nie `versionKey`: ten vracia List a Groovy
                // dva Listy porovnat odmietne (viz `najnovsiCase`). Tu to
                // doteraz neprasklo len preto, ze sa to volalo na sietach
                // s jednou verziou.
                .sort(false) { String v -> versionSortKey(v) }
                .reverse()
                .each { String v ->
                    out.put(v.replace(".", "_"),
                            v == newestVersion ? "${v} (najnovšia)" as String : v)
                }
        return out
    }

    /**
     * Pouzivatelia instancie, ako mapa id -> "Meno Priezvisko (e-mail)".
     *
     * Na vyber uctu, ktory sa ma upravit. Systemove ucty enginu (`system`,
     * anonymny) sa preskakuju - nemaju sa cez appku upravovat.
     */
    Map<String, String> userOptions() {
        Map<String, String> out = [:]
        userService.findAll(true).each { IUser u ->
            if (!isRealUser(u)) {
                return
            }
            out.put(u.stringId as String,
                    "${u.name} ${u.surname} (${u.email})" as String)
        }
        return out.sort { it.value }
    }

    /**
     * Je to ucet cloveka, alebo sluzobny ucet enginu?
     *
     * Anonymne sessiony sa ukladaju ako uzivatelia s e-mailom
     * `<hash>@anonymous.nae` (`PublicAuthenticationFilter`), takze filter na
     * PREFIX "anonymous" ich neodfiltruje - domena, nie zaciatok. Systemovy
     * ucet enginu je `engine@netgrif.com` (`SystemUserRunner.SYSTEM_USER_EMAIL`),
     * nie `system@netgrif.com`, ako som najprv predpokladal.
     *
     * Kym to bolo napisane zle, `userOptions()` ponukalo tri anonymne sessiony
     * a systemovy ucet ako uzivatelov na upravu.
     */
    boolean isRealUser(IUser user) {
        String email = ((user?.email ?: "") as String).trim().toLowerCase()
        if (!email) {
            return false
        }
        if (email.endsWith("@anonymous.nae")) {
            return false
        }
        return !(email in ["engine@netgrif.com", "system@netgrif.com"])
    }

    /**
     * Heslo tak, ako ho poslal FORMULAR - teda dekoduje base64.
     *
     * Textove pole s `<component><name>password</name></component>` frontend
     * pred odoslanim ZAKODUJE do base64:
     *
     *     // FieldConverterService.formatValueForBackend
     *     if (resolveType(field) === TEXT && field.component.name === 'password') {
     *         return encodeBase64(value);
     *     }
     *
     * Kto to nevie, zahashuje base64 namiesto hesla a ucet sa potom NEDA
     * prihlasit tym, co clovek napisal - da sa prihlasit base64 z toho. Presne
     * toto sa stalo pri ucte zalozenom cez formular, kym akceptacny test presiel:
     * test posielal surovu hodnotu na oboch stranach, takze bol sam so sebou
     * konzistentny a chybu neuvidel.
     *
     * Pozor: rozhodnut sa "je to base64?" podla obsahu NEJDE - `password` je
     * platny base64 retazec. Preto je to pravidlo, nie hadanie: toto pole plni
     * formular, takze hodnota JE zakodovana, a kto ho plni cez REST, musi
     * zakodovat rovnako.
     */
    String formPassword(Object value) {
        String raw = ((value ?: "") as String)
        if (!raw) {
            return ""
        }
        try {
            return new String(Base64.decoder.decode(raw), StandardCharsets.UTF_8)
        } catch (IllegalArgumentException ignored) {
            // Neplatny base64 - hodnota nepresla frontendom. Beriem ju ako je.
            return raw
        }
    }

    /**
     * Systemove authorities instancie, ako mapa nazov -> popis.
     *
     * NATVRDO SA TO NAPISAT NEDA, a stalo to jedno 500: pole s dvomi moznostami
     * (`ROLE_USER`, `ROLE_ADMIN`) nedokaze zobrazit ucet, ktory ma aj
     * `ROLE_ANONYMOUS` alebo `ROLE_SYSTEMADMIN` - engine hodnotu mimo `options`
     * neprijme a vrati "Could not parse value of field". A `super@netgrif.com`
     * ma vsetky styri, takze na prvom skutocnom ucte to spadlo.
     *
     * Popis odlisuje to, co sa bezne prideluje, od systemovych - ktore su
     * v zozname preto, aby sa dal zobrazit existujuci stav, nie aby sa
     * rozdavali.
     */
    Map<String, String> authorityOptions() {
        Map<String, String> out = [:]
        authorityService.findAll().each { Authority a ->
            String name = a.name as String
            if (!name) {
                return
            }
            String popis
            switch (name) {
                case "ROLE_USER": popis = "ROLE_USER — bežný používateľ"; break
                case "ROLE_ADMIN": popis = "ROLE_ADMIN — administrátor"; break
                case "ROLE_ANONYMOUS": popis = "ROLE_ANONYMOUS — anonymná session (systémová)"; break
                case "ROLE_SYSTEMADMIN": popis = "ROLE_SYSTEMADMIN — systémová"; break
                default: popis = name
            }
            out.put(name, popis)
        }
        return out.sort { it.key }
    }

    /**
     * Aktualny stav uctu, na predvyplnenie formulara pri uprave.
     *
     * Kluce: meno, priezvisko, email, authorities (List<String>),
     * roly (Map<identifikatorSiete, List<importId>>).
     */
    Map<String, Object> userSnapshot(String userId) {
        IUser user = userId ? userService.findById(userId, false) : null
        if (user == null) {
            return [:]
        }
        // ProcessRole nenesie identifikator siete, takze sa hlada spatne podla
        // `stringId`. Index sa stavia RAZ - povodna verzia prechadzala vsetky
        // verzie vsetkych sieti pre KAZDU rolu uctu, co je pri ucte so 70
        // rolami a 30 sietach 2100 prehladani a `zl_sync` na tom vytimeoutoval.
        Map<String, List<String>> roles = [:]
        Map<String, String> netByRoleId = roleIdToNetIndex()
        (user.processRoles ?: []).each { ProcessRole role ->
            if (role.importId in ["default", "anonymous"]) {
                return
            }
            String identifier = netByRoleId.get(role.stringId as String)
            if (identifier == null) {
                return
            }
            roles.computeIfAbsent(identifier, { [] as List<String> })
            if (!roles[identifier].contains(role.importId)) {
                roles[identifier] << (role.importId as String)
            }
        }
        return [
                meno       : user.name as String,
                priezvisko : user.surname as String,
                email      : user.email as String,
                authorities: (user.authorities ?: []).collect { it.name as String }.sort(),
                roly       : roles,
        ]
    }

    /**
     * Zmena mena a priezviska existujuceho uctu.
     *
     * E-mail sa zamerne menit neda: je to prihlasovacie meno a zaroven kluc,
     * podla ktoreho ucty hlada `seed.json`, `EtaskUserCreator` aj kazdy test.
     * Zmena e-mailu je zalozenie noveho uctu, nie uprava.
     */
    IUser updateUserProfile(String userId, String name, String surname) {
        IUser user = userId ? userService.findById(userId, false) : null
        if (user == null) {
            return null
        }
        if (name != null && !(name as String).trim().isEmpty()) {
            user.name = (name as String).trim()
        }
        if (surname != null && !(surname as String).trim().isEmpty()) {
            user.surname = (surname as String).trim()
        }
        return userService.save(user)
    }

    /**
     * Nastavi systemove authorities uctu na presne tento zoznam.
     *
     * Nie pridanie - nastavenie: pri uprave sa ocakava, ze co v zozname nie je,
     * ucet mat nema. Neexistujuca authority sa zalozi
     * (`authorityService.getOrCreate`), rovnako ako v `createNewUser`.
     */
    IUser setUserAuthorities(String userId, List<String> authorities) {
        IUser user = userId ? userService.findById(userId, false) : null
        if (user == null) {
            return null
        }
        Set<Authority> wanted = (authorities ?: [])
                .findAll { it != null && !(it as String).trim().isEmpty() }
                .collect { authorityService.getOrCreate((it as String).trim()) } as Set<Authority>
        user.authorities = wanted
        return userService.save(user)
    }

    // ---- pomocne, nepouzivat priamo z akcie -------------------------------

    /**
     * `stringId` roly -> identifikator siete, pre vsetky aplikacne siete
     * a vsetky ich verzie. Jeden prechod namiesto prehladavania per rola.
     */
    private Map<String, String> roleIdToNetIndex() {
        Map<String, String> out = [:]
        petriNetService.getAll().each { PetriNet net ->
            if (net.identifier == null || !net.identifier.contains("/")) {
                return
            }
            net.roles.values().each { ProcessRole role ->
                out.put(role.stringId as String, net.identifier as String)
            }
        }
        return out
    }

    private List<String> applicationNetIdentifiers() {
        // Systemove siete enginu (`filter`, `preference_filter_item`, ...) maju
        // identifikator bez `/`, aplikacne siete v tomto repozitari maju tvar
        // `appka/siet`. Preto to rozlisenie.
        return petriNetService.getAll()
                .collect { it.identifier }
                .findAll { it != null && it.contains("/") }
                .unique()
                .sort()
    }

    private static List<ProcessRole> assignableRoles(PetriNet net) {
        // `default` a `anonymous` su vstavane a neprideluju sa.
        return net.roles.values().findAll { it.importId != null &&
                !(it.importId in ["default", "anonymous"]) }.toList()
    }

    private PetriNet resolveNet(String netIdentifier, String version) {
        if (!netIdentifier) {
            return null
        }
        String v = ((version ?: "") as String).trim()
        if (v.isEmpty() || v == VSETKY_VERZIE) {
            return petriNetService.getNewestVersionByIdentifier(netIdentifier)
        }
        return petriNetService.getPetriNet(netIdentifier, parseVersion(v))
    }

    /**
     * "1.0.0" -> Version. Trieda `Version` ma len @AllArgsConstructor, ziadne
     * `fromString` - a v Groovy by volanie neexistujucej statickej metody
     * preslo kompilaciou a spadlo az za behu.
     */
    private static Version parseVersion(String v) {
        // Kluc moznosti je zaslugovany ("1_0_0"), verzia z ineho zdroja moze
        // prist s bodkami. Berieme oboje.
        List<Integer> parts = versionKey((v ?: "").replace("_", "."))
        while (parts.size() < 3) {
            parts << 0
        }
        return new Version(parts[0] as long, parts[1] as long, parts[2] as long)
    }

    /** Verzia ako jedno cislo - porovnatelne, na rozdiel od zoznamu castí. */
    private static long versionSortKey(String v) {
        List<Integer> parts = versionKey(v)
        while (parts.size() < 3) {
            parts << 0
        }
        return (parts[0] as long) * 1_000_000L + (parts[1] as long) * 1_000L + (parts[2] as long)
    }

    private static List<Integer> versionKey(String v) {
        return (v ?: "0").split("\\.").collect {
            try { Integer.parseInt(it) } catch (NumberFormatException ignored) { 0 }
        }
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

    // ==================================================================
    // Cítanie faktúry z prílohy
    //
    // Volá sa z Petriflow akcie (tlačidlo "Načítať z prílohy" v fa_faktura):
    //     def v = precitajFakturu(fa_skan, useCase.stringId)
    //
    // Logika je v com.netgrif.etask.doc, delegát len presmeruje a vyrieši,
    // kde na disku príloha vlastne leží.
    // ==================================================================

    /**
     * Precita fakturu z prilohy a vrati polia, ktore sa z nej dali vytiahnut.
     *
     * XML e-fakturu (UBL 2.1 / CII podla EN 16931, alebo ISDOC) <b>cita</b>,
     * PDF s textovou vrstvou cita cez PDFBox, sken a fotku prezenie OCR
     * (binarka `tesseract`, ked je k dispozicii). Nikdy nic nezapisuje sama -
     * vysledok je na predvyplnenie formulara, ktory clovek potvrdi.
     *
     * Kluce vysledku: `zdroj` (xml|text|ocr|nic), `dodavatel`, `cislo`, `suma`,
     * `mena`, `splatnost`, `vystavenie`, `ico`, `dic`, `iban`, `vs`, `chyba`,
     * `poznamka`, `nedocitane`.
     *
     * @param priloha pole typu `file` (alebo jeho hodnota, alebo cesta)
     * @param caseId  stringId pripadu - `useCase.stringId`; sluzi na dopocitanie
     *                cesty k prilohe, ked ju hodnota pola nenesie
     */
    Map<String, Object> precitajFakturu(Object priloha, String caseId = null) {
        File file = resolveAttachment(priloha, caseId)
        if (file == null) {
            return [zdroj: "nic", nedocitane: [],
                    chyba: "Príloha nie je nahraná - priložte XML e-faktúru, PDF alebo sken."]
        }
        return invoiceReaderService.read(file)
    }

    /**
     * Je OCR na tomto stroji k dispozicii? Siet to vie povedat cloveku skor,
     * nez zbytocne priloži fotku.
     */
    boolean ocrDostupne() {
        return invoiceReaderService.ocrAvailable()
    }

    // ==================================================================
    // Notifikacne maily
    //
    // Volá sa z Petriflow akcie, napríklad po podaní faktúry:
    //     notifikuj(fa_schvalovatelia, "Faktúra na schválenie", text)
    //
    // Logika je v com.netgrif.etask.mail.NotifyService; delegát rieši len to,
    // čo Petriflow nevie - dostať z userList poľa e-mailové adresy.
    // ==================================================================

    /**
     * Da sa posielat? Siet sa to pyta, aby o tom vedela napisat do priebehu
     * pripadu - "notifikacie su vypnute" je informacia, nie chyba.
     */
    boolean notifikacieZapnute() {
        return notifyService.available()
    }

    /**
     * Posle notifikacny mail a vrati, kolkym prijemcom sa to podarilo.
     *
     * Nikdy nevyhodi vynimku. Notifikacia sa posiela z udalosti `finish`, teda
     * vnutri transakcie, ktora prepina token - keby padla, zlyhalo by
     * schvalenie faktury na tom, ze sa nepodarilo poslat mail o schvaleni.
     *
     * @param prijemcovia userList pole, jeho hodnota, zoznam id, zoznam adries
     *                    alebo jedna adresa
     */
    int notifikuj(Object prijemcovia, String predmet, String telo) {
        try {
            return notifyService.send(emailyOf(prijemcovia), predmet, telo)
        } catch (Throwable t) {
            return 0
        }
    }

    /**
     * E-mailove adresy z coho sa da: userList pole, jeho hodnota, zoznam id,
     * zoznam adries alebo jedna adresa.
     */
    List<String> emailyOf(Object co) {
        if (co instanceof String) {
            return ((String) co).contains("@") ? [((String) co).trim()] : []
        }
        return usersOf(co).collect { IUser u -> (u.email ?: "") as String }
                .findAll { it }.unique()
    }

    /**
     * Mena uzivatelov, "Meno Priezvisko" (alebo e-mail, ked meno chyba).
     *
     * Preco to je primitiv a nie akcia: pole, ktore ma cloveku povedat, u koho
     * jeho faktura lezi, je `text`, teda `String` - a ten sa neprekladá
     * (RUNBOOK 9). Menu clovoka to netrapi, ale slovo "riaditeľ" by v anglickom
     * portali bolo jedina slovenska vec v zozname. Preto do takeho pola patria
     * MENA, a mena sa z roly (`usersWithRoleAll` vracia id) inak nedaju.
     */
    List<String> menaUzivatelov(Object co) {
        return usersOf(co).collect { IUser u ->
            String meno = ((u.name ?: "") as String).trim()
            String priezvisko = ((u.surname ?: "") as String).trim()
            String cele = (meno + " " + priezvisko).trim()
            return cele ?: ((u.email ?: "") as String)
        }.findAll { it }.unique()
    }

    /**
     * Hociaky tvar "zoznam uzivatelov" na skutocne ucty.
     *
     * Prijme: userList pole, jeho `UserListFieldValue`, zoznam id, zoznam
     * e-mailov, jedno id, jeden e-mail. Vsetky tieto tvary si siete medzi sebou
     * naozaj posielaju - `schvalovatelia_strediska` vracia id, `f.fa_zadal` je
     * pole a konfiguracia pracuje s adresami.
     */
    private List<IUser> usersOf(Object co) {
        if (co == null) {
            return []
        }
        List<IUser> out = []
        Closure<Void> pridaj = { Object item ->
            if (item == null) return
            if (item instanceof IUser) {
                out << (IUser) item
                return
            }
            if (item instanceof Map) {
                // UserFieldValue serializovany do mapy: uz nesie meno aj mail,
                // ale kvoli jednotnemu tvaru sa dohleda ucet.
                Object id = item["_id"] ?: item["id"]
                if (id) {
                    IUser u = userService.findById(id as String, false)
                    if (u != null) {
                        out << u
                        return
                    }
                }
                if (item["email"]) {
                    IUser u = userService.findByEmail(item["email"] as String, false)
                    if (u != null) out << u
                }
                return
            }
            String str = (item as String).trim()
            if (!str) return
            IUser u = str.contains("@") ? userService.findByEmail(str, false)
                    : userService.findById(str, false)
            if (u != null) out << u
        }

        def value = co.hasProperty("value") ? co.value : co
        if (value == null) {
            return []
        }
        if (value.hasProperty("userValues") && value.userValues) {
            value.userValues.each { pridaj(it) }
        } else if (value instanceof Collection) {
            ((Collection) value).each { pridaj(it) }
        } else {
            pridaj(value)
        }
        return out.unique { IUser u -> u.stringId as String }
    }

    /**
     * Najde prilohu na disku. Hodnota `file` pola nesie `name` a `path`, ale
     * `path` je relativna k pracovnemu priecinku procesu a po zmene
     * `nae.storage.path` alebo po prenose databazy medzi prostrediami uz sediet
     * nemusí. Preto sa skusa v poradí: cesta z hodnoty, cesta dopocitana
     * enginom (`getPath(caseId, fieldId)`) a nakoniec hladanie podla nazvu
     * v storage - inak by akcia hlasila "priloha nie je nahrana" na prilohe,
     * ktora tam je.
     */
    private File resolveAttachment(Object priloha, String caseId) {
        if (priloha == null) {
            return null
        }
        if (priloha instanceof File) {
            return ((File) priloha).exists() ? (File) priloha : null
        }
        if (priloha instanceof String) {
            File f = new File((String) priloha)
            return f.exists() ? f : null
        }

        def value = priloha.hasProperty("value") ? priloha.value : priloha
        if (value == null) {
            return null
        }

        String name = value.hasProperty("name") ? (value.name as String) : null
        String path = value.hasProperty("path") ? (value.path as String) : null

        List<String> candidates = []
        if (path) {
            candidates << path
        }
        if (caseId && priloha.hasProperty("importId")) {
            try {
                candidates << (value.getPath(caseId, priloha.importId as String) as String)
            } catch (Exception ignored) {
                // Pretazenie getPath(String, String) je Groovy metoda enginu;
                // ked sa zmeni, nesmie to zhodit celu akciu.
            }
        }
        for (String c : candidates) {
            if (!c) {
                continue
            }
            File f = new File(c)
            if (f.exists() && f.length() > 0) {
                return f
            }
        }
        return name ? findInStorage(name) : null
    }

    /** Posledna moznost: nájdi v storage subor, ktoreho nazov konci nazvom prilohy. */
    private static File findInStorage(String name) {
        File root = new File(System.getProperty("nae.storage.path", "storage"))
        if (!root.isDirectory()) {
            return null
        }
        File hit = null
        root.eachFileRecurse { File f ->
            if (hit == null && f.isFile() && f.name.endsWith(name)) {
                hit = f
            }
        }
        return hit
    }

}
