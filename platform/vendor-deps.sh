#!/usr/bin/env bash
#
# Dve tranzitívne závislosti Netgrif Application Engine 6.3.1 sa už nedajú
# stiahnuť z verejného repozitára:
#
#   com.novemberain:quartz-mongodb:2.2.0-rc2
#       Deklarovaná v pome enginu, ale neexistuje na Maven Central, Clojars,
#       maven.scijava.org ani na mulesoft. Pôvodne žila na maven.imagej.net,
#       ktorý bol vyradený z prevádzky a dnes presmerováva na scijava, kde
#       artefakt nie je. Na Central je jej zrkadlo pod groupId
#       io.fluidsonic.mirror - ten istý projekt, tí istí autori, tá istá verzia.
#
#   com.github.kenglxn.qrgen:javase:2.6.0
#       JitPack artefakt. Pom enginu ale JitPack ako repozitár nedeklaruje,
#       takže ho Maven nehľadá. Rieši to settings.xml nižšie.
#
# Skript je idempotentný - už nainštalované artefakty preskočí.
set -euo pipefail

M2="${HOME}/.m2"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

CENTRAL="https://repo1.maven.org/maven2"
JITPACK="https://jitpack.io"

log() { printf '  %s\n' "$*"; }

# --- 1. Sanity check nastrojov ----------------------------------------------
#
# JitPack tu ZAMERNE NIE JE ako Maven repozitár, hoci to tak bolo.
#
# Dôvod je zmeraný: JitPack odpovedá Mavenu na neznámy artefakt 403 s HTML
# telom, a Maven to telo uloží pod menom .jar. Prvý build, ktorý na taký súbor
# narazí, padne až v Groovy stub compileri na
#
#   ZipException opening "xml-apis-ext-1.3.04.jar": zip END header not found
#   cannot access java / cannot access groovy
#
# čo vyzerá ako pokazený JDK alebo Groovy, nie ako pokazený download úplne
# iného artefaktu. Maven nemá spôsob, ako repozitár obmedziť na jednu
# groupId, takže jediná obrana je nemať tam repozitár, ktorý si vymýšľa
# odpovede - a qrgen aj tak ťaháme priamo cez curl (krok 3).

command -v mvn  >/dev/null || { echo "vendor-deps: mvn nie je v PATH" >&2; exit 2; }
command -v curl >/dev/null || { echo "vendor-deps: curl nie je v PATH" >&2; exit 2; }

# Overi, ze stiahnuty subor je citatelny zip. Bez toho sa pokazeny download
# nainstaluje do .m2 a chyba sa objavi az o niekolko minut inde.
zip_ok() {
  if command -v unzip >/dev/null 2>&1; then
    unzip -tqq "$1" >/dev/null 2>&1
  else
    # bez unzip aspon magicke bajty: kazdy jar zacina "PK"
    [ "$(head -c 2 "$1")" = "PK" ]
  fi
}

overit_jar() {
  zip_ok "$1" || {
    echo "vendor-deps: $1 nie je platny jar (stiahlo sa HTML alebo skratena odpoved)" >&2
    exit 1
  }
}

# --- 2. quartz-mongodb zo zrkadla pod pôvodnými súradnicami ------------------

QM_DIR="${M2}/repository/com/novemberain/quartz-mongodb/2.2.0-rc2"

if [ -f "${QM_DIR}/quartz-mongodb-2.2.0-rc2.jar" ]; then
  log "quartz-mongodb 2.2.0-rc2 už v .m2, preskakujem"
else
  log "ťahám quartz-mongodb 2.2.0-rc2 zo zrkadla io.fluidsonic.mirror"
  BASE="${CENTRAL}/io/fluidsonic/mirror/quartz-mongodb/2.2.0-rc2/quartz-mongodb-2.2.0-rc2"
  curl -fsSL --retry 3 -o "${TMP}/qm.pom" "${BASE}.pom"
  curl -fsSL --retry 3 -o "${TMP}/qm.jar" "${BASE}.jar"
  overit_jar "${TMP}/qm.jar"

  # Prepíšeme groupId na pôvodný, aby to Maven našiel pod súradnicami,
  # ktoré žiada pom enginu. Zvyšok pomu (tranzitívne závislosti) ostáva.
  sed 's|<groupId>io\.fluidsonic\.mirror</groupId>|<groupId>com.novemberain</groupId>|' \
    "${TMP}/qm.pom" > "${TMP}/qm-novemberain.pom"

  mvn -q -B install:install-file \
    -Dfile="${TMP}/qm.jar" \
    -DpomFile="${TMP}/qm-novemberain.pom" \
    -DgroupId=com.novemberain \
    -DartifactId=quartz-mongodb \
    -Dversion=2.2.0-rc2 \
    -Dpackaging=jar
fi

# --- 3. qrgen z JitPacku ----------------------------------------------------
#
# JitPack odpovedá Mavenu 403, ale na priame stiahnutie funguje, takže
# artefakty doťahujeme sami a nainštalujeme lokálne. Treba aj parent pom
# a modul core, inak sa javase nerozreší.

QR_DIR="${M2}/repository/com/github/kenglxn/qrgen"

if [ -f "${QR_DIR}/javase/2.6.0/javase-2.6.0.jar" ]; then
  log "qrgen 2.6.0 už v .m2, preskakujem"
else
  log "ťahám qrgen 2.6.0 z JitPacku (parent, core, javase)"
  curl -fsSL --retry 3 -o "${TMP}/qrgen-parent.pom" "${JITPACK}/com/github/kenglxn/qrgen/qrgen-parent/2.6.0/qrgen-parent-2.6.0.pom"
  curl -fsSL --retry 3 -o "${TMP}/core.pom"        "${JITPACK}/com/github/kenglxn/qrgen/core/2.6.0/core-2.6.0.pom"
  curl -fsSL --retry 3 -o "${TMP}/core.jar"        "${JITPACK}/com/github/kenglxn/qrgen/core/2.6.0/core-2.6.0.jar"
  curl -fsSL --retry 3 -o "${TMP}/javase.pom"      "${JITPACK}/com/github/kenglxn/qrgen/javase/2.6.0/javase-2.6.0.pom"
  curl -fsSL --retry 3 -o "${TMP}/javase.jar"      "${JITPACK}/com/github/kenglxn/qrgen/javase/2.6.0/javase-2.6.0.jar"
  overit_jar "${TMP}/core.jar"
  overit_jar "${TMP}/javase.jar"

  mvn -q -B install:install-file -Dfile="${TMP}/qrgen-parent.pom" -DpomFile="${TMP}/qrgen-parent.pom" -Dpackaging=pom
  mvn -q -B install:install-file -Dfile="${TMP}/core.jar"         -DpomFile="${TMP}/core.pom"
  mvn -q -B install:install-file -Dfile="${TMP}/javase.jar"       -DpomFile="${TMP}/javase.pom"
fi

log "závislosti pripravené"
