package com.netgrif.etask.petrinet.service;

import com.netgrif.etask.petrinet.service.interfaces.IModelLinkService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;

/**
 * HMAC-SHA256 over "netId|expiry", with a key generated at startup.
 *
 * The key is deliberately <b>not</b> configured and <b>not</b> persisted. A
 * link lives five minutes, so nothing is lost by invalidating every outstanding
 * one on restart - and a secret that is never written down is a secret that
 * cannot leak from a properties file, an image layer or a git history. The cost
 * is that links do not survive a restart or work across replicas; if this ever
 * runs behind a load balancer with more than one instance, this is the class
 * that has to grow a shared key.
 */
@Slf4j
@Service
public class ModelLinkService implements IModelLinkService {

    private static final Duration VALIDITY = Duration.ofMinutes(5);
    private static final String ALGORITHM = "HmacSHA256";

    private final SecretKeySpec key;

    public ModelLinkService() {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);
        this.key = new SecretKeySpec(secret, ALGORITHM);
        log.info("Model link signing key generated; links are valid for {} minutes and do not survive a restart",
                VALIDITY.toMinutes());
    }

    @Override
    public Duration validity() {
        return VALIDITY;
    }

    @Override
    public String sign(String netId, long expiresAtEpochSecond) {
        try {
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(key);
            byte[] raw = mac.doFinal((netId + "|" + expiresAtEpochSecond).getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
        } catch (Exception e) {
            // Both exceptions here mean the JVM lacks HmacSHA256, which cannot
            // happen on a supported runtime. Failing loudly beats minting a
            // link nobody can verify.
            throw new IllegalStateException("Cannot sign model link", e);
        }
    }

    @Override
    public boolean verify(String netId, long expiresAtEpochSecond, String signature) {
        if (netId == null || signature == null) {
            return false;
        }
        if (Instant.now().getEpochSecond() > expiresAtEpochSecond) {
            return false;
        }
        // Constant time: a plain equals() leaks how much of a guessed signature
        // was right, one byte at a time.
        return MessageDigest.isEqual(
                sign(netId, expiresAtEpochSecond).getBytes(StandardCharsets.UTF_8),
                signature.getBytes(StandardCharsets.UTF_8));
    }
}
