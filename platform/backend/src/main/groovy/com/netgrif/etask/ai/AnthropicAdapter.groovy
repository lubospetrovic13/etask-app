package com.netgrif.etask.ai

import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service

/**
 * Anthropic Messages API.
 *
 * Zámerne priamo cez HTTP a nie cez oficiálne Java SDK: SDK 2.34.0 je skompilované
 * proti Kotlin stdlib 1.8+, kým Netgrif Application Engine so Spring Bootom 2.x
 * pinuje Kotlin 1.6.21. Kompilácia prešla, ale deserializácia odpovede padala na
 * NoClassDefFoundError kotlin/jvm/optionals/OptionalsKt. Zdvihnutie Kotlinu pod
 * celou platformou je väčšie riziko než jeden POST request.
 *
 * Kľúč sa berie z premennej prostredia ANTHROPIC_API_KEY cez application.properties,
 * nikdy nie z Petriflow poľa.
 */
@Service
class AnthropicAdapter implements AiProviderClient {

    /** Verzia Anthropic API, posiela sa v hlavičke anthropic-version. */
    private static final String API_VERSION = "2023-06-01"

    @Value('${ai.anthropic.base-url:https://api.anthropic.com}')
    private String baseUrl

    @Value('${ai.anthropic.api-key:}')
    private String apiKey

    @Value('${ai.timeout-seconds:180}')
    private int timeoutSeconds

    @Override
    boolean supports(AiProvider provider) {
        return provider == AiProvider.ANTHROPIC
    }

    @Override
    AiResult call(AiRequest request) {
        if (!apiKey?.trim()) {
            throw new IllegalStateException("Nie je nastavený ANTHROPIC_API_KEY " +
                    "(property ai.anthropic.api-key).")
        }

        Map body = [
                model     : request.modelKey,
                max_tokens: request.maxTokens,
                messages  : [[role: "user", content: request.userPrompt]]
        ]
        if (request.systemPrompt?.trim()) {
            body.system = request.systemPrompt
        }
        // temperature sa zámerne neposiela - na Claude Opus 5, Sonnet 5, Opus 4.8
        // a novších je parameter odstránený a request by skončil chybou 400.

        Map headers = [
                "x-api-key"        : apiKey.trim(),
                "anthropic-version": API_VERSION
        ]

        def root = AiHttp.postJson(
                "${AiHttp.trimSlash(baseUrl)}/v1/messages", headers, body, timeoutSeconds)

        AiResult result = new AiResult(via: "anthropic (Messages API ${API_VERSION})" as String)

        // content je zoznam blokov, textové majú type=text
        def blocks = (root?.content instanceof List) ? (root.content as List) : []
        result.text = blocks
                .findAll { b -> b?.type == "text" && b?.text }
                .collect { b -> b.text as String }
                .join("\n")
                .trim()

        result.inputTokens = (root?.usage?.input_tokens ?: -1L) as long
        result.outputTokens = (root?.usage?.output_tokens ?: -1L) as long

        // Bezpečnostné klasifikátory môžu request odmietnuť - vráti sa HTTP 200
        // s prázdnym obsahom, takže to treba ošetriť zvlášť.
        if (root?.stop_reason == "refusal") {
            result.note = "Model request odmietol. Kategória: ${root?.stop_details?.category}, " +
                    "dôvod: ${root?.stop_details?.explanation ?: ''}" as String
        } else if (!result.text) {
            result.note = "Model vrátil prázdnu odpoveď (stop_reason=${root?.stop_reason}). " +
                    "Pri max_tokens skús hodnotu zvýšiť." as String
        } else if (root?.stop_reason == "max_tokens") {
            result.note = "Odpoveď je useknutá na limite max_tokens, zvýš ho."
        }

        String tempNote = "temperature sa na Anthropic modely neposiela, aktuálne modely ju odmietajú chybou 400"
        result.note = result.note ? (result.note + " | " + tempNote) : tempNote
        return result
    }
}
