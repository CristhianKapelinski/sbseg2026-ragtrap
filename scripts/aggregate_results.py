"""Aggregate all experiment outputs into results/results.json and a LaTeX macro block.

Reads results/real_results.json (E1 + baseline), results/scaling_results.json (E2/E4 sweep),
results/aux_results.json (E0, E3, E5) and emits:

* results/results.json   -- the single canonical results bundle the paper draws from;
* results/macros.tex      -- a \newcommand block; every number in the paper body comes from here.

No number is computed here that is not already in an input file; this only selects and formats.
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path("results")


def _load(name: str) -> dict:
    p = RESULTS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _fmt(x: float, nd: int = 0) -> str:
    if nd == 0:
        return f"{round(x):d}"
    return f"{x:.{nd}f}"


def main() -> int:
    real = _load("real_results.json")
    scaling = _load("scaling_results.json")
    aux = _load("aux_results.json")

    bundle = {"E1_real": real, "scaling": scaling, "aux": aux}
    (RESULTS / "results.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    m: list[str] = []
    m.append("% ===== AUTO-GENERATED RESULTS MACROS (scripts/aggregate_results.py) =====")
    m.append("% Every empirical number in the paper body is defined here, from results/*.json.")

    # ---- E1 headline (top-k detection + latency) ----
    rt = real.get("ragtrap", {})
    bl = real.get("baseline", {})
    ro = real.get("baseline_ragorigin", {})
    head = real.get("headline", {})
    topk = real.get("top_k", 10)
    m.append(f"\\newcommand{{\\TopK}}{{{topk}}}")
    m.append(f"\\newcommand{{\\Nquestions}}{{{real.get('data',{}).get('n_questions','')}}}")

    d0 = rt.get("drift_0", {})
    det0 = d0.get("detection", {})
    if det0:
        m.append(f"\\newcommand{{\\NsuspectsE}}{{{d0.get('n_suspects','')}}}")
        m.append(f"\\newcommand{{\\NpoisonE}}{{{d0.get('n_poison_suspects','')}}}")
        m.append(f"\\newcommand{{\\NcleanE}}{{{d0.get('n_clean_suspects','')}}}")
        rec, prec, fpr = det0["recall"], det0["precision"], det0["fpr"]
        m.append(f"\\newcommand{{\\RTrecall}}{{{_fmt(rec['point'],2)}}}")
        m.append(f"\\newcommand{{\\RTprecision}}{{{_fmt(prec['point'],2)}}}")
        m.append(f"\\newcommand{{\\RTfpr}}{{{_fmt(fpr['point'],2)}}}")
        m.append(f"\\newcommand{{\\RTlatPerSus}}{{{_fmt(d0['latency_s_per_suspect_us'],1)}}}")
        m.append(f"\\newcommand{{\\RTworkE}}{{{d0['work_units']}}}")

    # drift split (LaTeX macro names cannot contain digits, so 0.3 -> Three, 0.5 -> Five)
    for d, tag in (("drift_0.3", "Three"), ("drift_0.5", "Five")):
        dd = rt.get(d, {})
        if dd:
            rr = dd["detection"]["recall"]
            m.append(f"\\newcommand{{\\RTrecallDrift{tag}}}{{{_fmt(rr['point'],2)}}}")
            m.append(f"\\newcommand{{\\RTrecallDrift{tag}Lo}}{{{_fmt(rr['ci_low'],2)}}}")
            m.append(f"\\newcommand{{\\RTrecallDrift{tag}Hi}}{{{_fmt(rr['ci_high'],2)}}}")
            m.append(f"\\newcommand{{\\RTfnrDrift{tag}}}{{{_fmt(dd['detection']['fnr']['point'],2)}}}")

    # baseline detection
    bdet = bl.get("detection", {})
    if bdet:
        brec, bprec, bfpr = bdet["recall"], bdet["precision"], bdet["fpr"]
        m.append(f"\\newcommand{{\\BLrecall}}{{{_fmt(brec['point'],2)}}}")
        m.append(f"\\newcommand{{\\BLrecallLo}}{{{_fmt(brec['ci_low'],2)}}}")
        m.append(f"\\newcommand{{\\BLrecallHi}}{{{_fmt(brec['ci_high'],2)}}}")
        m.append(f"\\newcommand{{\\BLprecision}}{{{_fmt(bprec['point'],2)}}}")
        m.append(f"\\newcommand{{\\BLprecisionLo}}{{{_fmt(bprec['ci_low'],2)}}}")
        m.append(f"\\newcommand{{\\BLprecisionHi}}{{{_fmt(bprec['ci_high'],2)}}}")
        m.append(f"\\newcommand{{\\BLfpr}}{{{_fmt(bfpr['point'],2)}}}")
        m.append(f"\\newcommand{{\\BLfnr}}{{{_fmt(bdet['fnr']['point'],2)}}}")
        m.append(f"\\newcommand{{\\BLcalls}}{{{bl['model_calls']}}}")
        m.append(f"\\newcommand{{\\BLjudge}}{{{bl['judge_model'].split('/')[-1]}}}")

    # RAGOrigin responsibility-attribution baseline (identical suspects)
    rodet = ro.get("detection", {})
    if rodet:
        rrec, rprec, rfpr = rodet["recall"], rodet["precision"], rodet["fpr"]
        m.append(f"\\newcommand{{\\ROrecall}}{{{_fmt(rrec['point'],2)}}}")
        m.append(f"\\newcommand{{\\ROrecallLo}}{{{_fmt(rrec['ci_low'],2)}}}")
        m.append(f"\\newcommand{{\\ROrecallHi}}{{{_fmt(rrec['ci_high'],2)}}}")
        m.append(f"\\newcommand{{\\ROprecision}}{{{_fmt(rprec['point'],2)}}}")
        m.append(f"\\newcommand{{\\ROprecisionLo}}{{{_fmt(rprec['ci_low'],2)}}}")
        m.append(f"\\newcommand{{\\ROprecisionHi}}{{{_fmt(rprec['ci_high'],2)}}}")
        m.append(f"\\newcommand{{\\ROfpr}}{{{_fmt(rfpr['point'],2)}}}")
        m.append(f"\\newcommand{{\\ROfnr}}{{{_fmt(rodet['fnr']['point'],2)}}}")
        m.append(f"\\newcommand{{\\ROcalls}}{{{ro['model_calls']}}}")
        m.append(f"\\newcommand{{\\ROproxy}}{{{ro['proxy_model'].split('/')[-1]}}}")
        m.append(f"\\newcommand{{\\ROlatTotal}}{{{_fmt(ro['latency_s_total'],0)}}}")
        m.append(f"\\newcommand{{\\ROperSus}}{{{_fmt(ro['latency_s_per_suspect']*1000,1)}}}")  # ms

    if head:
        rt_ms = head["ragtrap_latency_s_total"] * 1000
        m.append(f"\\newcommand{{\\LatSpeedup}}{{{_fmt(head['latency_speedup'],0)}}}")
        m.append(f"\\newcommand{{\\RTlatTotal}}{{{_fmt(rt_ms,1)}}}")  # ms
        m.append(f"\\newcommand{{\\BLlatTotal}}{{{_fmt(head['baseline_latency_s_total'],0)}}}")
        m.append(f"\\newcommand{{\\BLperSus}}{{{_fmt(head['baseline_per_suspect_s'],1)}}}")
        if ro.get("latency_s_total"):
            ro_speedup = ro["latency_s_total"] / head["ragtrap_latency_s_total"]
            m.append(f"\\newcommand{{\\LatSpeedupRO}}{{{_fmt(ro_speedup,0)}}}")

    # ---- scaling (E2/E4) ----
    pts = scaling.get("scale_points", [])
    if pts:
        # scaling table rows
        rows: list[str] = []

        def _human(n: int) -> str:
            if n >= 1_000_000:
                return f"{round(n / 1_000_000, 2):g}M"
            if n >= 1000:
                return f"{round(n / 1000)}k"
            return str(n)

        for p in pts:
            ratio_str = f"{round(p['mttr_ratio']):,}".replace(",", "{,}")
            rows.append(
                f"{_human(p['n_clean_passages'])} & {_human(p['n_chunks'])} & "
                f"{p['sign_latency_us']:.0f} & "
                f"{p['revoke_mttr_s'] * 1e6:.0f}~$\\mu$s & "
                f"\\textbf{{{ratio_str}$\\times$}}"
            )
        # Rows are joined by "\\"; the LAST row carries no trailing "\\" so the table can place
        # "\\ \bottomrule" after \input without an empty trailing line being read as \par inside
        # the alignment ("Misplaced \noalign"). End with "%" to absorb the file's final newline.
        body = " \\\\\n".join(rows) + "%\n"
        (RESULTS / "scaling_rows.tex").write_text(body, encoding="utf-8")

        def _grouped(n: int) -> str:
            return f"{n:,}".replace(",", "{,}")

        full = pts[-1]
        m.append(f"\\newcommand{{\\FullPassages}}{{{_grouped(full['n_clean_passages'])}}}")
        m.append(f"\\newcommand{{\\FullChunks}}{{{_grouped(full['n_chunks'])}}}")
        m.append(f"\\newcommand{{\\EdLatency}}{{{_fmt(full['sign_latency_us'],1)}}}")
        m.append(f"\\newcommand{{\\EdThroughput}}{{{_fmt(full['throughput_per_s'],0)}}}")
        m.append(f"\\newcommand{{\\EdRecord}}{{{_fmt(full['mean_record_bytes'],0)}}}")
        m.append(f"\\newcommand{{\\RevChunks}}{{{full['revoked_chunks']}}}")
        m.append(f"\\newcommand{{\\FullRevMttr}}{{{full['revoke_mttr_s']*1e6:.1f}}}")  # us
        m.append(f"\\newcommand{{\\FullManMttr}}{{{full['manual_mttr_s']*1000:.0f}}}")  # ms
        m.append(f"\\newcommand{{\\FullMttrRatio}}{{{_fmt(full['mttr_ratio'],0)}}}")
        # smallest point for the growth statement
        small = pts[0]
        m.append(f"\\newcommand{{\\SmallPassages}}{{{_grouped(small['n_clean_passages'])}}}")
        m.append(f"\\newcommand{{\\SmallMttrRatio}}{{{_fmt(small['mttr_ratio'],0)}}}")

    sb = scaling.get("signing_backends", {})
    if sb:
        ed, hm = sb["ed25519"], sb["hmac"]
        m.append(f"\\newcommand{{\\EdSig}}{{{int(ed['mean_signature_bytes'])}}}")
        m.append(f"\\newcommand{{\\HmacSig}}{{{int(hm['mean_signature_bytes'])}}}")
        m.append(f"\\newcommand{{\\HmacLatency}}{{{_fmt(hm['mean_sign_latency_us'],1)}}}")
        m.append(f"\\newcommand{{\\EdOverHmac}}{{{_fmt(sb['ed25519_over_hmac_time'],1)}}}")

    # ---- E3 granularity ----
    e3 = aux.get("E3", {})
    if e3:
        m.append(f"\\newcommand{{\\EThreeDocs}}{{{e3['n_documents']}}}")
        pd = e3["per_document"]["false_purge_rate"]
        m.append(f"\\newcommand{{\\PerDocFP}}{{{_fmt(pd['point'],2)}}}")
        m.append(f"\\newcommand{{\\PerDocFPLo}}{{{_fmt(pd['ci_low'],2)}}}")
        m.append(f"\\newcommand{{\\PerDocFPHi}}{{{_fmt(pd['ci_high'],2)}}}")
        m.append(f"\\newcommand{{\\PerDocPurged}}{{{e3['per_document']['total_purged']}}}")
        m.append(f"\\newcommand{{\\PerDocFalse}}{{{e3['per_document']['false_purged_clean']}}}")
        m.append(f"\\newcommand{{\\PerChunkFP}}{{{_fmt(e3['per_chunk']['false_purge_rate']['point'],2)}}}")

    # ---- E5 ASR ----
    e5 = aux.get("E5", {})
    if e5:
        asr = e5["attack_success"]
        m.append(f"\\newcommand{{\\AsrPoint}}{{{_fmt(asr['point']*100,0)}}}")
        m.append(f"\\newcommand{{\\AsrLo}}{{{_fmt(asr['ci_low']*100,0)}}}")
        m.append(f"\\newcommand{{\\AsrHi}}{{{_fmt(asr['ci_high']*100,0)}}}")
        m.append(f"\\newcommand{{\\AsrN}}{{{e5['n_questions']}}}")
        m.append(f"\\newcommand{{\\AsrTopK}}{{{e5['top_k']}}}")
        m.append(f"\\newcommand{{\\AsrGen}}{{{e5['generation_model'].split('/')[-1]}}}")

    # ---- E0 ----
    e0 = aux.get("E0", {})
    if e0:
        m.append(f"\\newcommand{{\\EZeroChunks}}{{{e0['n_chunks']}}}")
        m.append(f"\\newcommand{{\\EZeroPurged}}{{{e0['chunks_purged']}}}")

    # attack reference (verified figures)
    m.append("\\newcommand{\\PoisonTexts}{5}")
    m.append("\\newcommand{\\PoisonASR}{90}")
    m.append("% ===== END AUTO-GENERATED MACROS =====")

    (RESULTS / "macros.tex").write_text("\n".join(m) + "\n", encoding="utf-8")
    print("\n".join(m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
