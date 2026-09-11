package com.netgrif.etask.petrinet.service.interfaces;

import java.time.Duration;

/**
 * Short-lived, signed permission to read one process model without being
 * logged in.
 *
 * The Netgrif builder opens a model from {@code ?modelUrl=<url>} and fetches
 * that URL <b>itself</b>, from its own page, with no header of ours - so the
 * caller's session never reaches it. Verified against the running engine:
 * {@code /api/petrinet/{id}/file} answers 401 anonymously, the token is
 * accepted only as a header (every query-string spelling returns 401), and an
 * anonymous session cannot read it either. A model the builder can open must
 * therefore be readable without authentication, and this is the narrowest way
 * to allow that: one net, for a few minutes, for whoever holds the signature.
 */
public interface IModelLinkService {

    /** How long a minted link stays valid. */
    Duration validity();

    /**
     * Signature binding one net id to one expiry. Both go into the URL, so both
     * are covered - otherwise the expiry could simply be edited.
     */
    String sign(String netId, long expiresAtEpochSecond);

    /** Whether the signature matches and has not expired. */
    boolean verify(String netId, long expiresAtEpochSecond, String signature);
}
