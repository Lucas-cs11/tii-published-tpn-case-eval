#!/usr/bin/env python3
"""Independently draw the adapted manufacturing TPN (no published figure copied)."""
from pathlib import Path
import json, subprocess

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "figures" / "manufacturing"


def main():
    model = json.loads((HERE / "jas2026_fig6_adapted.json").read_text())
    resources = {"p_R1", "p_R2", "p_R3", "p_M1", "p_M2", "p_Ifree"}
    lines = ['digraph G {', 'rankdir=LR;', 'graph [fontname="Helvetica", nodesep=0.18, ranksep=0.42, splines=true, pad=0.15];',
             'node [fontname="Helvetica", fontsize=8];', 'edge [arrowsize=0.55, color="#40546b"];']
    for p in model["places"]:
        pid = p["id"]
        if pid in resources:
            shape, fill, col = "ellipse", "#dbe4ee", "#40546b"
        elif pid in ("p_raw", "p_done"):
            shape, fill, col = "circle", "#eef3f8", "#04182e"
        else:
            shape, fill, col = "circle", "#ffffff", "#40546b"
        label = pid + (f"\\n({p['initial']})" if p["initial"] else "")
        lines.append(f'"{pid}" [shape={shape}, style="filled", fillcolor="{fill}", color="{col}", label="{label}"];')
    for t in model["transitions"]:
        tid = t["id"]
        if t["fault"]:
            fill, col, font = "#f6e3d3", "#b5651d", "#8a4a12"
        elif t["observable"]:
            fill, col, font = "#e6f0e2", "#2f6b3a", "#1d4424"
        else:
            fill, col, font = "#f2f5f9", "#04182e", "#04182e"
        lab = tid
        if t["latest"] == t["earliest"]:
            lab += f"\\n[{t['earliest']}]"
        else:
            lab += f"\\n[{t['earliest']},{t['latest']}]"
        if t["observable"]:
            lab += f"\\n/{t['label']}/"
        lines.append(f'"{tid}" [shape=box, style="rounded,filled", fillcolor="{fill}", color="{col}", fontcolor="{font}", label="{lab}"];')
    for t in model["transitions"]:
        for p, w in t["inputs"].items():
            lines.append(f'"{p}" -> "{t["id"]}"' + (f' [label="{w}"]' if w > 1 else '') + ';')
        for p, w in t["outputs"].items():
            lines.append(f'"{t["id"]}" -> "{p}"' + (f' [label="{w}"]' if w > 1 else '') + ';')
    # simple rank hints for readability
    lines += ['{rank=same; "p_raw"; "s1";}', '{rank=same; "a1"; "a2"; "a3"; "a4"; "a5"; "a6";}',
              '{rank=same; "p_R1"; "p_M1"; "p_R2"; "p_M2"; "p_R3"; "p_Ifree";}',
              '{rank=same; "p_done"; "p_slip";}', '}']
    OUT.mkdir(parents=True, exist_ok=True)
    dot = OUT / "jas2026_fig6_adapted.dot"
    dot.write_text("\n".join(lines) + "\n")
    for fmt in ("pdf", "png"):
        subprocess.run(["dot", f"-T{fmt}", str(dot), "-o", str(OUT / f"jas2026_fig6_adapted.{fmt}")], check=True)
    print("wrote", dot)


if __name__ == "__main__":
    main()
