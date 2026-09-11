package com.netgrif.etask.doc

import groovy.util.logging.Slf4j
import groovy.xml.XmlSlurper
import groovy.xml.slurpersupport.GPathResult
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.stereotype.Service

import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.regex.Matcher
import java.util.regex.Pattern

/**
 * Precita fakturu a vrati polia, ktore sa z nej dali vytiahnut.
 *
 * Dve cesty a je medzi nimi velky rozdiel v istote:
 *
 * <ul>
 *   <li><b>XML e-faktura</b> - polia sa <i>citaju</i>. Ziadne hadanie, ziadna
 *       chyba OCR. Podporujeme semanticky model EN 16931 v oboch syntaxiach
 *       (UBL 2.1 a UN/CEFACT CII) a k tomu ISDOC, ktory je u nas rozsireny.
 *       Toto je cesta, ktora bude s povinnou e-fakturaciou prevladat.</li>
 *   <li><b>Text z PDF alebo OCR</b> - polia sa <i>hadaju</i> podla popiskov
 *       ("Celkom k úhrade", "Dátum splatnosti", "IČO"). Kazdy dodavatel ma iny
 *       formular, takze toto nikdy nebude 100 %. Preto sa vysledok
 *       PREDVYPLNI a clovek ho potvrdi - nikdy sa podla neho nic neschvaluje.</li>
 * </ul>
 *
 * Popisky sa hladaju bez diakritiky (`deaccent`), lebo OCR ju z casti zjedava
 * ("Datum splatnosti", "ICO"), ale hodnoty sa berú z <b>povodneho</b> textu -
 * preto je preklad znak za znak a nie NFD normalizacia, ktora meni dlzku
 * retazca a rozhodila by pozicie.
 */
@Slf4j
@Service
class InvoiceReaderService {

    @Autowired
    private DocumentTextService documentTextService

    /** Popisky sumy na uhradu, v poradí istoty. */
    private static final List<String> AMOUNT_LABELS = [
            "celkom k uhrade", "celkovo k uhrade", "suma k uhrade", "suma na uhradu",
            "k uhrade", "na uhradu", "celkova suma s dph", "celkom s dph", "spolu s dph",
            "celkom vratane dph", "celkom (s dph)", "total amount", "amount due", "grand total",
    ]
    private static final List<String> DUE_LABELS = [
            "datum splatnosti", "splatnost", "due date", "payment due",
    ]
    private static final List<String> ISSUE_LABELS = [
            "datum vystavenia", "datum vyhotovenia", "datum vydania", "issue date", "invoice date",
    ]
    private static final List<String> NUMBER_LABELS = [
            "faktura c", "faktura cislo", "cislo faktury", "cislo dokladu", "doklad c",
            "invoice no", "invoice number", "vs",
    ]

    /**
     * Cislo v texte. Zvlada 1452.60 | 1 452,60 | 1.234,56 | 1,234.56.
     *
     * Jedna vetva zacinajuca `\d+` je tu zamerne. Verzia s alternativou
     * `\d{1,3}(skupiny)|\d+` vracala z "1452.60" hodnotu **145**: prva
     * alternativa vzala tri cislice, dalsia skupina uz nesedela a regex sa
     * uspokojil so skratenym zapasom. Odhalil to az akceptacny test.
     */
    private static final Pattern P_AMOUNT = Pattern.compile(
            /(\d+(?:[  .,]\d{3})*(?:[.,]\d{1,2})?)/)
    private static final Pattern P_DATE_SK = Pattern.compile(/(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})/)
    private static final Pattern P_DATE_ISO = Pattern.compile(/(\d{4})-(\d{2})-(\d{2})/)
    private static final Pattern P_ICO = Pattern.compile(/(?i)ic[o0]\s*[:\s]\s*(\d{6,8})/)
    private static final Pattern P_DIC = Pattern.compile(/(?i)ic\s*dph\s*[:\s]*\s*([A-Z]{2}\d{9,12})/)
    private static final Pattern P_DIC2 = Pattern.compile(/(?i)\bdic\s*[:\s]\s*(\d{9,12})/)
    /**
     * Kandidat na IBAN. Zamerne VOLNY vzor - hranicu urcuje kontrolny sucet
     * (mod 97), nie regex. Tesnejsi vzor tu uz dvakrat zlyhal: s dvomi
     * skupinami po styroch sa na vzor chytilo IC DPH ("SK2023445566")
     * a s povolenymi medzerami zas vzor preskocil do dalsieho slova
     * ("SK68... CELKOM"). Cislo, ktore nesedi na kontrolny sucet, IBAN nie je.
     */
    private static final Pattern P_IBAN_CANDIDATE = Pattern.compile(
            /(?i)\b([A-Z]{2}\d{2}[A-Z0-9  ]{11,40})/)
    private static final Pattern P_IBAN_LABEL = Pattern.compile(
            /(?i)\biban\b\s*[:\s]\s*([A-Z0-9  ]{15,40})/)
    private static final Pattern P_VS = Pattern.compile(
            /(?i)(?:variabilny\s*symbol|var\.\s*symbol|\bvs\b)\s*[:\s]\s*(\d{4,12})/)
    private static final Pattern P_FIRMA = Pattern.compile(
            /(?i)(s\.\s?r\.\s?o\.|a\.\s?s\.|spol\.\s*s\s*r\.\s?o\.|k\.\s?s\.|v\.\s?o\.\s?s\.|s\.\s?p\.)/)

    /** Je OCR k dispozicii? Siet to vie povedat cloveku skor, nez priloži fotku. */
    boolean ocrAvailable() {
        return documentTextService.isOcrAvailable()
    }

    /**
     * Hlavny vstup: subor prilohy -> polia faktury.
     *
     * Kluce vysledku: `zdroj`, `dodavatel`, `cislo`, `suma`, `mena`,
     * `splatnost`, `vystavenie`, `ico`, `dic`, `iban`, `vs`, `chyba`,
     * `poznamka`, `nedocitane` (zoznam popiskov, ktore sa najst nedali).
     */
    Map<String, Object> read(File file) {
        DocumentTextService.Extracted ex = documentTextService.extract(file)
        Map<String, Object> out
        if (ex.source == DocumentTextService.Source.XML) {
            out = parseXml(ex.text)
            out.zdroj = "xml"
        } else if (ex.isEmpty()) {
            out = emptyResult()
            out.zdroj = "nic"
        } else {
            out = parseText(ex.text)
            out.zdroj = (ex.source == DocumentTextService.Source.OCR) ? "ocr" : "text"
        }
        if (ex.note) {
            out.poznamka = ((out.poznamka ?: "") as String) ? (out.poznamka + " " + ex.note) : ex.note
        }
        out.nedocitane = missing(out)
        return out
    }

    // -------------------------------------------------------------- XML

    /**
     * XML e-faktura. Parsuje sa <b>bez namespace</b> a hlada sa podla lokalnych
     * nazvov elementov - jeden kod tak zvlada UBL, CII aj ISDOC, ktore sa lisia
     * syntaxou, ale nesu tie iste semanticke polia (EN 16931).
     *
     * Namespace-unaware parsovanie ma jednu pascu: `ICO` dodavatela a odberatela
     * su ten isty element na dvoch miestach. Preto sa polia strany hladaju LEN
     * v podstrome dodavatela.
     */
    Map<String, Object> parseXml(String xml) {
        Map<String, Object> out = emptyResult()
        GPathResult root
        try {
            XmlSlurper slurper = new XmlSlurper(false, false)
            // Prilozene XML je cudzi vstup: DOCTYPE a externe entity von (XXE).
            slurper.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)
            slurper.setFeature("http://xml.org/sax/features/external-general-entities", false)
            slurper.setFeature("http://xml.org/sax/features/external-parameter-entities", false)
            root = slurper.parseText(xml)
        } catch (Exception e) {
            out.chyba = "XML sa nepodarilo rozparsovať: ${e.message}"
            return out
        }

        // maxLen 40: `ID` je v UBL aj CII cislo faktury, ale ten isty lokalny
        // nazov nesu aj identifikatory strán a riadkov - dlhy retazec je znak,
        // ze sme trafili nieco ine.
        out.cislo = firstText(root, ["ID", "InvoiceNumber", "DocumentNumber"], 40)
        out.vystavenie = firstDate(root, ["IssueDate", "IssueDateTime", "TaxPointDate", "DateTimeString"])
        out.splatnost = firstDate(root, ["DueDate", "DueDateDateTime", "PaymentDueDate"])

        // Suma: PayableAmount (UBL) / GrandTotalAmount (CII) / TaxInclusiveAmount
        // (fallback aj pre ISDOC). Poradie je poradie istoty, nie abecedy.
        GPathResult amount = firstNode(root, ["PayableAmount", "GrandTotalAmount",
                                              "DuePayableAmount", "TaxInclusiveAmount",
                                              "TotalWithVAT", "PayableRoundingAmount"])
        if (amount != null) {
            out.suma = parseAmount(amount.text())
            String cur = attr(amount, "currencyID")
            out.mena = cur ?: firstText(root, ["DocumentCurrencyCode", "InvoiceCurrencyCode"], 3) ?: "EUR"
        }

        GPathResult supplier = firstNode(root, ["AccountingSupplierParty", "SellerTradeParty",
                                               "IssuingSupplierParty", "SupplierParty"])
        GPathResult scope = supplier ?: root
        out.dodavatel = firstText(scope, ["RegistrationName", "Name", "PartyName", "TradingBusinessName"], 200)
        out.ico = firstDigitsInRange(scope, ["CompanyID", "ID", "PartyIdentification"], 6, 8)
        out.dic = firstMatchingText(scope, ["CompanyID", "ID"], ~/(?i)^[A-Z]{2}\d{9,12}$/)
        if (!out.dic) {
            out.dic = firstMatchingText(scope, ["CompanyID", "ID", "TaxNumber"], ~/^\d{9,12}$/)
        }

        // Aj v XML sa IBAN overuje kontrolnym suctom: `cbc:ID` v UBL nesie
        // cokolvek a `PayeeFinancialAccount` nie je jediny element s tym nazvom.
        out.iban = firstIban(root, ["IBANID", "IBAN", "ID", "AccountNumber"])
        out.vs = digits(firstText(root, ["PaymentID", "PaymentReference", "VariableSymbol"], 20), 4, 12)

        if (!out.cislo && !out.suma) {
            out.chyba = "V XML som nenašiel ani číslo faktúry, ani sumu. " +
                    "Je to naozaj e-faktúra (UBL / CII / ISDOC)?"
        }
        return out
    }

    // ------------------------------------------------------------- text

    /** Text z PDF alebo z OCR -> polia. Hada podla popiskov. */
    Map<String, Object> parseText(String text) {
        Map<String, Object> out = emptyResult()
        if (!text) return out
        String flat = text.replace(' ', ' ')
        String plain = deaccent(flat).toLowerCase()

        out.suma = amountNear(flat, plain, AMOUNT_LABELS)
        out.mena = flat.toLowerCase().contains("eur") || flat.contains("€") ? "EUR" : null
        out.splatnost = dateNear(flat, plain, DUE_LABELS)
        out.vystavenie = dateNear(flat, plain, ISSUE_LABELS)
        out.cislo = numberNear(flat, plain)
        out.ico = group(P_ICO, deaccent(flat))
        out.dic = group(P_DIC, deaccent(flat)) ?: group(P_DIC2, deaccent(flat))
        out.iban = ibanFrom(flat)
        out.vs = group(P_VS, deaccent(flat))
        if (!out.cislo && out.vs) out.cislo = out.vs
        out.dodavatel = supplierFromText(flat, plain)
        return out
    }

    /**
     * Dodavatel z textu. Blok dodavatela je na fakturach nad blokom odberatela,
     * takze hladame len v casti PRED popiskom odberatela - inak by sme na
     * polovici faktur vytiahli hotel sam.
     */
    private static String supplierFromText(String flat, String plain) {
        int cut = -1
        for (String label : ["odberatel", "kupujuci", "prijemca", "customer", "buyer"]) {
            int i = plain.indexOf(label)
            if (i >= 0 && (cut < 0 || i < cut)) cut = i
        }
        String head = (cut > 40) ? flat.substring(0, cut) : flat
        List<String> lines = head.readLines()*.trim().findAll { it }
        // Riadok s pravnou formou je takmer vzdy nazov firmy.
        String firma = lines.find { P_FIRMA.matcher(it).find() && it.length() < 80 }
        if (firma) {
            // "Dodávateľ: Gastro Trade s.r.o." -> odrezat popisok
            return firma.replaceAll(/(?i)^\s*(dodavatel|dodávateľ|dodavatel'|supplier|seller)\s*[:\-]?\s*/, "").trim()
        }
        // Bez pravnej formy: prvy riadok za popiskom "Dodávateľ", inak prvy riadok.
        int di = plain.indexOf("dodavatel")
        if (di >= 0) {
            List<String> rest = flat.substring(di).readLines()*.trim().findAll { it }
            if (rest.size() > 1) return stripLabel(rest[1])
            if (rest.size() == 1) return stripLabel(rest[0])
        }
        return lines ? lines[0] : null
    }

    private static String stripLabel(String s) {
        return s.replaceAll(/(?i)^\s*(dodavatel|dodávateľ|supplier|seller)\s*[:\-]?\s*/, "").trim()
    }

    // -------------------------------------------------------- pomocne XML

    private static String localName(GPathResult node) {
        String n = node.name()
        return n.contains(":") ? n.substring(n.lastIndexOf(":") + 1) : n
    }

    private static GPathResult firstNode(GPathResult root, List<String> names) {
        for (String name : names) {
            def hit = root.depthFirst().find { localName(it as GPathResult) == name }
            if (hit != null) return hit as GPathResult
        }
        return null
    }

    private static String firstText(GPathResult root, List<String> names, int maxLen) {
        for (String name : names) {
            def hit = root.depthFirst().find {
                localName(it as GPathResult) == name && (it.text() as String).trim()
            }
            if (hit != null) {
                String v = (hit.text() as String).trim()
                if (v.length() <= maxLen) return v
            }
        }
        return null
    }

    private static String firstMatchingText(GPathResult root, List<String> names, Pattern pattern) {
        for (String name : names) {
            def hit = root.depthFirst().find {
                localName(it as GPathResult) == name &&
                        pattern.matcher(((it.text() as String) ?: "").replaceAll("\\s", "")).matches()
            }
            if (hit != null) return ((hit.text() as String) ?: "").replaceAll("\\s", "")
        }
        return null
    }

    /**
     * Prvy element z danych nazvov, ktoreho cislice sa zmestia do rozsahu.
     *
     * Preco nie `firstText` + kontrola dlzky: `cbc:CompanyID` je v UBL dvakrat -
     * raz ako IC DPH (SK + 10 cislic) a raz ako ICO (8 cislic). Kto vezme prvy
     * a zisti, ze nesedi, vrati prazdno, hoci ten spravny je o dva elementy
     * nizsie. Prejst sa musia vsetky.
     */
    /** Prvy element z danych nazvov, ktoreho obsah je platny IBAN. */
    private static String firstIban(GPathResult root, List<String> names) {
        for (String name : names) {
            def hits = root.depthFirst().findAll { localName(it as GPathResult) == name }
            for (def hit : hits) {
                String c = iban((hit.text() as String))
                if (c) return c
            }
        }
        return null
    }

    private static String firstDigitsInRange(GPathResult root, List<String> names, int min, int max) {
        for (String name : names) {
            def hits = root.depthFirst().findAll { localName(it as GPathResult) == name }
            for (def hit : hits) {
                String d = digits((hit.text() as String), min, max)
                if (d) return d
            }
        }
        return null
    }

    private static String attr(GPathResult node, String name) {
        try {
            String v = node.attributes()?.get(name)
            return v?.trim() ?: null
        } catch (Exception ignored) {
            return null
        }
    }

    private static LocalDate firstDate(GPathResult root, List<String> names) {
        for (String name : names) {
            def hits = root.depthFirst().findAll { localName(it as GPathResult) == name }
            for (def hit : hits) {
                // CII ma datum v podelemente `DateTimeString` s formatom 102 (yyyyMMdd),
                // UBL priamo ako yyyy-MM-dd.
                String raw = ((hit.text() as String) ?: "").trim()
                LocalDate d = parseXmlDate(raw)
                if (d != null) return d
                def inner = (hit as GPathResult).depthFirst().find {
                    parseXmlDate(((it.text() as String) ?: "").trim()) != null
                }
                if (inner != null) return parseXmlDate(((inner.text() as String) ?: "").trim())
            }
        }
        return null
    }

    private static LocalDate parseXmlDate(String raw) {
        if (!raw) return null
        String s = raw.trim()
        try {
            if (s ==~ /\d{4}-\d{2}-\d{2}.*/) return LocalDate.parse(s.substring(0, 10))
            if (s ==~ /\d{8}/) return LocalDate.parse(s, DateTimeFormatter.BASIC_ISO_DATE)
        } catch (Exception ignored) {
        }
        return null
    }

    // ------------------------------------------------------- pomocne text

    private static Double amountNear(String flat, String plain, List<String> labels) {
        for (String label : labels) {
            int i = plain.indexOf(label)
            while (i >= 0) {
                // Okno za popiskom: cislo je bud na tom istom riadku, alebo hned
                // za nim - na fakturach s tabulkou aj o riadok nizsie.
                String window = flat.substring(Math.min(i + label.length(), flat.length()),
                        Math.min(i + label.length() + 60, flat.length()))
                Double v = parseAmount(window)
                if (v != null && v > 0) return v
                i = plain.indexOf(label, i + 1)
            }
        }
        return null
    }

    private static LocalDate dateNear(String flat, String plain, List<String> labels) {
        for (String label : labels) {
            int i = plain.indexOf(label)
            while (i >= 0) {
                String window = flat.substring(Math.min(i + label.length(), flat.length()),
                        Math.min(i + label.length() + 40, flat.length()))
                LocalDate d = parseDate(window)
                if (d != null) return d
                i = plain.indexOf(label, i + 1)
            }
        }
        return null
    }

    private static String numberNear(String flat, String plain) {
        for (String label : NUMBER_LABELS) {
            int i = plain.indexOf(label)
            while (i >= 0) {
                String window = flat.substring(Math.min(i + label.length(), flat.length()),
                        Math.min(i + label.length() + 40, flat.length()))
                Matcher m = Pattern.compile(/([0-9][0-9\-\/]{3,19})/).matcher(window)
                if (m.find()) return m.group(1)
                i = plain.indexOf(label, i + 1)
            }
        }
        return null
    }

    /**
     * Cislo z textu. Zvlada "1 234,56", "1.234,56", "1,234.56" aj "1234.56":
     * desatinny oddelovac je ten POSLEDNY, ked su za nim najviac dve cislice.
     */
    static Double parseAmount(String s) {
        if (!s) return null
        Matcher m = P_AMOUNT.matcher(s)
        while (m.find()) {
            String raw = m.group(1)
            String cleaned = raw.replaceAll("[  ]", "")
            int lastDot = cleaned.lastIndexOf('.')
            int lastComma = cleaned.lastIndexOf(',')
            int dec = Math.max(lastDot, lastComma)
            String norm
            if (dec >= 0 && cleaned.length() - dec - 1 <= 2 && cleaned.length() - dec - 1 > 0) {
                norm = cleaned.substring(0, dec).replaceAll("[.,]", "") + "." +
                        cleaned.substring(dec + 1)
            } else {
                norm = cleaned.replaceAll("[.,]", "")
            }
            try {
                double v = Double.parseDouble(norm)
                if (v > 0) return v
            } catch (Exception ignored) {
            }
        }
        return null
    }

    static LocalDate parseDate(String s) {
        if (!s) return null
        Matcher m = P_DATE_SK.matcher(s)
        if (m.find()) {
            try {
                return LocalDate.of(m.group(3) as int, m.group(2) as int, m.group(1) as int)
            } catch (Exception ignored) {
            }
        }
        Matcher iso = P_DATE_ISO.matcher(s)
        if (iso.find()) {
            try {
                return LocalDate.of(iso.group(1) as int, iso.group(2) as int, iso.group(3) as int)
            } catch (Exception ignored) {
            }
        }
        return null
    }

    private static String group(Pattern p, String text) {
        if (!text) return null
        Matcher m = p.matcher(text)
        return m.find() ? m.group(1).trim() : null
    }

    private static String digits(String s, int min, int max) {
        if (!s) return null
        String d = s.replaceAll("\\D", "")
        return (d.length() >= min && d.length() <= max) ? d : null
    }

    /**
     * IBAN z textu. Najprv podla popisku "IBAN:", potom skenom kandidatov;
     * o kazdom rozhodne `iban` s kontrolnym suctom, takze IC DPH ani
     * nalepene slovo neprejde.
     */
    private static String ibanFrom(String flat) {
        String labelled = iban(group(P_IBAN_LABEL, flat))
        if (labelled) return labelled
        Matcher m = P_IBAN_CANDIDATE.matcher(flat)
        while (m.find()) {
            String c = iban(m.group(1))
            if (c) return c
        }
        return null
    }

    /**
     * Vrati IBAN, ak sa v kandidatovi da najst - inak null.
     *
     * Skusa sa od najdlhsieho po najkratsi, lebo z textu casto pride aj to,
     * co za IBANom nasleduje ("SK68...353 Celkom"): po odstraneni medzier
     * je to jeden retazec a odrezat ho spravne vie len kontrolny sucet.
     *
     * Mod 97 (ISO 13616) je zaroven ochrana pred OCR: prehodena cislica
     * kontrolu neprejde, takze appka radsej IBAN nevyplni, nez by vyplnila
     * cislo, na ktore niekto posle peniaze.
     */
    static String iban(String candidate) {
        if (!candidate) return null
        String s = candidate.toUpperCase().replaceAll(/[^A-Z0-9]/, "")
        for (int len = Math.min(s.length(), 34); len >= 15; len--) {
            String c = s.substring(0, len)
            if (!(c ==~ /[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}/)) continue
            if (mod97(c) == 1) return c
        }
        return null
    }

    /** ISO 13616: prve styri znaky na koniec, litery na cisla (A=10), mod 97. */
    private static int mod97(String iban) {
        String rearranged = iban.substring(4) + iban.substring(0, 4)
        int rest = 0
        for (int i = 0; i < rearranged.length(); i++) {
            char ch = rearranged.charAt(i)
            int value = Character.isDigit(ch) ? (ch - (char) 48) : (ch - (char) 55)
            if (value < 0 || value > 35) return -1
            rest = (value > 9) ? ((rest * 100 + value) % 97) : ((rest * 10 + value) % 97)
        }
        return rest
    }

    /**
     * Diakritika von, dlzka zachovana. NFD normalizacia by retazec predlzila
     * a rozhodila pozicie, podla ktorych sa hodnoty citaju z povodneho textu.
     */
    static String deaccent(String s) {
        if (!s) return s
        final String from = "áäčďéěíĺľňóôöřšťúůüýžÁÄČĎÉĚÍĹĽŇÓÔÖŘŠŤÚŮÜÝŽ"
        final String to = "aacdeeillnooorstuuuyzAACDEEILLNOOORSTUUUYZ"
        StringBuilder sb = new StringBuilder(s.length())
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i)
            int idx = from.indexOf((int) c)
            sb.append(idx >= 0 ? to.charAt(idx) : c)
        }
        return sb.toString()
    }

    private static Map<String, Object> emptyResult() {
        return [zdroj: "nic", dodavatel: null, cislo: null, suma: null, mena: null,
                splatnost: null, vystavenie: null, ico: null, dic: null, iban: null,
                vs: null, chyba: null, poznamka: null, nedocitane: []] as Map<String, Object>
    }

    private static List<String> missing(Map<String, Object> out) {
        Map<String, String> labels = ["dodavatel": "dodávateľ", "cislo": "číslo faktúry",
                                      "suma"     : "suma", "splatnost": "splatnosť"]
        return labels.findAll { k, v -> !out[k] }.values().toList()
    }
}
