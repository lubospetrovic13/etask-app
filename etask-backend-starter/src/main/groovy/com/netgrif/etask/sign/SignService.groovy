package com.netgrif.etask.sign

import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import groovy.util.logging.Slf4j
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service

import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.StandardCharsets
import java.time.Duration

/**
 * Elektronicky podpis cez DocuSeal - jedna vec, ktoru Petriflow akcia sama
 * nevie: HTTP volanie na cudzie API.
 *
 * Preco DocuSeal a preco zo SABLONY:
 *
 *   * OpenSign v self-hosted free verzii API token nema, zmluva by sa z appky
 *     poslat nedala. DocuSeal ma REST API aj v open-source verzii.
 *   * Open-source DocuSeal vie vytvorit podpis len zo sablony
 *     (`POST /api/submissions`); z PDF alebo HTML (`/submissions/pdf|html`)
 *     je to Pro funkcia. Sablonu zmluvy teda raz pripravi clovek v DocuSeale
 *     a jej id je v SLA plane.
 *
 * Polia sablony sa predvyplnia LEN ked v sablone naozaj su - mena sa zistia
 * cez `GET /api/templates/{id}`. Neznamy kluc by DocuSeal odmietol a zmluva by
 * neodisla kvoli predvyplneniu, ktore nikto nepotreboval.
 *
 * Nic tu nevyhadzuje vynimku: vysledok je mapa `ok` / `sprava` a siet ju
 * napise do formulara. Volanie ide z tlacidla v organizacii a chyba cudzej
 * sluzby nesmie zhodit formular.
 *
 * Nastavenie: etask.sign.url (DOCUSEAL_URL), etask.sign.token (DOCUSEAL_API_TOKEN).
 */
@Slf4j
@Service
class SignService {

    @Value('${etask.sign.url:http://localhost:3002}')
    private String url

    @Value('${etask.sign.token:}')
    private String token

    boolean available() {
        return token?.trim() && token.trim() != "''"
    }

    /**
     * Posle sablonu na podpis jednemu podpisujucemu.
     *
     * @param values mena poli -> hodnoty; pouziju sa len tie, ktore sablona ma
     *               (porovnava sa bez ohladu na velkost pismen)
     * @return [ok, submissionId, status, sprava, filled]
     */
    Map send(Object templateId, String email, String name, String role, Map values, String message) {
        if (!available()) {
            return [ok: false, sprava: "Signing is not configured - set DOCUSEAL_API_TOKEN (DocuSeal: Settings -> API)."]
        }
        String tid = (templateId ?: "").toString().trim().replaceAll(/\.0+$/, "")
        if (!tid) {
            return [ok: false, sprava: "The SLA plan has no contract template - fill in its DocuSeal template id."]
        }
        try {
            Map tpl = call("GET", "/api/templates/" + tid, null) as Map
            List fields = (tpl?.fields ?: []) as List
            List roles = ((tpl?.submitters ?: []) as List).collect { (it.name ?: "") as String }.findAll { it }
            String useRole = role && roles.any { it.equalsIgnoreCase(role) } ? roles.find { it.equalsIgnoreCase(role) } : (roles ? roles[0] : role)
            Map filled = [:]
            (values ?: [:]).each { k, v ->
                def f = fields.find { ((it.name ?: "") as String).equalsIgnoreCase(k as String) }
                if (f != null && v != null && (v as String).trim()) {
                    filled[f.name as String] = v as String
                }
            }
            Map submitter = [role: useRole, email: email, name: name]
            if (filled) submitter.values = filled
            Map body = [template_id: tid as Long, send_email: true, submitters: [submitter]]
            if (message) body.message = [subject: "Service Desk contract to sign", body: message]
            def resp = call("POST", "/api/submissions", body)
            List list = resp instanceof List ? resp : ((resp?.submitters ?: []) as List)
            def first = list ? list[0] : null
            def sid = first?.submission_id ?: resp?.id
            if (!sid) {
                return [ok: false, sprava: "DocuSeal did not return a submission: " + abbreviate(JsonOutput.toJson(resp), 300)]
            }
            return [ok: true, submissionId: sid.toString(), status: (first?.status ?: "sent") as String, filled: filled.keySet() as List,
                    sprava: "Contract sent to " + email + " for signature" + (filled ? " (prefilled: " + filled.keySet().join(", ") + ")" : "")]
        } catch (Throwable t) {
            log.warn("DocuSeal send failed: {}", t.message)
            return [ok: false, sprava: "DocuSeal: " + abbreviate(t.message, 400)]
        }
    }

    /**
     * Stav podpisu. `status` je stav DocuSealu: pending, completed, declined,
     * expired (u podpisujuceho aj sent, opened).
     *
     * @return [ok, status, completedAt, documentUrl, auditUrl, sprava]
     */
    Map status(Object submissionId) {
        if (!available()) {
            return [ok: false, sprava: "Signing is not configured - set DOCUSEAL_API_TOKEN."]
        }
        String sid = (submissionId ?: "").toString().trim()
        if (!sid) return [ok: false, sprava: "Nothing was sent for signature yet."]
        try {
            Map s = call("GET", "/api/submissions/" + sid, null) as Map
            String st = (s?.status ?: "") as String
            if (!st) {
                def sub = ((s?.submitters ?: []) as List)
                st = sub ? ((sub[0].status ?: "pending") as String) : "pending"
            }
            String doc = (s?.combined_document_url ?: (((s?.documents ?: []) as List) ? s.documents[0].url : null)) as String
            return [ok: true, status: st, completedAt: s?.completed_at as String, documentUrl: doc,
                    auditUrl: s?.audit_log_url as String, sprava: "DocuSeal status: " + st]
        } catch (Throwable t) {
            log.warn("DocuSeal status failed: {}", t.message)
            return [ok: false, sprava: "DocuSeal: " + abbreviate(t.message, 400)]
        }
    }

    private Object call(String method, String path, Map body) {
        HttpRequest.Builder req = HttpRequest.newBuilder()
                .uri(URI.create(url.replaceAll('/+$', '') + path))
                .timeout(Duration.ofSeconds(20))
                .header("X-Auth-Token", token.trim())
                .header("Accept", "application/json")
        if (body != null) {
            req.header("Content-Type", "application/json")
                    .method(method, HttpRequest.BodyPublishers.ofString(JsonOutput.toJson(body), StandardCharsets.UTF_8))
        } else {
            req.method(method, HttpRequest.BodyPublishers.noBody())
        }
        HttpResponse<String> resp = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build()
                .send(req.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
        if (resp.statusCode().intdiv(100) != 2) {
            throw new IllegalStateException("HTTP " + resp.statusCode() + " " + path + ": " + abbreviate(resp.body(), 300))
        }
        return resp.body() ? new JsonSlurper().parseText(resp.body()) : null
    }

    private static String abbreviate(String s, int max) {
        if (!s) return ""
        return s.length() <= max ? s : s.substring(0, max) + "..."
    }
}
