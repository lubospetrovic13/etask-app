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
     * A system admin always sees the whole tree. Without this, mis-configuring
     * a node could hide the only route to the screen that fixes it.
     */
    private static final String SYSTEM_ADMIN = "ROLE_SYSTEMADMIN";

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
        if (authorities.contains(SYSTEM_ADMIN)) {
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
