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

# --- 1. JitPack ako repozitár pre qrgen -------------------------------------

if [ ! -f "${M2}/settings.xml" ]; then
  log "zapisujem ${M2}/settings.xml s JitPack repozitárom"
  mkdir -p "${M2}"
  cat > "${M2}/settings.xml" <<'XML'
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0">
  <profiles>
    <profile>
      <id>etask-extra-repos</id>
      <repositories>
        <repository>
          <id>jitpack</id>
          <url>https://jitpack.io</url>
        </repository>
      </repositories>
    </profile>
  </profiles>
  <activeProfiles>
    <activeProfile>etask-extra-repos</activeProfile>
  </activeProfiles>
</settings>
XML
else
  log "settings.xml už existuje, nechávam ho"
fi

# --- 2. quartz-mongodb zo zrkadla pod pôvodnými súradnicami ------------------

QM_DIR="${M2}/repository/com/novemberain/quartz-mongodb/2.2.0-rc2"

if [ -f "${QM_DIR}/quartz-mongodb-2.2.0-rc2.jar" ]; then
  log "quartz-mongodb 2.2.0-rc2 už v .m2, preskakujem"
else
  log "ťahám quartz-mongodb 2.2.0-rc2 zo zrkadla io.fluidsonic.mirror"
  BASE="${CENTRAL}/io/fluidsonic/mirror/quartz-mongodb/2.2.0-rc2/quartz-mongodb-2.2.0-rc2"
  curl -fsSL --retry 3 -o "${TMP}/qm.pom" "${BASE}.pom"
  curl -fsSL --retry 3 -o "${TMP}/qm.jar" "${BASE}.jar"

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

  mvn -q -B install:install-file -Dfile="${TMP}/qrgen-parent.pom" -DpomFile="${TMP}/qrgen-parent.pom" -Dpackaging=pom
  mvn -q -B install:install-file -Dfile="${TMP}/core.jar"         -DpomFile="${TMP}/core.pom"
  mvn -q -B install:install-file -Dfile="${TMP}/javase.jar"       -DpomFile="${TMP}/javase.pom"
fi

log "závislosti pripravené"
