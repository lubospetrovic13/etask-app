#!/usr/bin/env python3
"""
pflayout - rozlozenie siete na platne buildera (suradnice miest, prechodov a hran).

Siete sa pisu ako text a suradnice v nich vznikaju odhadom. V builderi potom
uzly sedia na sebe, popisky sa prekryvaju a vsetky spatne hrany ("vratit na
doplnenie") idu jednou ciarou cez cely hlavny riadok - model vyzera ako chyba,
hoci je v poriadku. Na behanie procesu to nema ziadny vplyv, na citanie modelu
zasadny.

Rozlozenie:

  * stlpce su vrstvy toku: od miesta s tokenom, spatne hrany sa do vrstiev
    nerataju (inak by cyklus "vratit" nemal zaciatok),
  * najdlhsia cesta tokom je hlavny riadok, vetvy su pod nim,
  * rozostup stlpcov podla dlzky popiskov, aby sa neprekryvali,
  * hrana cez viac stlpcov ide nad riadkom (dopredu) alebo pod nim (spat),
    kazda vo vlastnej drahe - `<breakpoint>` - takze sa neprekryvaju,
  * samostatne casti (prehlad na read arcu) su v riadku pod sietou.

Vysledok je funkcia struktury siete, nie povodnych suradnic: dva behy dajú to
iste a zmena siete prekresli len to, co sa zmenilo. Menia sa len `<x>`/`<y>`
miest a prechodov a `<breakpoint>` hran; komentare a vsetko ostatne zostava.

    python3 tools/pflayout.py processes/*.xml            # prepise
    python3 tools/pflayout.py --check processes/         # 1, ak by sa nieco zmenilo

Exit 0 = hotovo / sedi, 1 = --check nasiel rozdiel, 2 = zle pouzitie.
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

LEFT = 60            # okraj platna
ROW_H = 130          # riadky uzlov (popisok je pod uzlom)
LANE = 26            # rozostup drah hran
LANE_GAP_UP = 46     # prva draha nad riadkom
LANE_GAP_DOWN = 64   # prva draha pod riadkom (pod popiskom)
MIN_GAP = 120        # najmensi rozostup stlpcov
CHAR_W = 6.6         # sirka znaku popisku v builderi (Roboto 12px)
LABEL_PAD = 28
COMPONENT_GAP = 90
SPREAD = 10          # rozostup zvislych usekov hran z jedneho uzla


def label_width(text):
    return len((text or "").strip()) * CHAR_W


def layout(root):
    """Vrati ({id: (x, y)}, {arc_id: [(x, y), ...]})."""
    nodes, labels, kinds, tokens = [], {}, {}, {}
    for p in root.findall("place"):
        pid = p.findtext("id")
        nodes.append(pid)
        labels[pid] = p.findtext("label") or ""
        kinds[pid] = "place"
        tokens[pid] = int((p.findtext("tokens") or "0").strip() or 0)
    for t in root.findall("transition"):
        tid = t.findtext("id")
        nodes.append(tid)
        labels[tid] = t.findtext("label") or ""
        kinds[tid] = "transition"
        tokens[tid] = 0
    order = {n: i for i, n in enumerate(nodes)}
    arcs = []
    for a in root.findall("arc"):
        s, d = a.findtext("sourceId"), a.findtext("destinationId")
        if s in order and d in order:
            arcs.append((a.findtext("id"), s, d))
    out = {n: [] for n in nodes}
    und = {n: set() for n in nodes}
    for _, s, d in arcs:
        out[s].append(d)
        und[s].add(d)
        und[d].add(s)

    # Komponenty (neorientovane), v poradi prveho uzla v XML.
    comps, seen = [], set()
    for n in nodes:
        if n in seen:
            continue
        stack, comp = [n], []
        seen.add(n)
        while stack:
            x = stack.pop()
            comp.append(x)
            for y in sorted(und[x], key=order.get):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        comps.append(sorted(comp, key=order.get))
    # Hlavna cast (s tokenom a najvacsia) hore, ostatne pod nou.
    comps.sort(key=lambda c: (-any(tokens[n] for n in c), -len(c), order[c[0]]))

    pos, bps = {}, {}
    top = 0
    for comp in comps:
        cset = set(comp)
        # --- vrstvy: DFS od miest s tokenom, spatne hrany von -------------
        starts = [n for n in comp if tokens[n] > 0] or \
                 [n for n in comp if not any(n in out[m] for m in comp)] or comp[:1]
        state, back = {}, set()

        def dfs(u):
            state[u] = 1
            for v in out[u]:
                if v not in cset:
                    continue
                if state.get(v) == 1:
                    back.add((u, v))
                elif v not in state:
                    dfs(v)
            state[u] = 2
        sys.setrecursionlimit(10000)
        for s in starts + comp:
            if s not in state:
                dfs(s)
        rank = {n: 0 for n in comp}
        topo = []
        visited = set()

        def topo_visit(u):
            visited.add(u)
            for v in out[u]:
                if v in cset and (u, v) not in back and v not in visited:
                    topo_visit(v)
            topo.append(u)
        for s in starts + comp:
            if s not in visited:
                topo_visit(s)
        topo.reverse()
        for u in topo:
            for v in out[u]:
                if v in cset and (u, v) not in back:
                    rank[v] = max(rank[v], rank[u] + 1)

        # --- hlavny riadok: najdlhsia cesta ---------------------------------
        row = {}
        end = max(comp, key=lambda n: (rank[n], -order[n]))
        spine = [end]
        while rank[spine[-1]] > 0:
            cur = spine[-1]
            preds = [m for m in comp if cur in out[m] and (m, cur) not in back and rank[m] == rank[cur] - 1]
            if not preds:
                break
            spine.append(min(preds, key=order.get))
        for n in spine:
            row[n] = 0
        # --- ostatne uzly: najblizsi volny riadok k susedom ------------------
        taken = {(rank[n], 0) for n in spine}
        for n in sorted(comp, key=lambda m: (rank[m], order[m])):
            if n in row:
                continue
            near = [row[m] for m in und[n] if m in row]
            want = round(sum(near) / len(near)) if near else 1
            cands = sorted(range(-len(comp), len(comp) + 1),
                           key=lambda r: (abs(r - want), r < 0, abs(r)))
            for r in cands:
                if r != 0 and (rank[n], r) not in taken:
                    row[n] = r
                    taken.add((rank[n], r))
                    break
        # Vetvy nad hlavnym riadkom len ak je hore volno; inak vsetko dole.
        minrow = min(row.values())

        # --- x podla popiskov -------------------------------------------------
        maxrank = max(rank.values())
        widest = [max([label_width(labels[n]) for n in comp if rank[n] == r] or [0]) for r in range(maxrank + 1)]
        xs = [LEFT]
        for r in range(1, maxrank + 1):
            gap = max(MIN_GAP, (widest[r - 1] + widest[r]) / 2 + LABEL_PAD)
            xs.append(xs[-1] + gap)

        # --- hrany: rovno, alebo drahou nad / pod -----------------------------
        up, down = [], []
        for aid, s, d in arcs:
            if s not in cset:
                continue
            diff = rank[d] - rank[s]
            if diff == 1 and (s, d) not in back:
                continue
            lo, hi = sorted((xs[rank[s]], xs[rank[d]]))
            # Dopredu aj spat nad riadkom: builder kresli popisok POD uzlom, takze
            # draha pod riadkom by kazdy popisok, z ktoreho hrana zisla, preciarkla.
            # Smer je vidno zo sipky; dopredu a spat sa lisia aj tym, ze spatne hrany
            # su dlhsie a sedia vo vyssich drahach.
            up.append((aid, s, d, lo, hi))

        def lanes(items):
            placed = []
            result = {}
            for aid, s, d, lo, hi in sorted(items, key=lambda i: (i[4] - i[3], i[3], i[0])):
                k = 0
                while any(pk == k and not (hi + 20 < plo or lo - 20 > phi) for pk, plo, phi in placed):
                    k += 1
                placed.append((k, lo, hi))
                result[aid] = k
            return result
        up_lane, down_lane = lanes(up), lanes(down)
        n_up = (max(up_lane.values()) + 1) if up_lane else 0
        n_down = (max(down_lane.values()) + 1) if down_lane else 0
        maxrow = max(row.values())

        base = top + (LANE_GAP_UP + (n_up - 1) * LANE if n_up else 0) + 40
        def y_of(r):
            return base + (r - minrow) * ROW_H
        for n in comp:
            pos[n] = (int(round(xs[rank[n]])), int(round(y_of(row[n]))))
        up_y0 = y_of(minrow) - LANE_GAP_UP
        down_y0 = y_of(maxrow) + LANE_GAP_DOWN

        # Zvisle useky z jedneho uzla vedla seba, zoradene podla druheho konca.
        ends = {}
        for side, items, lane in (("u", up, up_lane), ("d", down, down_lane)):
            for aid, s, d, lo, hi in items:
                for node, other in ((s, d), (d, s)):
                    ends.setdefault((node, side), []).append((pos[other][0], lane[aid], aid))
        dx = {}
        for (node, side), lst in ends.items():
            lst.sort()
            for i, (_, _, aid) in enumerate(lst):
                dx[(aid, node)] = int(round((i - (len(lst) - 1) / 2) * SPREAD))
        for side, items, lane, y0, sign in (("u", up, up_lane, up_y0, -1), ("d", down, down_lane, down_y0, 1)):
            for aid, s, d, lo, hi in items:
                ly = int(round(y0 + sign * lane[aid] * LANE))
                bps[aid] = [(pos[s][0] + dx[(aid, s)], ly), (pos[d][0] + dx[(aid, d)], ly)]

        top = (down_y0 + (n_down - 1) * LANE if n_down else y_of(maxrow) + 40) + COMPONENT_GAP
    return pos, bps


def apply(raw, pos, bps):
    """Prepise suradnice v texte siete; nic ine sa nezmeni."""
    def node_block(m):
        block = m.group(0)
        nid = re.search(r"<id>\s*(.*?)\s*</id>", block).group(1)
        if nid not in pos:
            return block
        x, y = pos[nid]
        # Vlastne <x>/<y> uzla su pred prvym vnorenym blokom (dataRef ma tiez <x>).
        cut = min([i for i in (block.find("<dataGroup"), block.find("<dataRef"), block.find("<roleRef"),
                               block.find("<event"), block.find("<userRef"), block.find("<trigger"))
                   if i >= 0] or [len(block)])
        headp, tail = block[:cut], block[cut:]
        headp = re.sub(r"<x>\s*-?\d+\s*</x>", f"<x>{x}</x>", headp, count=1)
        headp = re.sub(r"<y>\s*-?\d+\s*</y>", f"<y>{y}</y>", headp, count=1)
        return headp + tail
    raw = re.sub(r"<place>.*?</place>", node_block, raw, flags=re.S)
    raw = re.sub(r"<transition>.*?</transition>", node_block, raw, flags=re.S)

    def arc_block(m):
        block = m.group(0)
        aid = re.search(r"<id>\s*(.*?)\s*</id>", block).group(1)
        block = re.sub(r"\n?[ \t]*<breakpoint>.*?</breakpoint>", "", block, flags=re.S)
        pts = bps.get(aid)
        if not pts:
            return block
        indent = re.search(r"\n([ \t]*)<id>", block)
        ind = indent.group(1) if indent else "\t\t"
        inner = ind + ("\t" if ind.startswith("\t") else "  ")
        text = "".join(f"\n{ind}<breakpoint>\n{inner}<x>{x}</x>\n{inner}<y>{y}</y>\n{ind}</breakpoint>" for x, y in pts)
        pre = block[:block.rindex("</arc>")]
        close = re.search(r"\n([ \t]*)$", pre)
        return pre.rstrip() + text + "\n" + (close.group(1) if close else "") + "</arc>"
    raw = re.sub(r"<arc>.*?</arc>", arc_block, raw, flags=re.S)
    return raw


def process(path, check):
    raw = Path(path).read_text(encoding="utf-8")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"{path}: XML sa neda rozparsovat ({e})")
        return 2
    if not root.findall("place") and not root.findall("transition"):
        return 0
    pos, bps = layout(root)
    new = apply(raw, pos, bps)
    if new == raw:
        return 0
    if check:
        print(f"{path}: rozlozenie sa rozislo - python3 tools/pflayout.py {path}")
        return 1
    Path(path).write_text(new, encoding="utf-8", newline="\n")
    print(f"{path}: rozlozene ({len(pos)} uzlov, {len(bps)} hran s drahou)")
    return 0


def main(argv):
    check = "--check" in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    files = []
    for a in args:
        p = Path(a)
        files += sorted(p.glob("*.xml")) if p.is_dir() else [p]
    rc = 0
    for f in files:
        rc = max(rc, process(f, check))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
