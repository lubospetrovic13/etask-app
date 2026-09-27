package com.netgrif.etask.ai

/**
 * Výsledok jedného volania modelu.
 */
class AiResult {

    /** Text odpovede modelu. */
    String text = ""

    /** Poznámka pre report - odmietnutie, prázdna odpoveď, vynechaný parameter. */
    String note

    long inputTokens = -1L

    long outputTokens = -1L

    /** Čím sa volanie vykonalo, pre report. Napr. "anthropic (SDK)". */
    String via

    boolean hasTokenCounts() {
        return inputTokens >= 0
    }
}
