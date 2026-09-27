package com.netgrif.etask.ai

/**
 * Adaptér na jedného poskytovateľa LLM.
 *
 * Pridanie ďalšieho poskytovateľa = jedna nová trieda s {@code @Service}.
 * {@link AiCallService} si všetky implementácie vyzbiera sám, nikde sa nič
 * neregistruje ručne.
 */
interface AiProviderClient {

    /** Ktorých poskytovateľov tento adaptér obsluhuje. */
    boolean supports(AiProvider provider)

    /** Vykoná volanie. Chybu nech hodí ako výnimku, report ju zachytí. */
    AiResult call(AiRequest request)
}
