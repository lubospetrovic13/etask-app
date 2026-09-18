package com.netgrif.etask.mail

import com.netgrif.application.engine.auth.domain.RegisteredUser
import com.netgrif.application.engine.auth.service.interfaces.IRegistrationService
import com.netgrif.application.engine.configuration.properties.ServerAuthProperties
import com.netgrif.application.engine.mail.EmailType
import com.netgrif.application.engine.mail.MailService
import com.netgrif.application.engine.mail.domain.MailDraft
import freemarker.template.TemplateException
import groovy.util.logging.Slf4j
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.beans.factory.annotation.Value

import javax.mail.MessagingException
import javax.mail.internet.MimeMessage
import java.time.format.DateTimeFormatter

/**
 * Registracny mail a mail na obnovu hesla s VLASTNYM PREDMETOM.
 *
 * Telo mailu sa da prepisat bez Javy: `MailService` berie sablony cez
 * `configuration.getTemplate(...)` z classpathu `/templates`, takze subor
 * `src/main/resources/templates/registration.html` tieni ten z jaru. To je
 * cela sablona a nic viac na nu netreba.
 *
 * PREDMET sa takto prepisat NEDA. `MailService` ho berie z
 * `EmailType.REGISTRATION.getSubject()`, co je natvrdo `"Registration invite"`
 * v enume enginu - bez setteru, bez property, bez modelu. Cela appka je pritom
 * dvojjazycna a chodi slovenskym ludom. To je ta chybajuca vec, kvoli ktorej
 * tu servis vobec je: engine nema ziadny extension point na predmet
 * systemoveho mailu.
 *
 * Preto sa prekryvaju obe `send*` metody. Telo, model aj odkaz zostavaju
 * enginove - meni sa jedine predmet. Bean je `@Primary`, nie prepisany
 * (`mailService` z `MailConfiguration` existuje dalej), lebo prepisanie beanu
 * rovnakym menom by vyzadovalo `spring.main.allow-bean-definition-overriding`
 * a rozbilo by sa ticho pri kazdej zmene poradia konfiguracii.
 *
 * Predmety sa daju zmenit bez zasahu do kodu:
 *   etask.mail.subject.registration
 *   etask.mail.subject.password-reset
 */
@Slf4j
class EtaskMailService extends MailService {

    /**
     * Vlastne autowire: v `MailService` su oba servisy `private`, takze
     * z podtriedy sa na ne nedostaneme, hoci su to tie iste beany.
     */
    @Autowired
    private IRegistrationService registrationServiceRef

    @Autowired
    private ServerAuthProperties serverAuthPropertiesRef

    @Value('${etask.mail.subject.registration:eTask - invitation}')
    private String subjectRegistration

    @Value('${etask.mail.subject.password-reset:eTask - password reset}')
    private String subjectPasswordReset

    @Override
    void sendRegistrationEmail(RegisteredUser user) throws MessagingException, IOException, TemplateException {
        Map<String, Object> model = model(user)
        MailDraft draft = MailDraft.builder(getMailFrom(), [user.email])
                .subject(subjectRegistration)
                .body(getConfiguration().getTemplate(EmailType.REGISTRATION.template).toString())
                .model(model)
                .build()
        MimeMessage email = buildEmail(draft)
        getMailSender().send(email)
        log.info("Registracny mail poslany na [${user.email}], odkaz plati do [${model.expiration}]")
    }

    @Override
    void sendPasswordResetEmail(RegisteredUser user) throws MessagingException, IOException, TemplateException {
        Map<String, Object> model = model(user)
        model.put(NAME, user.name)
        MailDraft draft = MailDraft.builder(getMailFrom(), [user.email])
                .subject(subjectPasswordReset)
                .body(getConfiguration().getTemplate(EmailType.PASSWORD_RESET.template).toString())
                .model(model)
                .build()
        MimeMessage email = buildEmail(draft)
        getMailSender().send(email)
        log.info("Mail na obnovu hesla poslany na [${user.email}], odkaz plati do [${model.expiration}]")
    }

    /**
     * Model pre sablonu - presne to iste, co stavia engine.
     *
     * `token` sa koduje TU a nie skor: `registrationService.encodeToken` berie
     * token, ktory uctu prave nastavil `createNewUser`/`resetPassword`, takze
     * mimo tohto volania uz nie je aktualny.
     */
    private Map<String, Object> model(RegisteredUser user) {
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd.MM.yyyy")
        return [
                (TOKEN)     : registrationServiceRef.encodeToken(user.email, user.token),
                (VALIDITY)  : "" + serverAuthPropertiesRef.tokenValidityPeriod,
                (EXPIRATION): registrationServiceRef.generateExpirationDate().format(formatter),
                (SERVER)    : getServerURL(),
        ] as Map<String, Object>
    }
}
