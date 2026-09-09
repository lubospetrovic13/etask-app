#!/usr/bin/env python3
"""
pfnew - vygeneruje skelet appky, ktory hned prejde celou overovacou retazou.

DOVOD: appka postavena od nuly znamena znovu vymyslet vzory, ktore v repozitari
uz su - stavove pole s `immediate`, nazov pripadu zacinajuci stavom, farba,
menu s deviatimi argumentmi a delete+recreate, `allowedNets` kvoli stlpcom,
slucka obchadzajuca B8b, akceptacny test proti beziacemu enginu. To je zaroven
vacsina nakladu na jednu appku a vacsina cyklov straveni na tichych pascach.

Vygenerovane subory ich uz obsahuju. Agent potom pise ROZDIELY - domenovu
logiku - nie appku.

    python3 tools/pfnew.py dovolenky ziadost "Žiadosť o dovolenku" \\
        --initials ZOD --role veduci --role-title "Vedúci oddelenia" \\
        --icon beach_access

    python3 tools/pfnew.py --help

Co vznikne:

    processes/<app>_<entita>.xml   siet: 3 miesta, 2 prechody, stav, farba
    processes/<app>_menu.xml       karta a dve zobrazenia so stlpcami
    processes.json                 doplneny import, bootstrapCase, uriNodes
    tools/<app>check.py            akceptacny test proti beziacemu enginu

Nic sa neprepisuje - ked subor existuje, pfnew skonci a povie to.

Po vygenerovani:

    python3 tools/pflint.py processes/
    python3 tools/pfgroovy.py processes/
    tools/up.sh                    # manifest sa pakuje do jaru, treba prestavat
    python3 tools/<app>check.py
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- sablony
#
# Nahradzuju sa tokeny __TAKTO__, nie `str.format` - v Groovy je zlozena
# zatvorka na kazdom druhom riadku a escapovanie by sablony spravilo necitatelne.

NET = '''<document xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="https://petriflow.com/petriflow.schema.xsd">
	<id>__APP__/__NET__</id>
	<version>1.0.0</version>
	<initials>__INITIALS__</initials>
	<title>__TITLE__</title>
	<icon>__ICON__</icon>
	<defaultRole>false</defaultRole>
	<anonymousRole>false</anonymousRole>
	<transitionRole>false</transitionRole>
	<!--
		Skelet z tools/pfnew.py. Domenova logika sa dopisuje, vzory nizsie sa
		nemenia bez dovodu - kazdy z nich je tu kvoli konkretnej tichej pasci.

		  p_novy -> t___PREFIX___podanie -> p_hotovy

		Stav je SAMOSTATNE POLE s `immediate="true"`, nie len poloha tokenu:
		inak sa neda dat do stlpca zoznamu ani podla neho hladat. Nazov pripadu
		zacina stavom, lebo stlpec Nazov sa v zozname skracuje a odpada koniec.

		Ked pridas dalsiu ulohu, NEVES ju na read arc z miesta, ktore nejaky
		prechod konzumuje - odmietnute DOKONCIT ju zmaze a neobnovi
		(PETRIFLOW_LEARNINGS B8b). Bud sink, alebo cast tej istej ulohy.
	-->
	<caseEvents>
		<event type="create">
			<id>__PREFIX___create</id>
			<actions phase="post">
				<action id="1"><![CDATA[
__PREFIX___stav_label: f.__PREFIX___stav_label, __PREFIX___predmet: f.__PREFIX___predmet;

change __PREFIX___stav_label value { "Rozpísané" }
changeCaseProperty("title").about { nazov(__PREFIX___predmet, "Rozpísané") }
changeCaseProperty("color").about { "grey" }
				]]></action>
			</actions>
		</event>
	</caseEvents>
	<function scope="process" name="kto"><![CDATA[
{ def u ->
    // `?.` chráni pred null, nie pred chýbajúcou property.
    return (u.hasProperty("fullName") && u.fullName) ? (u.fullName as String) : (u.email as String)
}
	]]></function>
	<function scope="process" name="nazov"><![CDATA[
{ def pole, def stav ->
    // Stav je na ZACIATKU: stlpec Nazov sa v zozname skracuje a to, co je na
    // konci, odpadne prve.
    def p = ((pole.value ?: "") as String).trim()
    return (stav as String) + " · " + (p ?: "__TITLE__")
}
	]]></function>
	<roleRef>
		<id>__ROLE__</id>
		<caseLogic>
			<create>true</create>
			<view>true</view>
		</caseLogic>
	</roleRef>
	<role>
		<id>__ROLE__</id>
		<title>__ROLE_TITLE__</title>
	</role>
	<data type="i18n">
		<id>div___PREFIX___zadanie</id>
		<title/>
		<init>Zadanie</init>
	</data>
	<data type="i18n">
		<id>div___PREFIX___vysledok</id>
		<title/>
		<init>Výsledok</init>
	</data>
	<data type="text" immediate="true">
		<id>__PREFIX___predmet</id>
		<title>Predmet</title>
	</data>
	<data type="text">
		<id>__PREFIX___popis</id>
		<title>Popis</title>
		<component>
			<name>textarea</name>
		</component>
	</data>
	<data type="text" immediate="true">
		<id>__PREFIX___stav_label</id>
		<title>Stav</title>
		<desc>Samostatné pole, aby sa dalo dať do stĺpca a hľadať podľa neho.</desc>
	</data>
	<data type="text">
		<id>__PREFIX___podal</id>
		<title>Podal</title>
	</data>
	<data type="dateTime">
		<id>__PREFIX___podane_o</id>
		<title>Podané</title>
	</data>
	<transition>
		<id>t___PREFIX___podanie</id>
		<x>140</x>
		<y>80</y>
		<label>Podanie</label>
		<icon>__ICON__</icon>
		<!--
			`auto` je v poriadku na OSOBNU ulohu jedneho aktera. Na zdielanu
			(pult, front, prepazka) patri `manual` - auto ju priradi tomu, kto
			ju vyrobil (PETRIFLOW_LEARNINGS B21).
		-->
		<assignPolicy>auto</assignPolicy>
		<roleRef>
			<id>__ROLE__</id>
			<!--
				`perform` je skratka pre assign+cancel+finish+view+set,
				`delegate` v nej NIE JE. `cancel` nezakazuj - uvolnuje ulohu,
				nerusi ju.
			-->
			<logic>
				<perform>true</perform>
			</logic>
		</roleRef>
		<dataGroup>
			<id>g___PREFIX___zadanie</id>
			<cols>6</cols>
			<layout>grid</layout>
			<dataRef>
				<id>div___PREFIX___zadanie</id>
				<logic><behavior>visible</behavior></logic>
				<layout><x>0</x><y>0</y><rows>1</rows><cols>6</cols><template>material</template><appearance>outline</appearance></layout>
				<component><name>divider</name></component>
			</dataRef>
			<dataRef>
				<id>__PREFIX___predmet</id>
				<logic><behavior>editable</behavior><behavior>required</behavior></logic>
				<layout><x>0</x><y>1</y><rows>1</rows><cols>6</cols><template>material</template><appearance>outline</appearance></layout>
			</dataRef>
			<dataRef>
				<id>__PREFIX___popis</id>
				<logic><behavior>editable</behavior></logic>
				<layout><x>0</x><y>2</y><rows>3</rows><cols>6</cols><template>material</template><appearance>outline</appearance></layout>
			</dataRef>
		</dataGroup>
		<event type="finish">
			<id>t___PREFIX___podanie_finish</id>
			<actions phase="pre">
				<action id="2"><![CDATA[
__PREFIX___predmet: f.__PREFIX___predmet;

// Sem validacie, ktore `required` neoveri. Odmietnutie vrati HTTP 200
// a dovod v tele ako `error` - test na stavovy kod ho prehliadne.
if (!((__PREFIX___predmet.value ?: "") as String).trim()) {
    throw new java.lang.IllegalStateException("Predmet musí byť vyplnený.")
}
				]]></action>
			</actions>
			<actions phase="post">
				<action id="3"><![CDATA[
__PREFIX___predmet: f.__PREFIX___predmet, __PREFIX___stav_label: f.__PREFIX___stav_label,
__PREFIX___podal: f.__PREFIX___podal, __PREFIX___podane_o: f.__PREFIX___podane_o;

change __PREFIX___stav_label value { "Podané" }
change __PREFIX___podal value { kto(loggedUser()) }
change __PREFIX___podane_o value { java.time.LocalDateTime.now() }
changeCaseProperty("title").about { nazov(__PREFIX___predmet, "Podané") }
changeCaseProperty("color").about { "green" }
				]]></action>
			</actions>
		</event>
	</transition>
	<transition>
		<id>t___PREFIX___prehlad</id>
		<x>332</x>
		<y>80</y>
		<label>Podané</label>
		<icon>fact_check</icon>
		<assignPolicy>auto</assignPolicy>
		<!--
			Read arc z `p_hotovy`, ktore je SINK - nikto ho nekonzumuje, takze
			tento pohlad nemoze zmiznut po odmietnutom DOKONCIT (B8b).
		-->
		<roleRef>
			<id>__ROLE__</id>
			<logic>
				<perform>true</perform>
			</logic>
		</roleRef>
		<dataGroup>
			<id>g___PREFIX___prehlad</id>
			<cols>6</cols>
			<layout>grid</layout>
			<dataRef>
				<id>__PREFIX___stav_label</id>
				<logic><behavior>visible</behavior></logic>
				<layout><x>0</x><y>0</y><rows>1</rows><cols>2</cols><template>material</template><appearance>outline</appearance></layout>
			</dataRef>
			<dataRef>
				<id>__PREFIX___predmet</id>
				<logic><behavior>visible</behavior></logic>
				<layout><x>2</x><y>0</y><rows>1</rows><cols>4</cols><template>material</template><appearance>outline</appearance></layout>
			</dataRef>
			<dataRef>
				<id>div___PREFIX___vysledok</id>
				<logic><behavior>visible</behavior></logic>
				<layout><x>0</x><y>1</y><rows>1</rows><cols>6</cols><template>material</template><appearance>outline</appearance></layout>
				<component><name>divider</name></component>
			</dataRef>
			<dataRef>
				<id>__PREFIX___popis</id>
				<logic><behavior>visible</behavior></logic>
				<layout><x>0</x><y>2</y><rows>3</rows><cols>6</cols><template>material</template><appearance>outline</appearance></layout>
			</dataRef>
			<dataRef>
				<id>__PREFIX___podal</id>
				<logic><behavior>visible</behavior></logic>
				<layout><x>0</x><y>5</y><rows>1</rows><cols>3</cols><template>material</template><appearance>outline</appearance></layout>
			</dataRef>
			<dataRef>
				<id>__PREFIX___podane_o</id>
				<logic><behavior>visible</behavior></logic>
				<layout><x>3</x><y>5</y><rows>1</rows><cols>3</cols><template>material</template><appearance>outline</appearance></layout>
			</dataRef>
		</dataGroup>
	</transition>
	<place>
		<id>p_novy</id>
		<x>40</x>
		<y>80</y>
		<label>Rozpísané</label>
		<tokens>1</tokens>
		<static>false</static>
	</place>
	<place>
		<id>p_hotovy</id>
		<x>236</x>
		<y>80</y>
		<label>Podané</label>
		<tokens>0</tokens>
		<static>false</static>
	</place>
	<arc>
		<id>a___PREFIX___podanie_in</id>
		<type>regular</type>
		<sourceId>p_novy</sourceId>
		<destinationId>t___PREFIX___podanie</destinationId>
		<multiplicity>1</multiplicity>
	</arc>
	<arc>
		<id>a___PREFIX___podanie_out</id>
		<type>regular</type>
		<sourceId>t___PREFIX___podanie</sourceId>
		<destinationId>p_hotovy</destinationId>
		<multiplicity>1</multiplicity>
	</arc>
	<arc>
		<id>a___PREFIX___prehlad</id>
		<type>read</type>
		<sourceId>p_hotovy</sourceId>
		<destinationId>t___PREFIX___prehlad</destinationId>
		<multiplicity>1</multiplicity>
	</arc>
</document>
'''


MENU = '''<document xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="https://petriflow.com/petriflow.schema.xsd">
	<id>__APP__/__PREFIX___menu</id>
	<version>1.0.0</version>
	<initials>__MENU_INITIALS__</initials>
	<title>Menu __TITLE__</title>
	<icon>menu</icon>
	<defaultRole>false</defaultRole>
	<anonymousRole>false</anonymousRole>
	<transitionRole>false</transitionRole>
	<!--
		Skelet z tools/pfnew.py. Kazdy vzor tu je kvoli konkretnej pasci:

		  * `createOrUpdateMenuItem` sa vola s DEVIATIMI argumentmi. Existuje
		    dvakrat - projektova (7-9) a enginova (11) - a rozlisuju sa len
		    aritou. Pri osmich si Groovy vyberie enginovu a padne to.
		  * Jej UPDATE cesta nefunguje, takze polozka sa vzdy zahodi a postavi
		    znova. PORADIE: najprv `deleteMenuItem`, POTOM `deleteFilter` -
		    naopak to padne, lebo deleteMenuItem si filter jeste raz nacita.
		  * `nets` (allowedNets) musi byt, inak sa nevykreslia stlpce
		    z datovych poli - a to bez akehokolvek hlasenia.
		  * URI cesta MUSI sedet s klucom v `uriNodes` v processes.json, inak
		    polozka vznikne bez karty, na ktorej by bola vidno.
	-->
	<caseEvents>
		<event type="create">
			<id>__PREFIX___menu_create</id>
			<actions phase="post">
				<action id="1"><![CDATA[
def created = []
def unchanged = []
def failed = []

def siet = "__APP__/__NET__"
def vsetky = "processIdentifier:\\"" + siet + "\\""
def stlpce = "meta-title" +
        ",__APP__/__NET__-__PREFIX___stav_label" +
        ",__APP__/__NET__-__PREFIX___predmet"

def views = [
        // Nazov prveho zobrazenia je TITULOK SIETE, nie kopia toho retazca.
        // Titulok siete je I18nString a ma svoj preklad v bloku `<i18n>`, takze
        // sa preklada na jednom mieste; kopia by znamenala prelozit to dvakrat
        // a druhy vyskyt by nikto nenasiel - nazvy zobrazeni su v Groovy akcii,
        // kde `pfi18n` nedosiahne.
        [id: "__PREFIX___vsetky", name: petriNetService.getNewestVersionByIdentifier(siet).title,
         type: "Case", icon: "__ICON__",
         query: vsetky, nets: [siet], roles: [:], headers: stlpce],
        // Filtrovanie podla DATOVEHO POLA, nie podla polohy tokenu. Ide to,
        // lebo `__PREFIX___stav_label` ma `immediate="true"` a engine ho
        // indexuje pod `dataSet.__PREFIX___stav_label.textValue`.
        [id: "__PREFIX___rozpisane", name: i18n("Rozpísané", ["en": "Draft"]),
         type: "Case", icon: "edit_note",
         query: vsetky + " AND dataSet.__PREFIX___stav_label.textValue:\\"Rozpísané\\"",
         nets: [siet], roles: [:], headers: stlpce],
]

views.each { v ->
    def id = v.id as String
    try {
        def existing = menu_item(id)
        if (existing != null) {
            // Porovnava sa dopyt A allowedNets - oboje ide do konstruktora
            // a na existujucej polozke sa zmenit nedaju.
            def current = getFilterFromMenuItem(existing)
            def currentQuery = ((current?.dataSet?."filter"?.value ?: "") as String)
            def currentNets = ((current?.dataSet?."filter"?.allowedNets ?: []) as List)
                    .collect { it as String } as Set
            def wantNets = (v.nets as List).collect { it as String } as Set
            // Do porovnania patri aj NAZOV, vratane prekladov. Bez toho by uz
            // nasadena instancia zmeneny nazov (a doplneny preklad) nikdy
            // nedostala: polozka tam je s tym istym dopytom, takze by sa vzdy
            // vyhodnotila ako nezmenena.
            def currentName = current?.dataSet?."i18n_filter_name"?.value
            def sameName = currentName != null &&
                    (currentName.defaultValue as String) == (v.name.defaultValue as String) &&
                    (currentName.translations ?: [:]) == (v.name.translations ?: [:])
            if (currentQuery == (v.query as String) && currentNets == wantNets && sameName) {
                nastav_zobrazenie(existing, v.nets as List, v.headers)
                unchanged << id
                return
            }
            deleteMenuItem(existing)
            if (current != null) {
                deleteFilter(current)
            }
        }
        def item = createOrUpdateMenuItem(
                id,                 // menu_item_identifier
                "__APP__",          // URI cesta - musi sedet s uriNodes
                v.type as String,
                v.query as String,
                v.icon as String,
                v.name,             // I18nString - polozka menu vie byt dvojjazycna
                v.nets as List,     // allowedNets - bez toho ziadne stlpce
                v.roles as Map,
                [:]                 // bannedRoles - dourcuje aritu na projektovu
        )
        if (item) { created << id } else { failed << id }
        nastav_zobrazenie(item, v.nets as List, v.headers)
    } catch (Exception e) {
        failed << (id + " (" + e.getClass().simpleName + ": " + e.message + ")")
    }
}

def summary = "Menu __TITLE__ – " + (created.size() + unchanged.size()) + "/" + views.size()
if (failed) {
    summary = "CHYBA menu __TITLE__ – nepodarilo sa: " + failed.join(", ")
}
changeCaseProperty("title").about { summary }
				]]></action>
			</actions>
		</event>
	</caseEvents>
	<function scope="process" name="nastav_zobrazenie"><![CDATA[
{ def menuItem, def nets, def headers ->
    // `enable_case_title`  - vypnuty dialog "Vyplnte nazov pripadu" pri "+".
    // `default_headers`    - predvolene stlpce zoznamu.
    // Ani jedno nie je argument `createOrUpdateMenuItem`.
    if (menuItem == null) return
    def payload = [:]
    if (nets) {
        payload.put("enable_case_title", ["value": false, "type": "boolean"])
        payload.put("case_require_title_in_creation", ["value": false, "type": "boolean"])
    }
    if (headers) {
        payload.put("default_headers", ["value": headers as String, "type": "text"])
    }
    if (payload) {
        setData("view", menuItem, payload)
    }
}
	]]></function>
	<function scope="process" name="menu_item"><![CDATA[
{ def identifier ->
    // `findMenuItem(id)` z ActionDelegate existujucu polozku nenajde (hlada
    // v inom rozsahu), takze by sa pri kazdom spusteni zalozila druha sada.
    def id = ((identifier ?: "") as String).trim()
    if (!id) return null
    def items = findCases { it.processIdentifier.eq("preference_filter_item") }
    return items?.find { ((it.dataSet["menu_item_identifier"]?.value ?: "") as String) == id }
}
	]]></function>
	<roleRef>
		<id>__ROLE__</id>
		<caseLogic>
			<create>true</create>
			<view>true</view>
		</caseLogic>
	</roleRef>
	<role>
		<id>__ROLE__</id>
		<title>__ROLE_TITLE__</title>
	</role>
	<transition>
		<id>t___PREFIX___menu</id>
		<x>112</x>
		<y>80</y>
		<label>Stav menu</label>
		<icon>menu</icon>
		<assignPolicy>auto</assignPolicy>
		<roleRef>
			<id>__ROLE__</id>
			<logic>
				<perform>true</perform>
			</logic>
		</roleRef>
	</transition>
	<place>
		<id>p_alive</id>
		<x>32</x>
		<y>80</y>
		<label>Živé</label>
		<tokens>1</tokens>
		<static>false</static>
	</place>
	<arc>
		<id>a___PREFIX___menu</id>
		<type>read</type>
		<sourceId>p_alive</sourceId>
		<destinationId>t___PREFIX___menu</destinationId>
		<multiplicity>1</multiplicity>
	</arc>
</document>
'''


CHECK = '''#!/usr/bin/env python3
"""
__APP__check - akceptacny test appky __TITLE__ proti BEZIACEMU enginu.

Skelet z tools/pfnew.py. Overuje to, co sa z XML ani z importu zistit neda.
Domenove kontroly sa dopisuju; to, co je tu, plati pre kazdu appku.

Styri veci, na ktore sa v tomto repozitari naletelo a preto su v kode napisane:

  1. Telo `POST /api/task/{id}/data` je {taskId: {fieldId: {...}}}, NIE
     {fieldId: {...}}. Ploche telo vrati HTTP 200 s hlaskou "Could not find
     task with id [<fieldId>]" a ticho nezapise nic.
  2. Engine odmietnutie NEHLASI HTTP kodom - `finish` vrati 200 a dovod da do
     tela ako `error`. Test na status by taky blok prehliadol.
  3. `GET /api/auth/login` vrati 405, ale token uz je v hlavicke - filter bezi
     pred handlerom.
  4. `GET /api/task/case/{id}` NEOVERUJE opravnenia. Na to, co uzivatel naozaj
     vidi, sa musi pouzit `POST /api/task/search`.

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/__APP__check.py
    python3 tools/__APP__check.py --wipe

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.
"""

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("PF_URL", "http://127.0.0.1:8080")
TEST_PASS = os.environ.get("ETASK_TEST_PASSWORD", "test1234")
SUPER_PASS = os.environ.get("PF_PASS", "password")
NET = "__APP__/__NET__"
CARD = "__APP__"
ROLE_USER_EMAIL = "admin@test.local"       # ucet, ktory ma rolu `__ROLE__`
OTHER_USER_EMAIL = "operator@test.local"   # ucet, ktory ju NEMA, ale karty vidi

OK, FAIL = [], []


class Client:
    def __init__(self, email, password, allow_fail=False):
        self.email = email
        self.token = None
        req = urllib.request.Request(
            URL + "/api/auth/login", method="GET",
            headers={"Authorization": "Basic " + base64.b64encode(
                f"{email}:{password}".encode()).decode()})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                self.token = r.headers.get("X-Auth-Token")
        except urllib.error.HTTPError as e:
            self.token = e.headers.get("X-Auth-Token")
        except urllib.error.URLError:
            sys.exit(f"__APP__check: engine na {URL} neodpoveda")
        if not self.token and not allow_fail:
            sys.exit(f"__APP__check: prihlasenie {email} zlyhalo")

    def call(self, method, path, body=None, timeout=120):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"X-Auth-Token": self.token,
                   # Bez hal+json vracaju HATEOAS endpointy 406.
                   "Accept": "application/hal+json, application/json;q=0.9, */*;q=0.8"}
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode("utf-8")
                return r.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def get(self, p):
        return self.call("GET", p)

    def post(self, p, body=None):
        return self.call("POST", p, body)


def check(label, cond, detail=""):
    (OK if cond else FAIL).append(label)
    print(("  [OK]   " if cond else "  [ZLE] ") + label + ((" -- " + str(detail)) if detail else ""))


def newest_net(cl, identifier):
    st, r = cl.post("/api/petrinet/search?size=200", {"identifier": identifier})
    refs = [x for x in r["_embedded"]["petriNetReferences"] if x["identifier"] == identifier]
    if not refs:
        sys.exit(f"__APP__check: siet {identifier} nie je naimportovana")
    refs.sort(key=lambda x: [int(n) for n in x["version"].split(".")])
    return refs[-1]


def new_case(cl, net_id):
    st, r = cl.post("/api/workflow/case", {"netId": net_id, "title": None, "color": ""})
    m = re.search(r"Case with id ([0-9a-f]{24})",
                  r.get("success", "") if isinstance(r, dict) else "")
    if not m:
        sys.exit(f"__APP__check: zalozenie pripadu zlyhalo: {st} {str(r)[:300]}")
    st, c = cl.get(f"/api/workflow/case/{m.group(1)}")
    return m.group(1), c


def tasks_of(cl, case_id):
    """Ulohy, ktore uzivatel NAOZAJ vidi - `/api/task/case/{id}` opravnenia
    neoveruje a vrati vsetko kazdemu, kto pozna id."""
    st, r = cl.post("/api/task/search?size=100", {"case": [{"id": case_id}]})
    tl = (r.get("_embedded") or {}).get("tasks", []) if isinstance(r, dict) else []
    return {t["transitionId"]: t["stringId"] for t in tl}


def field_map(cl, task_id):
    st, d = cl.get(f"/api/task/{task_id}/data")
    groups = (d.get("data") or d.get("outcome", {}).get("data") or []) if isinstance(d, dict) else []
    out = {}
    for grp in groups:
        for _, lst in grp.get("fields", {}).get("_embedded", {}).items():
            for f in lst:
                out[f["stringId"]] = f
    return out


def values(cl, task_id):
    return {k: v.get("value") for k, v in field_map(cl, task_id).items()}


def set_data(cl, task_id, vals):
    cl.get(f"/api/task/assign/{task_id}")
    return cl.post(f"/api/task/{task_id}/data", {task_id: vals})


def wipe(cl):
    st, r = cl.post("/api/workflow/case/search?size=500", {"process": [{"identifier": NET}]})
    cases = (r.get("_embedded") or {}).get("cases", [])
    for c in cases:
        cl.call("DELETE", f"/api/workflow/case/{c['stringId']}")
    print(f"__APP__check: zmazanych {len(cases)} pripadov")


def main():
    boss = Client("super@netgrif.com", SUPER_PASS)
    if "--wipe" in sys.argv:
        wipe(boss)
        return 0

    print("=== 1. karta v bocnom menu ===")
    user = Client(ROLE_USER_EMAIL, TEST_PASS)
    other = Client(OTHER_USER_EMAIL, TEST_PASS)
    for name, cl, expected in [("s rolou", user, True), ("bez roly", other, False)]:
        st, root = cl.get("/api/v2/uri/root")
        paths = [c["uriPath"] for c in root.get("children", [])]
        check(f"{name} {'vidi' if expected else 'nevidi'} kartu '{CARD}'",
              (CARD in paths) == expected, paths)
        if not expected:
            # Bez tejto kontroly by test presel aj vtedy, keby ucet nevidel
            # ziadnu kartu - a nedokazoval by nic.
            check(f"{name} pritom ine karty vidi", len(paths) > 0, paths)

    print("\\n=== 2. zobrazenia a stlpce ===")
    st, mi = boss.post("/api/workflow/case/search?size=300",
                       {"process": [{"identifier": "preference_filter_item"}]})
    items = {}
    for c in mi.get("_embedded", {}).get("cases", []):
        items.setdefault(c["title"], c["stringId"])

    def view_fields(title):
        st, tl = boss.get(f"/api/task/case/{items[title]}")
        vt = [t for t in (tl or []) if t["transitionId"] == "view"]
        return values(boss, vt[0]["stringId"]) if vt else {}

    for want in ["__TITLE__", "Rozpísané"]:
        check(f"zobrazenie '{want}' existuje", want in items, sorted(items))
        if want not in items:
            continue
        v = view_fields(want)
        check(f"'{want}' ma predvolene stlpce", bool(v.get("default_headers")),
              v.get("default_headers"))
        # Stlpec z datoveho pola sa vykresli LEN ak je jeho siet v allowedNets:
        # ponuku stlpcov sklada CaseHeaderService z povolenych sieti a
        # `default_headers` v nej uniqueId iba vyhlada. Co nenajde, necha
        # prazdne a NIC nezaloguje.
        need = {h.rsplit("-", 1)[0] for h in (v.get("default_headers") or "").split(",")
                if h and not h.startswith("meta-")}
        have = set()
        if v.get("filter_case_id"):
            st, fc = boss.get(f"/api/workflow/case/{v['filter_case_id']}")
            for d in (fc.get("immediateData") or []):
                if d.get("allowedNets"):
                    have = set(d["allowedNets"])
        check(f"'{want}' ma v allowedNets siete svojich stlpcov", need <= have,
              f"treba {sorted(need)}, ma {sorted(have)}")

    st, mc = boss.post("/api/workflow/case/search?size=20",
                       {"process": [{"identifier": "__APP__/__PREFIX___menu"}]})
    mt = [c["title"] for c in mc.get("_embedded", {}).get("cases", [])]
    check("bootstrap case menu hlasi 2/2", any("2/2" in t for t in mt), mt)

    print("\\n=== 3. priebeh pripadu ===")
    net = newest_net(user, NET)
    print(f"  siet {net['identifier']} v{net['version']}")
    case_id, case = new_case(user, net["stringId"])
    check("nazov pripadu zacina stavom", case["title"].startswith("Rozpísané"), case["title"])
    t = tasks_of(user, case_id)
    check("na zaciatku je PRESNE jedna uloha", list(t) == ["t___PREFIX___podanie"], list(t))
    podanie = t.get("t___PREFIX___podanie")
    if not podanie:
        print("\\n__APP__check: uloha podania sa nenasla")
        return 1

    # Prazdny predmet musi byt odmietnuty - a odmietnutie prichadza ako HTTP 200
    # s `error` v tele.
    set_data(user, podanie, {"__PREFIX___predmet": {"type": "text", "value": ""}})
    st, r = user.get(f"/api/task/finish/{podanie}")
    check("prazdny predmet je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:110])

    stamp = str(int(time.time()))
    predmet = f"Test {stamp}"
    set_data(user, podanie, {
        "__PREFIX___predmet": {"type": "text", "value": predmet},
        "__PREFIX___popis": {"type": "text", "value": "Popis z testu."}})
    st, r = user.get(f"/api/task/finish/{podanie}")
    check("DOKONCIT presiel", isinstance(r, dict) and "success" in r, str(r)[:110])

    t2 = tasks_of(user, case_id)
    check("po podani je PRESNE jedna uloha (prehlad)",
          list(t2) == ["t___PREFIX___prehlad"], list(t2))
    if t2.get("t___PREFIX___prehlad"):
        v = values(user, t2["t___PREFIX___prehlad"])
        check("stav je 'Podané'", v.get("__PREFIX___stav_label") == "Podané",
              v.get("__PREFIX___stav_label"))
        check("je zapisane, kto podal", bool(v.get("__PREFIX___podal")),
              v.get("__PREFIX___podal"))
    st, c = user.get(f"/api/workflow/case/{case_id}")
    check("nazov pripadu zacina 'Podané'", c["title"].startswith("Podané"), c["title"])
    check("farba pripadu je zelena", c.get("color") == "green", c.get("color"))

    print("\\n=== 4. zobrazenie 'Rozpísané' filtruje podla datoveho pola ===")
    q = f'processIdentifier:"{NET}" AND dataSet.__PREFIX___stav_label.textValue:"Rozpísané"'
    st, r = user.post("/api/workflow/case/search?size=100", {"query": q})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \\
        if isinstance(r, dict) else []
    check("podany pripad v 'Rozpísané' nie je", case_id not in ids, f"{len(ids)} pripadov")
    c2, _ = new_case(user, net["stringId"])
    st, r = user.post("/api/workflow/case/search?size=100", {"query": q})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \\
        if isinstance(r, dict) else []
    check("novy rozpisany pripad v 'Rozpísané' je", c2 in ids, f"{len(ids)} pripadov")

    print(f"\\n__APP__check: {len(OK)} preslo, {len(FAIL)} zlyhalo")
    for f in FAIL:
        print("  ZLYHALO:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
'''


# Preklady retazcov, ktore skelet vlastni.
#
# Kluce doplni `pfi18n --init` (odvodi ich z id elementov, aby ich schema bola
# jedna a tá istá vsade), a tento slovnik potom TODO riadky prelozi. Preto tu
# nie su `name=` atributy natvrdo v sablone: keby sa schema klucov niekedy
# zmenila, sablona by sa rozisla s nastrojom a nikto by si to nevsimol - kluc
# bez prekladu sa totiz nijako neprejavi.
#
# `__TITLE__` a `__ROLE_TITLE__` tu nie su zamerne. Su od uzivatela, ich
# anglicky preklad nikto nepozna, takze zostanu ako `TODO ...` a `pfi18n` ich
# nahlasi ako upozornenie. To je cielene: appka, ktora sa tvari dvojjazycne
# a ma dvakrat to iste, je horsia nez appka, o ktorej vie, ze preklad chyba.
SKELETON_EN = {
    "Zadanie": "Brief",
    "Výsledok": "Result",
    "Predmet": "Subject",
    "Popis": "Description",
    "Stav": "Status",
    "Samostatné pole, aby sa dalo dať do stĺpca a hľadať podľa neho.":
        "A field of its own, so it can be a column and be searched on.",
    "Podal": "Submitted by",
    "Podané": "Submitted",
    "Podanie": "Submission",
    "Rozpísané": "Draft",
    "Stav menu": "Menu state",
    "Živé": "Alive",
}


def add_translations(paths):
    """Doplni `name=` a blok `<i18n locale="en">` do vygenerovanych sieti."""
    import pfi18n

    for path in paths:
        if path.suffix != ".xml":
            continue
        pfi18n.init(path)
        raw = path.read_text(encoding="utf-8")
        for sk, en in SKELETON_EN.items():
            raw = raw.replace(f">{pfi18n.TODO}{sk}</i18nString>",
                              f">{en}</i18nString>")
        path.write_text(raw, encoding="utf-8")


# ---------------------------------------------------------------- generator

sys.path.insert(0, str(Path(__file__).resolve().parent))


def render(template, subs):
    out = template
    for token, value in subs.items():
        out = out.replace(token, value)
    # Aj `_TOKEN__` s jednym uvodnym podtrzitkom - presne to zostane po kolizii
    # dvoch susediacich tokenov a povodna kontrola to prehliadla.
    left = re.findall(r"_{1,2}[A-Z][A-Z_]{2,}__", out)
    if left:
        raise SystemExit(f"pfnew: nedoplneny token v sablone: {sorted(set(left))}")
    return out


def patch_manifest(app, prefix, entity, icon, role, dry):
    path = ROOT / "processes.json"
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)

    net_file = f"{prefix}_{entity}.xml"
    menu_file = f"{prefix}_menu.xml"
    menu_id = f"{app}/{prefix}_menu"

    todo = []
    if net_file not in data.get("import", []):
        todo.append(("import", net_file))
    if menu_file not in data.get("import", []):
        todo.append(("import", menu_file))
    # Menu siet sa zapisuje v objektovej forme s `rebuildOnNewVersion`. Jej
    # akcia je v udalosti `create`, teda bezi raz za case, a case si drzi verziu
    # siete - bez toho by sa po re-importe menu siete zmena zobrazeni nikdy
    # neprejavila a vyzeralo by to, ze re-import nefunguje.
    menu_entry = {"net": menu_id, "rebuildOnNewVersion": True}
    have = data.get("bootstrapCase", [])
    if not any((e == menu_id) or (isinstance(e, dict) and e.get("net") == menu_id)
               for e in have):
        todo.append(("bootstrapCase", menu_entry))
    if app not in (data.get("uriNodes") or {}):
        todo.append(("uriNodes", app))

    if not todo:
        print("  processes.json: uz obsahuje vsetko, nemenim")
        return

    # Manifest sa edituje ako DATA, nie ako text - komentare v nom su v poli
    # "_comment", takze json.dumps ich nezahodi.
    data.setdefault("import", []).extend(
        [v for k, v in todo if k == "import"])
    data.setdefault("bootstrapCase", []).extend(
        [v for k, v in todo if k == "bootstrapCase"])
    if any(k == "uriNodes" for k, _ in todo):
        data.setdefault("uriNodes", {})[app] = {
            "icon": icon,
            "requiredAuthorities": [],
            "requiredProcessRoles": [role],
        }

    def label(k, v):
        return f"{k}:{v['net'] if isinstance(v, dict) else v}"

    if dry:
        print("  processes.json: doplnil by som " + ", ".join(label(k, v) for k, v in todo))
        return
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("  processes.json: doplnene " + ", ".join(label(k, v) for k, v in todo))


def patch_seed(app, dry):
    """Doplni `<app>/*` do `netScope` v seed.json.

    ROLE NIKOMU NEPRIDELUJE - kto ma ktoru rolu dostat, je rozhodnutie
    nasadenia, nie generatora. Ale bez `netScope` by `pfseed` nepridelil nic
    ani po tom, co si to niekto do `users` dopise, a to je presne ten druh
    ticha, kvoli ktoremu tento repozitar vyzera ako ze nefunguje.
    """
    path = ROOT / "seed.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    pattern = f"{app}/*"
    if pattern in (data.get("netScope") or []):
        print("  seed.json: netScope uz obsahuje " + pattern)
        return
    if dry:
        print("  seed.json: doplnil by som netScope " + pattern)
        return
    data.setdefault("netScope", []).append(pattern)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("  seed.json: netScope doplneny o " + pattern)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pfnew.py",
        description="Vygeneruje skelet appky, ktory hned prejde overovacou retazou.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Priklad:\n"
               "  python3 tools/pfnew.py dovolenky ziadost \"Žiadosť o dovolenku\" \\\n"
               "      --initials ZOD --role veduci --role-title \"Vedúci oddelenia\"\n")
    ap.add_argument("app", help="appka = URI uzol a prefix identifikatora, napr. dovolenky")
    ap.add_argument("entity", help="entita, napr. ziadost (vznikne <app>/<prefix>_<entity>)")
    ap.add_argument("title", help="nazov procesu, napr. \"Žiadosť o dovolenku\"")
    ap.add_argument("--prefix", help="prefix poli a suborov (default: prve dve litery appky)")
    ap.add_argument("--initials", help="3 VELKE litery (default: z nazvu)")
    ap.add_argument("--role", default="pracovnik", help="importId roly (default: pracovnik)")
    ap.add_argument("--role-title", help="nazov roly (default: podla --role)")
    ap.add_argument("--icon", default="assignment", help="Material ikona (default: assignment)")
    ap.add_argument("--dry-run", action="store_true", help="len vypis, nic nezapisuj")
    args = ap.parse_args(argv)

    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.app):
        raise SystemExit("pfnew: appka musi byt male litery, cislice a podtrznik")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.entity):
        raise SystemExit("pfnew: entita musi byt male litery, cislice a podtrznik")

    prefix = args.prefix or args.app[:2]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", prefix):
        raise SystemExit("pfnew: prefix musi byt male litery, cislice a podtrznik")

    initials = (args.initials or "".join(
        w[0] for w in re.findall(r"\w+", args.title))[:3] or prefix).upper()
    initials = (initials + "XXX")[:3]
    if not re.fullmatch(r"[A-Z]{3}", initials):
        raise SystemExit(f"pfnew: <initials> musia byt presne 3 velke litery, mam '{initials}'")
    # Menu potrebuje vlastne, ine ako siet - inak sa dve siete tvaria rovnako.
    menu_initials = (initials[:2] + "M")

    role_title = args.role_title or (args.role[:1].upper() + args.role[1:])

    subs = {
        "__APP__": args.app,
        # `__NET__` je cely `<prefix>_<entita>` ako JEDEN token. Rozdelene na
        # `__PREFIX___ENTITY__` to nefungovalo: po nahradeni prefixu zostalo
        # `ma_ENTITY__` a druhy token sa uz netrafil. Engine taky identifikator
        # bez namietky naimportoval, pflint aj pfgroovy presli - odhalilo to az
        # precitanie vystupu `pfcheck`.
        "__NET__": f"{prefix}_{args.entity}",
        "__PREFIX__": prefix,
        "__ENTITY__": args.entity,
        "__TITLE__": args.title,
        "__INITIALS__": initials,
        "__MENU_INITIALS__": menu_initials,
        "__ROLE__": args.role,
        "__ROLE_TITLE__": role_title,
        "__ICON__": args.icon,
    }

    targets = [
        (ROOT / "processes" / f"{prefix}_{args.entity}.xml", render(NET, subs)),
        (ROOT / "processes" / f"{prefix}_menu.xml", render(MENU, subs)),
        (ROOT / "tools" / f"{args.app}check.py", render(CHECK, subs)),
    ]

    existing = [t[0] for t in targets if t[0].exists()]
    if existing:
        raise SystemExit("pfnew: uz existuje, nic neprepisujem:\n  " +
                         "\n  ".join(str(p.relative_to(ROOT)) for p in existing))

    print(f"pfnew: {args.app}/{prefix}_{args.entity} ({args.title}), rola {args.role}")
    for path, content in targets:
        if args.dry_run:
            print(f"  {path.relative_to(ROOT)}: {len(content.splitlines())} riadkov (dry-run)")
            continue
        path.write_text(content, encoding="utf-8")
        print(f"  {path.relative_to(ROOT)}: {len(content.splitlines())} riadkov")
    if not args.dry_run:
        add_translations([t[0] for t in targets])
        print("  + preklady: doplnene `name=` a blok <i18n locale=\"en\">")
    patch_manifest(args.app, prefix, args.entity, args.icon, args.role, args.dry_run)
    patch_seed(args.app, args.dry_run)

    print("""
Dalej:
  python3 tools/pflint.py processes/
  python3 tools/pfgroovy.py processes/
  python3 tools/pfi18n.py processes/      # prelozi TODO riadky (nazov appky a roly)
  python3 tools/pfview.py
  tools/up.sh                     # manifest sa pakuje do jaru, treba prestavat
  # do seed.json dopis, kto ma dostat rolu `%s` (netScope je uz doplneny),
  python3 tools/pfseed.py
  python3 tools/%scheck.py

Skelet je zamerne minimalny: jedno podanie a jeden prehlad. Domenova logika sa
dopisuje, ale vzory v komentaroch nemen bez dovodu - kazdy z nich je tam kvoli
konkretnej tichej pasci a v cheatsheete je napisane kvoli akej.""" % (
        args.role, args.app))
    return 0


if __name__ == "__main__":
    sys.exit(main())
