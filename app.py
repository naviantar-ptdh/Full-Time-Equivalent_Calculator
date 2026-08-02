# app.py (v7 — "Looker light": orange header band, white cards, English UI)
"""
FTE Calculator — PT Darma Henwa

Three modes (picked from the sidebar nav):

*   **Calculator**        — one equipment type, result shown straight away.
*   **Basecase All Unit** — every unit of ONE site, shown as a dashboard.
*   **Summary**           — the same dashboard, aggregated across ALL sites.

Basecase and Summary share one dashboard body (`render_dashboard_body`), so a
layout change lands in both at once:

    header band  ->  formula parameters (collapsed)  ->  role legend
    ->  KPI row  ->  section chart + M1-M3 donut
    ->  monthly cost (half circle + detail) + yearly cost
    ->  details (collapsed expander -> tabs)

The section chart used to be two charts (totals, then the M1-M3 split); they
are one stacked chart now, with each section total printed above its bar. The
cost chart used to be a speedometer scaled against the most expensive site —
that comparison is gone; it is a plain half circle whose colours are the
per-role share, paired with a yearly twin.

Calculation logic (`calculator.py`, `data_loader.py`, `config.py`) is
untouched — this file is purely the presentation layer.
"""
import math
import os
from typing import List

import pandas as pd
import streamlit as st

import charts
import theme
from calculator import (
    CalculationError,
    FTEInput,
    compute_fte,
    compute_site_cost,
    compute_site_summary,
    compute_staff_fte,
)
from charts import num, rp, rp_short
from config import (
    BASE_MECHANIC_HOURS,
    COST_RATE,
    MONTH_COLS,
    STAFF_COST_RATE,
    TRAVEL_DIVISOR,
    UNIT_EDIT_PASSWORD,
)
from data_loader import (
    BackendDataError,
    UnitRow,
    load_backend_data,
    load_staff_data,
    load_unit_data,
)

st.set_page_config(
    page_title="FTE Calculator — PT Darma Henwa",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="expanded",
)

PAGE_SIZE = 10
DEMO = os.getenv("FTE_DEMO") == "1"

theme.inject_css()


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner="Loading BACKEND reference data…")
def get_backend():
    if DEMO:
        import demo_data
        return demo_data.backend()
    return load_backend_data()


@st.cache_data(ttl=600, show_spinner="Loading unit data per site…")
def get_units():
    if DEMO:
        import demo_data
        return demo_data.units()
    return load_unit_data()


@st.cache_data(ttl=600, show_spinner="Loading staff data…")
def get_staff():
    if DEMO:
        import demo_data
        return demo_data.staff()
    return load_staff_data()


def units_to_df(rows: List[UnitRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Category": r.category, "Jenis Unit": r.jenis_unit,
             "Jumlah Unit": r.jumlah_unit, "PA": r.pa}
            for r in rows
        ],
        columns=["Category", "Jenis Unit", "Jumlah Unit", "PA"],
    )


def df_to_units(df: pd.DataFrame) -> List[UnitRow]:
    rows = []
    for _, r in df.iterrows():
        try:
            rows.append(UnitRow(
                category=str(r["Category"]),
                jenis_unit=str(r["Jenis Unit"]),
                jumlah_unit=float(r["Jumlah Unit"]),
                pa=float(r["PA"]),
            ))
        except Exception:
            continue
    return rows


def _blank_levels() -> dict:
    return {"M1": 0.0, "M2": 0.0, "M3": 0.0, "Tot": 0.0}


def _add_levels(dst: dict, src_: dict) -> dict:
    for k in ("M1", "M2", "M3", "Tot"):
        dst[k] = dst.get(k, 0.0) + src_.get(k, 0.0)
    return dst


def aggregate_all_sites(backend, units_all, competency_factor: float) -> dict | None:
    """Roll every site up into one summary/cost pair shaped like a single site.

    Summary mode reuses the exact dashboard body that Basecase uses, so the
    aggregate has to mimic the shape `compute_site_summary` returns:
    mechanic_by_category, welder_total, electric_total, detail_rows,
    skipped_units. Each site is still computed by the untouched calculator —
    only the results are summed here.

    Cached in session_state per competency factor: recomputing every site on
    each rerun is the single most expensive thing this app does.
    """
    key = f"_allsites_{competency_factor:.2f}"
    if key in st.session_state:
        return st.session_state[key]

    mech_by_cat: dict = {}
    weld = _blank_levels()
    elec = _blank_levels()
    cost_total: dict = {r: _blank_levels() for r in ("Mechanic", "Electric", "Welder")}
    cost_total["Total"] = _blank_levels()
    detail_rows, skipped, per_site, ok_sites = [], [], {}, []
    oper_acc: dict = {}
    plan_acc: dict = {}

    for s in (backend.sites or []):
        rows = units_all.get(s) or []
        if not rows:
            continue
        try:
            summ = compute_site_summary(s, rows, backend, competency_factor)
            c = compute_site_cost(
                summ["mechanic_by_category"], summ["welder_total"], summ["electric_total"]
            )
        except (CalculationError, BackendDataError, KeyError, ValueError):
            continue

        ok_sites.append(s)
        per_site[s] = c["Total"]["Tot"]

        # Staff dihitung per site lalu dijumlahkan per posisi, supaya section
        # Staff di mode Summary memakai blok tampilan yang sama persis dengan
        # mode Basecase.
        try:
            staff = compute_staff_fte(
                s, summ["mechanic_by_category"], summ["welder_total"],
                summ["electric_total"], get_staff(),
            )
        except (CalculationError, BackendDataError, KeyError, ValueError):
            staff = {"operational": [], "planner": []}
        for r in staff["operational"]:
            acc = oper_acc.setdefault(
                r["posisi"], {"posisi": r["posisi"], "jumlah_mekanik": 0,
                              "foreman": 0, "supervisor": 0})
            acc["jumlah_mekanik"] += r["jumlah_mekanik"]
            acc["foreman"] += r["foreman"]
            acc["supervisor"] += r["supervisor"]
        for r in staff["planner"]:
            acc = plan_acc.setdefault(r["posisi"], {"posisi": r["posisi"], "fte": 0})
            acc["fte"] += r["fte"]
        for cat, v in summ["mechanic_by_category"].items():
            mech_by_cat.setdefault(cat, _blank_levels())
            _add_levels(mech_by_cat[cat], v)
        _add_levels(weld, summ["welder_total"])
        _add_levels(elec, summ["electric_total"])
        for role in ("Mechanic", "Electric", "Welder", "Total"):
            _add_levels(cost_total[role], c.get(role, {}))
        for d in summ["detail_rows"]:
            detail_rows.append({**d, "site": s})
        for sk in summ["skipped_units"]:
            skipped.append([s, *sk] if isinstance(sk, (list, tuple)) else [s, sk])

    if not ok_sites:
        st.session_state[key] = None
        return None

    # kategori diurutkan mengikuti urutan resmi di BACKEND supaya sumbu X
    # chart section konsisten dengan mode Basecase
    order = [c for c in (backend.classification_order or []) if c in mech_by_cat]
    order += [c for c in mech_by_cat if c not in order]
    mech_by_cat = {c: mech_by_cat[c] for c in order}

    out = {
        "summary": {
            "mechanic_by_category": mech_by_cat,
            "welder_total": weld,
            "electric_total": elec,
            "detail_rows": detail_rows,
            "skipped_units": skipped,
        },
        "cost": cost_total,
        "sites": ok_sites,
        "per_site_cost": per_site,
        "unit_rows": sum(len(units_all.get(s) or []) for s in ok_sites),
        "operational": list(oper_acc.values()),
        "planner": list(plan_acc.values()),
    }
    st.session_state[key] = out
    return out


ROLE_LEGEND = [
    ("Mechanic", theme.ROLE_COLORS["Mechanic"]),
    ("Electrician", theme.ROLE_COLORS["Electric"]),
    ("Welder", theme.ROLE_COLORS["Welder"]),
]
LEVEL_LEGEND = [
    ("M1 · Senior", theme.LEVEL_SHADES["M1"]),
    ("M2 · Middle", theme.LEVEL_SHADES["M2"]),
    ("M3 · Junior", theme.LEVEL_SHADES["M3"]),
]
MONTHS_PER_YEAR = 12


# ---------------------------------------------------------------------------
# Formula parameters panel
# ---------------------------------------------------------------------------
def formula_items(backend, unit_qty: float, site: str | None = None) -> list:
    """The four inputs the manpower formula actually turns on.

    Trimmed down deliberately: the earlier version listed every constant in
    the model (RACI, splits, cost rates, competency factor...), which buried
    the numbers a reader checks in practice. Unit QUANTITY is used here, not
    the number of unit types — one Sheet9 row can carry 25 units.
    """
    if site:
        jarak = backend.jarak.get(site)
        ratio = backend.ratio_shift.get(site)
        lost = backend.lost_time.get(site)
        return [
            ("Unit quantity", num(unit_qty), "total units in scope"),
            ("Shift ratio", num(ratio, 2) if ratio is not None else "", f"site {site}"),
            ("Distance", f"{num(jarak, 2)} km" if jarak is not None else "",
             f"travel hours = distance / {TRAVEL_DIVISOR}"),
            ("Effective working hour",
             f"{num(BASE_MECHANIC_HOURS - lost, 2)} h" if lost is not None else "",
             f"{num(BASE_MECHANIC_HOURS)} − lost time {num(lost, 2)} h"
             if lost is not None else ""),
        ]

    dists = [v for v in backend.jarak.values() if v is not None]
    ratios = list(backend.ratio_shift.values())
    losts = list(backend.lost_time.values())
    ewh = [BASE_MECHANIC_HOURS - v for v in losts]
    def rng(vals, dec=2, unit=""):
        if not vals:
            return ""
        lo, hi = min(vals), max(vals)
        if abs(hi - lo) < 1e-9:
            return f"{num(lo, dec)}{unit}"
        return f"{num(lo, dec)} – {num(hi, dec)}{unit}"
    return [
        ("Unit quantity", num(unit_qty), "total units across all sites"),
        ("Shift ratio", rng(ratios), "range across sites"),
        ("Distance", rng(dists, 2, " km"), f"travel hours = distance / {TRAVEL_DIVISOR}"),
        ("Effective working hour", rng(ewh, 2, " h"),
         f"{num(BASE_MECHANIC_HOURS)} − lost time"),
    ]


def unit_list_df(detail_rows: list, with_site: bool = False) -> pd.DataFrame:
    """The unit list that used to live in the "Per-unit detail" tab.

    It moved into the parameters panel because that is where a reader asks
    "which units is this built from?". In Summary the same unit type shows up
    once per site, so a Site column is prepended to keep the rows distinct.
    """
    cols = (["Site"] if with_site else []) + ["Category", "Unit Type", "Qty", "PA (%)"]
    rows = []
    for d in detail_rows:
        row = {
            "Category": d["category"],
            "Unit Type": d["jenis_unit"],
            "Qty": d["jumlah_unit"],
            "PA (%)": d["pa"],
        }
        if with_site:
            row = {"Site": d.get("site", ""), **row}
        rows.append(row)
    return pd.DataFrame(rows, columns=cols)


def render_formula_panel(items: list, detail_rows: list, with_site: bool = False,
                         skipped: list | None = None):
    with st.container(key="param_panel"):
        with st.expander("Formula parameters & unit list", expanded=False):
            st.markdown(
                '<p class="dh-secnote">These four inputs drive the manpower '
                'formula. The table below lists every unit the numbers are '
                'built from.</p>',
                unsafe_allow_html=True,
            )
            st.markdown(theme.info_grid(items), unsafe_allow_html=True)
            st.write("")
            df = unit_list_df(detail_rows, with_site)
            st.markdown(f"**Unit list — {len(df)} rows**")
            if len(df):
                st.dataframe(df, width="stretch", hide_index=True,
                             height=min(360, 40 + 35 * len(df)))
            else:
                st.info("No unit rows were calculated.")
            if skipped:
                st.caption(
                    f"{len(skipped)} rows skipped — Sub Category not registered in BACKEND."
                )


# ---------------------------------------------------------------------------
# Cost blocks — monthly and yearly share one builder
# ---------------------------------------------------------------------------
def cost_detail_table(cost: dict, head_counts: dict, grand_head: float,
                      factor: int = 1) -> str:
    """Role | MPP | M1 | M2 | M3 | Total.

    MPP is a headcount; the four level columns are money. `factor` turns the
    monthly figures into yearly ones without recomputing anything.
    """
    rows = []
    for role in ("Mechanic", "Electric", "Welder"):
        v = cost.get(role, {})
        rows.append([
            theme.ROLE_LABEL[role],
            num(head_counts[role].get("Tot", 0)),
            rp_short(v.get("M1", 0) * factor),
            rp_short(v.get("M2", 0) * factor),
            rp_short(v.get("M3", 0) * factor),
            rp_short(v.get("Tot", 0) * factor),
        ])
    t = cost.get("Total", {})
    return theme.table_html(
        ["Role", "MPP", "M1", "M2", "M3", "Total"], rows,
        total_row=[
            "TOTAL", num(grand_head),
            rp_short(t.get("M1", 0) * factor), rp_short(t.get("M2", 0) * factor),
            rp_short(t.get("M3", 0) * factor), rp_short(t.get("Tot", 0) * factor),
        ],
        total_col=5,
    )


def render_cost_block(key: str, title: str, sub: str, cost: dict, head_counts: dict,
                      grand_head: float, factor: int, per_head_label: str):
    total = cost.get("Total", {}).get("Tot", 0) * factor
    per_head = total / grand_head if grand_head else 0
    with theme.card(key, title, sub, accent=theme.BRAND["orange_deep"]):
        st.plotly_chart(
            charts.cost_semicircle(
                cost, rp_short(total), f"{rp_short(per_head)} {per_head_label}", height=200,
            ),
            width="stretch", config={"displayModeBar": False},
        )
        st.markdown(theme.legend_html(ROLE_LEGEND), unsafe_allow_html=True)
        st.markdown(cost_detail_table(cost, head_counts, grand_head, factor),
                    unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Staff section (Foreman / Supervisor / Planner)
# ---------------------------------------------------------------------------
STAFF_COLORS = {
    "Foreman": theme.BRAND["orange"],
    "Supervisor": theme.BRAND["navy"],
    "Planner": theme.BRAND["amber"],
}


def render_staff_section(operational: list, planner: list):
    """Staff gets its own section on the dashboard, mirroring the mechanic block.

    It used to be hidden inside the Details expander. Composition is shown as a
    table rather than a chart on purpose: foreman and supervisor land on 1 per
    section almost everywhere, so a bar chart of identical bars would carry no
    information. The cost split, which IS proportional, gets the half circle.
    """
    st.write("")
    st.markdown(
        theme.legend_strip("Staff", [("Foreman", STAFF_COLORS["Foreman"]),
                                     ("Supervisor", STAFF_COLORS["Supervisor"]),
                                     ("Planner", STAFF_COLORS["Planner"])]),
        unsafe_allow_html=True,
    )

    if not operational and not planner:
        st.markdown(
            theme.empty_state(
                "No staff data",
                "Fill in Area Kerja, Beban Admin and Jam Efektif on the Hasil Staff sheet.",
                "🗂️",
            ),
            unsafe_allow_html=True,
        )
        return

    f_sum = sum(r["foreman"] for r in operational)
    s_sum = sum(r["supervisor"] for r in operational)
    p_sum = sum(r["fte"] for r in planner)
    f_cost = f_sum * STAFF_COST_RATE["Foreman"]
    s_cost = s_sum * STAFF_COST_RATE["Supervisor"]
    # Planner memakai tarif yang sama dengan Foreman.
    p_cost = p_sum * STAFF_COST_RATE["Planner"]
    staff_cost = f_cost + s_cost + p_cost

    s1, s2 = st.columns([1.6, 1], gap="small")

    with s1:
        with theme.card("staff_table", "Foreman & Supervisor per section",
                        "one line per section, plus the planner roles",
                        accent=theme.BRAND["navy"]):
            rows = [
                [r["posisi"], num(r["jumlah_mekanik"]), num(r["foreman"]),
                 num(r["supervisor"]), num(r["foreman"] + r["supervisor"])]
                for r in operational
            ]
            if rows:
                st.markdown(
                    theme.table_html(
                        ["Section", "Mechanics", "Foreman", "Supervisor", "Total"], rows,
                        total_row=["TOTAL", "–", num(f_sum), num(s_sum), num(f_sum + s_sum)],
                        total_col=4,
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.info("No Foreman/Supervisor data for this scope yet.")

            if planner:
                st.write("")
                st.markdown("**FTE Planner**")
                st.markdown(
                    theme.table_html(
                        ["Position", "FTE"],
                        [[r["posisi"], num(r["fte"])] for r in planner],
                        total_row=["TOTAL", num(p_sum)], total_col=1,
                    ),
                    unsafe_allow_html=True,
                )

    with s2:
        with theme.card("staff_cost", "Staff cost",
                        f"Foreman & Planner {rp_short(STAFF_COST_RATE['Foreman'], 1)} · "
                        f"Supervisor {rp_short(STAFF_COST_RATE['Supervisor'], 1)} per month",
                        accent=theme.BRAND["orange_deep"]):
            st.plotly_chart(
                charts.share_semicircle(
                    ["Foreman", "Supervisor", "Planner"], [f_cost, s_cost, p_cost],
                    [STAFF_COLORS["Foreman"], STAFF_COLORS["Supervisor"],
                     STAFF_COLORS["Planner"]],
                    rp_short(staff_cost),
                    f"{rp_short(staff_cost * MONTHS_PER_YEAR)} per year",
                    height=355,
                ),
                width="stretch", config={"displayModeBar": False},
            )
            st.markdown(
                theme.table_html(
                    ["Role", "MPP", "Cost / month", "Cost / year"],
                    [
                        ["Foreman", num(f_sum), rp_short(f_cost),
                         rp_short(f_cost * MONTHS_PER_YEAR)],
                        ["Supervisor", num(s_sum), rp_short(s_cost),
                         rp_short(s_cost * MONTHS_PER_YEAR)],
                        ["Planner", num(p_sum), rp_short(p_cost),
                         rp_short(p_cost * MONTHS_PER_YEAR)],
                    ],
                    total_row=["TOTAL", num(f_sum + s_sum + p_sum), rp_short(staff_cost),
                               rp_short(staff_cost * MONTHS_PER_YEAR)],
                    total_col=3,
                ),
                unsafe_allow_html=True,
            )



# ---------------------------------------------------------------------------
# Dashboard body shared by Basecase All Unit and Summary
# ---------------------------------------------------------------------------
def render_dashboard_body(summary: dict, cost: dict) -> dict:
    mech_total = {m: sum(v.get(m, 0) for v in summary["mechanic_by_category"].values())
                  for m in MONTH_COLS}
    mech_total["Tot"] = sum(mech_total[m] for m in MONTH_COLS)
    weld_total = summary["welder_total"]
    elec_total = summary["electric_total"]

    level_totals = {
        m: mech_total.get(m, 0) + weld_total.get(m, 0) + elec_total.get(m, 0)
        for m in MONTH_COLS
    }
    grand_total = sum(level_totals.values())
    cost_total = cost["Total"]["Tot"]
    head_counts = {"Mechanic": mech_total, "Electric": elec_total, "Welder": weld_total}

    st.markdown(
        theme.legend_strip(
            "Role colours", ROLE_LEGEND + [("M1 senior → M3 junior", theme.LEVEL_SHADES["M2"])]
        ),
        unsafe_allow_html=True,
    )

    # ---------------- KPI ----------------
    k = st.columns(5, gap="small")
    with k[0]:
        st.markdown(
            theme.kpi_card("Total MPP", num(grand_total), "",
                           accent=theme.BRAND["navy"], emoji="👷"),
            unsafe_allow_html=True,
        )
    with k[1]:
        share = mech_total["Tot"] / grand_total * 100 if grand_total else 0
        st.markdown(
            theme.kpi_card("Mechanic", num(mech_total["Tot"]),
                           f"<b>{num(share, 0)}%</b> of MPP", role="Mechanic"),
            unsafe_allow_html=True,
        )
    with k[2]:
        st.markdown(
            theme.kpi_card("Electrician", num(elec_total["Tot"]),
                           f"M1 <b>{num(elec_total['M1'])}</b> · M2 <b>{num(elec_total['M2'])}</b>",
                           role="Electric"),
            unsafe_allow_html=True,
        )
    with k[3]:
        st.markdown(
            theme.kpi_card("Welder", num(weld_total["Tot"]),
                           f"M1 <b>{num(weld_total['M1'])}</b> · M2 <b>{num(weld_total['M2'])}</b>",
                           role="Welder"),
            unsafe_allow_html=True,
        )
    with k[4]:
        per_fte = cost_total / grand_total if grand_total else 0
        st.markdown(
            theme.kpi_card("Cost per month", rp_short(cost_total),
                           f"<b>{rp_short(per_fte)}</b> per MPP",
                           accent=theme.BRAND["orange_deep"], emoji="💰", value_size=21),
            unsafe_allow_html=True,
        )

    st.write("")

    # ------- row 1: one merged section chart + level composition -------
    # Baris ini dulu dua chart terpisah (total per section, lalu persebaran
    # M1-M3 di bawahnya). Stacked chart sudah mencetak total di atas tiap
    # batang, jadi keduanya cukup jadi satu chart.
    r1a, r1b = st.columns([1.6, 1], gap="small")
    with r1a:
        with theme.card("total_section", "MPP & level split per section",
                        f"{len(summary['mechanic_by_category'])} unit categories "
                        f"+ 2 company-wide roles · bar height = section MPP",
                        accent=theme.LEVEL_SHADES["M2"]):
            st.plotly_chart(
                charts.level_stack_by_section(
                    summary["mechanic_by_category"], weld_total, elec_total, height=300),
                width="stretch", config={"displayModeBar": False},
            )
            st.markdown(theme.legend_html(LEVEL_LEGEND), unsafe_allow_html=True)
    with r1b:
        with theme.card("level_donut", "M1 – M3 composition", "all roles",
                        accent=theme.LEVEL_SHADES["M1"]):
            st.plotly_chart(charts.level_donut(level_totals, height=311), width="stretch",
                            config={"displayModeBar": False})

    # ------- row 2: monthly cost + yearly cost, identical shape -------
    c1, c2 = st.columns(2, gap="small")
    with c1:
        render_cost_block("cost_month", "Cost per month", "colour = share per role",
                          cost, head_counts, grand_total, 1, "per MPP / month")
    with c2:
        render_cost_block("cost_year", "Cost per year", f"monthly × {MONTHS_PER_YEAR}",
                          cost, head_counts, grand_total, MONTHS_PER_YEAR, "per MPP / year")

    return {
        "mech_total": mech_total, "weld_total": weld_total, "elec_total": elec_total,
        "grand_total": grand_total, "cost_total": cost_total,
    }


def render_summary_tab(summary, mech_total, weld_total, elec_total, cost):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**MPP per category & role**")
        rows = [
            [cat, num(v["M1"]), num(v["M2"]), num(v["M3"]), num(v["Tot"])]
            for cat, v in summary["mechanic_by_category"].items()
        ]
        rows.append(["Electrician", num(elec_total["M1"]), num(elec_total["M2"]),
                     num(elec_total.get("M3", 0)), num(elec_total["Tot"])])
        rows.append(["Welder", num(weld_total["M1"]), num(weld_total["M2"]),
                     num(weld_total.get("M3", 0)), num(weld_total["Tot"])])
        grand = {
            m: mech_total.get(m, 0) + weld_total.get(m, 0) + elec_total.get(m, 0)
            for m in ("M1", "M2", "M3", "Tot")
        }
        if rows:
            st.markdown(
                theme.table_html(
                    ["Category / role", "M1", "M2", "M3", "Total"], rows,
                    total_row=["TOTAL", num(grand["M1"]), num(grand["M2"]),
                               num(grand["M3"]), num(grand["Tot"])],
                    total_col=4,
                ),
                unsafe_allow_html=True,
            )
        else:
            st.info("No data for this scope.")
    with c2:
        st.markdown("**Cost per level**")
        rows = []
        for role in ("Mechanic", "Electric", "Welder"):
            v = cost.get(role, {})
            rows.append([
                theme.ROLE_LABEL[role], rp_short(v.get("M1", 0)),
                rp_short(v.get("M2", 0)), rp_short(v.get("M3", 0)), rp_short(v.get("Tot", 0)),
            ])
        t = cost.get("Total", {})
        st.markdown(
            theme.table_html(
                ["Role", "M1", "M2", "M3", "Total"], rows,
                total_row=["TOTAL", rp_short(t.get("M1", 0)), rp_short(t.get("M2", 0)),
                           rp_short(t.get("M3", 0)), rp_short(t.get("Tot", 0))],
                total_col=4,
            ),
            unsafe_allow_html=True,
        )


def render_unit_tab(site: str):
    df = st.session_state.working_units_df
    total_rows = len(df)
    total_pages = max(1, math.ceil(total_rows / PAGE_SIZE))
    st.session_state.page_num = min(st.session_state.get("page_num", 0), total_pages - 1)
    start = st.session_state.page_num * PAGE_SIZE
    page_df = df.iloc[start:start + PAGE_SIZE].reset_index(drop=True)

    head, lock = st.columns([6, 1.2])
    with head:
        st.caption(
            f"{total_rows} unit rows for site **{site}**, pulled from Sheet9 — "
            f"page {st.session_state.page_num + 1} of {total_pages}."
        )
    with lock:
        with st.popover("Edit", width="stretch"):
            if st.session_state.get("edit_unlocked"):
                st.success("Edit mode active for this session.")
                st.caption("Changes are not written back to the spreadsheet and are lost on reload.")
                if st.button("Lock again", width="stretch"):
                    st.session_state.edit_unlocked = False
                    st.rerun()
                if st.button("Reset to source data", width="stretch"):
                    st.session_state.working_units_df = units_to_df(get_units().get(site, []))
                    st.rerun()
            else:
                pwd = st.text_input("Password", type="password", key="edit_pwd_input")
                if st.button("Unlock edit mode", width="stretch"):
                    if pwd == UNIT_EDIT_PASSWORD:
                        st.session_state.edit_unlocked = True
                        st.rerun()
                    else:
                        st.error("Wrong password.")

    if st.session_state.get("edit_unlocked"):
        edited = st.data_editor(
            page_df, num_rows="fixed", width="stretch",
            key=f"editor_{site}_{st.session_state.page_num}",
            column_config={
                "Jumlah Unit": st.column_config.NumberColumn("Unit Count", min_value=0, step=1),
                "PA": st.column_config.NumberColumn("PA (%)", min_value=1, max_value=100, step=1),
            },
        )
        df.iloc[start:start + PAGE_SIZE] = edited.values
        st.session_state.working_units_df = df
    else:
        st.dataframe(page_df, width="stretch", hide_index=True)

    p1, p2, _ = st.columns([1, 1, 5])
    with p1:
        if st.button("← Previous", disabled=st.session_state.page_num <= 0,
                     width="stretch", key="bc_prev"):
            st.session_state.page_num -= 1
            st.rerun()
    with p2:
        if st.button("Next →", disabled=st.session_state.page_num >= total_pages - 1,
                     width="stretch", key="bc_next"):
            st.session_state.page_num += 1
            st.rerun()


# ===========================================================================
# Mode: Kalkulator
# ===========================================================================
def render_calculator_mode(backend):
    st.markdown(
        theme.header_band(
            "FTE Calculator — Single Unit Type",
            "Quick manpower estimate for one equipment type",
            chips=["Mode <b>Calculator</b>"],
        ),
        unsafe_allow_html=True,
    )

    sites = backend.sites or []
    sub_cats = backend.sub_categories or list(backend.load_factor.index)

    # ---------------- Parameter: satu kartu MELEBAR penuh ----------------
    # Empat input utama berjajar dalam satu baris, competency factor di baris
    # sendiri (butuh lebar untuk track slider), lalu catatan jarak + tombol.
    # Hasil perhitungan menyusul DI BAWAH kartu ini, bukan di sampingnya.
    with theme.card("calc_param", "Parameters", "all fields required"):
        p1, p2, p3, p4 = st.columns(4, gap="medium")
        with p1:
            site = st.selectbox("Site", options=sites, index=None,
                                placeholder="Select site…", key="calc1_site")
        with p2:
            sub_category = st.selectbox("Equipment type", options=sub_cats, index=None,
                                        placeholder="Select sub category…", key="calc1_subcat")
        with p3:
            jumlah_unit = st.number_input("Unit count", min_value=0.0, value=1.0,
                                          step=1.0, key="calc1_jml")
        with p4:
            pa = st.number_input("PA target (%)", min_value=1.0, max_value=100.0,
                                 value=85.0, step=1.0, key="calc1_pa")

        cf = st.slider("Competency factor", min_value=0.1, max_value=1.0,
                       value=0.6, step=0.01, key="calc1_cf")

        jarak_km = backend.jarak.get(site) if site else None
        n1, n2 = st.columns([2.6, 1], gap="medium")
        with n1:
            if site and jarak_km is None:
                st.markdown(
                    theme.inline_note(
                        f"No distance on record for site <b>{site}</b>. "
                        f"The calculation cannot run until that value exists.",
                        warn=True,
                    ),
                    unsafe_allow_html=True,
                )
            elif jarak_km is not None:
                st.markdown(
                    theme.inline_note(
                        f"Work area distance for site {site}: <b>{num(jarak_km, 2)} km</b>"
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    theme.inline_note("Select a site and equipment type to enable the calculation."),
                    unsafe_allow_html=True,
                )
        with n2:
            with st.container(key="calc_go"):
                compute_clicked = st.button(
                    "Calculate FTE", width="stretch", key="calc1_button",
                    disabled=not (site and sub_category and jarak_km is not None),
                )

    if compute_clicked:
        try:
            orig_sc = backend.original_sub_name(sub_category) or sub_category
            st.session_state.calc1_result = compute_fte(
                FTEInput(
                    site=site, competency_factor=cf, jarak_km=jarak_km,
                    sub_category=orig_sc, jenis_unit="",
                    pa_percent=pa, populasi=jumlah_unit,
                ),
                backend,
            )
        except CalculationError as exc:
            st.error(f"Calculation failed: {exc}")
            st.session_state.calc1_result = None
        st.rerun()

    result = st.session_state.get("calc1_result")

    st.write("")

    if not result:
        st.markdown(
            theme.empty_state(
                "No result yet",
                "Fill in the parameters above, then press Calculate FTE.",
                "🧮",
            ),
            unsafe_allow_html=True,
        )
        return

    # ---------------- Hasil: tiga panel berjajar di bawah parameter ----------
    tot = result["fte"]["Total"]
    cost_lv = result["cost"]["Total"]

    r1, r2, r3 = st.columns([1, 1.12, 1.24], gap="medium")

    with r1:
        with theme.card("calc_donut", "Split per role", "share of each role",
                        accent=theme.ROLE_COLORS["Mechanic"]):
            st.plotly_chart(
                charts.role_donut(result["fte"], height=177, show_legend=False),
                width="stretch", config={"displayModeBar": False},
            )
            # Legend bawaan Plotly hanya menampilkan nama role. Diganti legend
            # sendiri supaya FTE dan persentase share-nya ikut terbaca.
            grand = sum(result["fte"][r]["Tot"] for r in ("Mechanic", "Electric", "Welder")) or 1
            st.markdown(
                theme.donut_legend([
                    (theme.ROLE_COLORS[r], theme.ROLE_LABEL[r],
                     f"{num(result['fte'][r]['Tot'])} FTE",
                     f"{num(result['fte'][r]['Tot'] / grand * 100, 1)}%")
                    for r in ("Mechanic", "Electric", "Welder")
                ]),
                unsafe_allow_html=True,
            )

    with r2:
        # Qty & cost di readout sengaja TOTAL lintas role (mekanik +
        # electrician + welder digabung) — rincian per role sudah ada di panel
        # sebelahnya, jadi readout cukup menjawab "berapa orang dan berapa
        # biayanya di tiap level".
        with theme.card("calc_out", "Calculator result", "total across all roles",
                        accent=theme.BRAND["orange_deep"]):
            st.markdown(
                theme.calc_readout(
                    total_fte=num(tot["Tot"]),
                    levels=[
                        (m, theme.LEVEL_NOTE[m], num(tot[m]), rp(cost_lv[m]))
                        for m in MONTH_COLS
                    ],
                    grand_label="Estimated cost<br/>per month",
                    grand_value=rp(cost_lv["Tot"]),
                ),
                unsafe_allow_html=True,
            )

    with r3:
        with theme.card("calc_table", "Breakdown per role", "FTE per level"):
            rows, sums = [], {"M1": 0.0, "M2": 0.0, "M3": 0.0, "Tot": 0.0}
            for role in ("Mechanic", "Electric", "Welder"):
                v = result["fte"][role]
                rows.append([theme.ROLE_LABEL[role], num(v["M1"]), num(v["M2"]),
                             num(v["M3"]), num(v["Tot"])])
                for kk in sums:
                    sums[kk] += v.get(kk, 0)
            st.markdown(
                theme.table_html(
                    ["Role", "M1", "M2", "M3", "Total"], rows,
                    total_row=["TOTAL", num(sums["M1"]), num(sums["M2"]),
                               num(sums["M3"]), num(sums["Tot"])],
                    total_col=4,
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                theme.stat_list([
                    (f"Cost · {theme.ROLE_LABEL[role]}", rp(result["cost"][role]["Tot"]))
                    for role in ("Mechanic", "Electric", "Welder")
                ]),
                unsafe_allow_html=True,
            )


# ===========================================================================
# Mode: Basecase All Unit  /  Summary
# ===========================================================================
def render_basecase_sidebar(backend):
    st.sidebar.markdown('<div class="dh-side-label">Site parameters</div>',
                        unsafe_allow_html=True)
    site = st.sidebar.selectbox("Site", options=(backend.sites or []), index=None,
                                placeholder="Select site…", key="bc_site")
    cf = st.sidebar.slider("Competency factor", min_value=0.1, max_value=1.0,
                           value=0.6, step=0.01, key="bc_cf")

    c1, c2 = st.sidebar.columns(2)
    with c1:
        with st.container(key="sb_refresh"):
            refresh = st.button("Reload", width="stretch", key="sb_refresh_btn")
    with c2:
        with st.container(key="sb_compute"):
            compute = st.button("Calculate", width="stretch",
                                disabled=site is None, key="sb_compute_btn")

    return site, cf, refresh, compute


def render_summary_sidebar():
    st.sidebar.markdown('<div class="dh-side-label">Summary parameters</div>',
                        unsafe_allow_html=True)
    cf = st.sidebar.slider("Competency factor", min_value=0.1, max_value=1.0,
                           value=0.6, step=0.01, key="sm_cf")
    c1, c2 = st.sidebar.columns(2)
    with c1:
        with st.container(key="sm_refresh"):
            refresh = st.button("Reload", width="stretch", key="sm_refresh_btn")
    with c2:
        with st.container(key="sm_compute"):
            compute = st.button("Calculate", width="stretch", key="sm_compute_btn")
    return cf, refresh, compute


def _clear_caches():
    get_backend.clear()
    get_units.clear()
    get_staff.clear()
    for k in list(st.session_state.keys()):
        if k.startswith("_allsites_"):
            del st.session_state[k]


def render_details_section(tab_specs: list):
    """Collapsed "Details" block — same idea as the parameters panel above.

    These used to be permanently visible tabs, which pushed the dashboard
    itself off the first screen. Now nothing renders until it is opened.
    """
    with st.container(key="detail_panel"):
        with st.expander("Details", expanded=False):
            tabs = st.tabs([label for label, _fn in tab_specs])
            for tab, (_label, fn) in zip(tabs, tab_specs):
                with tab:
                    fn()


def render_basecase_mode(backend):
    site, cf, refresh, compute_clicked = render_basecase_sidebar(backend)

    if refresh:
        _clear_caches()
        st.rerun()

    if site is None:
        st.markdown(
            theme.header_band(
                "Basecase All Unit",
                "Manpower requirement for every unit within one site",
                chips=["Site <b>not selected</b>"],
            ),
            unsafe_allow_html=True,
        )
        st.session_state.current_site = None
        st.session_state.calc_result = None
        st.markdown(
            theme.empty_state(
                "Pick a site to start",
                "Choose a site and competency factor in the left panel, then press Calculate.",
                "📍",
            ),
            unsafe_allow_html=True,
        )
        return

    try:
        units_all = get_units()
    except BackendDataError as exc:
        st.error(f"Unit data (Sheet9) failed to load: {exc}")
        return

    if st.session_state.get("current_site") != site:
        st.session_state.current_site = site
        st.session_state.working_units_df = units_to_df(units_all.get(site, []))
        st.session_state.page_num = 0
        st.session_state.calc_result = None
        st.session_state.edit_unlocked = False

    if compute_clicked:
        try:
            summary = compute_site_summary(
                site, df_to_units(st.session_state.working_units_df), backend, cf
            )
            staff_res = compute_staff_fte(
                site, summary["mechanic_by_category"], summary["welder_total"],
                summary["electric_total"], get_staff(),
            )
            cost = compute_site_cost(
                summary["mechanic_by_category"], summary["welder_total"],
                summary["electric_total"],
            )
            st.session_state.calc_result = {"summary": summary, "staff": staff_res, "cost": cost}
        except CalculationError as exc:
            st.error(f"Calculation failed: {exc}")
            st.session_state.calc_result = None
        except BackendDataError as exc:
            st.error(f"Staff data failed to load: {exc}")
            st.session_state.calc_result = None

    result = st.session_state.get("calc_result")

    jarak = backend.jarak.get(site)
    chips = [f"Site <b>{site}</b>", f"Competency factor <b>{num(cf, 2)}</b>"]
    if jarak is not None:
        chips.append(f"Distance <b>{num(jarak, 1)} km</b>")
    st.markdown(
        theme.header_band(
            f"Basecase All Unit — {site}",
            "Manpower requirement for every unit within one site",
            chips=chips,
        ),
        unsafe_allow_html=True,
    )

    if not result:
        st.markdown(
            theme.empty_state(
                f"Site {site} is ready",
                f"{len(st.session_state.working_units_df)} unit rows loaded. "
                f"Press Calculate in the left panel to build the dashboard.",
                "▶️",
            ),
            unsafe_allow_html=True,
        )
        with st.expander(f"View unit data for site {site}"):
            render_unit_tab(site)
        return

    summary, staff_res, cost = result["summary"], result["staff"], result["cost"]
    unit_qty = sum(d["jumlah_unit"] for d in summary["detail_rows"])

    render_formula_panel(
        formula_items(backend, unit_qty, site=site),
        summary["detail_rows"], with_site=False, skipped=summary["skipped_units"],
    )
    totals = render_dashboard_body(summary, cost)
    render_staff_section(staff_res["operational"], staff_res["planner"])

    render_details_section([
        ("MPP summary", lambda: render_summary_tab(
            summary, totals["mech_total"], totals["weld_total"],
            totals["elec_total"], cost)),
        (f"Unit data ({len(st.session_state.working_units_df)})",
         lambda: render_unit_tab(site)),
    ])


def render_summary_mode(backend):
    cf, refresh, compute_clicked = render_summary_sidebar()

    if refresh:
        _clear_caches()
        st.rerun()

    try:
        units_all = get_units()
    except BackendDataError as exc:
        st.error(f"Unit data (Sheet9) failed to load: {exc}")
        return

    if compute_clicked:
        st.session_state.pop(f"_allsites_{cf:.2f}", None)
        st.session_state.summary_ready = True

    st.markdown(
        theme.header_band(
            "Summary — All Sites",
            "Every unit across every site, rolled up into one view",
            chips=[f"Competency factor <b>{num(cf, 2)}</b>",
                   f"Sites <b>{len(backend.sites or [])}</b>"],
        ),
        unsafe_allow_html=True,
    )

    if not st.session_state.get("summary_ready"):
        st.markdown(
            theme.empty_state(
                "Ready to aggregate",
                "Set the competency factor in the left panel, then press Calculate. "
                "Every site is computed individually and the results are summed.",
                "🗺️",
            ),
            unsafe_allow_html=True,
        )
        return

    with st.spinner("Calculating every site…"):
        agg = aggregate_all_sites(backend, units_all, cf)

    if not agg:
        st.markdown(
            theme.empty_state(
                "Nothing to aggregate",
                "No site produced a usable result. Check the unit data on Sheet9.",
                "⚠️",
            ),
            unsafe_allow_html=True,
        )
        return

    summary, cost = agg["summary"], agg["cost"]
    unit_qty = sum(d["jumlah_unit"] for d in summary["detail_rows"])

    render_formula_panel(
        formula_items(backend, unit_qty),
        summary["detail_rows"], with_site=True, skipped=summary["skipped_units"],
    )
    totals = render_dashboard_body(summary, cost)
    render_staff_section(agg["operational"], agg["planner"])

    def _per_site_table():
        rows = [[s, rp_short(v), rp_short(v * MONTHS_PER_YEAR)]
                for s, v in sorted(agg["per_site_cost"].items(),
                                   key=lambda kv: kv[1], reverse=True)]
        total_m = sum(agg["per_site_cost"].values())
        st.markdown(
            theme.table_html(
                ["Site", "Cost / month", "Cost / year"], rows,
                total_row=["TOTAL", rp_short(total_m),
                           rp_short(total_m * MONTHS_PER_YEAR)],
                total_col=2,
            ),
            unsafe_allow_html=True,
        )

    render_details_section([
        ("MPP summary", lambda: render_summary_tab(
            summary, totals["mech_total"], totals["weld_total"],
            totals["elec_total"], cost)),
        ("Cost per site", _per_site_table),
    ])


# ===========================================================================
def main():
    try:
        backend = get_backend()
    except BackendDataError as exc:
        st.markdown(
            theme.header_band("FTE Calculator", "PT Darma Henwa"),
            unsafe_allow_html=True,
        )
        st.error(f"BACKEND data failed to load: {exc}")
        return

    st.session_state.setdefault("app_mode", "calculator")

    with st.sidebar:
        logo = theme.image_uri("logo_putih (2).png")
        mark = f'<div class="mark"><img src="{logo}" alt=""/></div>' if logo else '<div class="mark"></div>'
        st.markdown(
            f'<div class="dh-side-brand">{mark}'
            f'<div><div class="title">FTE Calculator</div>'
            f'<div class="subtitle">PT Darma Henwa</div></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="dh-side-label">Mode</div>', unsafe_allow_html=True)
        for key, label, container in (
            ("calculator", "Calculator", "nav_calc"),
            ("multisite", "Basecase All Unit", "nav_basecase"),
            ("summary", "Summary", "nav_summary"),
        ):
            with st.container(key=container):
                if st.button(label, width="stretch", key=f"btn_mode_{key}",
                             type="primary" if st.session_state.app_mode == key else "secondary"):
                    st.session_state.app_mode = key
                    st.rerun()

    if st.session_state.app_mode == "calculator":
        render_calculator_mode(backend)
    elif st.session_state.app_mode == "summary":
        render_summary_mode(backend)
    else:
        render_basecase_mode(backend)

    if DEMO:
        st.caption("Demo mode: bundled sample data, not Google Sheets. "
                   "Run without FTE_DEMO=1 for live data.")


if __name__ == "__main__":
    main()
