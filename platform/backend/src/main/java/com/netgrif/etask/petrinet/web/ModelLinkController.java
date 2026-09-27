package com.netgrif.etask.petrinet.web;

import com.netgrif.application.engine.auth.domain.Authority;
import com.netgrif.application.engine.auth.domain.IUser;
import com.netgrif.application.engine.auth.service.interfaces.IUserService;
import com.netgrif.application.engine.petrinet.domain.PetriNet;
import com.netgrif.application.engine.petrinet.service.interfaces.IPetriNetService;
import com.netgrif.etask.petrinet.service.interfaces.IModelLinkService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Lets the Workflow screen hand a process model to the Netgrif builder without
 * the admin having to download the XML and import it by hand.
 *
 * Why this needs a second endpoint at all: the builder takes the model as
 * {@code ?modelUrl=<url>} and fetches that URL from its own page with a plain
 * XHR. None of our authentication travels with it, and measured against the
 * running engine none of the shortcuts work either - the engine accepts its
 * token only as a header (every query-string spelling answers 401), an
 * anonymous session cannot read {@code /api/petrinet/{id}/file}, and a
 * {@code data:} URL carrying the model is rejected by the builder's own nginx
 * with 414 well below the size of a real net. So the model has to sit at an
 * address that anyone can GET, and the only question left is for how long and
 * for which net. Hence: mint a signed link, valid five minutes, for one net.
 *
 * Minting requires ROLE_ADMIN, which is also the authority that gates the
 * Workflow screen this is called from (nae.json, views.workflows.access).
 * Reading with a valid signature requires nothing - that is the whole point.
 */
@Slf4j
@RestController
@RequestMapping("/api")
@Tag(name = "Process model link")
public class ModelLinkController {

    private static final String ADMIN = "ROLE_ADMIN";

    private final IPetriNetService petriNetService;
    private final IUserService userService;
    private final IModelLinkService linkService;

    public ModelLinkController(IPetriNetService petriNetService, IUserService userService,
                               IModelLinkService linkService) {
        this.petriNetService = petriNetService;
        this.userService = userService;
        this.linkService = linkService;
    }

    @Operation(summary = "Mint a short-lived anonymous link to a process model",
            security = {@SecurityRequirement(name = "BasicAuth")})
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "OK"),
            @ApiResponse(responseCode = "403", description = "Caller is not an admin"),
            @ApiResponse(responseCode = "404", description = "No such process"),
    })
    @GetMapping(value = "/v2/model-link/{netId}", produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> createLink(@PathVariable("netId") String netId) {
        requireAdmin();
        requireNet(netId);

        long expiresAt = Instant.now().plus(linkService.validity()).getEpochSecond();
        String signature = linkService.sign(netId, expiresAt);

        // A PATH, not an absolute URL. Building the absolute one here would mean
        // trusting the Host header behind the reverse proxy, and nginx.conf
        // passes `$host` - which drops the port, so a portal on :4200 would be
        // handed a link to :80. The browser knows its own origin; let it prefix.
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("path", "/api/public/model/" + netId + "?exp=" + expiresAt + "&sig=" + signature);
        body.put("expiresAt", expiresAt);
        body.put("validForSeconds", linkService.validity().getSeconds());
        return body;
    }

    @Operation(summary = "Read a process model with a signed link (no authentication)")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "OK"),
            @ApiResponse(responseCode = "404", description = "Link invalid, expired, or no such process"),
    })
    @GetMapping(value = "/public/model/{netId}", produces = MediaType.APPLICATION_XML_VALUE)
    public ResponseEntity<FileSystemResource> readModel(@PathVariable("netId") String netId,
                                                        @RequestParam("exp") long expiresAt,
                                                        @RequestParam("sig") String signature) {
        if (!linkService.verify(netId, expiresAt, signature)) {
            // 404, not 403: a bad or stale signature should not confirm that the
            // net exists. There is nothing here to retry against.
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        PetriNet net = requireNet(netId);
        FileSystemResource file = petriNetService.getFile(netId, null);
        if (file == null || !file.exists()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        log.info("Serving model {} v{} through a signed link", net.getIdentifier(), net.getVersion());
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_XML)
                .body(file);
    }

    private PetriNet requireNet(String netId) {
        PetriNet net;
        try {
            net = petriNetService.getPetriNet(netId);
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        if (net == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return net;
    }

    private void requireAdmin() {
        IUser user;
        try {
            user = userService.getLoggedUser();
        } catch (Exception e) {
            user = null;
        }
        if (user == null || !authorityNames(user).contains(ADMIN)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }
    }

    private Set<String> authorityNames(IUser user) {
        Set<Authority> authorities = user.getAuthorities();
        if (authorities == null) {
            return Set.of();
        }
        return authorities.stream()
                .map(Authority::getName)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());
    }
}
