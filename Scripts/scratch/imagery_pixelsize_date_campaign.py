"""Auto-generated campaign rows for qc/imagery_pixelsize_and_date.csv.

`build_campaign_rows()` turns each LANDED acquisition's measure.json/decision.json (written by
`pipeline/acquire_imagery.py verify`) into a table row: pixel-size cells are MEASURED from the delivered
file; the DATE cells are inherited from the acquisition's source (the manifest target carries a
`date_from` pointer to an existing table row, or PUBLISHED fields of its own). The main builder imports
this; nothing here is hand-maintained per file.
"""
import json
import pathlib

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = SCRIPTS / "pipeline" / "imagery_acquisition_manifest.json"

# date evidence per target id: either inherit from an existing row (same flight) or state it here with URL+quote
DATE_EVIDENCE = {
    "S16": {"inherit": "2016_snoh_rgbi.tif", "note": "same flight/service as the superseded row"},
    "U02": {"date_shot": "NOT FOUND for the Edmonds pixels (CONTESTED product-level 2002-06-11 - see the 2002_king_rgb.tif row)",
            "date_precision": "-", "evidence_grade": "NOT FOUND",
            "source_url": "https://web.archive.org/web/20040225060658if_/http://www.metrokc.gov/gis/sdc/raster/ortho/Ortho2002USGSNATMetadata.html",
            "verbatim_quote": "Source_Time_Period_of_Content: Time_Period_Information: Single_Date/Time: Calendar_Date:  20020611 Source_Citation_Abbreviation:  1192_6574_089 Source_Contribution:  Aerial photography used in orthorectification",
            "single_or_multi_date": "unknown", "note": "SAME product the King cache served (USGS HRO Seattle-Tacoma) - the date question is unchanged by the better copy"},
    "N15": {"date_shot": "2015-08-07", "date_precision": "single day", "evidence_grade": "PUBLISHED",
            "source_url": "https://naipeuwest.blob.core.windows.net/naip/v002/wa/2015/wa_fgdc_2015/47122/m_4712214_sw_10_1_20150807.txt",
            "verbatim_quote": "Time_Period_of_Content: Time_Period_Information: Single_Date/Time: Calendar_Date: 20150807 Currentness_Reference: Ground Condition",
            "single_or_multi_date": "single (all 8 Edmonds DOQQs carry 20150807)", "note": "leaf-on pair to the Feb-Mar 2015 King file"},
    "N17": {"date_shot": "2017-08-15 (m_4712214 quads) and 2017-08-21 (m_4712213 quads)", "date_precision": "2 flight days", "evidence_grade": "PUBLISHED",
            "source_url": "https://coastalimagery.blob.core.windows.net/digitalcoast/WA_NAIP_2017_8572/urllist8572.txt",
            "verbatim_quote": "m_4712213_ne_10_1_20170821.tif (the DOQQ file names in the provider's own urllist, saved to qc/imagery_date_evidence/raw_records/urllist8572.txt) ... m_4712214_nw_10_1_20170815.tif",
            "single_or_multi_date": "MULTI (2 days; Edmonds straddles the two quads)", "note": "August 4-band acquisition vs the May Pictometry mosaic held twice"},
    "N21": {"date_shot": "2021-07-13", "date_precision": "single day", "evidence_grade": "PUBLISHED",
            "source_url": "https://chs.coast.noaa.gov/htdata/raster5/imagery/WA_NAIP_2021_9586/stac/noaa_imagery_item_collection_m9586.json",
            "verbatim_quote": "\"id\": \"m_4712213_ne_10_060_20210713\", \"properties\": {\"created\": \"2024-04-02 ...\", \"license\": \"NLPL\", \"datetime\": \"2021-07-13T00:00:00Z\"}",
            "single_or_multi_date": "single (all 8 Edmonds QQs 2021-07-13)",
            "note": "STAC datetime; the per-quad FGDC sidecars for quad 47122 are absent from the Azure mirror (grade stays PUBLISHED on the provider's STAC record)"},
    "M18": {"date_shot": "2018-08-01 16:22-16:52 UTC", "date_precision": "exact timestamp (30-minute sortie)", "evidence_grade": "PUBLISHED",
            "source_url": "https://maps.edmondswa.gov/gis/rest/services/Basemap/Edmonds_Marsh_2018/ImageServer/keyProperties?f=json",
            "verbatim_quote": "\"acquisitionEndDate\":\"2018-08-01T16:52:13+00:00\",\"acquisitionStartDate\":\"2018-08-01T16:22:13+00:00\"",
            "single_or_multi_date": "single sortie", "note": "the only Edmonds layer with a machine-readable timestamp; marsh footprint only (~1 km^2)"},
    "S17": {"date_shot": "2017-08-15 and 2017-08-21 (WA consortium 1-ft flight areas over Edmonds)", "date_precision": "2 flight days", "evidence_grade": "PUBLISHED",
            "source_url": "https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/Statewide_Imagery_2017_Consortium_1_ft_Footprints_(Dates_and_Times)/FeatureServer/0/query",
            "verbatim_quote": "\"IDATE\":\"2017-08-15\" (city centroid) ... \"IDATE\":\"2017-08-21\" (also intersects the city bbox; raw responses qc/imagery_date_evidence/raw_records/wa_2017_1ft_citybbox.json)",
            "single_or_multi_date": "MULTI (2 flight areas)", "note": "the county's own HXIP flight - a different August acquisition from the May Pictometry mosaic"},
    "S19": {"date_shot": "2019-10-11 (WA consortium 1-ft flight area over Edmonds; same Hexagon flight as NAIP 2019)", "date_precision": "single day", "evidence_grade": "PUBLISHED",
            "source_url": "https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/2019_Statewide_imagery_consortium_1_foot_flight_areas/FeatureServer/0/query",
            "verbatim_quote": "\"IDATE\":\"2019 -10-11\" (stray space verbatim; city-centroid point query, raw response qc/imagery_date_evidence/raw_records/wa_2019_1ft_citycentroid.json)",
            "single_or_multi_date": "single flight area", "note": "OCTOBER - same late-season caveat as 2019n"},
    "S21": {"date_shot": "2021-06-25 to 2021-11-11", "date_precision": "window of 140 days", "evidence_grade": "PUBLISHED",
            "source_url": "https://snohomishcountywa.gov/5414/Interactive-Map-SCOPI",
            "verbatim_quote": "The 2021 aerial photos are 6 inch resolution and cover mainly the urban areas. The imagery was collected between June 25, 2021 and November 11, 2021.",
            "single_or_multi_date": "unknown; the superseded clip was flown in the AFTERNOON (shadow azimuth)", "note": "inherits the 2021_snoh_rgbi.tif evidence"},
    "S15": {"date_shot": "2015-08-07 15:31 (HXIP 2015 1-ft flight over Edmonds = the NAIP 2015 delivery)", "date_precision": "single day + minute", "evidence_grade": "PUBLISHED",
            "source_url": "https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/NAIP_2015_1ft_Ortho_Dates_and_Times_83s/FeatureServer/0/query",
            "verbatim_quote": "\"THEMENAME\":\"hxip_m_4712213_se_10_30\",\"SDATE\":\"08/07/2015 15:31\",\"SUNEL\":46,\"ACCURACY\":\"0.72m (ce 95%)\" (city-centroid point query; raw response qc/imagery_date_evidence/raw_records/wa_2015_1ft_citycentroid.json)",
            "single_or_multi_date": "single sortie over the city footprints", "note": "band 4 = ALPHA (pilot, both rendering modes) - exported 3-band"},
}


def _target_map():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {t["id"]: t for t in m["targets"]}, pathlib.Path(m["local_root"])


def build_campaign_rows(existing_files):
    """Rows for every landed target with a measure.json, except ones the hand-written ROWS already cover."""
    targets, local = _target_map()
    rows = []
    for tid, t in targets.items():
        if t.get("mode") not in ("export", "files"):
            continue
        acq = local / t["source_dir"] / "_acq" / tid
        mf, df = acq / "measure.json", acq / "decision.json"
        if not mf.exists():
            continue
        meas = json.loads(mf.read_text(encoding="utf-8"))
        dec = json.loads(df.read_text(encoding="utf-8")) if df.exists() else {}
        fname = meas.get("file")
        if not fname or fname in existing_files:
            continue
        ev = DATE_EVIDENCE.get(tid, {})
        cmp_ = meas.get("compare_to_held") or {}
        eff = meas.get("effective_cm")
        eff_txt = (f"{eff} (median of {meas.get('n_sites')} sites; {meas.get('oversampling')}x its grid)" if eff else
                   str((meas.get("effective_cm_marsh_centre") or {}).get("effective_cm", "not measured at the standard sites")) + " (footprint-local)")
        if cmp_.get("effective_cm_common_new"):
            eff_txt += f"; common grid vs held: {cmp_['effective_cm_common_new']} vs {cmp_['effective_cm_common_held']} cm, HF ratio {cmp_.get('hf_ratio_new_over_held')}"
        b4 = (meas.get("band_verdict") or {}).get("band4") or {}
        notes = (f"MEASURED on arrival ({acq / 'measure.json'}): {meas.get('width')}x{meas.get('height')} px, {meas.get('bands')} bands, "
                 f"EPSG:{meas.get('epsg')}, {meas.get('bytes'):,} B; city coverage {meas.get('city_coverage_pct')}%, study-extent {meas.get('study_coverage_pct')}%"
                 + (f"; band 4 {b4.get('verdict')} (std {b4.get('std')}, NDVI p90 {b4.get('ndvi_p90')})" if b4 else "")
                 + f"; JPEG 8x8 signature {'present' if (meas.get('jpeg_block') or {}).get('signature') else 'absent'}. "
                 f"Decision {dec.get('verdict')}: wins={dec.get('wins')} losses={dec.get('losses')}. "
                 + (t.get("pilot_waiver", "") and f"WAIVER: {t['pilot_waiver']} ") + (ev.get("note", "")))
        rows.append({
            "file": fname, "year_label": f"{t.get('year_label')} (campaign {tid})",
            "source": (t.get("url") or t.get("base_url", "")) + " via pipeline/acquire_imagery.py " + ("(--via download: original source tiles)" if (acq / "download_items.json").exists() else f"({t.get('mode')})"),
            "grid_px": meas.get("px"), "grid_units": meas.get("units"), "crs": f"EPSG:{meas.get('epsg')}",
            "true_ground_cm": meas.get("true_gsd_cm"), "effective_cm": eff_txt,
            "native_flight_cm": {"S16": "30.48 (county 1-ft delivery)", "S17": "30.48", "S19": "30.48", "S15": "30.48", "S21": "15.24 (0.5 ft)",
                                 "U02": "33 acquired; delivered 0.98-ft/30 cm USGS tiles (these ARE the delivered tiles)",
                                 "N15": "100 (delivered 1 m)", "N17": "100 (delivered 1 m)", "N21": "60 delivered (native 15 cm, rectified 4x)",
                                 "M18": "3.36 (source pixelSizeX 0.0336 WM m; drone)"}.get(tid, "see manifest"),
            "date_shot": ev.get("date_shot", f"inherited from the {ev.get('inherit')} row" if ev.get("inherit") else "see parent row"),
            "date_precision": ev.get("date_precision", "-"), "single_or_multi_date": ev.get("single_or_multi_date", "unknown"),
            "evidence_grade": ev.get("evidence_grade", "INFERRED"),
            "source_url": ev.get("source_url", ""), "verbatim_quote": ev.get("verbatim_quote", f"(date evidence inherited from the {ev.get('inherit')} row - same flight, same service)" if ev.get("inherit") else "-"),
            "notes": notes[:1900],
            "px_evidence": "grid/true/effective MEASURED (acquire_imagery verify)",
            "row_type": "held imagery (campaign)",
        })
    return rows
