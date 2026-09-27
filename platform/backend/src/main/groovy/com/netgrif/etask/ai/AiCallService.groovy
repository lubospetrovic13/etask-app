package com.netgrif.etask.ai

import groovy.util.logging.Slf4j
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.stereotype.Service

/**
 * Orchestrácia volania LLM podľa aktívnej AI konfigurácie.
 *
 * Jediný vstupný bod pre proces - {@link EtaskActionDelegate#callAIToolByConfig}
 * len presmeruje sem, aby delegát zostal tenký.
 */
@Slf4j
@Service
class AiCallService {

    private final MailPayloadService mailPayloadService
    private final List<AiProviderClient> providerClients

    @Autowired
    AiCallService(MailPayloadService mailPayloadService, List<AiProviderClient> providerClients) {
        this.mailPayloadService = mailPayloadService
        this.providerClients = providerClients
    }

    /**
     * @param params mapa z Petriflow akcie - modelKey, provider, origin, systemPrompt,
     *               userPrompt, temperature, maxTokens, caseId, inputMode a polia mailu
     * @return čitateľný report pre pole test_result
     */
    String callByConfig(Map params) {
        long started = System.currentTimeMillis()
        StringBuilder report = new StringBuilder()

        try {
            String modelKey = (params.modelKey as String)?.trim()
            if (!modelKey) {
                return "Chyba: v konfigurácii nie je kľúč modelu (modelKey)."
            }

            AiProvider provider = AiProvider.resolve(
                    params.provider as String, modelKey, params.origin as String)

            AiProviderClient client = providerClients.find { it.supports(provider) }
            if (!client) {
                return "Chyba: pre poskytovateľa '${provider.key}' nie je adaptér. " +
                        "Dostupní: ${AiProvider.allKeys().join(', ')}."
            }

            Map payload = mailPayloadService.buildPayload(params)

            AiRequest request = new AiRequest(
                    modelKey: modelKey,
                    provider: provider,
                    origin: params.origin as String,
                    systemPrompt: params.systemPrompt as String,
                    userPrompt: injectMessage(params.userPrompt as String, payload.text as String),
                    temperature: toDouble(params.temperature, 0.0d),
                    maxTokens: toInt(params.maxTokens, 4096)
            )

            report << "Model:    ${request.modelKey}\n"
            report << "Provider: ${provider.key}\n"
            report << "Vstup:    ${payload.description}\n"

            AiResult result = client.call(request)

            report << "Volané:   ${result.via}\n"
            report << "Trvanie:  ${System.currentTimeMillis() - started} ms\n"
            if (result.hasTokenCounts()) {
                report << "Tokeny:   vstup ${result.inputTokens}, výstup ${result.outputTokens}\n"
            }
            if (result.note) {
                report << "Pozn.:    ${result.note}\n"
            }
            report << "\n--- Odpoveď modelu ---\n${result.text}"
            return report.toString()

        } catch (Exception e) {
            log.error("Volanie AI podla konfiguracie zlyhalo", e)
            report << "\nVOLANIE ZLYHALO\n${e.getClass().simpleName}: ${e.message}"
            report << "\nTrvanie: ${System.currentTimeMillis() - started} ms"
            return report.toString()
        }
    }

    /**
     * Vloží text mailu do user promptu. Ak prompt zástupný text neobsahuje,
     * pripojí ho na koniec, aby sa volanie nespustilo bez obsahu.
     */
    protected static String injectMessage(String userPrompt, String mailText) {
        if (!userPrompt?.trim()) {
            return mailText
        }
        if (!userPrompt.contains('{{message}}')) {
            return userPrompt + "\n\nObsah mailu:\n" + mailText
        }
        return userPrompt.replace('{{message}}', mailText)
    }

    protected static int toInt(Object o, int fallback) {
        if (o instanceof Number) return ((Number) o).intValue()
        try {
            return Integer.parseInt(String.valueOf(o).trim())
        } catch (Exception ignored) {
            return fallback
        }
    }

    protected static double toDouble(Object o, double fallback) {
        if (o instanceof Number) return ((Number) o).doubleValue()
        try {
            return Double.parseDouble(String.valueOf(o).trim())
        } catch (Exception ignored) {
            return fallback
        }
    }
}
