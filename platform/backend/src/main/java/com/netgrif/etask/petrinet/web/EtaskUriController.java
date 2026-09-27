package com.netgrif.etask.petrinet.web;

import com.netgrif.application.engine.auth.domain.IUser;
import com.netgrif.application.engine.auth.service.interfaces.IUserService;
import com.netgrif.application.engine.petrinet.domain.UriNode;
import com.netgrif.application.engine.petrinet.service.interfaces.IUriService;
import com.netgrif.etask.petrinet.domain.UriNodeData;
import com.netgrif.etask.petrinet.domain.UriNodeDataRepository;
import com.netgrif.etask.petrinet.service.interfaces.IUriNodeVisibilityService;
import com.netgrif.etask.petrinet.responsebodies.EtaskUriNode;
import com.netgrif.etask.petrinet.responsebodies.EtaskUriNodeResource;
import com.netgrif.etask.petrinet.responsebodies.EtaskUriNodeResources;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import java.util.Base64;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * becomes obsolete in NAE 6.4.0 where double drawer menu is reworked
 */
@RestController
@RequestMapping("/api/v2/uri")
@Tag(name = "Process URI")
public class EtaskUriController {

    private final IUriService uriService;
    private final UriNodeDataRepository repository;
    private final IUserService userService;
    private final IUriNodeVisibilityService visibilityService;

    public EtaskUriController(IUriService uriService, UriNodeDataRepository repository,
                              IUserService userService, IUriNodeVisibilityService visibilityService) {
        this.uriService = uriService;
        this.repository = repository;
        this.userService = userService;
        this.visibilityService = visibilityService;
    }

    @Operation(summary = "Get root UriNodes", security = {@SecurityRequirement(name = "BasicAuth")})
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "OK"),
    })
    @GetMapping(value = "/root", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<EtaskUriNode> getRoot() {
        EtaskUriNode uriNode = new EtaskUriNode(uriService.getRoot());
        uriNode = populateDirectRelatives(loadUriNode(uriNode));
        return new EtaskUriNodeResource(uriNode);
    }

    /** The caller, or null when the request carries no resolvable user. */
    private IUser loggedUser() {
        try {
            return userService.getLoggedUser();
        } catch (Exception e) {
            return null;
        }
    }

    private boolean isVisible(UriNode node) {
        UriNodeData data = repository.findByUriNodeId(node.getId()).orElse(null);
        return visibilityService.isVisible(data, loggedUser());
    }

    @Operation(summary = "Get one UriNode by URI path", security = {@SecurityRequirement(name = "BasicAuth")})
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "OK"),
    })
    @GetMapping(value = "/{uri}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<EtaskUriNode> getOne(@PathVariable("uri") String uri) {
        uri = new String(Base64.getDecoder().decode(uri));
        UriNode found = uriService.findByUri(uri);
        if (found == null || !isVisible(found)) {
            // 404 rather than 403: a caller who may not see the node should not
            // learn it exists.
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        EtaskUriNode uriNode = new EtaskUriNode(found);
        uriNode = populateDirectRelatives(loadUriNode(uriNode));
        return new EtaskUriNodeResource(uriNode);
    }

    @Operation(summary = "Get UriNodes by parent id", security = {@SecurityRequirement(name = "BasicAuth")})
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "OK"),
    })
    @GetMapping(value = "/parent/{parentId}", produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EtaskUriNode> getByParent(@PathVariable("parentId") String parentId) {
        List<EtaskUriNode> uriNodes = uriService.findAllByParent(parentId).stream()
                .filter(this::isVisible)
                .map(this::loadUriNode).collect(Collectors.toList());
        uriNodes.forEach(this::populateDirectRelatives);
        return new EtaskUriNodeResources(uriNodes);
    }

    @Operation(summary = "Get UriNodes by on the same level", security = {@SecurityRequirement(name = "BasicAuth")})
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "OK"),
    })
    @GetMapping(value = "/level/{level}", produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EtaskUriNode> getByLevel(@PathVariable("level") int level) {
        List<EtaskUriNode> uriNodes = uriService.findByLevel(level).stream()
                .filter(this::isVisible)
                .map(this::loadUriNode).collect(Collectors.toList());
        uriNodes.forEach(this::populateDirectRelatives);
        return new EtaskUriNodeResources(uriNodes);
    }

    protected EtaskUriNode populateDirectRelatives(EtaskUriNode customUriNode) {
        uriService.populateDirectRelatives(customUriNode);
        // Children are filtered here, which covers the whole tree: every
        // response goes through this method, so a node the caller may not see
        // never appears - not in the dashboard cards and not in the drawer.
        Set<UriNode> children = customUriNode.getChildren().stream()
                .filter(this::isVisible)
                .map(this::loadUriNode).collect(Collectors.toSet());
        customUriNode.setChildren(children);
        return customUriNode;
    }

    /**
     * Roles are deliberately not sent to the client any more. The list this
     * controller returns is already filtered server-side, so a second filter in
     * the browser could only ever remove nodes the user is allowed to see - and
     * it did, because it compared role string ids, which are minted per net
     * version and went stale on every re-import.
     */
    protected EtaskUriNode loadUriNode(UriNode node) {
        EtaskUriNode customUriNode = new EtaskUriNode(node);
        repository.findByUriNodeId(node.getId()).ifPresent(data -> {
            customUriNode.setMenuItemIdentifiers(data.getMenuItemIdentifiers());
            customUriNode.setIcon(data.getIcon());
            customUriNode.setIconSvg(data.isIconSvg());
            customUriNode.setSection(data.getSection());
            customUriNode.setHidden(data.isHidden());
        });
        return customUriNode;
    }
}
