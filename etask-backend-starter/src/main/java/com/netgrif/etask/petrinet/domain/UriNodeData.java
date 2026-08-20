package com.netgrif.etask.petrinet.domain;

import lombok.Data;
import lombok.NoArgsConstructor;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

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
    private Set<String> processRolesIds;
    private List<String> menuItemIdentifiers;

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

    public UriNodeData(String uriNodeId, String section, String icon, boolean isIconSvg, boolean isHidden, Set<String> processRolesIds, List<String> menuItemIdentifiers) {
        this.uriNodeId = uriNodeId;
        this.icon = icon;
        this.section = section;
        this.isIconSvg = isIconSvg;
        this.isHidden = isHidden;
        this.processRolesIds = processRolesIds;
        this.menuItemIdentifiers = menuItemIdentifiers;
    }
}
