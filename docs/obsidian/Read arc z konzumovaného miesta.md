# Read arc z konzumovaného miesta

Read-only pohľad zavesený na read arc z miesta, ktoré **nejaký prechod
konzumuje**, zmizne po prvom odmietnutom `finish` na tom prechode — a už sa
nevráti: žetón sa nepohol, takže úlohu nemá čo znova povoliť.

Preto sa taký pohľad vešia na miesto, ktoré **nikto nekonzumuje**: buď sink
(koncové miesto), alebo miesto so žetónom od založenia prípadu, ktoré nie je
vstupom nikam. To druhé dá read-only obrazovku na celý život prípadu — presne to,
čo potrebuje zadávateľ, ktorého štvoro očí vylúčilo zo schvaľovateľov.

`pfdoc learnings B8b` (kam nie) a `B25` (kam áno).

Súvisí: [[Tiché chyby]] · [[Vzory z reálnych appiek]]
