# POZOR: build context je ROOT repozitára, nie tento priečinok.
#   docker build -f etask-backend-starter/Dockerfile -t etask-backend .
# Dôvod: build potrebuje aj deploy/vendor-deps.sh z rootu.

# POZOR na základné obrazy: `maven:3-jdk-11` ani `openjdk:11-jdk` už na Docker
# Hube NEEXISTUJÚ - oficiálna rodina `openjdk` bola stiahnutá a JDK 11 tagy
# Mavenu s ňou. Build padne na
#   failed to resolve source metadata for docker.io/library/openjdk:11-jdk
# čo nevyzerá ako zastaraný Dockerfile, ale ako problém so sieťou alebo
# s prihlásením do registry. Nástupca je Eclipse Temurin.
#
# JDK (nie JRE) aj v runtime stage zámerne: engine kompiluje Petriflow akcie
# Groovy compilerom za behu a stack drží Javu 11 (Groovy 3 na 17/21 padá).
FROM maven:3.9-eclipse-temurin-11 AS build
LABEL maintainer="Netgrif <devops@netgrif.com>"
WORKDIR /app

# Dve tranzitívne závislosti enginu 6.3.1 sa nedajú rozrešiť z verejných
# repozitárov - viď komentár v deploy/vendor-deps.sh. Bez tohto kroku padne
# `mvn package` na "Could not resolve dependencies" na akomkoľvek čistom stroji.
COPY deploy/vendor-deps.sh /app/vendor-deps.sh
# `sed` zmaze CR: na Windowse ma checkout CRLF (core.autocrlf=true), takze
# shebang sa v kontejneri cita ako `#!/usr/bin/env bash\r` a build padne na
#   /usr/bin/env: 'bash\r': No such file or directory
# co vyzera ako chybajuci bash v obraze, nie ako konce riadkov. .gitattributes
# v roote to riesi pre buduce checkouty; toto riesi ten aktualny.
RUN sed -i 's/\r$//' /app/vendor-deps.sh \
 && chmod +x /app/vendor-deps.sh \
 && /app/vendor-deps.sh

COPY etask-backend-starter/pom.xml /app/pom.xml
COPY etask-backend-starter/src /app/src

# Siete Service Desku sa do jaru beru priamo z modelovacieho priecinka (viď
# <resources> v pom.xml), takze musia byt na tej istej relativnej ceste ako v
# repozitari - inak by ich Maven mlcky preskocil a jar by sa zbalil bez nich.
COPY etask-configuration/processes /etask-configuration/processes
# `processes.json` je manifest: zoznam a poradie importu, `bootstrapCase`
# a `uriNodes`. Musi byt v kontexte zvlast - `processes` je priecinok so
# sietami, manifest lezi o uroven vyssie.
#
# Kym tu tento riadok nebol, obraz obsahoval siete, ale NIE manifest, a Maven
# chybajuci resource mlcky preskocil (pozri komentar v pom.xml). Prejavilo sa
# to az v bezicom kontejneri dvoma riadkami v logu:
#   NetRunner: petriNets/processes.json: ziadne siete na import
#   BootstrapCaseRunner finished        (za 13 ms, bez jedineho case-u)
# Cize: prazdna appka bez menu a bez konfiguracie, a v logu ziadna chyba.
COPY etask-configuration/processes.json /etask-configuration/processes.json

RUN mvn -B -DskipTests=true -f /app/pom.xml clean package \
 && test -f /app/target/classes/petriNets/sd_ticket.xml \
 && test -f /app/target/classes/petriNets/processes.json \
 || { echo "CHYBA: siete alebo manifest sa nedostali do buildu"; exit 1; }


FROM eclipse-temurin:11-jdk
LABEL maintainer="Netgrif <devops@netgrif.com>"

# Backend ukladá nahraný Petriflow model pod názvom procesu ako názov súboru.
# Pri ASCII locale zhodí InvalidPathException každý upload procesu, ktorý má
# v názve diakritiku. UTF-8 tu nie je kozmetika.
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Pozor: NIE app-exec.jar. Ten má v manifeste
# Start-Class: org.springframework.boot.loader.JarLauncher, teda ukazuje sám
# na seba a pri štarte skončí na StackOverflowError. Spôsobuje to
# <classifier>exec</classifier> na exekúcii build-info v pom.xml.
# Spustiteľný je app.jar so Start-Class: com.netgrif.etask.EtaskApplication.
COPY --from=build /app/target/app.jar /app.jar
COPY --from=build /app/src/main/resources /src/main/resources

# openssl je pre entrypoint - generuje JWT kluc, ak chyba.
#
# tesseract je pre citanie skenovanych faktur (com.netgrif.etask.doc).
# Textova vrstva PDF ide cez PDFBox a nic navyse nepotrebuje, ale sken a fotka
# potrebuju OCR - a to je binarka, nie Java kniznica (Tess4J by znamenal
# nativnu kniznicu na kazdom stroji). Preto je v obraze: appka bez nej bezi,
# len OCR povie "nie je k dispozicii" a to na demo nestaci.
#
# `tesseract-ocr-slk` je povinne: bez slovenskych jazykovych dat vracia
# tesseract na slovenskej fakture zmes znakov, ktora VYZERA ako precitany text,
# takze sa to neprejavi ako chyba, ale ako nezmyselne predvyplnene polia.
# `poppler-utils` nie je potreba - PDF sa rasterizuje PDFBoxom.
# `unzip` je pre CI: krok "verify jar" v .github/workflows/deploy.yml cita
# obsah /app.jar prikazom `unzip` VNUTRI tohto obrazu. Obraz `openjdk:11-jdk`
# ho mal, `eclipse-temurin:11-jdk` nie - a bez neho ten krok nepadne na
# "unzip: not found", ale na "CHYBA: /app.jar nema Start-Class", cize hlasi
# uplne iny problem, nez aky ma.
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssl \
      unzip \
      tesseract-ocr \
      tesseract-ocr-slk \
      tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/* \
 && tesseract --list-langs

COPY etask-backend-starter/docker-entrypoint.sh /docker-entrypoint.sh
# To iste co pri vendor-deps.sh, len tu by sa CRLF neprejavil pri builde, ale
# az pri starte kontejnera - "exec /docker-entrypoint.sh: no such file or
# directory" na subore, ktory v obraze zjavne je.
RUN sed -i 's/\r$//' /docker-entrypoint.sh \
 && chmod +x /docker-entrypoint.sh

# Volume, aby kluc prezil restart aj vymenu obrazu. Keby sa generoval pri kazdom
# starte, vsetkym by pri kazdom nasadeni vypadli sessions.
VOLUME ["/etask/certificates"]

EXPOSE 8080
ENTRYPOINT ["/docker-entrypoint.sh"]
