package com.netgrif.etask.petrinet.service.interfaces;

import com.netgrif.application.engine.auth.domain.IUser;
import com.netgrif.etask.petrinet.domain.UriNodeData;

public interface IUriNodeVisibilityService {

    /**
     * @param data per-node configuration, may be null for an unconfigured node
     * @param user the caller, may be null
     * @return true when the user may see the node
     */
    boolean isVisible(UriNodeData data, IUser user);
}
