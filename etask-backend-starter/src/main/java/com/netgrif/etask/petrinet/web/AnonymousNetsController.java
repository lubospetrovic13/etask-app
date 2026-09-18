package com.netgrif.etask.petrinet.web;

import com.netgrif.application.engine.petrinet.domain.PetriNet;
import com.netgrif.application.engine.petrinet.service.interfaces.IPetriNetService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

/**
 * Ktore procesy maju verejny (anonymny) formular.
 *
 * Preco to existuje: `GET /api/petrinet/{id}` vracia len author, createdDate,
 * defaultCaseName, icon, identifier, immediateData, initials, stringId, title
 * a version. Priznak `anonymousRoleEnabled` je na domenovom objekte `PetriNet`,
 * ale do referencie sa nedostane, takze frontend o nom nema ako vediet.
 *
 * Dosledok bez tohto endpointu: zoznam procesov ukazuje "Verejna URL" pri
 * KAZDOM procese, aj pri tych, ktore anonyma nikdy nepustia. Taky odkaz
 * skonci na prihlasovacej obrazovke a vyzera to ako chyba appky.
 *
 * Vracia identifikatory, nie stringId: stringId sa razi per verzia siete,
 * takze by sa zoznam po kazdom re-importe rozisiel s tym, co ma frontend
 * v zozname. Identifikator je stabilny.
 */
@RestController
@RequestMapping("/api/etask/petrinet")
public class AnonymousNetsController {

    private final IPetriNetService petriNetService;

    public AnonymousNetsController(IPetriNetService petriNetService) {
        this.petriNetService = petriNetService;
    }

    /**
     * Identifikatory procesov, ktore maju v hlavicke {@code anonymousRole true}.
     * Zoradene, aby bola odpoved stabilna medzi volaniami.
     */
    @GetMapping("/anonymous")
    public Set<String> anonymousNets() {
        List<PetriNet> nets = petriNetService.getAll();
        return nets.stream()
                .filter(PetriNet::isAnonymousRoleEnabled)
                .map(PetriNet::getIdentifier)
                .collect(Collectors.toCollection(TreeSet::new));
    }
}
