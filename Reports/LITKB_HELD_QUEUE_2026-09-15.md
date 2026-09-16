# litkb held queue — the rows the P3 load could not settle, 2026-09-15

Worktree `D:\edmonds-pipeline\treedata-heldq`, branch `work/20260915-held-queue`, database `litkb`, 
workstream `held-queue` `01a0a854-1a26-7497-bed5-7a4b61a07017` — **left OPEN**.
Inputs: the search table for the 68 held rows and the 29 binding-failed rows, and `Reports/LITKB_P3_REPORT_2026-09-15.md` §case table. Sci-Hub and the browser were not used.

Per-row detail, with the sha256 and the path of every file the knowledge base now holds: **`Reports/held_queue_results.csv`** (83 rows). This report is its summary and its argument.

## What was done, mechanically

Each row was offered to the tool in one of two shapes, and admission decided:

1. **`admit --doi <the corrected DOI> --tracker-id N`** — the tracker row's own words are the claim, and check 1 compares them with the registry record. Most held rows were case C only because P3 had compared the claim against the *wrong* paper: the DOI stored on the row resolved to something else. With the DOI the search corrected, the same claim passes.
2. **`acquire --doi D --routes open_access,annas`** for every work that admitted. Where acquire stopped at `duplicate-held` — the open-access copy is the file already on disk — the archive route was re-run alone (`--routes annas`), which found a *different* copy three times (328, 432, 434).
3. **Where check 1 refused the claim**, the row has no work, so the archive is unreachable (acquire requires an admitted work). The open-access URL the search had found was fetched with curl, verified to start with `%PDF-` in the scratchpad, copied to `_litkb_staging/incoming/<name>.download`, and offered as **`admit --doi D --file <that path>`** with no claim at all — the P3 case-B path, where the FILE's binding is the comparison. 16 rows were settled this way.

Nothing under `D:\edmonds-pipeline\Literture\` was deleted, moved or renamed. No `.pdf` was written into the literature root by hand (a `*.pdf` there dedupes against itself); only `.download` files, and only after the bytes were verified to be a PDF.

## Totals

| outcome | rows | what it means |
|---|---|---|
| **admitted+bound** | 32 | the work is admitted and a file is attached and bound |
| **admitted+pending** | 10 | the work is admitted; no file bound (nothing obtainable, or the archive holds only the copy already on disk) |
| **binding-failed** | 2 | a correct file was fetched and check 3 refused it; the file is in `_quarantine/` |
| **duplicate+pending** | 2 | the work was already admitted by an earlier workstream; still no file |
| **refused-check1** | 22 | the registry record contradicts the row's claim and no file could be fetched to decide |
| **skipped-low** | 15 | low-confidence candidate, not attempted (the brief's instruction) |
| **total** | 83 | 68 held rows + the 15 distinct works behind the 29 binding-failed rows |

The 29 binding-failed rows are 15 works: 14 tracker rows each have a manifest twin carrying the same DOI (the twin would dedupe at check 2), and `Kats_2019b_soft-staple-algorithm-combined` is manifest-only. Each work was run once; the CSV carries one line per work, named by its tracker id, or by `manifest:<stem>` for Kats.

**The knowledge base after this run:** 44 works admitted by this workstream, 32 with an active file (16 filed by acquire at `_litkb_staging/filed/<stem>.pdf`, 16 recorded in place at `_litkb_staging/incoming/<name>.download` — see *What the tooling did wrong*, 3). `ws status`: candidates admitted 44, duplicate 2, rejected 43; admissions admitted 44, refused 45.

## Archive spend

| | |
|---|---|
| download URLs issued by this run | **12** |
| account counter, first read this run | 3 of 1000 |
| account counter, after the last row | **15 of 1000** |
| quota margin in force | 50 (the tool's default; never reached) |

The two numbers agree: the account counter moved 3 → 15 while the run issued 12 URLs. The archive counts a download when it *issues* the URL, so the two `bad-file` attempts on tracker 280 are inside that 12 even though no PDF arrived — and the account's own counter did not move on the second of them (15 → 15). Six archive attempts cost nothing at all: the record's md5 was already on disk (`duplicate-held`), which is the gate that stops this queue re-downloading what the corpus already holds.

## Admitted and bound (32)

| row | set | route | work key | sha256 |
|---|---|---|---|---|
| 290 | binding-failed | annas | Chernozhukov_2018_double-debiased-machine-lear… | 1b3f1f5db31f4197623a60b88f6b3bd0f044a41a537aa18f35b64ac0d15fc5df |
| 327 | binding-failed | annas | Girard_2019_noisy-supervision-correcting-misal… | b7ee30328be2e85ba1856dd6b43bb0e5db8977b490d6086f26bbc70e9cbc2a78 |
| 328 | binding-failed | annas | VargasMunoz_2019_correcting-rural-building-ann… | 08e42059f77711b48a3040325690734a04a503bcf8234c884d25880ea5d19bd0 |
| 379 | binding-failed | annas | Bacry_2015_hawkes-processes-finance | fcaafb0a035a0b3622aee1855c8816880fec4b4ff55885c3dabc3f0dee752522 |
| 432 | binding-failed | annas | Parisi_2014_ranking-combining-multiple-predict… | 3f9b7e00d2080ea90194b7867e52b5aff0449ba93855561bfc7f7e5e9024497e |
| 434 | binding-failed | annas | Ratner_2017_snorkel-work | f31079c6b771bc14b054178c436dd472e6a8b01a44abf072c706a260dd3edd1d |
| 112 | held | open_access | Wang_2020_tent-fully-test-time | 215223e9885dd7208cad9dbff2cf315f1cc96554fedc4660d0d2c4932364e5f7 |
| 113 | held | open_access | Niu_2023_stable-test-time-adaptation | 08047cf6acb61163844d0fefb917f94ec97b30b5f72781f9e8b1a4e631dcd21e |
| 12 | held | annas | Nowak_2018_declining-urban-community-tree | 134058d2669823506c92d253453c32cbe96618ed8482826a450a0b139adbdcd3 |
| 120 | held | open_access-file | Angelopoulos_2022_conformal-risk-control | 32c3b9689cb69dbec96ce87ba8b0fe98293bb1c9a59247480b16dbae6aa37df2 |
| 124 | held | open_access | Tibshirani_2019_conformal-prediction-covariate… | d80dba944a136e075bbfe281009152ce42041e0a455f68f73684ace83cfc3fed |
| 127 | held | open_access | Fang_2020_rethinking-importance-weighting-deep | ea2cb57e27ad94531b9875607d592ab8d28055b6abe1f076ea6700043a41edc7 |
| 133 | held | open_access | Straka_2025_satdino-deep-dive-self | a4c771a9927fef908ce4664826f2cc229ad204d0ebe9a833e38c8251bc0056fd |
| 17 | held | annas | Tuia_2011_active-learning-adapt-remote | 1bc2e6d02e929be7ad27863310e46efd3effa3c42a003a40d440a14e3dc87cde |
| 19 | held | open_access-file | Khan_2025_deeptrees-tree-crown-segmentation | b2d1eaab235f24b634dce12589ff0e9a9bab7b1785c8bb1fd421782be97e9693 |
| 207 | held | open_access | Geirhos_2018_imagenet-trained-cnns-biased | 758c0fa11cbba89947e69e3ba4963961e1483a5013916b0b6afbe6f6ff2b56b8 |
| 23 | held | annas | Chen_2014_assessment-image-misregistration-eff… | 30b2925e16871387cf9b29304f85e360c18ec130a15e2158398de000ff066353 |
| 284 | held | open_access | Chen_2022_new-p-control-chart | 1cf72222dfaa60ff4a6af840afed3b16eb692d9e07adad70be9cf8c273fc5fbf |
| 285 | held | open_access-file | Itkin_2026_quickest-detection-hallucination-on… | 0412750524774889497f0eaf2cdc4b38d0156380ff2da0e99f35ffdea4140bbb |
| 286 | held | open_access-file | Crowder_2017_introduction-bernoulli-cusum | 5cdb2a68a4392ff9e6fc1c014da48f70cce25a3e39e749ab05f0766992612ab8 |
| 29 | held | open_access-file | Henrich_2024_general-deep-learning-based | be202222cb1ee37d53e39befc85692fd00f77cb8610f3dd07f875b3a18603655 |
| 30 | held | open_access-file | Tasar_2020_standardgan-multi-source-domain | b7e4a1d0f84fd41898f50328e5ad3e0561f9d3b0eabcf21316580d23a3c0ede8 |
| 31 | held | open_access-file | Ahishali_2025_ada-net-attention-guided | 1b18d088f1ba9ad41ba8fd6cacb762172ff6b2df8cd440dd9a6c782aa9fd9e17 |
| 35 | held | open_access-file | Dionelis_2024_learning-unlabelled-data-transfo… | 7368848faf4e699547583c8c3a43dc89f5556240f70ea6d02020f3f613dd36df |
| 36 | held | open_access-file | Madani_2026_morphing-through-time-diffusion | b81515909a11660f7a8cbeeaca16de4043f10297ad64e11439ab1f80a2275ca0 |
| 37 | held | open_access-file | Ferreira_2025_data-augmentation-resolution-enh… | a270381d7d5a5e370fa9f394150ffb25dcd702e6ca484fb1dbf81470ca5732a2 |
| 38 | held | open_access-file | Szczecina_2026_sparse-data-tree-canopy | 2d8bcbcf14fddbb87a26538150bc27bd31bd82aafd57c7fabe30e95851f5e420 |
| 40 | held | open_access-file | Weinstein_2021_benchmark-dataset-canopy-crown | a8c1cb596ca0f7c8fa8e866e1378ae0f1e90afeee4360dd55b1f09e5f36e063c |
| 44 | held | open_access-file | Liu_2024_task-specific-pretraining-noisy | f2eec433905e6d70942d338d00a3d3801e8c97c6d5fd5da74153f55b290862b6 |
| 45 | held | open_access-file | Yang_2025_sam2-elnet-label-enhancement | a7a043065224a207b352fe695a56aba9d133a688e52d3b292928a7ce376d339d |
| 47 | held | open_access-file | Zhang_2024_knowledge-transfer-domain-adaptatio… | 7f262adb91de0d3110400efc78fac7a36b93fa39ac85ac4876179eba6af9976f |
| 65 | held | open_access-file | Fleming_2025_aerial-imagery-tool-monitoring | 63d1752d9cffd2eead9aad223d56cdbe88fe6caca558a489b86aabd2af14f738 |

`route` `open_access-file` means the file was fetched from the search's open-access URL and handed to `admit --file`; `open_access` and `annas` mean the tool's own route landed it through `acquire`.

## Admitted, still no file (10 + 2 already admitted elsewhere)

| row | set | outcome | why |
|---|---|---|---|
| 258 | binding-failed | admitted+pending | OA closed; annas duplicate-held: the archive record for this DOI is md5 1506bae4... which is already on disk, so no different copy exists and no download was spent; P3 binding failed at ratio 0.8296 (… |
| 306 | binding-failed | admitted+pending | OA duplicate-held (the arXiv PDF is byte-identical to the copy already on disk, the one whose binding failed); re-ran with --routes annas: not-in-archive |
| 311 | binding-failed | duplicate+pending | work already admitted by the edge-pre1990 workstream (check2 duplicate); OA bad-file; annas duplicate-held (archive md5 already on disk) - no different copy exists |
| 381 | binding-failed | admitted+pending | OA no-oa-copy; annas duplicate-held: the archive md5 for this DOI is already on disk (the cover-sheet copy whose binding failed) - no different copy exists |
| 382 | binding-failed | duplicate+pending | work already admitted by edge-pre1990 (check2 duplicate); OA no-oa-copy; annas duplicate-held (archive md5 already on disk) |
| 399 | binding-failed | admitted+pending | OA no-oa-copy; annas duplicate-held (archive md5 already on disk) |
| 423 | binding-failed | admitted+pending | OA no-oa-copy; annas duplicate-held (archive md5 already on disk) |
| 431 | binding-failed | admitted+pending | OA duplicate-held (arXiv PDF identical to the copy on disk whose binding failed); --routes annas: not-in-archive |
| manifest:Kats_2019b_soft-sta… | binding-failed | admitted+pending | manifest-only row (no tracker twin): claim restated from the manifest stem via --title/--authors Kats/--year 2019; OA no-oa-copy; annas not-in-archive |
| 165 | held | admitted+pending | unpaywall no-oa-copy; annas not-in-archive; CSV oa_url is the Apollo handle page (HTML, no %PDF-) |
| 280 | held | admitted+pending | admitted on the corrected DOI; OA no-oa-copy; annas issued a download URL twice and the partner bytes were not a PDF both times (bad-file); account counter 14->15 then 15->15 |
| 7 | held | admitted+pending | OA bad-file (Elsevier landing page); annas not-in-archive; corrected DOI admitted, tracker DOI ...103839 was another paper |

## A correct file that check 3 refused (2)

| row | what happened |
|---|---|
| 151 | arXiv PDF is the right paper but the arXiv stamp shares the title line: matched 'arXiv:2007.01434v1 [cs.LG] 2 Jul 2020 In Search of Lost Domain Generalization' ratio 0.6842 < 0.85; quarantined; annas not-in-archive |
| 291 | arXiv PDF is the right paper but check 3's title-region match picked the line 'https://pypi.org/project/uncertainty-calibration', ratio 0.641 < 0.85; quarantined at _quarantine/Kumar_2019_verified-uncertainty-calibration__binding-failed__cc4e4bde39f5.pdf; annas not-in-archive |

Both were fetched from the arXiv id the DOI itself names (`10.48550/arxiv.<id>` → `arxiv.org/pdf/<id>`, the tool's own rule), and in both the registry's first author WAS found on the first page — only the title-line match failed. They sit in `_quarantine/`, and they are the clearest evidence that the binding gate's title-region match has a false-negative mode; see below.

## Left for Kam

### Refused at check 1, no file to decide with (22)

The registry record and the row's claim contradict each other, and no open-access PDF could be fetched, so there is nothing to bind and the archive route cannot be reached. Each needs a human to say which side is right — or a copy of the paper, after which `admit --doi D --file <path>` settles it without a claim.

| row | doi offered | check 1 refused on | why no file |
|---|---|---|---|
| 2 | 10.2139/ssrn.4979539 | first author, year | the CSV oa_url is dx.doi.org and served the SSRN landing page, no %PDF- |
| 10 | 10.1080/17538947.2023.2257636 | first author | the T&F PDF endpoint returned an HTML challenge, no %PDF- |
| 20 | 10.1080/15481603.2018.1489446 | title ratio, year | T&F OA url returned an HTML challenge, no %PDF- |
| 22 | 10.1145/3347146.3359068 | first author | no OA url in the search table |
| 24 | 10.1016/j.rse.2021.112308 | first author | the OA url's host manuscript.elsevier.com does not resolve |
| 33 | 10.1016/j.rse.2025.115091 | first author, year | OA url returned 2747 bytes that are not a PDF |
| 39 | 10.3390/rs15030765 | first author | MDPI blocks the PDF endpoint (403 from Cloudflare), so no file to bind |
| 46 | 10.1080/22797254.2025.2609404 | first author | T&F OA url returned an HTML challenge |
| 48 | 10.1109/tpami.2024.3498346 | first author, year | no OA url |
| 52 | 10.34133/2022/9764982 | first author | OA url served HTML |
| 55 | 10.3390/plants14111677 | first author | MDPI PDF endpoint blocked (403) |
| 66 | 10.1007/s00267-023-01934-6 | first author | no OA url |
| 67 | 10.3390/geomatics4040022 | first author | MDPI PDF endpoint blocked (403) |
| 131 | 10.1109/icip55913.2025.11084679 | title ratio, year | OA url served HTML |
| 154 | 10.1137/1.9781611978032.28 | first author | no OA url |
| 177 | 10.1016/j.rse.2010.07.008 | first author | no OA url |
| 178 | 10.1016/j.rse.2010.07.010 | first author | no OA url |
| 186 | 10.1007/s10980-012-9719-2 | title ratio | no OA url |
| 187 | 10.5067/doc/ceoswgcv/lpv/lc.001 | first author | OA url served HTML |
| 239 | 10.1109/tgrs.2023.3297077 | title ratio | the OA url served a script page, not a PDF |
| 274 | 10.1016/j.jag.2022.102909 | title ratio | OA url served HTML |
| 293 | 10.1175/aies-d-22-0055.1 | year | OA url returned 0 bytes |

### Low-confidence candidates, not attempted (15)

The brief's instruction. The search's own candidate for each of these is weak — a different title, a different author, or both — so admitting on it would be guessing.

`25`, `28`, `49`, `50`, `53`, `57`, `117`, `122`, `132`, `174`, `193`, `194`, `235`, `242`, `369`

## The five stored DOIs that no longer resolved

Each was offered to the tool *first*, so the refusal is litkb's own measurement rather than the search's: four are confirmed by no registry the tool queries. A `doi` discrepancy naming the dead DOI is recorded against each row in `litkb.discrepancies` (source `tracker`, field `doi`), attached to this workstream.

| tracker row | stored DOI | litkb's verdict on it | what was admitted instead |
|---|---|---|---|
| 2 | `10.1016/j.tfp.2025.100146` | not confirmed by any registry | nothing — the replacement `10.2139/ssrn.4979539` is the SSRN **preprint** and its record contradicts the row's author and year |
| 25 | `10.3390/rs5041397` | not confirmed by any registry | nothing — low-confidence row, left for Kam |
| 33 | `10.1016/j.rse.2025.114632` | not confirmed by any registry | nothing — the replacement contradicts the row's first author and year |
| 36 | `10.48550/arxiv.2511.07976` | **it resolves**: check 1 refused it on the claimed first author, not on absence — so it is dead only at Crossref/OpenAlex/Semantic Scholar | `10.1109/wacv61042.2026.00050`, admitted on the binding of its open-access PDF |
| 55 | `10.3390/rs17112050` | not confirmed by any registry | nothing — the replacement contradicts the row's first author |

## What the tooling did wrong

1. **`admit --tracker-id 327` crashes on the tracker's own YEAR cell.** The cell reads `2019a` — the filename convention's same-year suffix, the very cell that ended the P3 load once. P3 fixed its loader (`migrate_legacy/export_shape.year_int` reads the leading four digits), but `admit.front.add_candidate` still calls `int(year)` on the raw cell, so the CLI path raises `ValueError` and the row cannot be admitted by tracker id at all. Worked around here with `--year 2019`, the same reading the loader gives it.
2. **Check 3 has a false-negative mode on arXiv PDFs** (tracker 151 and 291, above). The title-region match picks the best line on page 1: for 151 that line is `arXiv:2007.01434v1 [cs.LG] 2 Jul 2020 In Search of Lost Domain Generalization` — the stamp and the title share a line after `pdftotext -layout`, and the ratio falls to 0.6842. For 291 it picks `https://pypi.org/project/uncertainty-calibration`, ratio 0.641. Both papers are the right ones; both were quarantined. Short titles are the ones at risk.
3. **There is no `admit --from-file`, and `acquire` requires an admitted work.** A row whose claim the registry contradicts can therefore only be settled by `admit --doi --file`, which records the file *in place* wherever it was fetched to. 16 files are now recorded at `_litkb_staging/incoming/<name>.download` with no `.txt` extract beside them, instead of at `_litkb_staging/filed/<stem>.pdf`. They are correct, bound and hashed — they are just not filed, and re-handing them to `acquire --from-file` will not file them either: the first thing `land_and_attach` does is check the sha256 against the database's files, and these are now in it, so the call would return `duplicate-held` (read from the code, not run). The same chicken-and-egg is why the 22 refused rows could not be tried against the archive at all.
4. **`acquire` stops at the first `duplicate-held` and skips the remaining routes.** Three rows (328, 432, 434) reported `duplicate-held` from open access and then, on a second call with `--routes annas`, got a different copy that bound. A single call would have left all three unresolved.
5. **`--tracker-id` couples two unrelated things:** the claim to compare, and the `tracker` identifier to record. Case-B admissions must pass no claim, so the 16 rows settled that way carry no `tracker` identifier — their link back to the tracker row lives only in this report and its CSV.
6. **`make_key` can pad a key with filler.** The Crossref title for `10.14778/3157794.3157797` is the single word *Snorkel*, so the key is `Ratner_2017_snorkel-work` — `work` is the padding `make_key` adds when fewer than two slug words survive.
7. **No CLI writes a discrepancy.** `litkb.record_discrepancy` is the token-checked writer the P3 loader uses, and `litkb/commands.py` exposes no subcommand for it, so the five dead-DOI discrepancies were recorded by calling that function directly with the workstream token read from `.litkb-workstream`.

## What this run left in `_litkb_staging/incoming/`

17 `.download` files, all written by this queue between 20:55 and 21:22 on 2026-09-15 (the 13 others there are an earlier session's, 20:16–20:24). 16 are the PDFs listed above, each now recorded as its work's active file. The seventeenth, `AllenMatthew_2026_manual-labelling.download`, is **not a paper**: it is the Cambridge Apollo handle page for tracker 165, written before the fetch was changed to verify `%PDF-` in the scratchpad first. It is referenced by nothing in the database. Nothing was deleted, so it is named here rather than removed.

## Reproducing any row

```
cd D:\edmonds-pipeline\treedata-heldq\Scripts
set PYTHONPATH=D:\edmonds-pipeline\treedata-heldq\Scripts\pipeline
py -3.12 -m litkb --dir D:\edmonds-pipeline\treedata-heldq admit --doi <doi> --tracker-id <N>
py -3.12 -m litkb --dir D:\edmonds-pipeline\treedata-heldq acquire --doi <doi> --routes open_access,annas
py -3.12 -m litkb --dir D:\edmonds-pipeline\treedata-heldq ws status
```

`LITKB_AGENT` / `LITKB_SESSION` must be set (`claude-opus-5`, `015MUcyGTfX2koRdYAjW5kED` for this run); the workstream token is read from `.litkb-workstream` and is never printed.

