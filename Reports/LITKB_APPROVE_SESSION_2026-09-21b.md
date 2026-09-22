# litkb approve session — S3 second session, tracker-era manual proposals

- Date: 2026-09-21
- Session label: `s3-approve-2` (agent `claude`)
- Workstream opened for this review: `01a0c6b5-87c3-73d6-ad39-a0ebfa712552` (slug `approve-2`,
  purpose "Kam ruling 2026-09-21: second-session review of the 13 tracker-era manual proposals and
  Chrisman_1982", branch `work/20260921-litkb-approve-2`)
- Worktree: `D:\edmonds-pipeline\wt-approve-2`, HEAD at start `1640f82` (checkout of `main`)
- Precedent followed: `Reports/LITKB_APPROVE_SESSION_2026-09-21.md` (session `s3-approve-1`)
- Scope as ruled by Kam: every `route='manual'`, `state='proposed'` admission in `litkb.admissions`.
- Evidence rule applied: APPROVE only when the document IS the claimed work — the document's own
  title matches the work version's title and the document's first author matches the work version's
  first author. A preprint or a later arXiv version of the same paper counts. A different paper or a
  different edition does not.

## Scope count — the brief says fourteen, the database holds thirteen

The brief names "the thirteen tracker-era manual proposals and the Chrisman_1982 proposal", i.e.
fourteen. There are **thirteen**, and the brief's own id list has thirteen entries: the
Chrisman admission `01a0a151-aaea-756f-9c01-25ed443e838b` is the first entry of that list, so it was
counted twice in the prose. Measured:

```
psql -U litkb_reader -d litkb -At -c "select count(*) from litkb.admissions
                                      where route='manual' and state='proposed'"
-> 13     (before this session; 0 after)
```

The same off-by-one runs through the brief's step 5: **twelve** of the thirteen carry `type='report'`,
not thirteen — Chrisman already carries `proceedings`.

```
select type,count(*) from litkb.main_works where key in (<the 13 keys>) group by type
-> proceedings 1 · report 12
```

## Evidence common to all thirteen

- Each admission's `checks` records `check1_study_exists` `pass`, `check2_duplicate` `pass`, and
  `check3_binding` `bound`; binding ratio 1.0 for eleven, 0.9461 for Kalinicheva, and the
  Pesonen row bound off `source: pdf-title` at ratio 1.0 (`best_any_ratio` 0.8195 on page 1).
  Every row carries `author_found: true` and `author_near_title: true`.
- Each has exactly one `file_versions` row, `status='active'`, `has_text_layer` true, under
  `D:\edmonds-pipeline\Literture\Validation\`. **I recomputed md5 from disk for all thirteen
  files: every one matches the md5 recorded in `file_versions`**, so the file I read is the file
  that was bound.
  ```
  cd D:\edmonds-pipeline\Literture\Validation ; md5sum <each>.pdf
  ```
- Each document was read with `pdftotext -l 2 <file> -` (read-only; output to the session scratchpad,
  nothing written under the literature root).
- Duplicate re-check at review time, not just at admission time: none of the thirteen keys existed in
  `litkb.main_works` before the approvals, and a title search for each subject found only three
  unrelated works (`Islam_2026_high-resolution-multi-temporal`, `Vapnik_2009_new-learning-paradigm-learning`,
  `Khan_2025_deeptrees-tree-crown-segmentation`).
- Admitter sessions are `edge-pre1990-20260914` (Chrisman) and `litkb-p3-20260915` (the other twelve);
  both differ from `s3-approve-2`, so `admissions_second_session_signs_off` had no reason to refuse.

---

## 01a0a151-aaea-756f-9c01-25ed443e838b — Chrisman_1982

- Work key: `Chrisman_1982_theory-cartographic-error-measurement` (work_id
  `01a0a151-aae7-7760-8dd5-102e6ed454b8`). Route `manual`, workstream `01a0a145-…` (`edge-pre1990`).
- Record: title "A theory of cartographic error and its measurement in digital data bases",
  authors `[{"given": "", "family": "Chrisman"}]`, year 1982, type `proceedings`, venue NULL,
  publisher NULL.
- `checks.manual_source`: "edge-pre1990 S4-176: Reports/lit_spatiotemporal_bibliography.csv".
  `check3_binding` matched "A THEORY OF CARTOGRAPHIC ERROR AND ITS MEASUREMENT IN DIGITAL DATA BASES"
  on page 1 line 0 at ratio 1.0.
- File: `Validation/Chrisman_1982_theory-cartographic-error-measurement.pdf`, md5
  `830007c67a6fef2a0c87ddf8d7254855` (recomputed from disk: match), 660,801 bytes, 10 pages.
  `pdf_metadata` Producer "JRAPublish 3.000", CreationDate "Wed Jul 2 18:34:10 2008" — a 2008 scan of
  a printed original, so the PDF's own date says nothing about the work's year.
- **Identifiers: NONE.** `litkb.identifier_versions` has zero rows for this work_id — this is the one
  work of the thirteen with no identifier of any kind, not even a tracker id or legacy stem.
- Document read (`pdftotext`, pages 1–2 and then the full 10 pages):
  - line 1: "A THEORY OF CARTOGRAPHIC ERROR AND ITS MEASUREMENT IN DIGITAL DATA BASES"
  - line 2: "Nicholas R. Chrisman University of Wisconsin - Madison"
  - printed page numbers run 159 … 168 (a chapter extracted from a paginated volume)
  - abstract: the epsilon distance model, GIRAS digital files, "7 percent of the selected study area
    around Pittsburgh lies in zones of potential error"
  - **no year and no venue are printed anywhere in the document.** The internal year evidence is:
    the latest external reference is "Thorpe, L.W. 1981, personal communication", and the paper
    self-cites "Chrisman, N.R. 1982, Methods of spatial analysis based on error in categorical maps,
    unpublished Ph.D. thesis, University of Bristol". That bounds the work at 1982 or later and is
    consistent with the recorded 1982; it does not prove it.
- **Decision: APPROVED.** The file is the 1982 "A theory of cartographic error and its measurement in
  digital data bases" by Chrisman: title verbatim, first author Nicholas R. Chrisman, pages 159–168,
  internally dated ≥1982. That the volume is Auto-Carto 5 is **not** established by anything I read —
  the document does not name it and no tracked file in this repository states it. Recorded here as
  INFERRED from the pp. 159–168 pagination plus the ≥1982 bound, not as measured.
- **Identifier the work should carry: none exists.** A CrossRef title+author query on 2026-09-21
  returned no record for this paper (nearest hits: Chrisman & Peucker 1975 `10.1559/152304075784447289`,
  and an unrelated "Error Theory and Fictionalism"). Auto-Carto-era proceedings papers were not
  registered. The only assignable identifier is therefore a `url` scheme row pointing at a stable
  scan of the proceedings; the correct value for a DOI is **absent**, and leaving the work with no
  DOI is the honest state, not a gap to be filled with a made-up one.
- Its three sibling admissions of the same title stay refused, verified at review time:
  `01a0a151-ab74-7e5b-b0d9-e2baa38d074a` (edge-pre1990 S4-207), `01a0a4d4-452e-7843-a5b2-687f2d365c9a`
  (tracker ID 370), `01a0a4de-ffca-710b-8b52-4791175181db` (manifest stem) — all `state='refused'`,
  each `check2_duplicate.matches` naming key `Chrisman_1982_theory-cartographic-error-measurement`,
  each bound at ratio 0.993 against the spelling "digital databases". A fifth row exists as a
  *candidate* only (`01a0a85d-3479-75df-b402-56d42a874095`, state `new`, "cited by
  Shi_1998_generic-statistical-approach-modelling as b1") — no admission, out of scope, untouched.

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0a151-aae7-7760-8dd5-102e6ed454b8", "entity": "work", "version": "01a0a151-aae7-7b79-83d6-940164a361db"},
  {"id": "01a0a151-aae9-7a7a-8b5d-b764a3a80723", "entity": "file", "version": "01a0a151-aae9-7e2c-be52-ad9528bd1907"}
]
```

Note: two moved entities, not three — there was no identifier to move.

---

## 01a0a4b1-e046-7214-84dd-e51d80fd807e — Pesonen_2026

- Key `Pesonen_2026_learning-image-based-tree`; record title "Learning image-based tree crown
  segmentation from enhanced lidar-based pseudo-labels", authors `[Pesonen]`, year 2026, type `report`.
  Identifiers: `tracker` 173, `legacy_stem` `Pesonen_2026_learning-image-based-tree-crown`.
  `manual_source` "tracker ID 173 (no registry record)".
- File `Validation/Pesonen_2026_learning-image-based-tree-crown.pdf`, md5
  `e7727912799081860c2847bf208af5ef` (match), 32,134,975 bytes, 21 pages.
- Document, page 1: "arXiv:2602.13022v1 [cs.CV] 13 Feb 2026"; title "Learning Image-based Tree Crown
  Segmentation from Enhanced Lidar-based Pseudo-labels"; byline "Julius Pesonen, Stefan Rua, Josef
  Taher, Niko Koivumäki, Xiaowei Yu, Eija Honkavaara" (Finnish Geospatial Research Institute / Aalto /
  ONERA).
- Matched: title verbatim (case aside), first author Pesonen, year 2026 printed in the arXiv stamp.
- **Decision: APPROVED.**

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0a4b1-e03c-7b8c-a45e-e25e3270fc4d", "entity": "work", "version": "01a0a4b1-e03d-7372-8668-28419bef4d17"},
  {"id": "01a0a4b1-e03f-7b13-b15f-587ce43ea8e7", "entity": "identifier", "version": "01a0a4b1-e040-70d2-adf5-4e04a0d0290b"},
  {"id": "01a0a4b1-e040-7a0f-b876-0ed674f960c3", "entity": "identifier", "version": "01a0a4b1-e040-7e9d-b949-c55b96bb7c34"},
  {"id": "01a0a4b1-e041-7b3c-91fc-2be491fc3484", "entity": "file", "version": "01a0a4b1-e044-7fa3-9e35-f5e78f3c7175"}
]
```

---

## 01a0a4ba-08cb-7da8-b449-edaf42e6e697 — Kalinicheva_2025

- Key `Kalinicheva_2025_super-resolved-canopy-height`; record title "Super-Resolved Canopy Height
  Mapping from Sentinel-2 Time Series Using Airborne LiDAR HD", authors `[Kalinicheva, Planells]`,
  year 2025, type `report`. `tracker` 241, `legacy_stem`. Binding ratio 0.9461.
- File `Validation/Kalinicheva_2025_super-resolved-canopy-height.pdf`, md5
  `38c9090afda465fdadafc911ad7f23e3` (match), 45,745,689 bytes, 24 pages.
- Document, page 1: "Super-Resolved Canopy Height Mapping from Sentinel-2 Time Series Using Airborne
  LiDAR HD **Reference Data across Metropolitan France**"; byline "Ekaterina Kalinicheva, Florian
  Helen, Stéphane Mermoz, Florian Mouret, Milena Planells"; "arXiv:2512.11524v3 [cs.CV] 27 May 2026";
  THREASURE-Net, MAE 2.63 / 2.70 / 2.89 m.
- Matched: first author Kalinicheva; the record's title is the document's title **truncated** after
  "LiDAR HD" — the same paper, an incomplete title field (this is what dropped the binding ratio to
  0.9461). Year 2025 corresponds to the arXiv v1 (2512 = December 2025); the copy on disk is v3,
  stamped 27 May 2026.
- **Decision: APPROVED** — a truncated title field is a metadata defect, not a different work.

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0a4ba-08c4-7ab4-8005-552d91bc133c", "entity": "work", "version": "01a0a4ba-08c4-7fab-842e-a93fb347b895"},
  {"id": "01a0a4ba-08c5-7cb1-8a9a-e4ec99412afe", "entity": "identifier", "version": "01a0a4ba-08c6-70ff-9959-2d941d283a59"},
  {"id": "01a0a4ba-08c6-7c16-92fe-4f16398657ee", "entity": "identifier", "version": "01a0a4ba-08c7-717a-ac6e-feb2d3276094"},
  {"id": "01a0a4ba-08c8-71ec-94ce-aba80b3bd017", "entity": "file", "version": "01a0a4ba-08ca-7e46-ac0c-6b1e5af702d9"}
]
```

---

## 01a0a4bb-f282-7c4e-9f46-ada1f900ea74 — LopezPaz_2016

- Key `LopezPaz_2016_unifying-distillation-privileged-information`; record title "Unifying distillation
  and privileged information", authors `[Lopez-Paz, Vapnik]`, year 2016, type `report`. `tracker` 244,
  `legacy_stem`. Binding ratio 1.0, matched on page 1 line 1.
- File `Validation/LopezPaz_2016_unifying-distillation-privileged.pdf`, md5
  `6c4b9a8aec88b53da0b13ed6277372b6` (match), 407,729 bytes, 10 pages.
- Document, page 1: "arXiv:1511.03643v3 [stat.ML] 26 Feb 2016"; "Published as a conference paper at
  ICLR 2016"; "UNIFYING DISTILLATION AND PRIVILEGED INFORMATION"; byline David Lopez-Paz (FAIR Paris),
  Léon Bottou, Bernhard Schölkopf, Vladimir Vapnik.
- Matched: title verbatim, first author Lopez-Paz, year 2016 printed twice (arXiv stamp, ICLR line).
- **Decision: APPROVED.**

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0a4bb-f27e-7150-bb77-dd95385d6900", "entity": "work", "version": "01a0a4bb-f27e-7838-be1d-737b0de5c550"},
  {"id": "01a0a4bb-f27f-7597-bd08-553738a7000f", "entity": "identifier", "version": "01a0a4bb-f27f-7bb2-aa70-d4ede2512503"},
  {"id": "01a0a4bb-f280-77a9-b30f-f2dc86fb930f", "entity": "identifier", "version": "01a0a4bb-f280-7d71-a950-b5d29468cc82"},
  {"id": "01a0a4bb-f281-79f2-b7b5-60372959019e", "entity": "file", "version": "01a0a4bb-f282-700a-9f39-384b5dbe1638"}
]
```

---

## 01a0a4bc-e0ad-7130-af30-4f05591fb12b — Pauls_2025

- Key `Pauls_2025_capturing-temporal-dynamics-large`; record title "Capturing Temporal Dynamics in
  Large-Scale Canopy Tree Height Estimation", authors `[Pauls]`, year 2025, type `report`.
  `tracker` 245, `legacy_stem` `Pauls_2025_capturing-temporal-dynamics-large-scale`. Ratio 1.0.
- File `Validation/Pauls_2025_capturing-temporal-dynamics-large-scale.pdf`, md5
  `8c964602539f176e41f500c5f6e56642` (match), 16,505,981 bytes, 17 pages.
- Document, page 1: title line verbatim; "arXiv:2501.19328v3 [cs.LG] 12 Mar 2026"; byline "Jan Pauls,
  Max Zimmer, Berkant Turan, Sassan Saatchi, Philippe Ciais, Sebastian Pokutta, Fabian Gieseke".
- Matched: title verbatim, first author Pauls. Year 2025 corresponds to the arXiv v1 (2501 = January
  2025); the copy on disk is v3, stamped 12 Mar 2026. No venue is printed on page 1.
- **Decision: APPROVED.**

CLI output — **LOST, reconstructed from the database.** This approval and the four that follow it were
run through a shell pipeline whose second stage (`python`) does not exist on this machine
("Python was not found"), so the CLI's JSON was consumed by the broken pipe and never displayed. The
approve call itself succeeded — `litkb.admissions` records `state='approved'`, `approver_agent='claude'`,
`approver_session='s3-approve-2'`, `approved_at 2026-09-21 18:27:14.00695-07`. The move list below was
read back from `work_versions` / `identifier_versions` / `file_versions` where `state='promoted'` for
this work_id. **It is not verbatim CLI output** and is labelled as such.

```
work        01a0a4bc-e0a9-7bf3-b7f7-a6f4b5202399  version 01a0a4bc-e0aa-7182-9342-00b1c11a4d5c
identifier  01a0a4bc-e0aa-7a67-a4c6-887564e0a0cb  version 01a0a4bc-e0aa-7ef1-b41d-f5b65d692098
identifier  01a0a4bc-e0ab-7658-8ef6-c5f3dd1f27e2  version 01a0a4bc-e0ab-7a40-abb4-a2b883c23412
file        01a0a4bc-e0ac-725f-b5a5-7281f2719edd  version 01a0a4bc-e0ac-76f0-8634-65f4d474471d
```

---

## 01a0a4be-4056-7cda-ba3f-546d6a4aeab4 — Touvron_2019

- Key `Touvron_2019_fixing-train-test-resolution`; record title "Fixing the Train-Test Resolution
  Discrepancy", authors `[Touvron, Jégou]`, year 2019, type `report`. `tracker` 256, `legacy_stem`.
  Ratio 1.0.
- File `Validation/Touvron_2019_fixing-train-test-resolution.pdf`, md5
  `3180a09119732e3e3e9725081718e0db` (match), 920,314 bytes, 14 pages.
- Document, page 1: "Fixing the train-test resolution discrepancy"; byline "Hugo Touvron, Andrea
  Vedaldi, Matthijs Douze, Hervé Jégou — Facebook AI Research"; "arXiv:1906.06423v4 [cs.CV] 20 Jan
  2022"; footnote 1 "Since the publication of this paper at Neurips, we have improved this state of
  the art by applying our method to EfficientNet."
- Matched: title verbatim, first author Touvron. The file is arXiv **v4 (Jan 2022)** of the NeurIPS
  2019 paper — a later version of the same work, which the rule admits. The recorded year 2019 is the
  publication year and is supported by the document's own footnote naming its NeurIPS publication,
  though the string "2019" is not itself printed on page 1.
- **Decision: APPROVED.**

CLI output — **LOST, reconstructed from the database** (same broken pipe; `approved_at
2026-09-21 18:27:14.554662-07`). Not verbatim.

```
work        01a0a4be-4051-72bd-93e1-c3eb5a07fc52  version 01a0a4be-4051-7a24-b397-91d2f7a4b999
identifier  01a0a4be-4052-7af7-80b4-9d860e9f3703  version 01a0a4be-4053-7534-9ecf-70c8881b59e0
identifier  01a0a4be-4054-73d1-adb6-3eca7eb8d97f  version 01a0a4be-4054-79d7-a505-1e805d5c55df
file        01a0a4be-4055-7926-b6e3-f494545a949c  version 01a0a4be-4056-7073-a025-c4decd723112
```

---

## 01a0a4bf-f17c-75dc-9ed7-c2cd5eb8e2eb — Krahenbuhl_2011

- Key `Krahenbuhl_2011_efficient-inference-fully-connected`; record title "Efficient Inference in Fully
  Connected CRFs with Gaussian Edge Potentials", authors `[Krähenbühl, Koltun]`, year 2011, type
  `report`. `tracker` 282, `legacy_stem`. Ratio 1.0.
- File `Validation/Krahenbuhl_2011_efficient-inference-fully-connected.pdf`, md5
  `468cd059c5eb1a974439fcf4e6dc5b74` (match), 4,105,338 bytes, 9 pages.
- Document, page 1: title verbatim; "arXiv:1210.5644v1 [cs.CV] 20 Oct 2012"; byline "Philipp
  Krähenbühl / Vladlen Koltun, Computer Science Department, Stanford University".
- Matched: title verbatim, both authors, in order.
- **Year NOT confirmed by the document.** No venue line is printed, and a scan of every four-digit
  year in the full text returns a maximum of 2012 — the string "2011" does not occur. The recorded
  year 2011 is the NIPS 2011 publication year; that attribution is INFERRED (my own knowledge), not
  read from the file or from any tracked file. Flagged for S5 alongside the type.
- **Decision: APPROVED** — the identity rule is title plus first author, and both match exactly. The
  year is a metadata field, recorded as unconfirmed rather than treated as a mismatch.

CLI output — **LOST, reconstructed from the database** (`approved_at 2026-09-21 18:27:15.228851-07`).
Not verbatim.

```
work        01a0a4bf-f179-70a5-8fe1-d592e215fd37  version 01a0a4bf-f179-7535-a1d7-1bc2f735836b
identifier  01a0a4bf-f179-7e94-8977-ce69dabcac8c  version 01a0a4bf-f17a-7293-a25b-01254762a1f1
identifier  01a0a4bf-f17a-7ac6-9b39-0e6b4e303752  version 01a0a4bf-f17a-7e5a-9742-2404bf308926
file        01a0a4bf-f17b-7997-ad6f-810a60122f67  version 01a0a4bf-f17b-7d83-b6b1-b9fe511443b7
```

---

## 01a0a4c5-0e5a-7cd5-aa33-cacee829adb4 — Batson_2019

- Key `Batson_2019_noise2self-blind-denoising-self`; record title "Noise2Self: Blind Denoising by
  Self-Supervision", authors `[Batson, Royer]`, year 2019, type `report`. `tracker` 302, `legacy_stem`.
  Ratio 1.0.
- File `Validation/Batson_2019_noise2self-blind-denoising-self.pdf`, md5
  `927fc626fb7a223a2d85c34cf0359743` (match), 6,024,828 bytes, 16 pages.
- Document, page 1: title verbatim; "arXiv:1901.11365v2 [cs.CV] 8 Jun 2019"; "Joshua Batson * 1 Loic
  Royer * 1"; footer "Proceedings of the 36 th International Conference on Machine Learning, Long
  Beach, California, PMLR 97, 2019. Copyright 2019 by the author(s)." — Chan-Zuckerberg Biohub.
- Matched: title verbatim, both authors, year 2019 printed in the venue footer.
- **Decision: APPROVED.**

CLI output — **LOST, reconstructed from the database** (`approved_at 2026-09-21 18:27:15.774341-07`).
Not verbatim.

```
work        01a0a4c5-0e57-798d-8ade-b04808b2fa27  version 01a0a4c5-0e57-7ee9-ab0f-46c05a6a7041
identifier  01a0a4c5-0e58-78db-a147-96f23219953b  version 01a0a4c5-0e58-7d39-988a-5e572c2bf43d
identifier  01a0a4c5-0e59-76d3-a7c2-9f0b563cf4b2  version 01a0a4c5-0e59-7a98-ae3c-41a2662dd7c3
file        01a0a4c5-0e5a-7280-ba88-66d6e7dca378  version 01a0a4c5-0e5a-7639-89d0-26746cb9c3c9
```

---

## 01a0a4c6-503b-7f7c-a4f3-31bd26587cc6 — Vincent_1993

- Key `Vincent_1993_grayscale-area-openings-closings`; record title "Grayscale area openings and
  closings, their efficient implementation and applications", authors `[Vincent]`, year 1993, type
  `report`. `tracker` 309, `legacy_stem`. Ratio 1.0, matched page 1 line 2.
- File `Validation/Vincent_1993_grayscale-area-openings-closings.pdf`, md5
  `d7cb2ab5354fd2ccc2c87d9978aeb145` (match), 119,600 bytes, 6 pages.
- Document, page 1 line 1: "Proc. EURASIP Workshop on Mathematical Morphology and its Applications to
  Signal Processing, Barcelona, Spain, pp. 22–27, May 1993." Then the title verbatim and "Luc Vincent,
  Xerox Imaging Systems, 9 Centennial Drive, Peabody MA 01960, USA".
- Matched: title verbatim, sole author Vincent, year 1993 printed with the venue and page range.
- **Decision: APPROVED.**

CLI output — **LOST, reconstructed from the database** (`approved_at 2026-09-21 18:27:16.433248-07`).
Not verbatim.

```
work        01a0a4c6-5037-719b-adad-c5f05604b32d  version 01a0a4c6-5037-7681-b27d-879d150c83ee
identifier  01a0a4c6-5039-7881-a0ab-3dd467ea0d66  version 01a0a4c6-5039-7f30-ad74-4446ad0f0832
identifier  01a0a4c6-503a-7818-8b5a-c9bbb260144c  version 01a0a4c6-503a-7bd6-bf4c-d3066e2c8d99
file        01a0a4c6-503b-7434-801b-bb9d375b5dc7  version 01a0a4c6-503b-77ed-892a-9b3ca50746a6
```

---

## 01a0a4d7-e8c9-72ca-9f85-5fd9ee5ed294 — Platanios_2014

- Key `Platanios_2014_estimating-accuracy-unlabeled-data`; record title "Estimating accuracy from
  unlabeled data", authors `[Platanios, Mitchell]`, year 2014, type `report`. `tracker` 429,
  `legacy_stem`. Ratio 1.0.
- File `Validation/Platanios_2014_estimating-accuracy-unlabeled-data.pdf`, md5
  `aaf5970d2229bf7a1d6080a3206461ea` (match), 148,922 bytes, 10 pages.
- Document, page 1: "Estimating Accuracy from Unlabeled Data"; byline "Emmanouil Antonios Platanios
  (Machine Learning Department, CMU) / **Avrim Blum** (Computer Science Department, CMU) / Tom
  Mitchell (Machine Learning Department, CMU)".
- Matched: title verbatim, first author Platanios. No venue line is printed; the latest reference is
  dated "January 2014", which bounds the work at ≥2014 and is consistent with the recorded year.
- **Distinct from the 2016 record**: this title has no ": A Bayesian Approach" and the second author
  is Blum, not Dubey. The two files are different documents, each matching its own record.
- **Decision: APPROVED.**

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0a4d7-e8c6-7515-b61b-a64edfa4796f", "entity": "work", "version": "01a0a4d7-e8c6-795d-9355-f925e78c50da"},
  {"id": "01a0a4d7-e8c7-71ea-96a8-aeac9d1c305c", "entity": "identifier", "version": "01a0a4d7-e8c7-75f3-a713-5613914decc5"},
  {"id": "01a0a4d7-e8c7-7df5-b15a-07c2fbd0496c", "entity": "identifier", "version": "01a0a4d7-e8c8-71aa-b870-f98b6a252e13"},
  {"id": "01a0a4d7-e8c8-7892-8f8b-30cb2dc03ed7", "entity": "file", "version": "01a0a4d7-e8c8-7c58-b47d-d7a437606f0d"}
]
```

---

## 01a0a4d8-d633-7c8f-8f16-a355c6cc482a — Platanios_2016

- Key `Platanios_2016_estimating-accuracy-unlabeled-data`; record title "Estimating accuracy from
  unlabeled data: a Bayesian approach", authors `[Platanios, Mitchell]`, year 2016, type `report`.
  `tracker` 430, `legacy_stem`. Ratio 1.0.
- File `Validation/Platanios_2016_estimating-accuracy-unlabeled-data.pdf`, md5
  `990953fea0f39236441b567dec0092c1` (match), 476,272 bytes, 10 pages.
- Document, page 1: "Estimating Accuracy from Unlabeled Data: A Bayesian Approach"; byline "Emmanouil
  Antonios Platanios, **Avinava Dubey**, Tom Mitchell — Carnegie Mellon University"; footer
  "Proceedings of the 33 rd International Conference on Machine Learning, New York, NY, USA, 2016.
  JMLR: W&CP volume 48."
- Matched: title verbatim, first author Platanios, year 2016 printed in the venue footer.
- **Decision: APPROVED.**

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0a4d8-d630-7fc3-ae55-03ec5e3b4cdd", "entity": "work", "version": "01a0a4d8-d631-7458-94bd-2eac319267a9"},
  {"id": "01a0a4d8-d631-7c79-936b-9c5466f70843", "entity": "identifier", "version": "01a0a4d8-d632-7073-95bc-990f2383d017"},
  {"id": "01a0a4d8-d632-7715-af57-ac101c71b307", "entity": "identifier", "version": "01a0a4d8-d632-7aad-8c7e-feffeb6fdc01"},
  {"id": "01a0a4d8-d633-71ae-92dc-fd5524c5280b", "entity": "file", "version": "01a0a4d8-d633-7576-ba2e-e1275b29532a"}
]
```

---

## 01a0a4da-bb04-7cbf-b897-d168005c7ab4 — Raykar_2010

- Key `Raykar_2010_learning-crowds`; record title "Learning from crowds", authors `[Raykar]`, year
  2010, type `report`. `tracker` 433, `legacy_stem`. Ratio 1.0, matched page 1 line 1.
- File `Validation/Raykar_2010_learning-crowds.pdf`, md5 `ab0d3394bbb5bdb2ea7f360dccb38ecd` (match),
  238,950 bytes, 26 pages.
- Document, page 1 line 1: "Journal of Machine Learning Research 11 (2010) 1297-1322"; then
  "Submitted 9/09; Revised 2/10; Published 4/10"; title "Learning From Crowds"; byline Vikas C.
  Raykar, Shipeng Yu (Siemens Healthcare), Linda H. Zhao (Penn), Gerardo Hermosillo Valadez, Charles
  Florin, Luca Bogoni (Siemens), Linda Moy (NYU).
- Matched: title verbatim, first author Raykar, year 2010 printed in the journal header.
- **Decision: APPROVED.**

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0a4da-bb01-7b6c-a5a6-230f90ed3749", "entity": "work", "version": "01a0a4da-bb02-701c-a967-2222ff8df1f6"},
  {"id": "01a0a4da-bb02-7bcc-8e33-beb478121a92", "entity": "identifier", "version": "01a0a4da-bb03-70fc-801f-794bf5d729ca"},
  {"id": "01a0a4da-bb03-782e-aedf-4c8d54bf0560", "entity": "identifier", "version": "01a0a4da-bb03-7bde-aa9e-d7805300e95a"},
  {"id": "01a0a4da-bb04-72ed-9e50-a68156c6769f", "entity": "file", "version": "01a0a4da-bb04-76c3-b13c-1aa2f63e5e3d"}
]
```

---

## 01a0a4e2-23d1-710f-ba1e-1790ec7540e9 — Krahenbuhl_2013

- Key `Krahenbuhl_2013_parameter-learning-convergent-inference`; record title "Parameter Learning and
  Convergent Inference for Dense Random Fields", authors `[Krahenbuhl, Koltun]`, year 2013, type
  `report`. Ratio 1.0.
- **Identifiers: `legacy_stem` only** (`Krahenbuhl_2013_parameter-learning-convergent`); no tracker id.
  `manual_source` reads "manifest stem Krahenbuhl_2013_parameter-learning-convergent (no registry
  record)" — this row came from the manifest, not from a numbered tracker line. That is why its move
  list has three entities, not four.
- File `Validation/Krahenbuhl_2013_parameter-learning-convergent.pdf`, md5
  `3ebea1a1088d321da0fa602262ecbef4` (match), 339,403 bytes, 9 pages.
- Document, page 1: title verbatim; "Philipp Krähenbühl / Vladlen Koltun,
  philkr@cs.stanford.edu / vladlen@cs.stanford.edu, Computer Science Department, Stanford University";
  footer "Proceedings of the 30 th International Conference on Machine Learning, Atlanta, Georgia,
  USA, 2013. JMLR: W&CP volume 28. Copyright 2013 by the author(s)."
- Matched: title verbatim, both authors, year 2013 printed in the venue footer.
- **Distinct from the 2011 record**: different title, different document, each matching its own record.
- **Decision: APPROVED.**

CLI output

```
"outcome": "approved"
"moved": [
  {"id": "01a0a4e2-23c6-79d6-a492-b224a71230f0", "entity": "work", "version": "01a0a4e2-23c7-7591-b1ca-06b743709bfd"},
  {"id": "01a0a4e2-23ca-7f99-a6ef-ecea856bbd95", "entity": "identifier", "version": "01a0a4e2-23cb-7ba5-ac70-cd9c15bbc603"},
  {"id": "01a0a4e2-23cd-7210-9c24-60a397612cf6", "entity": "file", "version": "01a0a4e2-23cf-7e4b-99f3-c8b91b6521c3"}
]
```

---

## DB verification after the approvals

```
select key,state from litkb.main_works where key in (<the 13 keys>) order by key
```

All thirteen read `promoted`:

```
Batson_2019_noise2self-blind-denoising-self                promoted
Chrisman_1982_theory-cartographic-error-measurement        promoted
Kalinicheva_2025_super-resolved-canopy-height              promoted
Krahenbuhl_2011_efficient-inference-fully-connected        promoted
Krahenbuhl_2013_parameter-learning-convergent-inference    promoted
LopezPaz_2016_unifying-distillation-privileged-information promoted
Pauls_2025_capturing-temporal-dynamics-large               promoted
Pesonen_2026_learning-image-based-tree                     promoted
Platanios_2014_estimating-accuracy-unlabeled-data          promoted
Platanios_2016_estimating-accuracy-unlabeled-data          promoted
Raykar_2010_learning-crowds                                promoted
Touvron_2019_fixing-train-test-resolution                  promoted
Vincent_1993_grayscale-area-openings-closings              promoted
```

`select count(*) … -> 13`. For a manual admission, approval IS promotion — the same behaviour
`s3-approve-1` recorded, and no separate promote step ran.

`select count(*) from litkb.admissions where route='manual' and state='proposed'` -> **0**. No
manual proposal is left waiting.

---

## Step 5 — `work_versions.type`, current and correct (for S5; NOT changed here)

The allowed vocabulary, from the table's own CHECK constraint, is
`article · book · chapter · proceedings · report · thesis · preprint · dataset`.

| key | current | should be | basis |
|---|---|---|---|
| Chrisman_1982_theory-cartographic-error-measurement | `proceedings` | `proceedings` (already right) | printed pp. 159–168 of a volume; venue not printed |
| Pesonen_2026_learning-image-based-tree | `report` | `preprint` | arXiv:2602.13022v1; no venue printed |
| Kalinicheva_2025_super-resolved-canopy-height | `report` | `preprint` | arXiv:2512.11524v3; no venue printed |
| LopezPaz_2016_unifying-distillation-privileged-information | `report` | `proceedings` | printed "Published as a conference paper at ICLR 2016" |
| Pauls_2025_capturing-temporal-dynamics-large | `report` | `preprint` | arXiv:2501.19328v3; no venue printed |
| Touvron_2019_fixing-train-test-resolution | `report` | `proceedings` | document's own footnote names its NeurIPS publication |
| Krahenbuhl_2011_efficient-inference-fully-connected | `report` | `preprint` on the evidence; `proceedings` if the NIPS 2011 venue is confirmed from a source | the file is arXiv:1210.5644v1 and prints no venue at all |
| Batson_2019_noise2self-blind-denoising-self | `report` | `proceedings` | printed "Proceedings of the 36th ICML … PMLR 97, 2019" |
| Vincent_1993_grayscale-area-openings-closings | `report` | `proceedings` | printed "Proc. EURASIP Workshop … pp. 22–27, May 1993" |
| Platanios_2014_estimating-accuracy-unlabeled-data | `report` | `preprint` on the evidence; `proceedings` if the NIPS 2014 venue is confirmed | no venue printed |
| Platanios_2016_estimating-accuracy-unlabeled-data | `report` | `proceedings` | printed "Proceedings of the 33rd ICML … JMLR W&CP 48, 2016" |
| Raykar_2010_learning-crowds | `report` | `article` | printed "Journal of Machine Learning Research 11 (2010) 1297-1322" |
| Krahenbuhl_2013_parameter-learning-convergent-inference | `report` | `proceedings` | printed "Proceedings of the 30th ICML … JMLR W&CP 28, 2013" |

Twelve of the thirteen carry the `report` migration default; only Chrisman does not. Where I wrote
"if the venue is confirmed", that is deliberate: the document on disk does not print one, so choosing
`proceedings` there would be a claim from memory, not from a file — exactly the kind of restatement
§3.2 forbids.

## Metadata-quality notes (not identity errors; none blocked the gate)

1. **`venue` and `publisher` are NULL on all thirteen.** Six of the thirteen print their venue on
   page 1 (Vincent, Batson, Platanios 2016, Krähenbühl 2013, LopezPaz, Raykar), so the information
   was available in the bound document and was simply never captured.
2. **Every author's `given` is the empty string** on all thirteen, so no given name is in the
   database — "Nicholas R." (Chrisman), "Julius" (Pesonen), "Luc" (Vincent) and the rest are absent.
   Same defect `s3-approve-1` recorded for its two approvals; it is systemic to the manual route, not
   specific to these rows.
3. **Author lists are truncated to first-and-last, which makes the stored "second" author the paper's
   LAST author.** Measured per document:
   - Kalinicheva: stored `[Kalinicheva, Planells]`; the document's five are Kalinicheva, Helen,
     Mermoz, Mouret, **Planells** — the stored second author is the fifth.
   - LopezPaz: stored `[Lopez-Paz, Vapnik]`; the document's four are Lopez-Paz, Bottou, Schölkopf,
     **Vapnik** — the stored second is the fourth.
   - Touvron: stored `[Touvron, Jégou]`; the document's four are Touvron, Vedaldi, Douze, **Jégou** —
     the stored second is the fourth.
   - Platanios 2014: stored `[Platanios, Mitchell]`; the document's three are Platanios, **Blum**,
     Mitchell — Blum is missing.
   - Platanios 2016: stored `[Platanios, Mitchell]`; the document's three are Platanios, **Dubey**,
     Mitchell — Dubey is missing.
   - Pesonen: stored one author; the document has six. Pauls: stored one; the document has seven.
     Raykar: stored one; the document has seven.
   - Correctly complete: Krähenbühl 2011, Krähenbühl 2013, Batson (two each), Vincent, Chrisman (one
     each).
   This is worse than a missing field: a reader who quotes "Kalinicheva and Planells (2025)" would be
   naming the first and fifth authors as if they were the only two. It is a citation-correctness
   defect, and it is now in the promoted record.
4. **Truncated titles and keys.** Kalinicheva's stored title stops mid-title after "Airborne LiDAR HD"
   (the document continues "Reference Data across Metropolitan France"). Keys are truncated against
   their own file stems in three cases: `Pesonen_2026_learning-image-based-tree` vs stem
   `…-tree-crown`; `Pauls_2025_capturing-temporal-dynamics-large` vs stem `…-large-scale`;
   `Krahenbuhl_2013_parameter-learning-convergent-inference` vs stem `…-convergent`.
5. **Chrisman has no identifier at all** — see its section. Nothing in the database can be used to
   look this work up outside the project, and nothing should be invented: CrossRef has no record.
6. **The year is not printed in the document for four works** (Chrisman, Krähenbühl 2011,
   Platanios 2014, and — as a publication year — Touvron, whose file is the 2022 arXiv version of a
   2019 paper). In each case I recorded what the document does bound the year to, and said where the
   recorded value comes from instead.
7. Not a defect, checked because it looked like one: the bare integers in `main_identifiers`
   (`173`, `433`, …) are scheme-qualified — `scheme='tracker'` — so they cannot collide with a DOI or
   an arXiv id. Census: `doi` 443, `tracker` 380, `legacy_stem` 169, `arxiv` 6, `url` 1.

## Refusals

**None.** All thirteen documents are the works their records claim, on title and first author. There
is no REFUSED and no PENDING-REFUSE row in this session. I checked the refuse path before deciding:
`litkb approve --help` takes only `admission_id`, and `pipeline/litkb/admit/front.py::approve`
(lines 410–419) has a single branch — it compares the approver's session with the admitter's and then
calls `litkb.approve_admission`. There is no refuse verb in the CLI, so a refusal would have been
recorded here as PENDING-REFUSE and no DB write improvised. None was needed.

## What I did NOT do

- Did not change any `work_versions.type`, author list, title, venue, publisher or identifier. Step 5
  is a record for S5; the thirteen rows are promoted exactly as they were proposed, defects included.
- Did not add the missing identifier for Chrisman, and did not invent a DOI for it.
- Did not refuse, re-open or otherwise touch the three refused Chrisman sibling admissions, nor the
  fifth Chrisman *candidate* row (`01a0a85d-…`, state `new`) that the cited-by pass created.
- Did not fetch any of these PDFs over the network; every file was read from
  `D:\edmonds-pipeline\Literture\Validation\` read-only, and nothing under the literature root was
  written, moved, renamed or deleted. The `pdftotext` output went to the session scratchpad.
- Did make one network call, and only one: a read-only CrossRef title query for the Chrisman paper, to
  establish whether a DOI exists. It returned no matching record. No file was downloaded.
- Did not hunt, admit, acquire, extract, ingest, or record any use.
- Did not edit code, run migrations, run `check.py`, or run any test.
- Did not open, read, print or copy `.litkb-workstream`.
- Did not merge, push, vault or delete anything. The only writes are the thirteen `approve` calls,
  this log, and the commit that adds it on `work/20260921-litkb-approve-2`.
- Did not verify that the Chrisman volume is Auto-Carto 5 — see that section; it is INFERRED and
  marked as such.
- Could not show the CLI's own `moved` output for five approvals (Pauls, Touvron, Krähenbühl 2011,
  Batson, Vincent): a shell pipeline of mine sent the JSON to a `python` that does not exist on this
  machine. The approvals themselves landed and are verified in `litkb.admissions`, and the move lists
  for those five are reconstructed from the promoted version rows and labelled as reconstructed, not
  verbatim. Re-running `approve` to recover the output was not an option: `litkb.approve_admission`
  raises on anything that is not a proposed manual admission —
  `IF a.route <> 'manual' OR a.state <> 'proposed' THEN RAISE EXCEPTION 'litkb: admission % is a %
  admission in state %; only a proposed manual admission is approved' … ERRCODE = '55000'`, read from
  `pg_get_functiondef(litkb.approve_admission)`. That guard is enforced in the function body, not by a
  source-text check — but I read it, I did not make it fire, so it is verified by inspection only.
