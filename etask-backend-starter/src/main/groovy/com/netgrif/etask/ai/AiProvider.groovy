package com.netgrif.etask.ai

/**
 * Poskytovateľ LLM. Je to routovací kľúč - podľa neho sa vyberá adaptér,
 * ktorý vie zložiť request v správnom tvare.
 *
 * Kľúč sa v číselníku modelov zapisuje ako tretie pole riadku:
 *     claude-opus-5 | Claude Opus 5 | anthropic
 *
 * Ak sa neuvedie, odvodí sa z názvu modelu a z pôvodu (viď {@link #resolve}).
 */
enum AiProvider {

    /** Anthropic Claude cez oficiálne Java SDK. */
    ANTHROPIC("anthropic"),

    /** OpenAI Chat Completions. */
    OPENAI("openai"),

    /** Google Gemini generateContent. */
    GEMINI("gemini"),

    /** Lokálny OpenAI kompatibilný server - Ollama, vLLM, LM Studio. */
    LOCAL("local"),

    /** Iný externý OpenAI kompatibilný endpoint. */
    CUSTOM("custom")

    final String key

    AiProvider(String key) {
        this.key = key
    }

    static AiProvider byKey(String key) {
        if (!key?.trim()) return null
        String k = key.trim().toLowerCase()
        return values().find { it.key == k }
    }

    /**
     * Určí poskytovateľa. Explicitná hodnota z číselníka má prednosť; ak chýba,
     * odvodí sa z predpony názvu modelu a nakoniec z pôvodu (local / external).
     *
     * @param declared hodnota z číselníka, môže byť null
     * @param modelKey identifikátor modelu, napr. claude-opus-5
     * @param origin   "local" alebo "external"
     */
    static AiProvider resolve(String declared, String modelKey, String origin) {
        AiProvider explicit = byKey(declared)
        if (explicit) return explicit

        String m = (modelKey ?: "").trim().toLowerCase()
        if (m.startsWith("claude-") || m.startsWith("anthropic.claude-")) return ANTHROPIC
        if (m.startsWith("gpt-") || m.startsWith("chatgpt") || m ==~ /^o[1-9].*/) return OPENAI
        if (m.startsWith("gemini") || m.startsWith("models/gemini")) return GEMINI

        return "local".equalsIgnoreCase(origin ?: "") ? LOCAL : CUSTOM
    }

    /** Zoznam kľúčov pre nápovedu a validáciu v procese. */
    static List<String> allKeys() {
        return values().collect { it.key }
    }

    @Override
    String toString() {
        return key
    }
}
