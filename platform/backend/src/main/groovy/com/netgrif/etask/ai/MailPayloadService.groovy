package com.netgrif.etask.ai

import com.netgrif.application.engine.workflow.domain.Case
import com.netgrif.application.engine.workflow.service.interfaces.IWorkflowService
import groovy.json.JsonSlurper
import groovy.util.logging.Slf4j
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.stereotype.Service

import com.netgrif.etask.doc.DocumentTextService

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Paths
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream

/**
 * Zloží text došlého mailu, ktorý sa pošle modelu. Žiadne čítanie schránky -
 * dáta prídu z procesu jedným z troch spôsobov:
 *
 *   form  - používateľ vyplní polia od, komu, predmet, telo, prílohy
 *   json  - vloží JSON v tvare nižšie
 *   zip   - nahrá archív, v ktorom je mail.json a/alebo textové prílohy
 *
 * Tvar JSON-u (rovnaký pre režim json aj pre mail.json v ZIP-e):
 * <pre>
 * {
 *   "from": "dodavatel@firma.sk",
 *   "to": "faktury@nasafirma.sk",
 *   "subject": "Faktúra 2026001",
 *   "body": "V prílohe posielame faktúru...",
 *   "attachments": [
 *     { "name": "faktura.pdf", "text": "FAKTÚRA č. 2026001 ..." }
 *   ]
 * }
 * </pre>
 */
@Slf4j
@Service
class MailPayloadService {

    @org.springframework.beans.factory.annotation.Autowired
    private DocumentTextService documentTextService

    private final IWorkflowService workflowService

    @Autowired
    MailPayloadService(IWorkflowService workflowService) {
        this.workflowService = workflowService
    }

    /**
     * @param params mapa z Petriflow akcie
     * @return [text: text pre model, description: čo sa použilo, do reportu]
     */
    Map buildPayload(Map params) {
        String mode = (params.inputMode ?: "form") as String

        switch (mode) {
            case "json":
                return fromJson(params.mailJson as String)
            case "zip":
                return fromZip(params.caseId as String, params.zipFieldId as String)
            case "form":
                return fromForm(params)
            default:
                throw new IllegalArgumentException("Neznámy režim vstupu: ${mode}")
        }
    }

    // ------------------------------------------------------------------
    // Režim form
    // ------------------------------------------------------------------

    private Map fromForm(Map params) {
        Map mail = [
                from       : params.mailFrom,
                to         : params.mailTo,
                subject    : params.mailSubject,
                body       : params.mailBody,
                attachments: splitAttachments(params.mailAttachments as String)
        ]
        if (!mail.body?.toString()?.trim() && !mail.attachments) {
            throw new IllegalArgumentException(
                    "Vo formulári nie je ani telo mailu, ani príloha. Vyplň aspoň jedno.")
        }
        String text = renderMail(mail)
        return [text: text, description: "formulár (${text.length()} znakov)" as String]
    }

    /**
     * Prílohy z formulára sú jeden textarea blok. Oddeľovač "---" umožní vložiť
     * viac príloh; bez neho je to jedna príloha.
     */
    private static List splitAttachments(String raw) {
        if (!raw?.trim()) return []
        List parts = raw.split(/(?m)^-{3,}\s*$/) as List
        return parts.findAll { it?.trim() }.withIndex().collect { part, idx ->
            [name: "priloha_${idx + 1}" as String, text: (part as String).trim()]
        }
    }

    // ------------------------------------------------------------------
    // Režim json
    // ------------------------------------------------------------------

    private Map fromJson(String raw) {
        if (!raw?.trim()) {
            throw new IllegalArgumentException("Pole s JSON-om je prázdne.")
        }
        def parsed
        try {
            parsed = new JsonSlurper().parseText(raw)
        } catch (Exception e) {
            throw new IllegalArgumentException("JSON sa nedá rozparsovať: ${e.message}")
        }
        if (!(parsed instanceof Map)) {
            throw new IllegalArgumentException("JSON musí byť objekt, nie ${parsed?.getClass()?.simpleName}.")
        }
        String text = renderMail(parsed as Map)
        return [text: text, description: "vložený JSON (${text.length()} znakov)" as String]
    }

    // ------------------------------------------------------------------
    // Režim zip
    // ------------------------------------------------------------------

    private Map fromZip(String caseId, String zipFieldId) {
        Case useCase = workflowService.findOne(caseId)
        if (!useCase) {
            throw new IllegalStateException("Case ${caseId} sa nenašiel.")
        }
        def fileValue = useCase.dataSet[zipFieldId]?.value
        if (!fileValue) {
            throw new IllegalStateException("Pole ${zipFieldId} je prázdne, nahraj ZIP.")
        }
        def zipPath = Paths.get(fileValue.path as String)
        if (!Files.exists(zipPath)) {
            throw new IllegalStateException("Súbor sa nenašiel na ceste ${zipPath}")
        }

        Map mailFromJson = null
        List attachments = []
        List<String> skipped = []

        Files.newInputStream(zipPath).withCloseable { stream ->
            ZipInputStream zis = new ZipInputStream(stream, StandardCharsets.UTF_8)
            ZipEntry entry
            while ((entry = zis.nextEntry) != null) {
                if (entry.directory) continue
                String name = entry.name
                byte[] bytes = zis.bytes

                if (name.toLowerCase().endsWith("mail.json")) {
                    try {
                        def parsed = new JsonSlurper().parseText(new String(bytes, StandardCharsets.UTF_8))
                        if (parsed instanceof Map) {
                            mailFromJson = parsed as Map
                        }
                    } catch (Exception e) {
                        skipped << "${name} (nečitateľný JSON: ${e.message})".toString()
                    }
                    continue
                }

                String text = extractText(name, bytes)
                if (text?.trim()) {
                    attachments << [name: name, text: text.trim()]
                } else {
                    skipped << name
                }
            }
        }

        Map mail = mailFromJson ?: [:]
        // Prílohy zo súborov v ZIP-e sa pripoja k tým z mail.json.
        List fromJsonAttachments = (mail.attachments instanceof List) ? (mail.attachments as List) : []
        mail.attachments = fromJsonAttachments + attachments

        if (!mail.body?.toString()?.trim() && !mail.attachments) {
            throw new IllegalStateException("V ZIP-e nie je nič použiteľné. " +
                    (skipped ? "Preskočené: ${skipped.join(', ')}. " : "") +
                    "Na PDF a skeny treba doplniť extrakciu v metóde extractText.")
        }

        String desc = "ZIP" +
                (mailFromJson ? ", mail.json" : "") +
                ", príloh ${mail.attachments.size()}" +
                (skipped ? ", preskočené: ${skipped.join(', ')}" : "")
        return [text: renderMail(mail), description: desc.toString()]
    }

    /**
     * Prevod obsahu súboru na text. Textové formáty rovno, PDF cez textovú
     * vrstvu a skeny cez OCR — všetko v {@link DocumentTextService}, teda to
     * isté, čo číta faktúry v procese `schvalovanie/fa_faktura`. Zámerne jedna
     * cesta pre oboje: keď sa OCR doladí pre faktúry, prílohy mailu ho majú
     * tiež, a nie sú to dve implementácie, ktoré sa rozídu.
     *
     * DOCX zatiaľ nie — potreboval by ďalšiu závislosť (poi-ooxml), kým PDFBox
     * je v classpath tranzitívne z `application-engine`.
     */
    protected String extractText(String entryName, byte[] bytes) {
        String lower = entryName.toLowerCase()
        if (lower.endsWith(".txt") || lower.endsWith(".md") || lower.endsWith(".csv")
                || lower.endsWith(".json") || lower.endsWith(".xml") || lower.endsWith(".html")
                || lower.endsWith(".eml")) {
            return new String(bytes, StandardCharsets.UTF_8)
        }
        DocumentTextService.Extracted ex = documentTextService.extract(bytes, entryName)
        return ex.isEmpty() ? null : ex.text
    }

    // ------------------------------------------------------------------

    /**
     * Zloží jednotný textový blok, ktorý dostane model. Rovnaký tvar pre všetky
     * tri režimy, aby prompt nemusel riešiť, odkiaľ dáta prišli.
     */
    protected static String renderMail(Map mail) {
        StringBuilder sb = new StringBuilder()
        appendIf(sb, "Od", mail.from)
        appendIf(sb, "Komu", mail.to)
        appendIf(sb, "Predmet", mail.subject)
        appendIf(sb, "Dátum", mail.date)

        if (mail.body?.toString()?.trim()) {
            sb << "\nTelo mailu:\n" << mail.body.toString().trim() << "\n"
        }

        List attachments = (mail.attachments instanceof List) ? (mail.attachments as List) : []
        attachments.eachWithIndex { att, idx ->
            String name = (att instanceof Map ? att.name : null) ?: "priloha_${idx + 1}"
            String text = (att instanceof Map ? att.text : att)?.toString()
            if (text?.trim()) {
                sb << "\nPríloha ${idx + 1} (${name}):\n" << text.trim() << "\n"
            }
        }
        return sb.toString().trim()
    }

    private static void appendIf(StringBuilder sb, String label, Object value) {
        if (value?.toString()?.trim()) {
            sb << "${label}: ${value.toString().trim()}\n"
        }
    }
}
