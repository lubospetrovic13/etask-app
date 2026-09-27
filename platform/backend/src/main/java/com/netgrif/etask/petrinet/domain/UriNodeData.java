package com.netgrif.etask.petrinet.domain;

import lombok.Data;
import lombok.NoArgsConstructor;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

import java.util.List;
import java.util.Set;

@Data
@Document
@NoArgsConstructor
public class UriNodeData {

    @Id
    private ObjectId id;

    @Indexed
    private String uriNodeId;

    private String icon;
    private String section;
    private boolean isIconSvg = false;
    private boolean isHidden = false;
    private List<String> menuItemIdentifiers;

    /**
     * Legacy: role string ids, kept only so UriNodeDataRunner can migrate them
     * to {@link #requiredProcessRoles} and clear them.
     *
     * <p>It never worked reliably. A role's string id is minted per net version,
     * so the list went stale on every re-import - and the only consumer was a
     * client-side filter over a list the server had already filtered. Do not
     * write to it.
     */
    @Deprecated
    @Field("processRolesIds")
    private Set<String> legacyProcessRolesIds;

    /**
     * Authority names, e.g. ROLE_ADMIN. When non-empty, only a user holding at
     * least one of them sees the node.
     */
    private Set<String> requiredAuthorities;

    /**
     * Process role import ids, e.g. agent. When non-empty, only a user holding
     * at least one process role with a matching import id sees the node.
     *
     * Import ids rather than role string ids on purpose: a role's string id is
     * minted per net version, so every re-import of a process would mint new
     * ones and silently invalidate the list. The import id is the id written in
     * the Petriflow XML and survives re-imports.
     */
    private Set<String> requiredProcessRoles;

    /**
     * @param requiredProcessRoles process role <em>import ids</em>, not string ids.
     */
    public UriNodeData(String uriNodeId, String section, String icon, boolean isIconSvg,
                       boolean isHidden, Set<String> requiredProcessRoles,
                       List<String> menuItemIdentifiers) {
        this.uriNodeId = uriNodeId;
        this.icon = icon;
        this.section = section;
        this.isIconSvg = isIconSvg;
        this.isHidden = isHidden;
        this.requiredProcessRoles = requiredProcessRoles;
        this.menuItemIdentifiers = menuItemIdentifiers;
    }
}
