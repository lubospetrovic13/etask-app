package com.netgrif.etask.mail

import com.netgrif.application.engine.mail.interfaces.IMailService
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.context.annotation.Primary
import org.springframework.mail.javamail.JavaMailSender

/**
 * Registruje {@link EtaskMailService} ako prednostny `IMailService`.
 *
 * `@Primary` a NOVE MENO BEANU (`etaskMailService`), nie prepisanie enginoveho
 * `mailService`. Prepisanie rovnakym menom vyzaduje
 * `spring.main.allow-bean-definition-overriding=true` a zavisi od poradia,
 * v ktorom Spring konfiguracie nacita - teda by sa rozbilo ticho a inde.
 * Takto engine svoj bean drzi dalej a kazdy, kto si pyta `IMailService`
 * (`AuthenticationController`, `ActionDelegate`), dostane nas.
 */
@Configuration
class EtaskMailConfiguration {

    /**
     * Ta ista freemarker `Configuration`, aku pouziva engine. Sablony sa z nej
     * beru z classpathu `/templates`, takze `src/main/resources/templates/`
     * tohto modulu tieni sablony z jaru.
     */
    @Autowired
    private freemarker.template.Configuration freemarkerConfiguration

    @Bean
    @Primary
    IMailService etaskMailService(JavaMailSender mailSender) {
        EtaskMailService service = new EtaskMailService()
        service.setMailSender(mailSender)
        // To iste, co robi MailConfiguration enginu. Opakuje sa zamerne:
        // poradie konfiguracii nie je zarucene a bez template loadera by
        // `getTemplate("registration.html")` skoncil na FileNotFound.
        freemarkerConfiguration.setClassForTemplateLoading(getClass(), "/templates")
        service.setConfiguration(freemarkerConfiguration)
        return service
    }
}
