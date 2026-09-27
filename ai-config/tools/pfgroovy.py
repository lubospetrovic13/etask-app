#!/usr/bin/env python3
"""
pfgroovy - skontroluje syntax Groovy v Petriflow akciach BEZ beziaceho enginu.

Rola v pipeline (pflint -> pfgroovy -> pfcheck):

  pflint.py  cita XML, Groovy neparsuje - je to text v CDATA.
  pfgroovy   parsuje Groovy v <action> a <function>. Offline, sekunda.
  pfcheck.sh import do enginu = ground truth.

Poznamka k pokryvaniu, aby nikto necakal viac, nez to je: engine akcie pri
importe SKUTOCNE kompiluje - siet so syntakticky rozbitym Groovy odmietne s
"Could not evaluate action[...] MultipleCompilationErrorsException" (overene na
fixtures/bad-groovy.xml). pfgroovy teda nezatvara dieru v pokryti, ale skracuje
smycku: nepotrebuje bezaci engine ani databazu a chybu ukaze s cislom riadku
priamo v XML. Pri iteracii nad sietou je to rozdiel medzi sekundou a dvoma
minutami zdvihania stacku.

Kontroluje LEN syntax, nie ze metody existuju - delegat je dynamicky, takze
`totalne_neexistujuca_metoda()` so spravnymi zavorkami prejde aj tu aj v enginu
a spadne az za behu.

Potrebuje JDK 11+ a groovy jar. Jar sa hlada v ~/.m2, alebo cez PF_GROOVY_JAR.

    python3 tools/pfgroovy.py processes/
    PF_GROOVY_JAR=/cesta/groovy.jar python3 tools/pfgroovy.py processes/net.xml

Exit 0 = vsetko sa parsuje, 1 = syntakticka chyba, 2 = chyba prostredie.
"""

import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


# NAE hlavicka nema len polia. `f.` je datove pole, `t.` prechod - to druhe je
# potrebne pre `make <pole>, <behavior> on <prechod> when { ... }`, ktore bez
# aliasu prechodu napisat nejde. Kym tu bolo len `f.`, cela hlavicka s `t.`
# padla do tela ako Groovy a pfgroovy hlasil syntakticku chybu na sieti, ktoru
# engine bez namietky naimportuje - presne ten falosny pozitiv, kvoli ktoremu
# existuje pftest. Prefix je preto jedno male pismeno, nie vypocet zoznamu.
HEADER_PAIR = re.compile(
    r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*:\s*[a-z]\.[A-Za-z_][A-Za-z0-9_]*\s*$")


def split_header(code):
    """Oddeli NAE hlavicku (`pole: f.pole, ine: f.ine;`) od tela.

    Hlavicka nie je Groovy. Jednopolozkova `x: f.x;` sa nahodou parsuje ako
    labeled statement, viacpolozkova uz nie - a NAE si ju aj tak preklada sam.
    Zistene tak, ze pfgroovy hlasil 47 chyb na sietach, ktore engine bez
    namietky skompiluje. Ground truth (pfcheck) je arbiter.
    """
    idx = code.find(";")
    if idx < 0:
        return [], code
    head = code[:idx]
    parts = [p for p in head.split(",") if p.strip()]
    if parts and all(HEADER_PAIR.match(p) for p in parts):
        names = [p.split(":", 1)[0].strip() for p in parts]
        return names, code[idx + 1:]
    return [], code


def find_groovy_jar():
    env = os.environ.get("PF_GROOVY_JAR")
    if env and Path(env).is_file():
        return env
    roots = [Path.home() / ".m2/repository/org/codehaus/groovy/groovy",
             Path.home() / ".m2/repository/org/apache/groovy/groovy"]
    found = []
    for r in roots:
        if r.is_dir():
            found.extend(r.glob("*/groovy-*.jar"))
    found = [f for f in found if "sources" not in f.name and "javadoc" not in f.name]
    return str(sorted(found)[-1]) if found else None


def find_java():
    # Groovy 3 na JDK 21+ pada na "Unsupported class file major version 65",
    # takze siahame po 11/17, ak su k dispozicii.
    #
    # `JAVA_HOME` je prvy zamerne: na CI runneri (setup-java) ani na Windowse
    # ziadna z tych debianovskych ciest neexistuje, a fallback na `java` z PATH
    # je tam obvykle najnovsie JDK - teda presne to, na com Groovy 3 padne.
    home = os.environ.get("JAVA_HOME")
    if home:
        for kandidat in (Path(home) / "bin" / "java", Path(home) / "bin" / "java.exe"):
            if kandidat.is_file():
                return str(kandidat)
    for cand in ("/usr/lib/jvm/java-11-openjdk-amd64/bin/java",
                 "/usr/lib/jvm/java-17-openjdk-amd64/bin/java"):
        if Path(cand).is_file():
            return cand
    return "java"


def strip_ns(tag):
    return tag.split("}", 1)[-1]


def line_of(raw, needle, start=0):
    idx = raw.find(needle, start)
    return (raw.count("\n", 0, idx) + 1) if idx >= 0 else 1


def collect(path):
    """Vrati [(label, line, code)] pre kazdu akciu a funkciu v sieti."""
    raw = Path(path).read_text(encoding="utf-8")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return None, [(f"{path}:{getattr(e, 'lineno', 1)}", 0, None)], raw
    out, cursor = [], 0
    for el in root.iter():
        name = strip_ns(el.tag)
        if name not in ("action", "function"):
            continue
        code = el.text or ""
        if not code.strip():
            continue
        ident = el.get("id") or el.get("name") or name
        if el.get("id"):
            marker = '%s id="%s"' % (name, ident)
        elif name == "function":
            marker = "function scope"
        else:
            marker = "<" + name
        ln = line_of(raw, marker, cursor)
        cursor = raw.find(marker, cursor) + 1 if raw.find(marker, cursor) >= 0 else cursor
        names, body = split_header(code)
        prelude = ("def " + ", ".join(names) + "\n") if names else ""
        out.append((f"{name} {ident}", ln, prelude + body))
    return out, None, raw


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__.strip())
        return 2

    jar = find_groovy_jar()
    if not jar:
        print("pfgroovy: groovy jar sa nenasiel. Nastav PF_GROOVY_JAR.", file=sys.stderr)
        print("          Kontrola Groovy syntaxe sa PRESKAKUJE - to nie je 'ciste'.", file=sys.stderr)
        return 2

    files = []
    for a in args:
        p = Path(a)
        files.extend(sorted(p.glob("*.xml")) if p.is_dir() else [p])
    if not files:
        print("pfgroovy: ziadne .xml", file=sys.stderr)
        return 2

    units, parse_errors = [], 0
    for f in files:
        items, err, _ = collect(f)
        if err:
            print(f"{f}: XML sa neda rozparsovat")
            parse_errors += 1
            continue
        for label, ln, code in items:
            units.append({"file": str(f), "label": label, "line": ln, "code": code})

    if not units:
        print(f"pfgroovy: {len(files)} sieti, ziadne akcie na kontrolu")
        return 1 if parse_errors else 0

    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        # Zamerne bez JSON: groovy.json je v Groovy 3 samostatny jar a nemusi
        # byt po ruke. Manifest + jeden subor na telo akcie staci.
        lines = []
        for i, u in enumerate(units):
            body = tmpd / ("u%d.groovy" % i)
            body.write_text(u["code"], encoding="utf-8")
            lines.append("\t".join([str(body), u["file"], str(u["line"]), u["label"]]))
        inp = tmpd / "manifest.tsv"
        inp.write_text("\n".join(lines), encoding="utf-8")
        script = tmpd / "Check.groovy"
        script.write_text(
            # Zamerne len faza CONVERSION (parsovanie), nie semanticka analyza.
            # GroovyShell.parse() by resolvoval triedy, a tento proces nema
            # classpath enginu - `org.bson.types.ObjectId` ani `JsonSlurper` by
            # nenasiel a hlasil by chyby v kode, ktory sa v enginu skompiluje.
            # pfgroovy kontroluje syntax; typy a triedy su vec enginu.
            'import org.codehaus.groovy.control.CompilationUnit\n'
            'import org.codehaus.groovy.control.Phases\n'
            '\n'
            'new File(args[0]).eachLine("UTF-8") { line ->\n'
            '    if (!line?.trim()) return\n'
            '    def p = line.split("\\t", 4)\n'
            '    def code = new File(p[0]).getText("UTF-8")\n'
            '    try {\n'
            '        def cu = new CompilationUnit()\n'
            '        cu.addSource("Action.groovy", "{ ->\\n" + code + "\\n}")\n'
            '        cu.compile(Phases.CONVERSION)\n'
            '    } catch (Throwable t) {\n'
            '        def msg = (t.message ?: "").readLines()\n'
            '                    .findAll { it.trim() && !(it =~ /^\\s*\\d+ error/) }\n'
            '                    .take(3).join(" ")\n'
            '        println "FAIL\\t" + p[1] + "\\t" + p[2] + "\\t" + p[3] + "\\t" + msg\n'
            '    }\n'
            '}\n', encoding="utf-8")
        env = dict(os.environ)
        env["JAVA_TOOL_OPTIONS"] = ""
        try:
            res = subprocess.run([find_java(), "-cp", jar, "groovy.ui.GroovyMain",
                                  str(script), str(inp)],
                                 capture_output=True, text=True, timeout=300, env=env)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"pfgroovy: groovy sa nepodarilo spustit: {e}", file=sys.stderr)
            return 2

    if res.returncode != 0 and "FAIL\t" not in res.stdout:
        print("pfgroovy: groovy skoncil chybou:", file=sys.stderr)
        print((res.stderr or res.stdout).strip()[:1200], file=sys.stderr)
        return 2

    failures = 0
    for line in res.stdout.splitlines():
        if not line.startswith("FAIL\t"):
            continue
        _, fpath, ln, label, msg = line.split("\t", 4)
        print(f"{fpath}:{ln}: ERROR [groovy-syntax] {label}: {msg}")
        failures += 1

    print(f"\npfgroovy: {len(files)} sieti, {len(units)} akcii, {failures} syntaktickych chyb")
    return 1 if (failures or parse_errors) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
