package com.netgrif.etask.ai

import groovy.transform.ToString

/**
 * Jedno volanie modelu, poskladané z aktívnej AI konfigurácie.
 */
@ToString(includeNames = true, excludes = ['systemPrompt', 'userPrompt'])
class AiRequest {

    /** Presný identifikátor modelu pre API poskytovateľa. */
    String modelKey

    /** Poskytovateľ - určuje, ktorý adaptér request vykoná. */
    AiProvider provider

    /** "local" alebo "external" - rozhoduje o base URL pri OpenAI kompatibilných. */
    String origin

    String systemPrompt

    /** Už s nahradeným zástupným textom obsahu faktúry. */
    String userPrompt

    /**
     * Uplatní sa len tam, kde ju API prijíma. Anthropic ju na aktuálnych modeloch
     * odmieta chybou 400, tam sa vynecháva.
     */
    Double temperature = 0.0d

    Integer maxTokens = 4096
}
