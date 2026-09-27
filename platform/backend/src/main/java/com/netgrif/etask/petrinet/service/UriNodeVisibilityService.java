package com.netgrif.etask.petrinet.service;

import com.netgrif.application.engine.auth.domain.Authority;
import com.netgrif.application.engine.auth.domain.IUser;
import com.netgrif.application.engine.petrinet.domain.roles.ProcessRole;
import com.netgrif.etask.petrinet.domain.UriNodeData;
import com.netgrif.etask.petrinet.service.interfaces.IUriNodeVisibilityService;
import org.springframework.stereotype.Service;

import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Decides whether a user may see a URI node.
 *
 * A UriNode carries no permissions of its own - the engine's document has no
 * roles field, and the engine's URI endpoints take no user - so before this the
 * whole menu tree was visible to every authenticated user regardless of what
 * they could actually open. The per-node data this reads
 * ({@link UriNodeData}) already existed in this project and already travelled
 * to the frontend; nothing had ever filtered on it.
 *
 * The rule is deliberately fail-open for unconfigured nodes: a node with no
 * requirements stays visible to everyone, so adding this changes nothing until
 * a node is configured. Restricting a node is then an explicit act.
 */
@Service
public class UriNodeVisibilityService implements IUriNodeVisibilityService {

    /**
     * Admins always see the whole tree.
     *
     * ROLE_SYSTEMADMIN is here because mis-configuring a node could otherwise
     * hide the only route to the screen that fixes it.
     *
     * ROLE_ADMIN is here because the engine already lets it create a case of
     * ANY net - verified against a running engine: an admin without the
     * `manager` process role created a `service_desk/sd_customer` case (200)
     * while a plain user got 403. Hiding the card was therefore never a
     * restriction, only a way to make a permission the admin already has
     * unreachable from the UI: no card means no view, and no view means no
     * "+" button. Filtering the menu below what the API allows is a lie, not
     * a control.
     */
    private static final Set<String> ADMIN_AUTHORITIES = Set.of("ROLE_SYSTEMADMIN", "ROLE_ADMIN");

    @Override
    public boolean isVisible(UriNodeData data, IUser user) {
        if (data == null) {
            return true;
        }
        if (user == null) {
            // No identity, no restricted content. Anonymous callers reach the
            // public task endpoints, not the menu.
            return isUnrestricted(data);
        }

        Set<String> authorities = authorityNames(user);
        if (authorities.stream().anyMatch(ADMIN_AUTHORITIES::contains)) {
            return true;
        }

        Set<String> required = data.getRequiredAuthorities();
        if (isNotEmpty(required) && required.stream().noneMatch(authorities::contains)) {
            return false;
        }

        Set<String> requiredRoles = data.getRequiredProcessRoles();
        if (isNotEmpty(requiredRoles)) {
            Set<String> held = processRoleImportIds(user);
            return requiredRoles.stream().anyMatch(held::contains);
        }
        return true;
    }

    private boolean isUnrestricted(UriNodeData data) {
        return !isNotEmpty(data.getRequiredAuthorities()) && !isNotEmpty(data.getRequiredProcessRoles());
    }

    private boolean isNotEmpty(Set<String> set) {
        return set != null && !set.isEmpty();
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

    private Set<String> processRoleImportIds(IUser user) {
        Set<ProcessRole> roles = user.getProcessRoles();
        if (roles == null) {
            return Set.of();
        }
        return roles.stream()
                .map(ProcessRole::getImportId)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());
    }
}
