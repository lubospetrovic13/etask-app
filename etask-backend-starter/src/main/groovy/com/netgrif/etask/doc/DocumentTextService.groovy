package com.netgrif.etask.doc

import groovy.util.logging.Slf4j
import org.apache.pdfbox.pdmodel.PDDocument
import org.apache.pdfbox.rendering.ImageType
import org.apache.pdfbox.rendering.PDFRenderer
import org.apache.pdfbox.text.PDFTextStripper
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service

import javax.imageio.ImageIO
import java.nio.charset.StandardCharsets
import java.util.Arrays
import java.util.concurrent.TimeUnit

/**
 * Text z prilozeneho dokumentu. Jedno miesto pre vsetko, co v tomto starteri
 * potrebuje z prilohy citat - faktury z Petriflow akcie aj prilohy mailu
 * v {@link com.netgrif.etask.ai.MailPayloadService}.
 *
 * Poradie je zamerne a je to cely trik: <b>najprv textova vrstva, OCR az
 * potom</b>. Vacsina doslych faktur je digitalne PDF s textom, kde PDFBox da
 * presny text - OCR by z presneho vstupu spravil odhad. OCR je tu len pre
 * skeny a fotky, teda pre to, co inak precitat nejde.
 *
 * PDFBox je v classpath tranzitivne z `application-engine` (pdfbox-2.0.25),
 * takze textova vrstva nepotrebuje ziadnu novu zavislost ani instalaciu.
 * OCR volame ako <b>binarku `tesseract`</b> a nie cez Tess4J zamerne: Tess4J
 * je nova Maven zavislost PLUS natívna kniznica, ktoru treba dostat na kazdy
 * stroj a do kazdeho kontejnera; binarka je `apt-get install tesseract-ocr
 * tesseract-ocr-slk`. Ked binarka chyba, sluzba to <b>povie</b> namiesto toho,
 * aby padla - appka funguje dalej, len bez OCR.
 */
@Slf4j
@Service
class DocumentTextService {

    /** Kolko znakov (bez bielych miest) uz povazujeme za pouzitelnu textovu vrstvu. */
    private static final int TEXT_LAYER_MIN = 120

    /** Kolko stran PDF poslat do OCR. Faktura je 1-2 strany; zvysok je priloha. */
    private static final int OCR_MAX_PAGES = 3

    /** DPI pre rasterizaciu PDF do OCR. Pod 200 klesa uspesnost na malych fontoch. */
    private static final int OCR_DPI = 300

    private static final long OCR_TIMEOUT_SECONDS = 90

    @Value('${etask.ocr.binary:tesseract}')
    private String ocrBinary

    /** Jazyky pre tesseract. `slk` treba doinstalovat zvlast (tesseract-ocr-slk). */
    @Value('${etask.ocr.languages:slk+eng}')
    private String ocrLanguages

    /**
     * Zdroj, z ktoreho text prisiel. Petriflow siet to zobrazuje cloveku:
     * pri `OCR` sa cisla kontroluju inak nez pri `XML`.
     */
    static enum Source {
        XML, TEXT, PDF_TEXT, OCR, NONE
    }

    static class Extracted {
        Source source = Source.NONE
        String text = ""
        String note = ""

        boolean isEmpty() {
            return !text || text.trim().isEmpty()
        }
    }

    /** Je OCR na tomto stroji vobec k dispozicii? */
    boolean isOcrAvailable() {
        try {
            Process p = new ProcessBuilder([ocrBinary, "--version"]).redirectErrorStream(true).start()
            boolean done = p.waitFor(10, TimeUnit.SECONDS)
            if (!done) {
                p.destroyForcibly()
                return false
            }
            return p.exitValue() == 0
        } catch (Exception ignored) {
            // IOException = binarka nie je v PATH. Nie je to chyba, je to stav.
            return false
        }
    }

    String getOcrBinaryName() {
        return ocrBinary
    }

    /** Text z prilohy na disku. */
    Extracted extract(File file) {
        Extracted out = new Extracted()
        if (file == null || !file.exists() || file.length() == 0) {
            out.note = "Príloha nie je nahraná alebo je prázdna."
            return out
        }
        // Typ sa urcuje podla OBSAHU, nie podla pripony: sken poslany ako
        // "faktura.pdf" nie je PDF, ked to je JPEG, a e-faktura chodi z
        // podatelni aj bez pripony. Pripona je len zaloha, ked magicke bajty
        // nic nepovedia.
        String sniffed = sniff(file)
        String lower = sniffed ?: file.name.toLowerCase()
        try {
            if (lower.endsWith(".xml")) {
                out.source = Source.XML
                out.text = file.getText("UTF-8")
                return out
            }
            if (isPlainText(lower)) {
                out.source = Source.TEXT
                out.text = file.getText("UTF-8")
                return out
            }
            if (lower.endsWith(".pdf")) {
                String layer = pdfTextLayer(file)
                if (usableText(layer)) {
                    out.source = Source.PDF_TEXT
                    out.text = layer
                    return out
                }
                // Skenovane PDF: ziadna textova vrstva, len obrazok strany.
                return ocrPdf(file, out)
            }
            if (isImage(lower)) {
                return ocrImage(file, out)
            }
            out.note = "Prílohu ${file.name} sa prečítať nedá" +
                    (sniffed ? " (podľa obsahu je to ${sniffed.substring(1).toUpperCase()})" : "") +
                    ". Priložte XML e-faktúru, PDF alebo obrázok."
            return out
        } catch (Exception e) {
            log.warn("Nepodarilo sa precitat prilohu ${file.name}: ${e.message}", e)
            out.note = "Prílohu sa nepodarilo prečítať: ${e.message}"
            return out
        }
    }

    /**
     * Typ suboru podla prvych bajtov. Vracia pseudo-priponu (".pdf", ".xml",
     * ".png", ...) alebo null, ked to nie je nic zname.
     *
     * PDF zacina "%PDF", PNG a JPEG maju svoje podpisy, XML sa pozna podla
     * "&lt;?xml" alebo prveho "&lt;" po bielych miestach (a po pripadnom BOM).
     */
    static String sniff(File file) {
        byte[] head = new byte[512]
        int read
        file.withInputStream { ins -> read = ins.read(head) }
        if (read <= 0) {
            return null
        }
        byte[] b = read < head.length ? Arrays.copyOf(head, read) : head
        if (startsWith(b, [0x25, 0x50, 0x44, 0x46] as int[])) return ".pdf"          // %PDF
        if (startsWith(b, [0x89, 0x50, 0x4E, 0x47] as int[])) return ".png"
        if (startsWith(b, [0xFF, 0xD8, 0xFF] as int[])) return ".jpg"
        if (startsWith(b, [0x49, 0x49, 0x2A, 0x00] as int[]) ||
                startsWith(b, [0x4D, 0x4D, 0x00, 0x2A] as int[])) return ".tif"
        if (startsWith(b, [0x42, 0x4D] as int[])) return ".bmp"
        String text = new String(b, StandardCharsets.UTF_8)
                .replaceFirst("^\ufeff", "").trim()
        if (text.startsWith("<?xml") || text.startsWith("<")) return ".xml"
        return null
    }

    private static boolean startsWith(byte[] data, int[] signature) {
        if (data.length < signature.length) {
            return false
        }
        for (int i = 0; i < signature.length; i++) {
            if ((data[i] & 0xFF) != signature[i]) {
                return false
            }
        }
        return true
    }

    /** Text z bajtov - pre prilohy, ktore nie su na disku (mail, ZIP). */
    Extracted extract(byte[] bytes, String fileName) {
        if (bytes == null || bytes.length == 0) {
            Extracted out = new Extracted()
            out.note = "Príloha je prázdna."
            return out
        }
        File tmp = File.createTempFile("etask-doc-", "-" + safeName(fileName))
        try {
            tmp.bytes = bytes
            return extract(tmp)
        } finally {
            tmp.delete()
        }
    }

    // ------------------------------------------------------------------ PDF

    /** Textova vrstva PDF. Prazdny retazec, ked v nom ziadna nie je. */
    String pdfTextLayer(File file) {
        PDDocument doc = null
        try {
            doc = PDDocument.load(file)
            if (doc.isEncrypted()) {
                // Zasifrovane PDF sa da niekedy citat s prazdnym heslom; ked nie,
                // padne to uz na `load` a chytime to nizsie.
                log.info("PDF ${file.name} je zasifrovane, citam len co pusti")
            }
            PDFTextStripper stripper = new PDFTextStripper()
            stripper.setSortByPosition(true)
            return stripper.getText(doc) ?: ""
        } catch (Exception e) {
            log.info("PDF ${file.name}: textova vrstva sa necita (${e.message})")
            return ""
        } finally {
            doc?.close()
        }
    }

    private Extracted ocrPdf(File file, Extracted out) {
        if (!isOcrAvailable()) {
            out.note = "PDF nemá textovú vrstvu, je to sken - a OCR nie je k dispozícii " +
                    "(binárka `${ocrBinary}` nie je v PATH). Priložte XML e-faktúru, " +
                    "PDF s textom, alebo doinštalujte tesseract."
            return out
        }
        PDDocument doc = null
        List<File> pages = []
        try {
            doc = PDDocument.load(file)
            PDFRenderer renderer = new PDFRenderer(doc)
            int count = Math.min(doc.numberOfPages, OCR_MAX_PAGES)
            StringBuilder sb = new StringBuilder()
            for (int i = 0; i < count; i++) {
                File png = File.createTempFile("etask-ocr-", "-p${i}.png")
                pages << png
                ImageIO.write(renderer.renderImageWithDPI(i, OCR_DPI, ImageType.GRAY), "png", png)
                sb.append(runTesseract(png)).append("\n")
            }
            out.source = Source.OCR
            out.text = sb.toString()
            if (!usableText(out.text)) {
                out.note = "OCR z tohto skenu nič použiteľné nevytiahlo. " +
                        "Skúste kvalitnejší sken, alebo vyplňte polia ručne."
            } else if (doc.numberOfPages > count) {
                out.note = "OCR prečítalo prvé ${count} z ${doc.numberOfPages} strán."
            }
            return out
        } catch (Exception e) {
            log.warn("OCR PDF ${file.name} zlyhalo: ${e.message}", e)
            out.note = "OCR zlyhalo: ${e.message}"
            return out
        } finally {
            doc?.close()
            pages.each { it.delete() }
        }
    }

    private Extracted ocrImage(File file, Extracted out) {
        if (!isOcrAvailable()) {
            out.note = "Je to obrázok, takže sa musí čítať OCR - a binárka " +
                    "`${ocrBinary}` nie je v PATH. Priložte XML e-faktúru alebo PDF s textom."
            return out
        }
        try {
            out.source = Source.OCR
            out.text = runTesseract(file)
            if (!usableText(out.text)) {
                out.note = "OCR z tohto obrázka nič použiteľné nevytiahlo."
            }
            return out
        } catch (Exception e) {
            log.warn("OCR obrazka ${file.name} zlyhalo: ${e.message}", e)
            out.note = "OCR zlyhalo: ${e.message}"
            return out
        }
    }

    /**
     * Jedno spustenie tesseractu. Vystup ide na stdout (`-` ako output),
     * takze po sebe nenechava subory.
     */
    private String runTesseract(File image) {
        List<String> cmd = [ocrBinary, image.absolutePath, "stdout", "-l", ocrLanguages, "--psm", "6"]
        Process p = new ProcessBuilder(cmd).redirectErrorStream(false).start()
        StringBuilder sout = new StringBuilder()
        StringBuilder serr = new StringBuilder()
        Thread tOut = Thread.start { sout.append(p.inputStream.getText("UTF-8")) }
        Thread tErr = Thread.start { serr.append(p.errorStream.getText("UTF-8")) }
        boolean done = p.waitFor(OCR_TIMEOUT_SECONDS, TimeUnit.SECONDS)
        if (!done) {
            p.destroyForcibly()
            throw new IllegalStateException("tesseract nedobehol do ${OCR_TIMEOUT_SECONDS} s")
        }
        tOut.join(5000)
        tErr.join(5000)
        if (p.exitValue() != 0) {
            String err = serr.toString().trim()
            // Najcastejsia chyba je chybajuci jazykovy model - povedzme to presne,
            // lebo `tesseract` v tom pripade vrati nenulovy kod a nic viac.
            if (err.toLowerCase().contains("failed loading language") ||
                    err.toLowerCase().contains("could not initialize tesseract")) {
                throw new IllegalStateException(
                        "tesseract nemá jazykové dáta pre '${ocrLanguages}' " +
                                "(doinštalujte tesseract-ocr-slk, alebo nastavte " +
                                "etask.ocr.languages=eng)")
            }
            throw new IllegalStateException("tesseract skončil s kódom ${p.exitValue()}: ${err}")
        }
        return sout.toString()
    }

    // ------------------------------------------------------------- pomocne

    private static boolean usableText(String text) {
        return text && text.replaceAll("\\s", "").length() >= TEXT_LAYER_MIN
    }

    private static boolean isPlainText(String lower) {
        return lower.endsWith(".txt") || lower.endsWith(".md") || lower.endsWith(".csv") ||
                lower.endsWith(".json") || lower.endsWith(".html") || lower.endsWith(".eml")
    }

    private static boolean isImage(String lower) {
        return lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") ||
                lower.endsWith(".tif") || lower.endsWith(".tiff") || lower.endsWith(".bmp")
    }

    private static String safeName(String name) {
        String n = (name ?: "priloha").replaceAll("[^A-Za-z0-9._-]", "_")
        return n.length() > 60 ? n.substring(n.length() - 60) : n
    }

    static String utf8(byte[] bytes) {
        return new String(bytes, StandardCharsets.UTF_8)
    }
}
