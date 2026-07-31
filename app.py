# app.py (v6 — "Looker light": header band orange, kartu putih, 1 layar utama)
"""
FTE Calculator — PT Dharma Henwa

Dua mode (dipilih dari nav di sidebar):

*   **Kalkulator** — hitung 1 jenis unit, hasil langsung tampil di readout.
*   **Basecase**   — hitung seluruh unit dalam 1 Site dari Sheet9, ditampilkan
    sebagai dashboard.

Susunan layar mode Basecase (mengikuti permintaan: total dulu, komposisi di
sampingnya, lalu rincian section dengan cost di sampingnya):

    ┌──────────────────────── header band (orange, logo putih) ─────────────┐
    ├─ legenda role ───────────────────────────────────────────────────────┤
    ├─ KPI: Total FTE │ Mekanik │ Electrician │ Welder │ Cost/bulan ───────┤
    ├─ Total FTE per Section (bar) ─────────────┬─ Komposisi M1–M3 (donut) ┤
    ├─ Persebaran M1–M3 per Section (stack) ────┬─ Cost (speedometer) ─────┤
    └─ Tab: Ringkasan │ Foreman & SPV │ Planner │ Data Unit │ Detail ──────┘

Baris KPI dan dua baris chart dirancang muat dalam satu layar tanpa scroll di
laptop 1920×1080; tab rincian di bawahnya memang perlu discroll sedikit.

Logika perhitungan (`calculator.py`, `data_loader.py`, `config.py`) tidak
diubah sama sekali — file ini murni lapisan tampilan.
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
from config import MONTH_COLS, UNIT_EDIT_PASSWORD
from data_loader import (
    BackendDataError,
    UnitRow,
    load_backend_data,
    load_staff_data,
    load_unit_data,
)

st.set_page_config(
    page_title="FTE Calculator — PT Dharma Henwa",
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
@st.cache_data(ttl=600, show_spinner="Mengambil data referensi BACKEND…")
def get_backend():
    if DEMO:
        import demo_data
        return demo_data.backend()
    return load_backend_data()


@st.cache_data(ttl=600, show_spinner="Mengambil data unit per site…")
def get_units():
    if DEMO:
        import demo_data
        return demo_data.units()
    return load_unit_data()


@st.cache_data(ttl=600, show_spinner="Mengambil data Hasil Staff…")
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


def site_cost_scale(backend, units_all, competency_factor: float) -> dict:
    """Cost/bulan tiap site — dipakai sebagai skala gauge (0 → site tertinggi).

    Dihitung sekali lalu disimpan di session_state per nilai competency
    factor, karena gauge-nya memakai skala relatif antar-site sehingga
    angka pembandingnya harus konsisten selama parameter tidak berubah.
    """
    key = f"_cost_scale_{competency_factor:.2f}"
    if key in st.session_state:
        return st.session_state[key]

    per_site = {}
    for s in (backend.sites or []):
        rows = units_all.get(s) or []
        if not rows:
            continue
        try:
            summ = compute_site_summary(s, rows, backend, competency_factor)
            c = compute_site_cost(
                summ["mechanic_by_category"], summ["welder_total"], summ["electric_total"]
            )
            total = c["Total"]["Tot"]
            if total > 0:
                per_site[s] = total
        except (CalculationError, BackendDataError, KeyError, ValueError):
            continue

    st.session_state[key] = per_site
    return per_site


# ---------------------------------------------------------------------------
# Blok tampilan yang dipakai bersama
# ---------------------------------------------------------------------------
ROLE_LEGEND = [
    ("Mekanik", theme.ROLE_COLORS["Mechanic"]),
    ("Electrician", theme.ROLE_COLORS["Electric"]),
    ("Welder", theme.ROLE_COLORS["Welder"]),
]
LEVEL_LEGEND = [
    ("M1 · Senior", theme.LEVEL_SHADES["M1"]),
    ("M2 · Madya", theme.LEVEL_SHADES["M2"]),
    ("M3 · Junior", theme.LEVEL_SHADES["M3"]),
]


def render_summary_tab(summary, mech_total, weld_total, elec_total, cost):
    st.markdown("**Mekanik per kategori unit**")
    if summary["mechanic_by_category"]:
        rows = [
            [cat, num(v["M1"]), num(v["M2"]), num(v["M3"]), num(v["Tot"])]
            for cat, v in summary["mechanic_by_category"].items()
        ]
        total_row = [
            "TOTAL", num(mech_total["M1"]), num(mech_total["M2"]),
            num(mech_total["M3"]), num(mech_total["Tot"]),
        ]
        st.markdown(
            theme.table_html(["Kategori", "M1", "M2", "M3", "Total"], rows,
                             total_row=total_row, total_col=4),
            unsafe_allow_html=True,
        )
    else:
        st.info("Tidak ada data mekanik untuk site ini.")

    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Welder & Electrician (company-wide)**")
        rows = [
            ["Electrician", num(elec_total["M1"]), num(elec_total["M2"]), num(elec_total["Tot"])],
            ["Welder", num(weld_total["M1"]), num(weld_total["M2"]), num(weld_total["Tot"])],
        ]
        st.markdown(
            theme.table_html(["Role", "M1", "M2", "Total"], rows, total_col=3),
            unsafe_allow_html=True,
        )
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


def render_operational_tab(operational):
    if not operational:
        st.info(
            "Belum ada data Foreman/Supervisor untuk site ini. "
            "Lengkapi kolom Area Kerja, Beban Admin, dan Jam Efektif di sheet "
            "**Hasil Staff** untuk site ini."
        )
        return
    rows, f_sum, s_sum = [], 0, 0
    for r in operational:
        tot = r["foreman"] + r["supervisor"]
        rows.append([r["posisi"], num(r["jumlah_mekanik"]), num(r["foreman"]),
                     num(r["supervisor"]), num(tot)])
        f_sum += r["foreman"]
        s_sum += r["supervisor"]
    st.markdown(
        theme.table_html(
            ["Posisi", "Mekanik M1", "Foreman", "Supervisor", "Total"], rows,
            total_row=["TOTAL", "–", num(f_sum), num(s_sum), num(f_sum + s_sum)],
            total_col=4,
        ),
        unsafe_allow_html=True,
    )


def render_planner_tab(planner):
    if not planner:
        st.info("Belum ada data FTE Planner untuk site ini.")
        return
    rows = [[r["posisi"], num(r["fte"])] for r in planner]
    st.markdown(
        theme.table_html(
            ["Posisi", "FTE"], rows,
            total_row=["TOTAL", num(sum(r["fte"] for r in planner))], total_col=1,
        ),
        unsafe_allow_html=True,
    )


def render_detail_tab(summary):
    rows = []
    for d in summary["detail_rows"]:
        raw = d["raw"]
        rows.append({
            "Category": d["category"],
            "Jenis Unit": d["jenis_unit"],
            "Jumlah Unit": d["jumlah_unit"],
            "PA": d["pa"],
            "Mech M1": round(raw["Mechanic"]["M1"], 3),
            "Mech M2": round(raw["Mechanic"]["M2"], 3),
            "Mech M3": round(raw["Mechanic"]["M3"], 3),
            "Elec M1": round(raw["Electric"]["M1"], 3),
            "Elec M2": round(raw["Electric"]["M2"], 3),
            "Weld M1": round(raw["Welder"]["M1"], 3),
            "Weld M2": round(raw["Welder"]["M2"], 3),
        })
    st.caption("Nilai mentah per baris unit, sebelum pembulatan di level total.")
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=340)
    else:
        st.info("Tidak ada baris unit yang berhasil dihitung.")

    if summary["skipped_units"]:
        with st.expander(
            f"{len(summary['skipped_units'])} baris unit dilewati — Sub Category "
            f"belum terdaftar di BACKEND"
        ):
            st.dataframe(
                pd.DataFrame(summary["skipped_units"],
                             columns=["Category", "Jenis Unit", "Alasan"]),
                width="stretch", hide_index=True,
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
            f"{total_rows} baris unit untuk site **{site}**, otomatis dari Sheet9 — "
            f"halaman {st.session_state.page_num + 1} dari {total_pages}."
        )
    with lock:
        with st.popover("Edit", width="stretch"):
            if st.session_state.get("edit_unlocked"):
                st.success("Mode edit aktif untuk sesi ini.")
                st.caption("Perubahan tidak tersimpan ke spreadsheet dan hilang saat halaman dimuat ulang.")
                if st.button("Kunci kembali", width="stretch"):
                    st.session_state.edit_unlocked = False
                    st.rerun()
                if st.button("Kembalikan ke data asli", width="stretch"):
                    st.session_state.working_units_df = units_to_df(get_units().get(site, []))
                    st.rerun()
            else:
                pwd = st.text_input("Password", type="password", key="edit_pwd_input")
                if st.button("Buka mode edit", width="stretch"):
                    if pwd == UNIT_EDIT_PASSWORD:
                        st.session_state.edit_unlocked = True
                        st.rerun()
                    else:
                        st.error("Password tidak cocok.")

    if st.session_state.get("edit_unlocked"):
        edited = st.data_editor(
            page_df, num_rows="fixed", width="stretch",
            key=f"editor_{site}_{st.session_state.page_num}",
            column_config={
                "Jumlah Unit": st.column_config.NumberColumn("Jumlah Unit", min_value=0, step=1),
                "PA": st.column_config.NumberColumn("PA (%)", min_value=1, max_value=100, step=1),
            },
        )
        df.iloc[start:start + PAGE_SIZE] = edited.values
        st.session_state.working_units_df = df
    else:
        st.dataframe(page_df, width="stretch", hide_index=True)

    p1, p2, _ = st.columns([1, 1, 5])
    with p1:
        if st.button("← Sebelumnya", disabled=st.session_state.page_num <= 0,
                     width="stretch", key="bc_prev"):
            st.session_state.page_num -= 1
            st.rerun()
    with p2:
        if st.button("Berikutnya →", disabled=st.session_state.page_num >= total_pages - 1,
                     width="stretch", key="bc_next"):
            st.session_state.page_num += 1
            st.rerun()


# ===========================================================================
# Mode: Kalkulator
# ===========================================================================
def render_calculator_mode(backend):
    st.markdown(
        theme.header_band(
            "Kalkulator FTE — Satu Jenis Unit",
            "Hitung cepat kebutuhan tenaga kerja untuk satu jenis equipment",
            chips=["Mode <b>Kalkulator</b>"],
        ),
        unsafe_allow_html=True,
    )

    sites = backend.sites or []
    sub_cats = backend.sub_categories or list(backend.load_factor.index)

    left, right = st.columns([1.25, 1], gap="medium")

    with left:
        with theme.card("calc_param", "Parameter", "semua kolom wajib kecuali Jenis Unit"):
            c1, c2 = st.columns(2)
            with c1:
                site = st.selectbox("Site", options=sites, index=None,
                                    placeholder="Pilih site…", key="calc1_site")
            with c2:
                sub_category = st.selectbox("Jenis equipment", options=sub_cats, index=None,
                                            placeholder="Pilih sub category…", key="calc1_subcat")

            jenis_options = backend.units_for(sub_category) if sub_category else []
            c3, c4 = st.columns(2)
            with c3:
                if jenis_options:
                    jenis_unit = st.selectbox("Jenis unit", options=jenis_options, key="calc1_jenis")
                else:
                    jenis_unit = st.text_input("Jenis unit", value="", key="calc1_jenis_text",
                                               placeholder="opsional")
            with c4:
                jumlah_unit = st.number_input("Jumlah unit", min_value=0.0, value=1.0,
                                              step=1.0, key="calc1_jml")

            c5, c6 = st.columns(2)
            with c5:
                pa = st.number_input("Target PA (%)", min_value=1.0, max_value=100.0,
                                     value=85.0, step=1.0, key="calc1_pa")
            with c6:
                cf = st.slider("Competency factor", min_value=0.1, max_value=1.0,
                               value=0.6, step=0.01, key="calc1_cf")

            jarak_km = backend.jarak.get(site) if site else None
            if site and jarak_km is None:
                st.warning(
                    f"Jarak untuk site {site} belum ada di BACKEND seksi 'Jarak'. "
                    f"Perhitungan tidak bisa dijalankan sampai data itu diisi."
                )
            elif jarak_km is not None:
                st.caption(f"Jarak area kerja site {site}: **{num(jarak_km, 2)} km** (otomatis dari BACKEND).")

            with st.container(key="calc_go"):
                compute_clicked = st.button(
                    "Hitung FTE", width="stretch", key="calc1_button",
                    disabled=not (site and sub_category and jarak_km is not None),
                )

    if compute_clicked:
        try:
            orig_sc = backend.original_sub_name(sub_category) or sub_category
            st.session_state.calc1_result = compute_fte(
                FTEInput(
                    site=site, competency_factor=cf, jarak_km=jarak_km,
                    sub_category=orig_sc, jenis_unit=jenis_unit or "",
                    pa_percent=pa, populasi=jumlah_unit,
                ),
                backend,
            )
        except CalculationError as exc:
            st.error(f"Perhitungan gagal: {exc}")
            st.session_state.calc1_result = None
        st.rerun()

    result = st.session_state.get("calc1_result")

    with right:
        if result:
            tot = result["fte"]["Total"]
            cost_tot = result["cost"]["Total"]["Tot"]
            st.markdown(
                '<div class="dh-readout">'
                '<div class="label">Total FTE</div>'
                f'<div class="big">{num(tot["Tot"])}</div>'
                '<div class="lv">'
                f'<span>M1 <b>{num(tot["M1"])}</b></span>'
                f'<span>M2 <b>{num(tot["M2"])}</b></span>'
                f'<span>M3 <b>{num(tot["M3"])}</b></span>'
                '</div>'
                f'<div class="cost">Estimasi cost per bulan <b>{rp(cost_tot)}</b></div>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.write("")
            with theme.card("calc_donut", "Sebaran per role", accent=theme.ROLE_COLORS["Mechanic"]):
                st.plotly_chart(charts.role_donut(result["fte"]), width="stretch",
                                config={"displayModeBar": False})
        else:
            st.markdown(
                theme.empty_state(
                    "Belum ada hasil",
                    "Lengkapi parameter di sebelah kiri, lalu tekan Hitung FTE.",
                    "🧮",
                ),
                unsafe_allow_html=True,
            )

    if result:
        with theme.card("calc_table", "Rincian per role"):
            rows, sums = [], {"M1": 0.0, "M2": 0.0, "M3": 0.0, "Tot": 0.0}
            for role in ("Mechanic", "Electric", "Welder"):
                v = result["fte"][role]
                rows.append([theme.ROLE_LABEL[role], num(v["M1"]), num(v["M2"]),
                             num(v["M3"]), num(v["Tot"])])
                for k in sums:
                    sums[k] += v.get(k, 0)
            st.markdown(
                theme.table_html(
                    ["Role", "M1", "M2", "M3", "Total"], rows,
                    total_row=["TOTAL", num(sums["M1"]), num(sums["M2"]),
                               num(sums["M3"]), num(sums["Tot"])],
                    total_col=4,
                ),
                unsafe_allow_html=True,
            )
            with st.expander("Nilai intermediate (H / I / J, load factor, RACI)"):
                st.json(result.get("intermediate", {}))


# ===========================================================================
# Mode: Basecase
# ===========================================================================
def render_basecase_sidebar(backend):
    st.sidebar.markdown('<div class="dh-side-label">Parameter site</div>', unsafe_allow_html=True)
    site = st.sidebar.selectbox("Site", options=(backend.sites or []), index=None,
                               placeholder="Pilih site…", key="bc_site")
    cf = st.sidebar.slider("Competency factor", min_value=0.1, max_value=1.0,
                           value=0.6, step=0.01, key="bc_cf")

    c1, c2 = st.sidebar.columns(2)
    with c1:
        with st.container(key="sb_refresh"):
            refresh = st.button("Muat ulang", width="stretch", key="sb_refresh_btn")
    with c2:
        with st.container(key="sb_compute"):
            compute = st.button("Hitung FTE", width="stretch",
                                disabled=site is None, key="sb_compute_btn")

    with st.sidebar.expander("Data BACKEND yang terbaca"):
        st.write("**Proporsi RACI**", backend.raci)
        st.write("**Split mekanik [M1,M2,M3]**", backend.split_mechanic)
        st.write("**Split welder [M1,M2]**", backend.split_welder)
        st.write("**Split electrician [M1,M2]**", backend.split_electrician)
        st.write("**Ratio shift per site**", backend.ratio_shift)
        st.write("**Lost time per site**", backend.lost_time)
        st.write("**Jarak per site (km)**", backend.jarak)
        st.write("**Urutan kategori**", backend.classification_order)

    return site, cf, refresh, compute


def render_basecase_mode(backend):
    site, cf, refresh, compute_clicked = render_basecase_sidebar(backend)

    if refresh:
        get_backend.clear()
        get_units.clear()
        get_staff.clear()
        for k in list(st.session_state.keys()):
            if k.startswith("_cost_scale_"):
                del st.session_state[k]
        st.rerun()

    if site is None:
        st.markdown(
            theme.header_band(
                "Basecase FTE per Site",
                "Kebutuhan tenaga kerja seluruh unit dalam satu site",
                chips=["Site <b>belum dipilih</b>"],
            ),
            unsafe_allow_html=True,
        )
        st.session_state.current_site = None
        st.session_state.calc_result = None
        st.markdown(
            theme.empty_state(
                "Pilih site untuk mulai",
                "Tentukan site dan competency factor di panel kiri, lalu tekan Hitung FTE.",
                "📍",
            ),
            unsafe_allow_html=True,
        )
        return

    try:
        units_all = get_units()
    except BackendDataError as exc:
        st.error(f"Data unit (Sheet9) gagal dimuat: {exc}")
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
            st.error(f"Perhitungan gagal: {exc}")
            st.session_state.calc_result = None
        except BackendDataError as exc:
            st.error(f"Data Hasil Staff gagal dimuat: {exc}")
            st.session_state.calc_result = None

    result = st.session_state.get("calc_result")

    # ---------------- header ----------------
    jarak = backend.jarak.get(site)
    chips = [f"Site <b>{site}</b>", f"Competency factor <b>{num(cf, 2)}</b>"]
    if jarak is not None:
        chips.append(f"Jarak <b>{num(jarak, 1)} km</b>")
    st.markdown(
        theme.header_band(
            f"Basecase FTE — Site {site}",
            "Kebutuhan tenaga kerja seluruh unit dalam satu site",
            chips=chips,
        ),
        unsafe_allow_html=True,
    )

    if not result:
        st.markdown(
            theme.empty_state(
                f"Site {site} siap dihitung",
                f"{len(st.session_state.working_units_df)} baris unit sudah termuat. "
                f"Tekan Hitung FTE di panel kiri untuk menampilkan dashboard.",
                "▶️",
            ),
            unsafe_allow_html=True,
        )
        with st.expander(f"Lihat data unit site {site}"):
            render_unit_tab(site)
        return

    summary, staff_res, cost = result["summary"], result["staff"], result["cost"]

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

    st.markdown(
        theme.legend_strip(
            "Warna role", ROLE_LEGEND + [("M1 senior → M3 junior", theme.LEVEL_SHADES["M2"])]
        ),
        unsafe_allow_html=True,
    )

    # ---------------- KPI ----------------
    k = st.columns(5, gap="small")
    with k[0]:
        senior = level_totals["M1"] / grand_total * 100 if grand_total else 0
        st.markdown(
            theme.kpi_card(
                "Total FTE", num(grand_total),
                f"Senior (M1) <b>{num(senior, 0)}%</b>",
                accent=theme.BRAND["navy"], emoji="👷",
            ),
            unsafe_allow_html=True,
        )
    with k[1]:
        share = mech_total["Tot"] / grand_total * 100 if grand_total else 0
        st.markdown(
            theme.kpi_card("Mekanik", num(mech_total["Tot"]),
                           f"<b>{num(share, 0)}%</b> dari total FTE", role="Mechanic"),
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
            theme.kpi_card("Cost per bulan", rp_short(cost_total),
                           f"<b>{rp_short(per_fte)}</b> per FTE",
                           accent=theme.BRAND["orange_deep"], emoji="💰", value_size=21),
            unsafe_allow_html=True,
        )

    st.write("")

    # ---------------- baris 1: total + komposisi level ----------------
    r1a, r1b = st.columns([1.6, 1], gap="small")
    with r1a:
        with theme.card("total_section", "Total FTE per Section",
                        f"{len(summary['mechanic_by_category'])} kategori unit + 2 role company-wide"):
            st.plotly_chart(
                charts.total_by_section_bar(summary["mechanic_by_category"], weld_total, elec_total),
                width="stretch", config={"displayModeBar": False},
            )
    with r1b:
        with theme.card("level_donut", "Komposisi M1 – M3", "seluruh role",
                        accent=theme.LEVEL_SHADES["M1"]):
            st.plotly_chart(charts.level_donut(level_totals), width="stretch",
                            config={"displayModeBar": False})

    # ---------------- baris 2: persebaran level + cost ----------------
    r2a, r2b = st.columns([1.6, 1], gap="small")
    with r2a:
        with theme.card("level_stack", "Persebaran M1 – M3 per Section",
                        "batang bertumpuk, tinggi total = FTE section",
                        accent=theme.LEVEL_SHADES["M2"]):
            st.plotly_chart(
                charts.level_stack_by_section(summary["mechanic_by_category"], weld_total, elec_total),
                width="stretch", config={"displayModeBar": False},
            )
            st.markdown(theme.legend_html(LEVEL_LEGEND), unsafe_allow_html=True)
    with r2b:
        scale = site_cost_scale(backend, units_all, cf)
        values = list(scale.values()) or [cost_total]
        scale_max = max(values)
        avg = sum(values) / len(values)
        top_site = max(scale, key=scale.get) if scale else None

        with theme.card("cost_gauge", "Estimasi Cost per Bulan",
                        "skala relatif antar-site", accent=theme.BRAND["orange_deep"]):
            st.plotly_chart(charts.cost_gauge(cost_total, scale_max, avg, top_site),
                            width="stretch", config={"displayModeBar": False})
            st.markdown(charts.cost_gauge_caption(scale_max, avg, top_site), unsafe_allow_html=True)
            st.plotly_chart(charts.cost_composition_bar(cost), width="stretch",
                            config={"displayModeBar": False})
            rows = [
                [theme.ROLE_LABEL[r],
                 num({"Mechanic": mech_total, "Electric": elec_total, "Welder": weld_total}[r]["Tot"]),
                 rp_short(cost.get(r, {}).get("Tot", 0))]
                for r in ("Mechanic", "Electric", "Welder")
            ]
            st.markdown(
                theme.table_html(
                    ["Role", "FTE", "Cost / bulan"], rows,
                    total_row=["TOTAL", num(grand_total), rp_short(cost_total)], total_col=2,
                ),
                unsafe_allow_html=True,
            )

    # ---------------- rincian ----------------
    tabs = st.tabs([
        "Ringkasan FTE", "Foreman & Supervisor", "FTE Planner",
        f"Data Unit ({len(st.session_state.working_units_df)})", "Detail per Unit",
    ])
    with tabs[0]:
        render_summary_tab(summary, mech_total, weld_total, elec_total, cost)
    with tabs[1]:
        render_operational_tab(staff_res["operational"])
    with tabs[2]:
        render_planner_tab(staff_res["planner"])
    with tabs[3]:
        render_unit_tab(site)
    with tabs[4]:
        render_detail_tab(summary)


# ===========================================================================
def main():
    try:
        backend = get_backend()
    except BackendDataError as exc:
        st.markdown(
            theme.header_band("FTE Calculator", "PT Dharma Henwa"),
            unsafe_allow_html=True,
        )
        st.error(f"Data BACKEND gagal dimuat: {exc}")
        return

    st.session_state.setdefault("app_mode", "calculator")

    with st.sidebar:
        logo = theme.image_uri("logo_putih.png")
        mark = f'<div class="mark"><img src="{logo}" alt=""/></div>' if logo else '<div class="mark"></div>'
        st.markdown(
            f'<div class="dh-side-brand">{mark}'
            f'<div><div class="title">FTE Calculator</div>'
            f'<div class="subtitle">PT Dharma Henwa</div></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="dh-side-label">Mode</div>', unsafe_allow_html=True)
        with st.container(key="nav_calc"):
            if st.button("Kalkulator", width="stretch", key="btn_mode_calc",
                         type="primary" if st.session_state.app_mode == "calculator" else "secondary"):
                st.session_state.app_mode = "calculator"
                st.rerun()
        with st.container(key="nav_basecase"):
            if st.button("Basecase per Site", width="stretch", key="btn_mode_multisite",
                         type="primary" if st.session_state.app_mode == "multisite" else "secondary"):
                st.session_state.app_mode = "multisite"
                st.rerun()

    if st.session_state.app_mode == "calculator":
        render_calculator_mode(backend)
    else:
        render_basecase_mode(backend)

    if DEMO:
        st.caption("Mode demo: data contoh bawaan, bukan Google Sheets. Jalankan tanpa FTE_DEMO=1 untuk data asli.")


if __name__ == "__main__":
    main()
