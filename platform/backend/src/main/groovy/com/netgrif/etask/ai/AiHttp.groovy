package com.netgrif.etask.ai

import groovy.json.JsonOutput
import groovy.json.JsonSlurper

import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.StandardCharsets
import java.time.Duration

/**
 * Minimálny JSON HTTP klient pre REST adaptéry. Java 11 HttpClient, žiadna
 * ďalšia závislosť.
 */
class AiHttp {

    /**
     * @return rozparsované telo odpovede
     * @throws IllegalStateException pri stavovom kóde mimo 2xx, so skrátenym telom v správe
     */
    static Object postJson(String url, Map headers, Map body, int timeoutSeconds) {
        HttpRequest.Builder req = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(JsonOutput.toJson(body), StandardCharsets.UTF_8))

        headers?.each { k, v ->
            if (v?.toString()?.trim()) {
                req.header(k as String, v as String)
            }
        }

        HttpClient http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .build()

        HttpResponse<String> resp = http.send(req.build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))

        if (resp.statusCode().intdiv(100) != 2) {
            throw new IllegalStateException(
                    "Endpoint vrátil HTTP ${resp.statusCode()} pre ${url}: ${abbreviate(resp.body(), 800)}")
        }
        return new JsonSlurper().parseText(resp.body())
    }

    static String trimSlash(String s) {
        return s?.replaceAll('/+$', '')
    }

    static String abbreviate(String s, int max) {
        if (!s) return ""
        return s.length() <= max ? s : s.substring(0, max) + "..."
    }
}
