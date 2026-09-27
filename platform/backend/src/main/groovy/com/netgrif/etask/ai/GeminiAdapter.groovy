package com.netgrif.etask.ai

import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service

/**
 * Google Gemini - generateContent.
 *
 * Tvar requestu je iný než OpenAI: system prompt ide do samostatného
 * system_instruction, správy do contents s parts, a limity do generationConfig.
 * Preto vlastný adaptér a nie zdieľanie s OpenAI cestou.
 */
@Service
class GeminiAdapter implements AiProviderClient {

    @Value('${ai.gemini.base-url:https://generativelanguage.googleapis.com}')
    private String baseUrl

    @Value('${ai.gemini.api-version:v1beta}')
    private String apiVersion

    @Value('${ai.gemini.api-key:}')
    private String apiKey

    @Value('${ai.timeout-seconds:180}')
    private int timeoutSeconds

    @Override
    boolean supports(AiProvider provider) {
        return provider == AiProvider.GEMINI
    }

    @Override
    AiResult call(AiRequest request) {
        if (!apiKey?.trim()) {
            throw new IllegalStateException("Nie je nastavený ai.gemini.api-key.")
        }

        // Gemini akceptuje aj "models/gemini-..." aj holé "gemini-..."
        String model = request.modelKey.startsWith("models/")
                ? request.modelKey.substring("models/".length())
                : request.modelKey

        Map body = [
                contents        : [[role: "user", parts: [[text: request.userPrompt]]]],
                generationConfig: [
                        temperature    : request.temperature,
                        maxOutputTokens: request.maxTokens
                ]
        ]
        if (request.systemPrompt?.trim()) {
            body.system_instruction = [parts: [[text: request.systemPrompt]]]
        }

        String url = "${AiHttp.trimSlash(baseUrl)}/${apiVersion}/models/${model}:generateContent"
        def root = AiHttp.postJson(url, ["x-goog-api-key": apiKey], body, timeoutSeconds)

        AiResult result = new AiResult(via: "gemini (${apiVersion})" as String)

        def candidate = root?.candidates?.getAt(0)
        def parts = candidate?.content?.parts
        if (parts) {
            result.text = parts.collect { it?.text }.findAll { it }.join("\n").trim()
        }

        if (!result.text) {
            // Gemini pri zablokovaní vráti 200 s promptFeedback a bez kandidáta.
            def blocked = root?.promptFeedback?.blockReason
            result.note = blocked
                    ? "Gemini request zablokoval, blockReason=${blocked}" as String
                    : "Gemini vrátil prázdnu odpoveď."
            if (!blocked) {
                result.text = groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(root))
            }
        }

        def finishReason = candidate?.finishReason
        if (finishReason && finishReason != "STOP") {
            String extra = "finishReason=${finishReason}" + (finishReason == "MAX_TOKENS"
                    ? " - odpoveď je useknutá, zvýš max_tokens" : "")
            result.note = result.note ? (result.note + " | " + extra) : extra
        }

        result.inputTokens = (root?.usageMetadata?.promptTokenCount ?: -1L) as long
        result.outputTokens = (root?.usageMetadata?.candidatesTokenCount ?: -1L) as long
        return result
    }
}
