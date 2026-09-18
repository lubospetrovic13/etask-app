package com.netgrif.etask.doc

import groovy.util.logging.Slf4j
import org.apache.poi.ss.usermodel.Cell
import org.apache.poi.ss.usermodel.ClientAnchor
import org.apache.poi.ss.usermodel.CreationHelper
import org.apache.poi.ss.usermodel.Drawing
import org.apache.poi.ss.usermodel.Row
import org.apache.poi.ss.usermodel.Sheet
import org.apache.poi.ss.usermodel.Workbook
import org.apache.poi.ss.usermodel.WorkbookFactory
import org.apache.poi.ss.util.CellReference
import org.springframework.stereotype.Service

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/**
 * Vyplni CUDZI xlsx zosit podla mapovania buniek a vlozi don obrazky.
 *
 * <b>Preco to existuje.</b> Engine vie vyrobit PDF z formulara
 * ({@code generatePdf}), teda dokument, ktoreho podobu urcuje sam. Tato sluzba
 * riesi opacny pripad: tlacivo drzi NIEKTO INY - uctovna firma, ktora ho raz
 * za cas prepise - a appka doň ma len doplnit hodnoty. Sablona preto nie je
 * sucastou kodu ani siete: je to priloha v konfiguracii appky a mapovanie
 * "pole -> bunka" je text vedla nej. Nova verzia tlaciva je potom vymena
 * prilohy a par riadkov mapovania, nie zmena kodu.
 *
 * <b>Co sluzba zamerne NEROBI.</b> Neprepocitava vzorce a nezasahuje do
 * buniek, ktore nie su v mapovani. Tlacivo si svoje vzorce (stravne, nahrady,
 * sucty) pocita samo a su na nom to najcennejsie - keby sme ich prepisali
 * vyratanymi cislami, kazda oprava sadzieb od uctovnej firmy by sa stratila.
 * Zapisuju sa teda len VSTUPY. Aby Excel po otvoreni vzorce prepocital, zosit
 * sa oznaci {@code setForceFormulaRecalculation}; do vtedy nesie hodnoty
 * z posledneho ulozenia sablony, co je pri holej sablone prazdno.
 *
 * Apache POI je v classpath tranzitivne z {@code application-engine}
 * (poi-ooxml 4.1.2), takze ziadna nova zavislost nepribuda.
 */
@Slf4j
@Service
class XlsxFillService {

    /**
     * @param sablona  xlsx subor, ktory sa ma vyplnit (necha sa nedotknuty)
     * @param harok    nazov harku; {@code null} = prvy v zosite
     * @param bunky    mapa {@code "C4" -> hodnota}; {@code null} hodnota bunku vyprazdni
     * @param obrazky  zoznam map s klucmi {@code subor} (File/byte[]), {@code bunka},
     *                 {@code sirka} a {@code vyska} (v stlpcoch a riadkoch)
     * @param cielovy  kam sa ma vysledok zapisat
     * @return pocty a hlaska; nikdy nevyhodi vynimku sama od seba
     */
    Map<String, Object> fill(File sablona, String harok, Map<String, Object> bunky,
                             List<Map<String, Object>> obrazky, File cielovy) {
        if (sablona == null || !sablona.exists() || sablona.length() == 0) {
            return [ok: false, sprava: "The xlsx template is not uploaded.", buniek: 0, obrazkov: 0]
        }
        Workbook wb = null
        try {
            wb = sablona.withInputStream { is -> WorkbookFactory.create(is) }
            Sheet sheet = harok ? wb.getSheet(harok) : wb.getSheetAt(0)
            if (sheet == null) {
                return [ok: false, buniek: 0, obrazkov: 0,
                        sprava: "The template has no sheet named '" + harok + "'. Sheets: " +
                                (0..<wb.numberOfSheets).collect { wb.getSheetName(it) }.join(", ")]
            }

            int zapisanych = 0
            List<String> problemy = []
            (bunky ?: [:]).each { String ref, Object hodnota ->
                try {
                    zapis(sheet, ref, hodnota)
                    zapisanych++
                } catch (Exception e) {
                    // Jedna zla suradnica nesmie zhodit cely export - vysledkom
                    // by bolo ziadne tlacivo namiesto tlaciva s jednou dierou.
                    problemy << (ref + ": " + e.message)
                }
            }

            int vlozenych = 0
            (obrazky ?: []).each { Map<String, Object> o ->
                try {
                    if (vlozObrazok(wb, sheet, o)) {
                        vlozenych++
                    }
                } catch (Exception e) {
                    problemy << (((o?.bunka ?: "?") as String) + ": " + e.message)
                }
            }

            // Vzorce sablony ostavaju. Bez tohto priznaku by Excel ukazal
            // hodnoty ulozene pri poslednom ulozeni SABLONY, teda prazdno.
            wb.setForceFormulaRecalculation(true)

            cielovy.parentFile?.mkdirs()
            cielovy.withOutputStream { os -> wb.write(os) }

            String sprava = "Filled in: " + zapisanych + " cells, " + vlozenych + " image(s)."
            if (problemy) {
                sprava += " Skipped: " + problemy.join("; ")
            }
            return [ok: true, sprava: sprava, buniek: zapisanych, obrazkov: vlozenych,
                    problemy: problemy]
        } catch (Throwable t) {
            log.warn("xlsx fill failed: {}", t.message, t)
            return [ok: false, buniek: 0, obrazkov: 0,
                    sprava: "The template could not be filled in: " + t.message]
        } finally {
            try { wb?.close() } catch (Exception ignored) { }
        }
    }

    /**
     * Zapise hodnotu do bunky podla A1 referencie.
     *
     * Bunka sa najprv VYPRAZDNI. Bez toho by sa do bunky so vzorcom ulozila len
     * cache hodnota, vzorec by zostal a po prvom prepocte by nas zapis prepisal
     * spat - stlpec by "sam od seba" zmenil hodnotu az v Exceli u cloveka.
     */
    private static void zapis(Sheet sheet, String ref, Object hodnota) {
        CellReference cr = new CellReference(ref)
        Row row = sheet.getRow(cr.row) ?: sheet.createRow(cr.row)
        Cell cell = row.getCell((int) cr.col) ?: row.createCell((int) cr.col)
        cell.setBlank()
        if (hodnota == null) {
            return
        }
        if (hodnota instanceof Number) {
            cell.setCellValue(((Number) hodnota).doubleValue())
        } else if (hodnota instanceof Boolean) {
            cell.setCellValue((Boolean) hodnota)
        } else if (hodnota instanceof LocalDate) {
            cell.setCellValue(java.sql.Date.valueOf((LocalDate) hodnota))
        } else if (hodnota instanceof LocalDateTime) {
            cell.setCellValue(java.util.Date.from(
                    ((LocalDateTime) hodnota).atZone(ZoneId.systemDefault()).toInstant()))
        } else if (hodnota instanceof LocalTime) {
            // Cas je v xlsx zlomok dna. Formatovanie bunky ostava zo sablony.
            LocalTime t = (LocalTime) hodnota
            cell.setCellValue(t.toSecondOfDay() / 86400.0d)
        } else if (hodnota instanceof Date) {
            cell.setCellValue((Date) hodnota)
        } else {
            String s = hodnota as String
            if (!s.isEmpty()) {
                cell.setCellValue(s)
            }
        }
    }

    /** Vlozi PNG do obdlznika, ktory zacina v danej bunke. Vrati, ci sa to podarilo. */
    private static boolean vlozObrazok(Workbook wb, Sheet sheet, Map<String, Object> o) {
        byte[] data = bajty(o?.subor)
        String bunka = (o?.bunka ?: "") as String
        if (data == null || data.length == 0 || !bunka) {
            return false
        }
        int sirka = Math.max(1, ((o?.sirka ?: 3) as Number).intValue())
        int vyska = Math.max(1, ((o?.vyska ?: 3) as Number).intValue())

        int index = wb.addPicture(data, Workbook.PICTURE_TYPE_PNG)
        Drawing<?> kresba = sheet.createDrawingPatriarch()
        CreationHelper helper = wb.getCreationHelper()
        ClientAnchor anchor = helper.createClientAnchor()
        CellReference cr = new CellReference(bunka)
        anchor.setCol1((int) cr.col)
        anchor.setRow1(cr.row)
        anchor.setCol2((int) cr.col + sirka)
        anchor.setRow2(cr.row + vyska)
        // MOVE_DONT_RESIZE: podpis si drzi velkost, aj ked sa vysky riadkov
        // v novej verzii tlaciva zmenia.
        anchor.setAnchorType(ClientAnchor.AnchorType.MOVE_DONT_RESIZE)
        kresba.createPicture(anchor, index)
        return true
    }

    private static byte[] bajty(Object subor) {
        if (subor == null) {
            return null
        }
        if (subor instanceof byte[]) {
            return (byte[]) subor
        }
        if (subor instanceof File) {
            File f = (File) subor
            return f.exists() ? f.bytes : null
        }
        File f = new File(subor as String)
        return f.exists() ? f.bytes : null
    }
}
