# Case.title sa neprekladá

`Case.title` je `java.lang.String` a `TextField extends Field<String>`. Ani
jedno nie je `I18nString`, takže čo tam akcia zapíše, tam v každom jazyku aj
zostane.

Prejav: `pfi18n` je zelený, formulár je anglický — a jediné slovenské slovo
v zozname je **stav**, teda to, čo sa číta najčastejšie.

Riešenie: stav je `enumeration_map` s preloženými možnosťami, akcia zapisuje
**kľúč**. Vedľajší zisk — dopyty v menu filtrujú podľa kľúča, takže nezávisia od
jazyka ani od preformulovania popisku.

Do názvu prípadu patria **dáta** (dodávateľ, číslo, suma), nie stav.

Súvisí: [[Tiché chyby]] · [[Vzory z reálnych appiek]]
