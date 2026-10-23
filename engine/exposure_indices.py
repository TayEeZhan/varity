"""Compare the AEI-based AI-exposure score with other published exposure indices (step 9, part A).

Why: the production exposure (engine/exposure.py) uses one source, the Anthropic Economic
Index (AEI) automation share. One source can be wrong or just different in kind. This module
reads three more published indices at the O*NET occupation level, puts all on one scale and
checks where they agree. It does NOT change the production stance. It only writes a flag
`stance_robust` that the app can show as "contested".

Inputs (raw files are gitignored, see data/SOURCES.md for URL, version, licence):
- data/exposure_occupations.csv      AEI automation_pct (derived from the AEI file by engine/exposure.py)
- data/exposure.csv                  production e_s and stance per skill
- data/taxonomy.json                 skills per category (weights)
- data/raw/ext/gpts/occ_level.csv    "GPTs are GPTs" occupation exposure (O*NET-SOC 2019 codes)
- data/raw/ext/aioe/*.xlsx           Felten-Raj-Seamans AIOE (6-digit SOC 2010 codes)
- data/raw/ext/msft/ai_applicability_scores.csv   Microsoft "Working with AI" (6-digit SOC 2018 codes)
- data/raw/ext/onet_xwalk/*          O*NET-SOC 2010 -> 2019 and 2019 -> SOC 2018 crosswalks

Outputs:
- data/exposure_indices.csv      occupation x index: raw value, rank (1 = most exposed), z
- data/exposure_agreement.json   correlations, per-category views, robust and contested categories
- data/exposure_robustness.csv   one row per skill with the stance_robust flag

Method in short
- Six indices from four independent source families (AEI, GPTs-are-GPTs, AIOE, Microsoft).
  Two GPTs variants (GPT-4 rated, human rated) and two AIOE variants (all applications,
  language modelling) are the same family: they share a method and inputs, so a family
  casts ONE vote (the mean of its variants' z).
- Occupation level: each index is turned into a z-score and a rank over the 8 occupations
  (population standard deviation; rank 1 = highest raw value = most exposed).
- Category level: a category's raw score = mean raw value of its occupations (the same map
  as the production score). Its deviation = category score minus the mean over the 40 skills
  (every skill counts once, as in the production e_s). z = deviation / SD over the 40 skills.
- Stance label per index: the production rule, on the z scale. The production neutral band is
  |e_s| <= 0.02; on the AEI scale that equals NEUTRAL_Z standard deviations, and every index uses
  the same NEUTRAL_Z. z above it -> AI-substitutable, below minus it -> AI-complement.
- stance_robust (per category and so per skill): more than half of the voting families SUPPORT
  the production stance. A family votes only if it has a value for the category. Support means:
  production AI-substitutable -> the family puts the category above the mean (z > 0);
  production AI-complement -> below the mean (z < 0);
  production neutral -> inside the neutral band (|z| <= NEUTRAL_Z).
  A polar stance is a claim about the side of the mean, so the side is what we test. A neutral
  stance is a claim about being near the mean, so the band is what we test. The exact-label
  count (same three-way label) is reported too, but it is not the rule: with a three-way label
  and a narrow band, it would flag every category as contested.
  Veto: a polar stance is also contested if any voting family reads the opposite side strongly
  (|z| > STRONG_Z = 1). A majority can hide a family that says the reverse with force.
- Spearman rank correlation between the AEI value and each other index across the occupations.
  With n = 8 this has very little power: the exact permutation p-value is reported.

Run:
    python -m engine.exposure_indices
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pandas as pd

if __package__ in (None, ""):  # allow "python engine/exposure_indices.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.exposure import CATEGORY_OCCUPATIONS, STANCE_THRESHOLD  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
EXT = DATA_DIR / "raw" / "ext"

OCC_CSV = DATA_DIR / "exposure_occupations.csv"
EXPOSURE_CSV = DATA_DIR / "exposure.csv"
TAXONOMY_JSON = DATA_DIR / "taxonomy.json"
INDICES_CSV = DATA_DIR / "exposure_indices.csv"
AGREEMENT_JSON = DATA_DIR / "exposure_agreement.json"
ROBUSTNESS_CSV = DATA_DIR / "exposure_robustness.csv"

GPTS_CSV = EXT / "gpts" / "occ_level.csv"
AIOE_XLSX = EXT / "aioe" / "AIOE_DataAppendix.xlsx"
AIOE_LM_XLSX = EXT / "aioe" / "Language_Modeling_AIOE_and_AIIE.xlsx"
MSFT_CSV = EXT / "msft" / "ai_applicability_scores.csv"
XWALK_2010_2019 = EXT / "onet_xwalk" / "2010_to_2019_Crosswalk.csv"
XWALK_2019_SOC = EXT / "onet_xwalk" / "2019_to_SOC_Crosswalk.xlsx"

BASELINE = "aei_automation"  # the production index
STRONG_Z = 1.0  # a family this far (in SDs of the 40 skills) on the opposite side vetoes a polar stance
PERM_SEED = 0
EXACT_PERM_MAX_N = 9  # 9! = 362,880 permutations: still fast. Above that, sample.
MC_PERMUTATIONS = 20_000

SUBSTITUTABLE = "AI-substitutable"
NEUTRAL = "neutral"
COMPLEMENT = "AI-complement"


@dataclass(frozen=True)
class IndexSpec:
    """One index column. `family` groups variants that share a method and inputs."""

    id: str
    family: str
    label: str


INDEX_SPECS: tuple[IndexSpec, ...] = (
    IndexSpec("aei_automation", "aei", "AEI automation share (Claude.ai usage)"),
    IndexSpec("gpts_gpt4_beta", "gpts", "GPTs are GPTs, beta, GPT-4 rated"),
    IndexSpec("gpts_human_beta", "gpts", "GPTs are GPTs, beta, human rated"),
    IndexSpec("aioe", "aioe", "AIOE (Felten, Raj, Seamans), all applications"),
    IndexSpec("aioe_lm", "aioe", "AIOE, language-modelling variant"),
    IndexSpec("msft_applicability", "msft", "Microsoft AI applicability score (Bing Copilot usage)"),
)
FAMILY_LABELS = {
    "aei": "Anthropic Economic Index",
    "gpts": "GPTs are GPTs",
    "aioe": "AIOE",
    "msft": "Microsoft Working with AI",
}

# Provenance. Values below were read from the files and pages named here on 22 Oct 2026.
SOURCE_INFO: dict[str, dict] = {
    "aei": {
        "name": "Anthropic Economic Index, release 2026-06-26 (collaboration_bucket_automation_pct)",
        "url": "https://huggingface.co/datasets/Anthropic/EconomicIndex",
        "version": "release_2026_06_26, commit 4e5f69fab13a9c3f7d0dcc31a6f893a9818738f6",
        "licence": "CC BY (data); see data/SOURCES.md section 1",
        "file": "data/exposure_occupations.csv (derived by engine/exposure.py)",
    },
    "gpts": {
        "name": "GPTs are GPTs (Eloundou, Manning, Mishkin, Rock), occupation level",
        "url": "https://github.com/openai/GPTs-are-GPTs",
        "version": "commit 0471612fef3cc22b74fb884d27bff9dbd3770582 (2025-10-04)",
        "licence": "MIT (repository LICENSE, Copyright 2024 OpenAI)",
        "file": "data/occ_level.csv, columns dv_rating_beta and human_rating_beta",
    },
    "aioe": {
        "name": "AIOE (Felten, Raj, Seamans), occupation level",
        "url": "https://github.com/AIOE-Data/AIOE",
        "version": "commit adca5fc2cd0e9a659ff05278b7fa7a53f4f324c1 (2024-06-03)",
        "licence": ("No licence file. The README asks users to cite Felten, Raj, Seamans (2021), "
                    "Strategic Management Journal 42(12):2195-2217. Treated as: use allowed with citation."),
        "file": ("AIOE_DataAppendix.xlsx sheet 'Appendix A' (AIOE) and "
                 "Language Modeling AIOE and AIIE.xlsx sheet 'LM AIOE' (aioe_lm)"),
    },
    "msft": {
        "name": "Microsoft Working with AI, AI applicability scores (Tomlinson et al. 2025)",
        "url": "https://github.com/microsoft/working-with-ai",
        "version": "v1.1, commit 18ec44905db3383a7fd7fd0c1ff3ab36ad7729db (2026-10-09)",
        "licence": "CC BY 4.0 (README and LICENSE.txt)",
        "file": "ai_applicability_scores.csv, column ai_applicability_score",
    },
}


# --------------------------------------------------------------------------------------
# Small file readers
# --------------------------------------------------------------------------------------

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx_rows(path: Path | str, sheet: str) -> list[list]:
    """Rows of one sheet of an .xlsx file as lists (strings and floats; None for empty cells).

    Standard library only, so the project needs no extra package (openpyxl) for this step.
    """
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        wb = ElementTree.fromstring(z.read("xl/workbook.xml"))
        rid = None
        for s in wb.find("m:sheets", _NS):
            if s.get("name") == sheet:
                rid = s.get(f"{{{_NS['r']}}}id")
        if rid is None:
            names = [s.get("name") for s in wb.find("m:sheets", _NS)]
            raise KeyError(f"sheet {sheet!r} not in {Path(path).name}; sheets are {names}")
        rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels.findall("rel:Relationship", _NS) if r.get("Id") == rid)
        target = target.lstrip("/")
        member = target if target.startswith("xl/") else f"xl/{target}"
        sheet_xml = ElementTree.fromstring(z.read(member))
    rows: list[list] = []
    for row in sheet_xml.iter(f"{{{_NS['m']}}}row"):
        cells: dict[int, object] = {}
        for c in row.findall("m:c", _NS):
            kind, v = c.get("t"), c.find("m:v", _NS)
            if kind == "inlineStr":
                value: object = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
            elif v is None or v.text is None:
                value = None
            elif kind == "s":
                value = shared[int(v.text)]
            elif kind in ("str", "e"):
                value = v.text
            elif kind == "b":
                value = bool(int(v.text))
            else:
                value = float(v.text)
            cells[_col_index(c.get("r"))] = value
        width = max(cells) + 1 if cells else 0
        rows.append([cells.get(i) for i in range(width)])
    return rows


def sha256_of(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------------------
# SOC crosswalks
# --------------------------------------------------------------------------------------

def soc6(onet_soc: str) -> str:
    """6-digit SOC from an O*NET-SOC code: '15-1299.08' -> '15-1299'."""
    m = re.fullmatch(r"(\d{2}-\d{4})(?:\.\d{2})?", str(onet_soc).strip())
    if not m:
        raise ValueError(f"not an O*NET-SOC or SOC code: {onet_soc!r}")
    return m.group(1)


def parents_2010(code_2019: str, walk: pd.DataFrame) -> list[str]:
    """6-digit SOC 2010 codes that feed one O*NET-SOC 2019 code, from the official O*NET
    2010 -> 2019 crosswalk (columns 'O*NET-SOC 2010 Code' and 'O*NET-SOC 2019 Code').

    Example: 15-1252.00 (Software Developers) comes from 15-1132.00 and 15-1133.00, so the
    parents are ['15-1132', '15-1133'].
    """
    rows = walk[walk["O*NET-SOC 2019 Code"] == code_2019]
    return sorted({soc6(c) for c in rows["O*NET-SOC 2010 Code"]})


def soc2018_of(code_2019: str, table: dict[str, str]) -> str:
    """SOC 2018 code of an O*NET-SOC 2019 code, from the official O*NET 2019 -> SOC 2018 table."""
    try:
        return table[code_2019]
    except KeyError as exc:
        raise KeyError(f"{code_2019} is not in the O*NET-SOC 2019 -> SOC 2018 crosswalk") from exc


def load_soc2018_table(path: Path | str = XWALK_2019_SOC) -> dict[str, str]:
    rows = read_xlsx_rows(path, "O-NET-SOC 2019 Occupation Listi")
    return {r[0]: r[2] for r in rows if r and r[0] and re.fullmatch(r"\d{2}-\d{4}\.\d{2}", str(r[0]))}


# --------------------------------------------------------------------------------------
# Index values per occupation
# --------------------------------------------------------------------------------------

def occupations() -> list[str]:
    """The 8 distinct O*NET-SOC codes of the production map, in a fixed order."""
    seen: list[str] = []
    for codes in CATEGORY_OCCUPATIONS.values():
        for c in codes:
            if c not in seen:
                seen.append(c)
    return seen


def load_aei_values(occ_csv: Path = OCC_CSV) -> dict[str, tuple[float, str]]:
    df = pd.read_csv(occ_csv, dtype={"onet_soc": str})
    out: dict[str, tuple[float, str]] = {}
    for code, g in df.groupby("onet_soc"):
        out[code] = (float(g["automation_pct"].iloc[0]), "O*NET-SOC 2019 code, direct (AEI uses it)")
    return out


def load_gpts_values(column: str, path: Path = GPTS_CSV) -> dict[str, tuple[float, str]]:
    df = pd.read_csv(path)
    return {r["O*NET-SOC Code"]: (float(r[column]), "O*NET-SOC 2019 code, direct")
            for _, r in df.iterrows()}


def read_aioe_sheet(path: Path, sheet: str, value_header: str) -> dict[str, float]:
    """{6-digit SOC 2010 code: value} from an AIOE workbook sheet."""
    rows = read_xlsx_rows(path, sheet)
    header = rows[0]
    if header[0] != "SOC Code" or header[2] != value_header:
        raise ValueError(f"unexpected AIOE header {header[:3]} in {path.name}")
    return {str(r[0]): float(r[2]) for r in rows[1:] if r and r[0] and r[2] is not None}


def aioe_for(code_2019: str, aioe: dict[str, float], walk: pd.DataFrame) -> tuple[float | None, str]:
    """AIOE value for an O*NET-SOC 2019 code.

    AIOE is indexed by 6-digit SOC (the 2010 system: it has 15-1132 and 15-1133, not 15-1252).
    Rule: take the 6-digit SOC 2010 parents of the code from the official O*NET crosswalk, and
    the unweighted mean of the AIOE values that exist. No weights, because AIOE comes with none.
    """
    parents = parents_2010(code_2019, walk)
    found = {p: aioe[p] for p in parents if p in aioe}
    if not found:
        return None, f"SOC 2010 parents {parents or 'none'}: none has an AIOE value"
    missing = [p for p in parents if p not in aioe]
    note = f"mean of AIOE at SOC 2010 parents {sorted(found)}"
    if missing:
        note += f" (no AIOE value for {missing})"
    return float(np.mean(list(found.values()))), note


def load_aioe_values(aioe: dict[str, float], walk: pd.DataFrame, codes: list[str]
                     ) -> dict[str, tuple[float | None, str]]:
    return {c: aioe_for(c, aioe, walk) for c in codes}


def load_msft_values(codes: list[str], table: dict[str, str], path: Path = MSFT_CSV
                     ) -> dict[str, tuple[float | None, str]]:
    df = pd.read_csv(path)
    by_soc = dict(zip(df["SOC Code"], df["ai_applicability_score"]))
    out: dict[str, tuple[float | None, str]] = {}
    for c in codes:
        soc = soc2018_of(c, table)
        if soc in by_soc:
            note = f"SOC 2018 code {soc}"
            if not c.endswith(".00"):
                note += f" (the O*NET detail {c} shares the broad SOC code, so it gets that code's score)"
            out[c] = (float(by_soc[soc]), note)
        else:
            out[c] = (None, f"SOC 2018 code {soc} is not in the Microsoft file")
    return out


# --------------------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------------------

def zscores(values) -> np.ndarray:
    """z = (x - mean) / sd with the population sd, ignoring NaN. A constant input gives zeros."""
    x = np.asarray(values, dtype=float)
    ok = ~np.isnan(x)
    out = np.full(x.shape, np.nan)
    if ok.sum() == 0:
        return out
    sd = x[ok].std(ddof=0)
    out[ok] = 0.0 if sd == 0 else (x[ok] - x[ok].mean()) / sd
    return out


def ranks_desc(values) -> np.ndarray:
    """Rank 1 = highest value (most exposed). Ties get the average rank. NaN stays NaN."""
    return pd.Series(np.asarray(values, dtype=float)).rank(ascending=False, method="average").to_numpy()


def spearman(x, y) -> float:
    """Spearman correlation: Pearson correlation of the average ranks. NaN pairs are dropped.
    Returns NaN when fewer than 3 pairs remain or either side is constant."""
    a, b = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = ~(np.isnan(a) | np.isnan(b))
    if ok.sum() < 3:
        return float("nan")
    ra = pd.Series(a[ok]).rank(method="average").to_numpy()
    rb = pd.Series(b[ok]).rank(method="average").to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def spearman_perm_p(x, y, seed: int = PERM_SEED) -> float:
    """Two-sided permutation p-value of the Spearman correlation.

    Exact (all n! orderings) for n <= EXACT_PERM_MAX_N, else MC_PERMUTATIONS random orderings
    with a fixed seed. Counts orderings with |rho| >= |observed rho|, with a small tolerance.
    """
    a, b = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = ~(np.isnan(a) | np.isnan(b))
    a, b = a[ok], b[ok]
    rho = spearman(a, b)
    if math.isnan(rho):
        return float("nan")
    n = len(a)
    ra = pd.Series(a).rank(method="average").to_numpy()
    rb = pd.Series(b).rank(method="average").to_numpy()
    sa = ra - ra.mean()

    def corr_of(perm: np.ndarray) -> float:
        sb = rb[perm] - rb.mean()
        return float((sa * sb).sum() / math.sqrt((sa ** 2).sum() * (sb ** 2).sum()))

    tol = 1e-9
    if n <= EXACT_PERM_MAX_N:
        hits = total = 0
        for perm in itertools.permutations(range(n)):
            total += 1
            hits += abs(corr_of(np.array(perm))) >= abs(rho) - tol
        return hits / total
    rng = np.random.default_rng(seed)
    hits = sum(abs(corr_of(rng.permutation(n))) >= abs(rho) - tol for _ in range(MC_PERMUTATIONS))
    return (hits + 1) / (MC_PERMUTATIONS + 1)


# --------------------------------------------------------------------------------------
# Category views and agreement
# --------------------------------------------------------------------------------------

def category_raw(raw_by_code: dict[str, float | None]) -> dict[str, float]:
    """Mean raw value over a category's occupations (NaN-aware). A category with no value is NaN."""
    out = {}
    for cat, codes in CATEGORY_OCCUPATIONS.items():
        vals = [raw_by_code[c] for c in codes if raw_by_code.get(c) is not None
                and not math.isnan(raw_by_code[c])]
        out[cat] = float(np.mean(vals)) if vals else float("nan")
    return out


def skill_weighted_z(cat_scores: dict[str, float], weights: dict[str, int]
                     ) -> tuple[dict[str, float], dict[str, float], float]:
    """Deviation and z per category when every skill counts once.

    dev = score - weighted mean; z = dev / weighted population sd. Categories with a NaN score
    are left out of the mean and the sd and get NaN. Returns (dev, z, sd).
    """
    cats = [c for c, v in cat_scores.items() if not math.isnan(v)]
    w = np.array([weights[c] for c in cats], dtype=float)
    s = np.array([cat_scores[c] for c in cats], dtype=float)
    mean = float((w * s).sum() / w.sum())
    sd = float(math.sqrt((w * (s - mean) ** 2).sum() / w.sum()))
    dev = {c: (cat_scores[c] - mean) if c in cats else float("nan") for c in cat_scores}
    z = {c: (dev[c] / sd if (c in cats and sd > 0) else float("nan")) for c in cat_scores}
    return dev, z, sd


def label_for(z: float, neutral_z: float) -> str | None:
    """Stance label of a z value with the production rule. None when z is NaN."""
    if z is None or math.isnan(z):
        return None
    if z > neutral_z:
        return SUBSTITUTABLE
    if z < -neutral_z:
        return COMPLEMENT
    return NEUTRAL


def direction_of(z: float) -> str | None:
    if z is None or math.isnan(z):
        return None
    return "above" if z > 0 else "below" if z < 0 else "at"


def supports(production_label: str, z: float, neutral_z: float) -> bool | None:
    """Does a family with this z support the production stance? None when z is NaN (abstains).

    AI-substitutable: z > 0 (above the mean). AI-complement: z < 0. neutral: |z| <= neutral_z.
    """
    if z is None or math.isnan(z):
        return None
    if production_label == SUBSTITUTABLE:
        return z > 0
    if production_label == COMPLEMENT:
        return z < 0
    return abs(z) <= neutral_z


def contradicts(production_label: str, z: float, strong_z: float = STRONG_Z) -> bool:
    """A strong opposite reading of a polar stance: z more than `strong_z` SDs on the other side.

    A neutral stance cannot be contradicted this way (the band test already covers it).
    """
    if z is None or math.isnan(z):
        return False
    if production_label == SUBSTITUTABLE:
        return z < -strong_z
    if production_label == COMPLEMENT:
        return z > strong_z
    return False


def agreement_for_category(production_label: str, production_direction: str,
                           family_z: dict[str, float], neutral_z: float,
                           strong_z: float = STRONG_Z) -> dict:
    """The agreement logic for one category.

    family_z: z of each family for the category (NaN = the family has no value and abstains).
    majority = strictly more than half of the voting families support the production stance
    (see `supports`). veto = some family contradicts a polar stance strongly (see `contradicts`).
    stance_robust = majority and no veto. direction_robust is looser: a majority is on the same
    side of the mean as the production e_s.
    """
    labels = {f: label_for(z, neutral_z) for f, z in family_z.items()}
    dirs = {f: direction_of(z) for f, z in family_z.items()}
    sup = {f: supports(production_label, z, neutral_z) for f, z in family_z.items()}
    voting = [f for f, v in labels.items() if v is not None]
    supporting = [f for f in voting if sup[f]]
    vetoing = [f for f in voting if contradicts(production_label, family_z[f], strong_z)]
    exact = [f for f in voting if labels[f] == production_label]
    same_side = [f for f in voting if dirs[f] == production_direction]
    n = len(voting)
    majority = bool(n > 0 and 2 * len(supporting) > n)
    return {
        "family_labels": labels,
        "family_directions": dirs,
        "n_voting": n,
        "n_support": len(supporting),
        "families_supporting": supporting,
        "families_vetoing": vetoing,
        "n_exact_label": len(exact),
        "n_same_side": len(same_side),
        "majority_supports": majority,
        "stance_robust": bool(majority and not vetoing),
        "direction_robust": bool(n > 0 and 2 * len(same_side) > n),
    }


# --------------------------------------------------------------------------------------
# Text for the app (kept here so app.py stays small and the wording is tested)
# --------------------------------------------------------------------------------------

_SHORT = {SUBSTITUTABLE: "substitutable", COMPLEMENT: "complement", NEUTRAL: "neutral"}


def crosscheck_rows(agreement: dict) -> list[dict]:
    """Table rows for the Method tab: one per category, one column per source family."""
    fams = agreement.get("families") or {}
    rows = []
    for cat, v in ((agreement.get("category_level") or {}).get("categories") or {}).items():
        row = {"Category": cat, "Skills": v.get("n_skills"), "Our stance": v.get("production_stance")}
        for f, name in fams.items():
            z = (v.get("family_z") or {}).get(f)
            label = (v.get("family_labels") or {}).get(f)
            row[name] = f"{z:+.2f} {_SHORT.get(label, '')}".strip() if isinstance(z, (int, float)) else "no value"
        row["Indices that support our stance"] = f"{v.get('n_support')} of {v.get('n_voting')}"
        row["Contested?"] = "no" if v.get("stance_robust") else "yes"
        rows.append(row)
    return rows


def correlation_text(agreement: dict) -> str:
    """One sentence: rank correlation of each other index with the AEI across the occupations."""
    corr = (agreement.get("occupation_level") or {}).get("spearman_vs_aei") or {}
    names = {i.get("id"): i.get("label") for i in agreement.get("indices") or []}
    parts = [f"{names.get(i, i)}: {c['spearman_vs_aei']:+.2f}" for i, c in corr.items()
             if isinstance(c.get("spearman_vs_aei"), (int, float))]
    if not parts:
        return ""
    return ("Rank correlation with the AEI across the occupations (8, or 7 for AIOE): "
            + "; ".join(parts) + ".")


def agreement_text(agreement: dict) -> str:
    robust = agreement.get("robust_categories") or []
    contested = agreement.get("contested_categories") or []
    return (f"**Most indices agree with our stance:** {', '.join(robust) or 'none'}. "
            f"**Contested:** {', '.join(contested) or 'none'}. "
            "Skills in a contested category show 'contested across indices' in Skill detail. "
            "The stance itself is unchanged.")


# --------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------

def collect_values(codes: list[str], paths: dict[str, Path] | None = None
                   ) -> dict[str, dict[str, tuple[float | None, str]]]:
    """{index id: {O*NET-SOC code: (raw value or None, mapping note)}} for all six indices."""
    p = {"gpts": GPTS_CSV, "aioe": AIOE_XLSX, "aioe_lm": AIOE_LM_XLSX, "msft": MSFT_CSV,
         "walk": XWALK_2010_2019, "soc": XWALK_2019_SOC, "occ": OCC_CSV}
    p.update(paths or {})
    missing = [str(v) for k, v in p.items() if not Path(v).exists()]
    if missing:
        raise FileNotFoundError("Raw files missing (download them as described in data/SOURCES.md): "
                                + "; ".join(missing))
    walk = pd.read_csv(p["walk"])
    table = load_soc2018_table(p["soc"])
    aioe = read_aioe_sheet(Path(p["aioe"]), "Appendix A", "AIOE")
    aioe_lm = read_aioe_sheet(Path(p["aioe_lm"]), "LM AIOE", "Language Modeling AIOE")
    gpts4 = load_gpts_values("dv_rating_beta", Path(p["gpts"]))
    gptsh = load_gpts_values("human_rating_beta", Path(p["gpts"]))
    aei = load_aei_values(Path(p["occ"]))
    for name, src in (("AEI", aei), ("GPTs", gpts4)):
        absent = [c for c in codes if c not in src]
        if absent:
            raise KeyError(f"{name} has no row for {absent}")
    return {
        "aei_automation": {c: aei[c] for c in codes},
        "gpts_gpt4_beta": {c: gpts4[c] for c in codes},
        "gpts_human_beta": {c: gptsh[c] for c in codes},
        "aioe": load_aioe_values(aioe, walk, codes),
        "aioe_lm": load_aioe_values(aioe_lm, walk, codes),
        "msft_applicability": load_msft_values(codes, table, Path(p["msft"])),
    }


def build_indices_table(values: dict[str, dict[str, tuple[float | None, str]]],
                        titles: dict[str, str]) -> pd.DataFrame:
    """Long table: one row per (occupation, index) with raw value, rank and z over the occupations."""
    rows = []
    for spec in INDEX_SPECS:
        per_code = values[spec.id]
        codes = list(per_code)
        raw = np.array([np.nan if per_code[c][0] is None else per_code[c][0] for c in codes])
        rk, z = ranks_desc(raw), zscores(raw)
        for i, c in enumerate(codes):
            rows.append({
                "onet_soc": c, "occupation_title": titles.get(c, ""), "source": spec.id,
                "family": spec.family,
                "raw_value": None if np.isnan(raw[i]) else round(float(raw[i]), 6),
                "rank": None if np.isnan(rk[i]) else float(rk[i]),
                "z": None if np.isnan(z[i]) else round(float(z[i]), 4),
                "n_occupations": int((~np.isnan(raw)).sum()),
                "mapping_note": per_code[c][1],
            })
    return pd.DataFrame(rows)


def build_agreement(values, production: pd.DataFrame, taxonomy: list[dict]) -> tuple[dict, pd.DataFrame]:
    """The agreement dict (for exposure_agreement.json) and the per-skill robustness table."""
    codes = list(values[BASELINE])
    weights: dict[str, int] = {}
    for t in taxonomy:
        weights[t["category"]] = weights.get(t["category"], 0) + 1

    # occupation level
    raw_mat = {s.id: np.array([np.nan if values[s.id][c][0] is None else values[s.id][c][0]
                               for c in codes]) for s in INDEX_SPECS}
    base = raw_mat[BASELINE]
    corr = {}
    for s in INDEX_SPECS:
        if s.id == BASELINE:
            continue
        corr[s.id] = {
            "spearman_vs_aei": _num(spearman(base, raw_mat[s.id])),
            "p_two_sided_permutation": _num(spearman_perm_p(base, raw_mat[s.id])),
            "n_occupations": int((~(np.isnan(base) | np.isnan(raw_mat[s.id]))).sum()),
        }
    matrix = {a.id: {b.id: _num(spearman(raw_mat[a.id], raw_mat[b.id])) for b in INDEX_SPECS}
              for a in INDEX_SPECS}

    # category level, per index
    per_index_z: dict[str, dict[str, float]] = {}
    per_index_dev: dict[str, dict[str, float]] = {}
    per_index_cat: dict[str, dict[str, float]] = {}
    for s in INDEX_SPECS:
        cat_raw = category_raw({c: (None if np.isnan(v) else float(v)) for c, v in zip(codes, raw_mat[s.id])})
        dev, z, _ = skill_weighted_z(cat_raw, weights)
        per_index_cat[s.id], per_index_dev[s.id], per_index_z[s.id] = cat_raw, dev, z

    # neutral band on the z scale, from the production band and the AEI e_s spread over the 40 skills
    prod_by_cat = production.drop_duplicates("category").set_index("category")
    e_s = {c: float(prod_by_cat.loc[c, "e_s"]) for c in weights}
    sd_e = math.sqrt(sum(weights[c] * e_s[c] ** 2 for c in weights) / sum(weights.values()))
    neutral_z = STANCE_THRESHOLD / sd_e

    families = list(dict.fromkeys(s.family for s in INDEX_SPECS))
    categories: dict[str, dict] = {}
    for cat in CATEGORY_OCCUPATIONS:
        fam_z = {}
        for f in families:
            zs = [per_index_z[s.id][cat] for s in INDEX_SPECS if s.family == f
                  and not math.isnan(per_index_z[s.id][cat])]
            fam_z[f] = float(np.mean(zs)) if zs else float("nan")
        prod_label = str(prod_by_cat.loc[cat, "stance"])
        prod_dir = direction_of(e_s[cat])
        ag = agreement_for_category(prod_label, prod_dir, fam_z, neutral_z)
        categories[cat] = {
            "n_skills": weights[cat],
            "occupations": CATEGORY_OCCUPATIONS[cat],
            "production_stance": prod_label,
            "production_e_s": round(e_s[cat], 6),
            "index_z": {i: _num(per_index_z[i][cat]) for i in per_index_z},
            "index_category_raw": {i: _num(per_index_cat[i][cat]) for i in per_index_cat},
            "index_labels": {i: label_for(per_index_z[i][cat], neutral_z) for i in per_index_z},
            "family_z": {f: _num(v) for f, v in fam_z.items()},
            **ag,
        }
    robust = sorted(c for c, v in categories.items() if v["stance_robust"])
    contested = sorted(c for c, v in categories.items() if not v["stance_robust"])

    rob_rows = []
    for t in taxonomy:
        c = categories[t["category"]]
        rob_rows.append({
            "skill": t["skill"], "category": t["category"],
            "production_stance": c["production_stance"],
            "stance_robust": str(c["stance_robust"]).lower(),
            "n_families_voting": c["n_voting"], "n_families_support": c["n_support"],
            "families_supporting": ";".join(c["families_supporting"]),
            "families_vetoing": ";".join(c["families_vetoing"]),
            "direction_robust": str(c["direction_robust"]).lower(),
        })
    robustness = pd.DataFrame(rob_rows)

    agreement = {
        "generated_by": "engine/exposure_indices.py",
        "baseline_index": BASELINE,
        "production_stance_changed": False,
        "indices": [{"id": s.id, "family": s.family, "label": s.label} for s in INDEX_SPECS],
        "families": {f: FAMILY_LABELS[f] for f in families},
        "sources": SOURCE_INFO,
        "occupations": codes,
        "occupation_level": {"spearman_vs_aei": corr, "spearman_matrix": matrix,
                             "note": ("n = 8 occupations (7 for AIOE: Data Scientists has no AIOE value). "
                                      "With so few points only a very large rho is significant.")},
        "category_level": {
            "neutral_band_z": round(neutral_z, 4),
            "neutral_band_note": ("The production neutral band |e_s| <= 0.02 expressed in standard "
                                  "deviations of e_s over the 40 skills. Every index uses it."),
            "categories": categories,
        },
        "robust_categories": robust,
        "contested_categories": contested,
        "robust_skills": [t["skill"] for t in taxonomy if t["category"] in robust],
        "contested_skills": [t["skill"] for t in taxonomy if t["category"] in contested],
        "rules": {
            "stance_robust": ("more than half of the voting source families support the production stance "
                              "(AEI is one of the voters). Support: AI-substitutable -> z > 0; "
                              "AI-complement -> z < 0; neutral -> |z| <= neutral_band_z). A polar stance is also "
                              "contested when a voting family reads the opposite side with |z| > 1 (veto)"),
            "family_vote": "mean z of the family's variants; a family with no value for a category abstains",
            "labels": "same three-way rule as engine/exposure.py, applied to z with the neutral band above (shown for information)",
        },
        "caveats": [
            "Eight occupations and four source families: this is a sanity check, not a measurement.",
            "AEI and Microsoft measure how people use a chatbot; GPTs and AIOE rate what a model could do. They answer different questions, so disagreement is expected.",
            "Skills in one category share one score, so 40 skills carry only 6 distinct values.",
            "15-1299.08 maps to the broad code 15-1299 / 15-1199 ('Computer Occupations, All Other') in AIOE and Microsoft: a coarse match.",
            "AIOE has no value for Data Scientists (15-2051), so the ai_ml category gets no AIOE vote.",
            "The 2010 -> 2019 crosswalk gives several parents for some codes; the unweighted mean of their AIOE values is a choice.",
        ],
    }
    return agreement, robustness


def _num(x):
    return None if (x is None or (isinstance(x, float) and math.isnan(x))) else round(float(x), 6)


def file_hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {k: sha256_of(v) for k, v in paths.items() if Path(v).exists()}


def build_all(write: bool = True) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    codes = occupations()
    titles = pd.read_csv(OCC_CSV).drop_duplicates("onet_soc").set_index("onet_soc")["occupation_title"].to_dict()
    values = collect_values(codes)
    table = build_indices_table(values, titles)
    production = pd.read_csv(EXPOSURE_CSV)
    taxonomy = json.loads(TAXONOMY_JSON.read_text(encoding="utf-8"))
    agreement, robustness = build_agreement(values, production, taxonomy)
    agreement["raw_file_sha256"] = file_hashes({
        "gpts/occ_level.csv": GPTS_CSV, "aioe/AIOE_DataAppendix.xlsx": AIOE_XLSX,
        "aioe/Language_Modeling_AIOE_and_AIIE.xlsx": AIOE_LM_XLSX,
        "msft/ai_applicability_scores.csv": MSFT_CSV,
        "onet_xwalk/2010_to_2019_Crosswalk.csv": XWALK_2010_2019,
        "onet_xwalk/2019_to_SOC_Crosswalk.xlsx": XWALK_2019_SOC})
    if write:
        table.to_csv(INDICES_CSV, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)
        AGREEMENT_JSON.write_text(json.dumps(agreement, indent=2) + "\n", encoding="utf-8")
        robustness.to_csv(ROBUSTNESS_CSV, index=False, encoding="utf-8")
    return table, agreement, robustness


def main() -> int:
    table, agreement, robustness = build_all()
    wide = table.pivot(index="onet_soc", columns="source", values="raw_value")
    print(wide.to_string())
    print()
    print("Spearman vs AEI:", json.dumps(agreement["occupation_level"]["spearman_vs_aei"], indent=1))
    print("Robust:", agreement["robust_categories"], "Contested:", agreement["contested_categories"])
    print(f"Wrote {INDICES_CSV.name}, {AGREEMENT_JSON.name}, {ROBUSTNESS_CSV.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
