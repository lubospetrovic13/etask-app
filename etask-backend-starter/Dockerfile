# POZOR: build context je ROOT repozitára, nie tento priečinok.
#   docker build -f etask-backend-starter/Dockerfile -t etask-backend .
# Dôvod: build potrebuje aj deploy/vendor-deps.sh z rootu.

FROM maven:3-jdk-11 AS build
MAINTAINER Netgrif <devops@netgrif.com>
WORKDIR /app

# Dve tranzitívne závislosti enginu 6.3.1 sa nedajú rozrešiť z verejných
# repozitárov - viď komentár v deploy/vendor-deps.sh. Bez tohto kroku padne
# `mvn package` na "Could not resolve dependencies" na akomkoľvek čistom stroji.
COPY deploy/vendor-deps.sh /app/vendor-deps.sh
RUN chmod +x /app/vendor-deps.sh && /app/vendor-deps.sh

COPY etask-backend-starter/pom.xml /app/pom.xml
COPY etask-backend-starter/src /app/src

RUN mvn -B -DskipTests=true -f /app/pom.xml clean package


FROM openjdk:11-jdk
MAINTAINER Netgrif <devops@netgrif.com>

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

EXPOSE 8080
ENTRYPOINT ["java","-jar","/app.jar"]
