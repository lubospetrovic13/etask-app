#!/usr/bin/env python3
"""
pfapi - vygeneruje inventar extension pointov volatelnych z Petriflow akcie.

Preco generovany a nie napisany rucne: ActionDelegate enginu ma 206 unikatnych
metod v 407 pretazeniach. Rucny zoznam by driftoval s kazdou verziou enginu
a nespravny zoznam je horsi nez ziadny.

Preco vobec: pri stavbe Service Desku som hodiny dekompiloval bajtkod, hadal
poradie argumentov `createFilterInMenu`, omylom vytvoril neplatne URI uzly
a napisal si vlastny helper na idempotenciu - pricom v tomto repozitari uz tri
roky existoval `createOrUpdateMenuItem()` so spravnym poradim aj funkcnou
update cestou. Nemal som ako vediet, ze existuje. Tento subor je fix toho.

    python3 tools/pfapi.py > docs/reference/action-api.md
    python3 tools/pfapi.py --check      # neaktualny vystup vrati 1 (pre CI)

Zdroje: jar enginu z ~/.m2 (cez javap) + zdrojak EtaskActionDelegate.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DELEGATE_FQN = "com.netgrif.application.engine.petrinet.domain.dataset.logic.action.ActionDelegate"
PROJECT_DELEGATE = REPO / "etask-backend-starter/src/main/groovy/com/netgrif/etask/EtaskActionDelegate.groovy"
OUTPUT = REPO / "docs/reference/action-api.md"

# Groovy/Spring vnutornosti a gettery autowirovanych servisov. Su volatelne, ale
# nie su to extension pointy - patria do implementacie, nie do akcie.
NOISE = re.compile(
    r"^(\$|ActionDelegate$|get(MetaClass|StaticMetaClass)|setMetaClass|super\$|"
    r"(get|set)(Orsr|PostalCode|Workflow|Task|Data|User|PetriNet|Uri|Filter|Mail|Elastic|Rule|Next|Field)"
    r"[A-Za-z]*(Service|Evaluator)$|(get|set)(FieldFactory|RuleRepository)$|"
    r"invokeMethod|getProperty|setProperty)"
)

# Zaradenie podla nazvu. Poradie zalezi - prvy match vyhrava.
GROUPS = [
    ("Case: zakladanie a hladanie", r"^(createCase|findCase|findCases|deleteCase|useCase)"),
    ("Case: vlastnosti a data",     r"^(change|setData|setDataWithPropagation|copyBehavior|makeDataSet)"),
    ("Task: priradenie a vykonanie", r"^(assignTask|assignTasks|cancelTask|cancelTasks|finishTask|finishTasks|executeTask|executeTasks|findTask|findTasks|getTaskId|execute)"),
    ("Uzivatelia a role",           r"^(assignRole|removeRole|changeUser|deleteUser|createUser|findUser|loggedUser|getUser|inviteUser)"),
    ("Filtre a menu",               r"^(create(Case|Task)?Filter|createFilterInMenu|createMenuItem|createTaskMenuItem|createOrUpdate|changeFilter|changeMenuItem|deleteFilter|deleteMenuItem|findFilter|findMenuItem|findFilters|findAllFilters|findDefaultFilters|getFilterFromMenuItem|import|export)"),
    ("URI uzly (bocne menu)",       r"^(createUri|getUri|moveUri|setUriNodeData)"),
    ("Subory a dokumenty",          r"^(file|generate|pdf|zip|save|load|delete.*File|upload|download)"),
    ("Mail a notifikacie",          r"^(send|mail)"),
    ("Validacie",                   r"^(valid|dynamicValidation|changeFieldValidations|always|never)"),
    ("Cache",                       r"^(cache|addToCache|removeFromCache|getFromCache)"),
]


def javap_lines(jar):
    try:
        res = subprocess.run(["javap", "-p", "-classpath", jar, DELEGATE_FQN],
                             capture_output=True, text=True, timeout=120,
                             env={**os.environ, "JAVA_TOOL_OPTIONS": ""})
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"javap sa nepodarilo spustit: {e}"
    if res.returncode != 0:
        return None, (res.stderr or "javap zlyhal").strip()[:300]
    return res.stdout.splitlines(), None


def engine_version_from_pom():
    """Verzia enginu, na ktorej projekt naozaj stoji - z pom.xml backendu.

    Bez toho sa brala lexikograficky posledna z ~/.m2, co na stroji s viacerymi
    verziami enginu (teda na kazdom, kde sa robi na viacerych projektoch)
    znamena inventar CUDZIEHO API: 6.5.0-SNAPSHOT namiesto 6.3.1, o 36 metod
    viac a ine signatury. A kedze `pflint` validuje nazvy metod proti tomuto
    inventaru, prijal by metody, ktore v beziacom enginu nie su, a naopak.
    """
    pom = Path(__file__).resolve().parent.parent.parent / "etask-backend-starter" / "pom.xml"
    if not pom.is_file():
        return None
    xml = pom.read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"<artifactId>\s*application-engine\s*</artifactId>\s*<version>\s*([^<\s]+)\s*</version>",
        xml)
    return m.group(1) if m else None


def find_engine_jar():
    env = os.environ.get("PF_ENGINE_JAR")
    if env and Path(env).is_file():
        return env
    root = Path.home() / ".m2/repository/com/netgrif/application-engine"
    if not root.is_dir():
        return None

    def real(jars):
        return [j for j in jars if "sources" not in j.name and "javadoc" not in j.name]

    version = engine_version_from_pom()
    if version:
        exact = real((root / version).glob("application-engine-*.jar")) \
            if (root / version).is_dir() else []
        if exact:
            return str(sorted(exact)[-1])
        print(f"pfapi: pom.xml chce engine {version}, ale jar preň v ~/.m2 nie je",
              file=sys.stderr)

    jars = real(list(root.glob("*/application-engine-*.jar")))
    if not jars:
        return None
    pick = str(sorted(jars)[-1])
    print(f"pfapi: POZOR beriem {Path(pick).name} - nie je to verzia z pom.xml",
          file=sys.stderr)
    return pick


def short(t):
    """java.util.List<java.lang.String> -> List<String>, bez mrzacenia medzier
    medzi typom a nazvom parametra."""
    t = re.sub(r"\b(?:[a-z][a-zA-Z0-9_]*\.)+([A-Z][A-Za-z0-9_]*)", r"\1", t)
    t = re.sub(r"<\s*([^<>]*?)\s*>", lambda m: "<" + re.sub(r"\s*,\s*", ",", m.group(1)) + ">", t)
    t = re.sub(r"\s*,\s*", ", ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def parse_signatures(lines):
    """{nazov: [zoznam skratenych parametrov]}"""
    out = {}
    for ln in lines:
        m = re.match(r"\s+public\s+(?:static\s+|final\s+|abstract\s+)*"
                     r"(?:<[^>]+>\s+)?([\w.<>,?\[\] $]+?)\s+([\w$]+)\(([^)]*)\)", ln)
        if not m:
            continue
        ret, name, params = m.group(1), m.group(2), m.group(3)
        if NOISE.match(name):
            continue
        out.setdefault(name, {"ret": short(ret), "sigs": set()})
        out[name]["sigs"].add(short(params) if params.strip() else "")
    return out


def parse_project_delegate(path):
    """[(nazov, params, prva veta javadocu)] zo zdrojaku - aj s komentarom."""
    if not path.is_file():
        return []
    src = path.read_text(encoding="utf-8")
    out, doc = [], None
    for block in re.finditer(
            r"(/\*\*(?P<doc>.*?)\*/\s*)?"
            r"^\s{4}(?!private|protected|static)(?:[\w<>,.\[\] ]+\s+)?"
            r"(?P<name>[a-zA-Z_]\w*)\s*\((?P<params>[^)]*)\)\s*\{",
            src, re.S | re.M):
        name = block.group("name")
        if name in ("if", "for", "while", "switch", "catch", "return", "each", "collect"):
            continue
        # Regex s volitelnym javadocom niekedy prejde aj cez modifikator, takze
        # viditelnost overime na realnom riadku deklaracie.
        line_start = src.rfind("\n", 0, block.start("name")) + 1
        decl = src[line_start:block.start("name")]
        if re.search(r"\b(private|protected)\b", decl):
            continue
        doc = block.group("doc") or ""
        first = ""
        for line in doc.splitlines():
            line = line.strip().lstrip("*").strip()
            if line and not line.startswith("@"):
                first = line
                break
        out.append((name, short(block.group("params")), first))
    return out


def group_of(name):
    for label, pattern in GROUPS:
        if re.match(pattern, name, re.I):
            return label
    return "Ostatne"


def render():
    jar = find_engine_jar()
    if not jar:
        return None, "jar enginu sa nenasiel v ~/.m2. Nastav PF_ENGINE_JAR."
    lines, err = javap_lines(jar)
    if err:
        return None, err

    engine = parse_signatures(lines)
    project = parse_project_delegate(PROJECT_DELEGATE)
    project_names = {n for n, _, _ in project}
    # Verzia je v nazve jaru, ale ked jar pride zvonku (`PF_ENGINE_JAR`, CI),
    # moze sa volat hocijako. Vtedy plati pom.xml - a to je aj spravnejsi zdroj:
    # inventar ma zodpovedat verzii, ktoru appka naozaj pouziva.
    #
    # Bez tohto fallbacku sa do hlavicky zapisalo "application-engine-?.jar",
    # `--check` to porovnal s commitnutym suborom a hlasil "inventar je
    # neaktualny" - co je nepravda a posle cloveka regenerovat nieco, co sedi.
    m_ver = re.search(r"application-engine-([\d.]+)\.jar", jar)
    version = m_ver.group(1) if m_ver else (engine_version_from_pom() or "?")

    o = []
    o.append("# Extension pointy volateľné z Petriflow akcie")
    o.append("")
    o.append("> **Generované — needituj ručne.** `python3 tools/pfapi.py > docs/reference/action-api.md`")
    o.append(f"> Zdroj: `application-engine-{version}.jar` + `EtaskActionDelegate.groovy`.")
    o.append("")
    o.append("Všetko nižšie sa dá zavolať priamo z `<action>` alebo `<function>` menom,")
    o.append("bez importov. Delegát je dynamický, takže preklep prejde parserom aj")
    o.append("importom a spadne až za behu — o to viac sa vyplatí pozrieť sem.")
    o.append("")
    o.append("## Pravidlo: najprv tento zoznam, potom nový kód")
    o.append("")
    o.append("Metóda, ktorá tu je, sa nemá písať znova. Nie je to štýlová poznámka —")
    o.append("stálo to hodiny dekompilovania bajtkódu a technický dlh v `UriNodeData`,")
    o.append("kde sú dnes dve polia pre to isté, lebo som nevedel o existujúcom")
    o.append("`setUriNodeData(..., roleIds)`.")
    o.append("")

    # --- projektove metody: to hlavne -----------------------------------
    o.append("## Vlastné metódy tohto projektu — pozri sem PRVÉ")
    o.append("")
    o.append("`EtaskActionDelegate` dedí engine a pridáva toto. Sú prispôsobené tomuto")
    o.append("stacku, takže bývajú správnejšie než ekvivalent v enginu.")
    o.append("")
    for name, params, doc in project:
        o.append(f"### `{name}({params})`")
        if doc:
            o.append(f"{doc}")
        o.append("")

    o.append("> **Pozor na `createOrUpdateMenuItem`.** Existuje dvakrát: tu (7–9 argumentov,")
    o.append("> funkčná update cesta cez `changeFilter`/`changeMenuItem`) a v enginu")
    o.append("> (11 argumentov, na update volá neexistujúce `updateFilter` a **padne**).")
    o.append("> Rozlišujú sa len aritou. Použi tú s 7 argumentmi. Funkčný príklad je")
    o.append("> v `etask-backend-starter/src/main/resources/petriNets/configuration_tiles.xml`.")
    o.append("")

    # --- engine, po skupinach -------------------------------------------
    o.append("## Engine `ActionDelegate`")
    o.append("")
    o.append(f"{len(engine)} unikátnych metód. Pretaženia sú zlúčené: uvedená je")
    o.append("**najdlhšia** varianta, počet ostatných je v zátvorke. Kratšie varianty")
    o.append("majú spravidla defaulty — presnú signatúru si over v jare.")
    o.append("")
    grouped = {}
    for name, info in engine.items():
        grouped.setdefault(group_of(name), []).append((name, info))
    order = [g for g, _ in GROUPS] + ["Ostatne"]
    for label in order:
        items = grouped.get(label)
        if not items:
            continue
        o.append(f"### {label}")
        o.append("")
        for name, info in sorted(items):
            mark = " ⚠️ **prekryté v projekte**" if name in project_names else ""
            sigs = sorted(info["sigs"], key=len)
            n = len(sigs)
            suffix = ""
            if n > 1:
                extra = n - 1
                word = "varianta" if extra == 1 else ("varianty" if extra <= 4 else "variantov")
                suffix = f"  _(+{extra} {word})_"
            o.append(f"- `{name}({sigs[-1]})` → `{info['ret']}`{suffix}{mark}")
        o.append("")
    return "\n".join(o) + "\n", None


def main(argv):
    text, err = render()
    if err:
        print(f"pfapi: {err}", file=sys.stderr)
        return 2
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current.strip() != text.strip():
            print("pfapi: docs/reference/action-api.md je neaktualny. Spusti:", file=sys.stderr)
            print("       python3 tools/pfapi.py > docs/reference/action-api.md", file=sys.stderr)
            return 1
        print("pfapi: docs/reference/action-api.md je aktualny")
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
