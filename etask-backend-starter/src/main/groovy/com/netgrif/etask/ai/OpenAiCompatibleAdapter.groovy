package com.netgrif.etask.ai

import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service

/**
 * OpenAI Chat Completions a všetko, čo hovorí ten istý protokol -
 * Ollama, vLLM, LM Studio, Groq, Together, OpenRouter a podobne.
 *
 * Base URL sa vyberá podľa poskytovateľa:
 *   OPENAI  -> ai.openai.base-url    + ai.openai.api-key
 *   LOCAL   -> ai.local.base-url     (bez kľúča)
 *   CUSTOM  -> ai.custom.base-url    + ai.custom.api-key
 */
@Service
class OpenAiCompatibleAdapter implements AiProviderClient {

    @Value('${ai.openai.base-url:https://api.openai.com}')
    private String openAiBaseUrl

    @Value('${ai.openai.api-key:}')
    private String openAiApiKey

    @Value('${ai.local.base-url:http://localhost:11434}')
    private String localBaseUrl

    @Value('${ai.custom.base-url:}')
    private String customBaseUrl

    @Value('${ai.custom.api-key:}')
    private String customApiKey

    @Value('${ai.timeout-seconds:180}')
    private int timeoutSeconds

    /**
     * Niektoré novšie OpenAI modely neprijímajú max_tokens a chcú
     * max_completion_tokens. Ak na to narazíš, prepni to prepínačom.
     */
    @Value('${ai.openai.use-max-completion-tokens:false}')
    private boolean useMaxCompletionTokens

    @Override
    boolean supports(AiProvider provider) {
        return provider == AiProvider.OPENAI ||
                provider == AiProvider.LOCAL ||
                provider == AiProvider.CUSTOM
    }

    @Override
    AiResult call(AiRequest request) {
        String baseUrl
        String apiKey

        switch (request.provider) {
            case AiProvider.OPENAI:
                baseUrl = openAiBaseUrl
                apiKey = openAiApiKey
                break
            case AiProvider.LOCAL:
                baseUrl = localBaseUrl
                apiKey = null
                break
            default:
                baseUrl = customBaseUrl
                apiKey = customApiKey
                break
        }

        if (!baseUrl?.trim()) {
            throw new IllegalStateException("Pre poskytovateľa ${request.provider} nie je nastavená base URL. " +
                    "Doplň ai.${request.provider.key}.base-url do application.properties.")
        }

        List messages = []
        if (request.systemPrompt?.trim()) {
            messages << [role: "system", content: request.systemPrompt]
        }
        messages << [role: "user", content: request.userPrompt]

        Map body = [
                model      : request.modelKey,
                messages   : messages,
                temperature: request.temperature,
                stream     : false
        ]
        if (useMaxCompletionTokens && request.provider == AiProvider.OPENAI) {
            body.max_completion_tokens = request.maxTokens
        } else {
            body.max_tokens = request.maxTokens
        }

        Map headers = [:]
        if (apiKey?.trim()) {
            headers["Authorization"] = "Bearer ${apiKey}"
        }

        def root = AiHttp.postJson(
                "${AiHttp.trimSlash(baseUrl)}/v1/chat/completions", headers, body, timeoutSeconds)

        AiResult result = new AiResult(via: "${request.provider.key} (OpenAI kompatibilné API, ${AiHttp.trimSlash(baseUrl)})" as String)
        def content = root?.choices?.getAt(0)?.message?.content
        if (content == null) {
            result.note = "V odpovedi nie je choices[0].message.content, vraciam celé telo."
            result.text = groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(root))
        } else {
            result.text = content.toString().trim()
        }
        result.inputTokens = (root?.usage?.prompt_tokens ?: -1L) as long
        result.outputTokens = (root?.usage?.completion_tokens ?: -1L) as long

        def finishReason = root?.choices?.getAt(0)?.finish_reason
        if (finishReason && finishReason != "stop") {
            String extra = "finish_reason=${finishReason}" + (finishReason == "length"
                    ? " - odpoveď je useknutá, zvýš max_tokens" : "")
            result.note = result.note ? (result.note + " | " + extra) : extra
        }
        return result
    }
}
