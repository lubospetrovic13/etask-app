package com.netgrif.etask.mail

import groovy.util.logging.Slf4j
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.beans.factory.annotation.Value
import org.springframework.mail.SimpleMailMessage
import org.springframework.mail.javamail.JavaMailSender
import org.springframework.stereotype.Service

/**
 * Odoslanie notifikacneho mailu - jedna vec, ktoru Petriflow akcia sama nevie.
 *
 * Preco to nie je priamo v akcii siete a preco nie cez `sendEmail` z enginu:
 *
 *   1. Notifikacia sa posiela z udalosti `finish`, teda VNUTRI transakcie,
 *      ktora prepina token. Ked SMTP nebezi (a na dev stroji nebezi skoro
 *      nikdy), `JavaMailSender` vyhodi vynimku - a schvalenie faktury zlyha
 *      na tom, ze sa nepodarilo poslat mail o schvaleni. To je horsie ako
 *      neposlany mail, takze chyba sa tu chyta a appka bezi dalej.
 *   2. `sendEmail` z `ActionDelegate` ide cez `IMailService` enginu, ktory
 *      pracuje s vlastnymi sablonami a `MailDraft`om. Na "posli tento text
 *      tomuto cloveku" je to obchadzka a nemame kontrolu nad tym, co spadne.
 *   3. Kill switch. Na demo instancii ma clovek vediet notifikacie vypnut
 *      jednym property, nie prepisovanim sieti.
 *
 * Nastavenie (application.properties / prostredie):
 *
 *   spring.mail.host=${MAIL_HOST}       host SMTP servera; prazdne = vypnute
 *   spring.mail.port=${MAIL_PORT}       1025 pre mailpit v compose
 *   nae.mail.from=${MAIL_FROM}          adresa odosielatela
 *   etask.notifications.enabled=true    kill switch
 *
 * V compose stacku bezi `mailpit`, ktory maily nikam neposiela a ukazuje ich
 * na http://localhost:8025 - teda presne to, co treba na demo aj na test.
 */
@Slf4j
@Service
class NotifyService {

    /**
     * Bean existuje len ked je na classpath spring-boot-starter-mail. Engine ho
     * tam ma, ale `required = false` je tu zamerne: bez neho by appka po
     * odstraneni mailu z enginu nenabehla vobec, a to je prilis vela za
     * notifikaciu.
     */
    @Autowired(required = false)
    private JavaMailSender mailSender

    @Value('${etask.notifications.enabled:true}')
    private boolean enabled

    /**
     * POZOR na default: `application.properties` ma
     * `spring.mail.host=${MAIL_HOST:''}`, takze ked premenna chyba, hodnota
     * NIE JE prazdny string - je to dvojznakovy string `''` (dve apostrofy).
     * Spring uvodzovky neodstranuje. Kontrola `if (!host)` by teda prehlasila
     * "SMTP je nastaveny" na kazdom stroji bez SMTP a kazda notifikacia by
     * skoncila vynimkou v logu.
     */
    @Value('${spring.mail.host:}')
    private String host

    @Value('${nae.mail.from:etask@localhost}')
    private String from

    /** Da sa vobec posielat? Siet sa to pyta, aby o tom vedela napisat do priebehu. */
    boolean available() {
        return enabled && mailSender != null && smtpHost() != null
    }

    String smtpHost() {
        String h = (host ?: "").trim()
        // Ockovanie z ${MAIL_HOST:''} aj z ${MAIL_HOST:""}.
        while (h.length() >= 2 && ((h.startsWith("'") && h.endsWith("'"))
                || (h.startsWith('"') && h.endsWith('"')))) {
            h = h.substring(1, h.length() - 1).trim()
        }
        return h ? h : null
    }

    /**
     * Posle kazdemu prijemcovi VLASTNY mail a vrati, kolkym sa to podarilo.
     *
     * Po jednom zamerne: v jednom maile by kazdy schvalovatel videl adresy
     * ostatnych, a jedna zla adresa by zhodila odoslanie vsetkym.
     */
    int send(List<String> prijemcovia, String predmet, String telo) {
        if (!available()) {
            log.debug("Notifikacie su vypnute alebo SMTP nie je nastaveny, nepostelam: ${predmet}")
            return 0
        }
        List<String> adresy = (prijemcovia ?: [])
                .collect { (it ?: "") as String }
                .collect { it.trim() }
                .findAll { it.contains("@") }
                .unique()
        int poslane = 0
        adresy.each { String adresa ->
            try {
                SimpleMailMessage msg = new SimpleMailMessage()
                msg.setFrom(from)
                msg.setTo(adresa)
                msg.setSubject(predmet ?: "eTask")
                msg.setText(telo ?: "")
                mailSender.send(msg)
                poslane++
            } catch (Throwable t) {
                // Zamerne Throwable: JavaMail vie hodit aj Error (chybajuca
                // trieda providera). Notifikacia nesmie zhodit schvalenie.
                log.warn("Notifikacia na ${adresa} sa neposlala: ${t.message}")
            }
        }
        if (poslane) {
            log.info("Notifikacia '${predmet}' poslana ${poslane}/${adresy.size()} prijemcom")
        }
        return poslane
    }
}
