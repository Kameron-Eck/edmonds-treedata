# The Edmonds Tree-Canopy Imagery Campaign, Plain English

*A non-technical account of the 2026-08-23–24 effort to collect better historical
aerial photos of Edmonds. This page was rewritten after each update through the
campaign; this final version closes it out as a complete record.*

## 1. What this campaign is

This campaign is part of a larger project studying how Edmonds' tree canopy — its
trees and green cover — has changed between 2000 and 2024, using historical aerial
photographs of the city. Most of the aerial photos the project had on hand were
compressed copies pulled from web mapping services — similar in spirit to zooming
into an online map — which look fine at a glance but have had real detail smoothed
away, and didn't cover every year that mattered. This campaign went back to the
original sources — county and federal map servers, and university and government
archives — to collect sharper, truer copies of these photos, fill in more years of
coverage, and, wherever possible, capture a "near-infrared" version of each one.
Near-infrared is a color of light just beyond red that human eyes can't see but
healthy leaves reflect strongly — it's the single most useful clue a photo can
carry for telling "this is a tree" apart from everything else in the picture.

## 2. Where things stand right now

*(final status, August 24, 2026 — the download programme is complete)*

- The download programme is complete. Over one long weekend, the campaign acquired
  29 aerial photo files, upgraded 5 full years to measurably better versions (2016,
  2002, 2019, 2021, 2023), and brought 4 calendar years that previously had zero
  imagery into coverage (2003, 2006, 2011, plus 1996 as historical context).
- It closes on a fitting note: the campaign began because the photos on hand were
  mostly lossy, web-map-compressed copies; it ends with the three highest-detail
  years — 2020, 2022, and 2024 — landing overnight as clean, unresampled 3-inch
  (8 cm) originals, about 91 GB across the three, each downloaded in 3,450 pieces
  with zero failures.
- The precious hand-annotated 2020 "anchor" file — the one dataset with real,
  human-checked ground truth the whole project is built on — was never touched; the
  new files simply sit alongside it.
- Near-infrared coverage — the single most useful clue for telling trees apart from
  everything else — went from 4 acquisitions to 10 over the course of the campaign.
- The project's imagery catalogue grew from 19 entries to 36, every one verified
  automatically (36/36 green). The documentation table recording all of this stands
  at 57 rows, every factual claim tied to a saved source, zero broken citations.
- One housekeeping item remains before the three overnight files are backed up to
  Google Drive: the Drive app's upload staging area needs to move from the small
  C: drive to the big D: drive first (an app-settings change, Kam's to make), after
  which a watcher will run the ~91 GB of copies automatically. The files are
  already safe, with verified checksums, on the local D: drive either way.
- Three things are still pending from outside the project: King County's reply
  about releasing its historical infrared originals (the biggest remaining
  prize — real infrared imagery from the year 2000), the state imagery
  consortium's answer about membership access, and NOAA's licence clarification for
  the still-quarantined land-cover file.

## 3. What happens next

- Kam moves Google Drive's upload staging cache from C: to D: in the app's
  settings; a watcher then automatically copies the three overnight files (~91 GB)
  to Drive.
- Wait on King County's reply about its historical infrared originals, including
  the year-2000 imagery that would be the campaign's biggest remaining win.
- Wait on the state imagery consortium's answer about membership access to its
  sharper 6-inch products.
- Wait on NOAA's licence clarification before the quarantined land-cover reference
  file can be used.

## 4. Timeline

*(newest first)*

### Campaign complete — final tally

Over one long weekend, the imagery-acquisition campaign wrapped up: 29 aerial photo
files acquired, 5 full years upgraded to measurably better versions (2016, 2002,
2019, 2021, and 2023), and 4 calendar years that previously had zero imagery now
covered (2003, 2006, 2011, plus 1996 as historical context). Near-infrared
coverage — the single most useful clue for telling trees apart from everything
else — went from 4 acquisitions to 10. The project's imagery catalogue grew from 19
entries to 36, every one verified automatically (36/36 green), and the
documentation table recording all of it stands at 57 rows, every factual claim tied
to a saved source, with zero broken citations. The campaign closes on a fitting
note: it began because the photos on hand were mostly lossy, web-map-compressed
copies, and it ends with the three highest-detail years landing as clean,
unresampled originals (below).

### Overnight (Aug 23–24) — The final three: 2020, 2022, and 2024 land as clean originals

The last three downloads of the campaign landed overnight: the county's own 3-inch
(8 cm) versions of 2020, 2022, and 2024, about 91 gigabytes across the three files,
each one downloaded in 3,450 pieces with zero failures. Unlike the city's copies of
these same years — which carry the tell-tale fingerprint of lossy, web-map-style
compression — these came through with clean, unresampled pixels, the camera's true
readings. The precious 2020 "anchor" file — the one dataset with real, hand-checked
ground truth that the whole project is built on — was never touched; the new files
simply sit alongside it.

### Overnight — Batch 6 and the delayed 2019 re-download finish

Between yesterday afternoon and this morning, the batch-6 downloads (2009, 2011,
2012, and the three 1-meter years 1996, 2006, and 2013) completed, along with the
2019 federal re-download that had been re-running since yesterday's web-address bug
fix. 2011 and 2006 joined the list of calendar years that had no prior imagery at
all; 2019 turned out good enough to join the list of full replacements.

### Midday, continued: 2002's surprise twin, 2003 arrives, batch 6 begins

A duplicate check produced a genuine surprise: the county's 2002 photos were
expected to simply duplicate the original 2002 government photos secured earlier
that morning from a university archive (below), but a similarity measurement said
otherwise — genuine duplicates typically match at 0.98 or higher, while the
county's version matched at only 0.85, confirming a separate, independent aerial
survey — so 2002 ended up with two independent photo sets on file. The same stretch
brought 2003 (a year the project previously had zero imagery for at all) and the
county's 2007 photos, which didn't measure up to the King County 2007 already on
file and were kept as a second reference view rather than a replacement. As a
safeguard after a brief Google Drive scare (below), the city-boundary reference
file the project's coverage measurements depend on was also copied to the local D:
drive, so a Drive hiccup could no longer blank a measurement. Batch 6 — 2009, 2011,
2012, and three 1-meter years — then began downloading.

### The Google Drive mystery is solved — it was never actually running out of room

For much of the afternoon, the project believed Google Drive itself was running low
on storage space, pausing file copies until Kam could empty its trash. That turned
out to have been a false alarm: Kam's Google account has 1.2 terabytes free out of
2, and the earlier deletion of an old 1-terabyte folder genuinely did work. What
every tool had actually been reading as "Google Drive's free space" all day was
really the free space on the laptop's own C: hard drive — because the Drive app
doesn't send files straight to the cloud, it first copies them into a temporary
holding area on C: and uploads them from there in the background, and it was that
local holding area filling up, not Google's cloud storage, that was the real
bottleneck. The fix: once in-progress uploads finish, that holding area moves from
the crowded C: drive to the much larger D: drive — the last piece of that move was
still pending as the campaign closed (see What Happens Next). A smaller, separate
scare in the same stretch: Google Drive briefly vanished from the computer entirely
(it normally shows up as its own drive letter, "G:") because of an accidentally
toggled setting — switching it back fixed it immediately.

### Midday: 2023 replaces its clipped copy, three historical years land, a crash bug gets fixed

The 2023 federal photo was replaced: the version the project had been holding was
cut off at just 69% of the study rectangle and slightly softened by the server it
came from, while 8 original files pulled from a copy of the same federal photos
that Microsoft hosts publicly online gave full coverage and 41% more real detail on
a fair comparison — all 8 shot the same single day, October 7, 2023. Three older,
black-and-white photo sets landed alongside it: 1990 (10-foot pixel size), 1998
(which turned out, per a file path the server accidentally revealed, to be a
Washington State Department of Natural Resources product), and 2001 (scanned film,
honestly measured at roughly 1 meter per pixel — blurrier than its official nominal
resolution). None of the three has a known flight date, so they're catalogued
plainly as "date not found," kept as historical context but left out of the
machine-learning training set since they carry only a single black-and-white band.
Separately, a wrong guess at a web address (Microsoft names its 2019 folder
differently than its 2023 one, tripping up a guessed path) used to crash an entire
download batch; the tool was fixed so a single bad guess is now recorded as one
failure while the rest of the batch continues.

### The 2018 gap is filled: the project's biggest missing year gets real coverage

Until this point, the project had no citywide photo coverage at all for 2018 — the
timeline jumped straight from 2017 to 2019, with only a small, limited Edmonds
Marsh drone survey (and its fake infrared band — see below) standing in for that
year. That gap closed when Snohomish County's server turned out to also carry the
state imagery consortium's 6-inch 2018 flight, photographed on a single day, August
7, 2018 — by pure coincidence, the same calendar date as the 2015 flight, just
three years apart. It landed as an 11.5-gigabyte, four-band file with genuine
near-infrared, resolving real detail down to about 21 cm. With this file in hand,
every year from 2015 through 2024 has at least one summer-or-fall photo set that
includes a real infrared band.

### Midday begins: 2021 replaced, 2015 lands, the land-cover file checks out

The 2021 county photo became the campaign's third replacement (after 2016 and 2002
earlier that day): the new download covered the project's entire study rectangle
where the old copy covered under 40% of it, and — because the old download tool had
been quietly softening pixels while the new one copied them exactly — it was also
measurably sharper, 43% more real detail on a fair comparison, all from a
875-piece, 10.8-gigabyte download with zero failures. The county's own 2015 photos
landed too, about three times sharper than the federal version already on hand,
though its promised infrared band turned out to be an empty placeholder rather than
real data — the same problem the Marsh drone survey had run into that morning
(below) — so it was filed honestly as color-only. And the large NOAA land-cover
reference map fully arrived and passed a thorough check — 99.8% agreement with the
smaller reference the project already used for scoring — confirming that existing
reference trustworthy; the larger file adds wider coverage and clearer
provenance (documentation of where data comes from) once it can be used.

### Late morning: the 2002 original, a marsh survey, and a duplicate dodged

The 2002 photo got its first replacement this stretch, at the time the campaign's
best result yet: a university archive (WAGDA, at the University of Washington)
turned out to hold the original 39 USGS (U.S. Geological Survey) tiles from the
2002 flight, which downloaded in 6 minutes and measured 54% sharper than the old
web-map copy, with none of its compression artifacts — the old file was kept,
marked superseded. Also landing: the county's own August 2017 and 2019 photos (a
different flight from the May versions already held, both with real infrared), a
new July 2021 federal photo set, and a small, extremely detailed 2018 drone survey
of Edmonds Marsh — sharp enough to see individual branches, though its promised
infrared band turned out to be an empty placeholder and the file itself a
compressed display copy, not a true original. A planned 15.8-gigabyte NOAA download
was skipped entirely after a quick header check (reading just the file's starting
information and a few sample windows, without downloading it) confirmed it was
identical to a file already on hand. And a speed test found NOAA's servers cap
total download speed at about 2 megabytes per second no matter how many files run
at once, unlike the uncapped university server — a lesson recorded for later.

### 10:42 AM — Four permission emails drafted, waiting on Kam to send

Four emails — each one only Kam can send — were drafted and saved to a file for his
review: one to King County asking for original, uncompressed imagery tiles,
including the 2000 color-infrared photos that are the source for our earliest year;
one to Snohomish County about its licensing position and for flight logs that would
pin down the exact dates the 2020, 2022, and 2024 photos were taken; one to the
state's imagery-sharing consortium asking about access to their sharper 6-inch
products; and one to NOAA about the land-cover map's contradictory licence wording.
(The full numbers behind the 2016 replacement are recorded in IMAGERY_FACTS.md,
section 10, for anyone who wants the technical detail.)

### 10:15–10:40 AM — Federal photos start downloading; a slow start gets fixed

Attention shifted to a new batch: federal aerial photos for 2015, 2017, and 2021
from NAIP — the National Agriculture Imagery Program, a USDA (the federal
agriculture department) effort that photographs the whole country every year or
two, freely available — plus a NOAA land-cover reference map for 2021 (C-CAP). All
of these include a near-infrared band. The download started slowly: one file at a
time at only about 1 megabyte per second, on pace to take 90 minutes for 5.9
gigabytes of data. The tool was changed to fetch six files simultaneously instead of
one, and the download restarted without losing progress. The land-cover map was
kept in a "quarantine" folder that no part of the project's software will read
from, because its posted usage terms contradict themselves about whether it can be
used to help check a computer model — one part of the fine print says no for five
years, another part says something narrower. NOAA was asked to clarify.

### 10:10 AM — The new 2016 photo is safely stored, and the project switches to using it

The new 2016 photo was saved in both of the project's storage locations — the
local computer and Google Drive — as the exact same file, matched by a verified
checksum, its digital fingerprint. The project's catalogue — its master list of
which imagery file represents each year — was updated to point 2016 at this new
file; the old, superseded file wasn't deleted, just kept on hand and clearly
labeled as replaced. An automated catalogue check and a separate pre-flight
check — a go/no-go check the project always runs before expensive computing
jobs — both came back clean. One side effect, expected and by design: the next time
the computer-training process touches 2016 imagery, it automatically rebuilds its
tile cache — small pre-cut pieces of the photo — from scratch, since the system
always checks whether the source photo has changed before reusing old pieces.

### 10:05 AM — A measurement bug found and fixed: pixel size was being over-read by 2.5%

A bug turned up in the measuring tools themselves: the inherited method for
computing a photo's true pixel size — how much ground each dot covers — was
consistently reading about 2.5% too high (31.3 cm instead of the correct 30.48 cm,
which is exactly one foot). The cause: that method converts the map's grid into
GPS-style latitude/longitude to measure distances, but this particular map's grid
is tilted relative to true geographic north, and the conversion didn't fully
account for the tilt. It was fixed to convert the units directly and exactly, with
the old approach kept only as a rough cross-check rather than the source of truth.
With the bug fixed, a fair comparison showed the old and new 2016 photos actually
resolve almost exactly the same amount of real detail (a ratio of 1.01) — which
makes sense, since they're built from the same original photographs. This also
revised an early pilot-test reading from earlier that morning (see the summary
below): an "18% more detail" reading from that early test turned out to be an
artifact of this same bug. The real, confirmed advantage of the new photo wasn't
extra sharpness — it was complete coverage of the city and pixels that are the
camera's true, unblurred readings rather than a server-smoothed copy.

### 10:00 AM — A rejection that taught us our own rule was wrong, not the file

When the finished 2016 photo was checked against the project's acceptance rule, it
was unexpectedly rejected — the rule said it only covered 82% of the project's
"study rectangle," the fixed rectangular boundary used to line up every year's
photo so they all overlap exactly. But the file wasn't the problem; the rule was.
That rectangle's northwest corner sits over Puget Sound, and no aerial photo — old
or new — will ever have pixels over open water, so measuring coverage against the
whole rectangle (water included) was never a fair test; the project already knew
roughly 83% of that rectangle is land. A fairer, second measurement was added:
coverage of Edmonds' actual city boundary, water excluded. By that measure, the new
photo covered 100% of the city — the old, clipped photo had covered only 67%.
Verdict: the new photo replaced the old one, with no downsides found.

### 9:00–9:55 AM — Setting up: a new download tool built, tested, and proven on 2016

Kam approved the campaign that morning with four ground rules: cover every
Snohomish County year available on its public map server, free up Drive storage,
get 2016 at its true full sharpness, and treat the three biggest years (2020, 2022,
2024) with extra caution. A review of the old March download tool found 15
defects — including quiet blurring of every photo and silently-hidden gaps when the
server refused a piece — so a new tool was built from scratch, keeping a "ledger"
that records every downloaded piece for resumability and diagnosis. It passed all
12 rehearsals against a deliberately broken practice server, then a small live test
on a real 500-meter patch of the 2016 photo came back clean: pixel-for-pixel exact,
genuine near-infrared confirmed, no hidden quality loss (two early readings from
this test were later corrected — see 10:05 AM above). The full 2016 photo then
downloaded cleanly — 234 pieces, zero failures, 9.5 minutes, with 30 empty pieces
forming a neat staircase over Puget Sound where no photo could ever have data — and
was stitched into one 2.59 GB file, then spot-checked dot for dot with no errors
found.

## 5. Glossary

*Technical terms used above, explained simply.*

- **Anchor** — the 2020 hand-annotated dataset the entire project is built on: real
  tree crowns checked and marked by a person, not guessed by a computer. Every
  other year's imagery is measured against this one. It was never touched or
  replaced during this campaign.
- **Band** — one layer of color information in a photo. An ordinary photo has three
  bands (red, green, blue); some of ours have a fourth, near-infrared. A
  black-and-white photo has just one band — brightness only, no color.
- **Bilinear ("blur-resample")** — a way of filling in a photo that blends
  neighboring pixels together, softening detail. The opposite of nearest-neighbor,
  which copies the camera's real pixel values unchanged ("unresampled").
- **C-CAP** — a NOAA (the federal ocean and weather agency) reference map that
  classifies coastal land into categories like forest, grass, pavement, and water.
  Wanted to independently check the project's own tree-detection results against,
  not to train the computer model on.
- **Catalogue** — the master list the project's software reads to know exactly
  which imagery file represents each year. Updating an entry is what makes a newly
  downloaded photo the one actually used going forward.
- **Checksum / fingerprint** — a short code calculated from a file's exact contents;
  if even one bit of the file changes, the fingerprint changes too, so it's used to
  prove a copy is exact.
- **Chunk / piece** — one of the many postcard-sized pieces a map server hands out
  at a time; the pieces are stitched back together into one big picture.
- **Dot-for-dot / byte-for-byte check** — comparing two files value by value to
  confirm they're truly identical, not just similar-looking.
- **Drive letters (C:, D:, G:)** — the project's computer has two real, physical
  hard drives: C: (small, built-in, holds Windows and everyday programs) and D:
  (large, used for the bulk of this project's data). Google Drive isn't a physical
  disk at all — it's cloud storage — but Windows makes it appear as a third drive,
  "G:," for convenience.
- **Header check** — confirming what's inside a file, or whether two files are
  identical, by reading just its starting information and a few small sample
  pieces over the internet — without downloading the whole thing.
- **Ledger** — a running receipt a download tool keeps of every piece it downloads:
  its size, its fingerprint, and how long it took. Lets an interrupted download
  resume, and lets slow spots be diagnosed.
- **NAIP** — the National Agriculture Imagery Program, a USDA (the federal
  agriculture department) effort that photographs the entire country from the air
  every year or two, mainly to monitor farmland. The photos are free to use and
  happen to cover Edmonds too.
- **NIR (near-infrared)** — a color of light just past red, invisible to human eyes
  but visible to cameras. Healthy leaves reflect it strongly, making it the single
  most useful clue for telling trees and plants apart from roads, roofs, and
  everything else in a photo.
- **Offline test** — a rehearsal where a new tool runs against a fake, scripted
  stand-in for a real map server, built to fail in specific ways, to prove the tool
  handles problems correctly before it ever touches the real thing.
- **Pilot** — a small trial download from the actual, real server (as opposed to an
  offline test), done over a small area before committing to a large, expensive
  download.
- **Pixel / pixel size ("resolution")** — a pixel is one dot in a digital photo;
  pixel size is how much real ground that one dot covers. Smaller pixel size means
  finer detail. "True 1-foot" means each dot genuinely represents one foot of
  ground, as measured by the camera — not a "zoomed-in" copy where a computer has
  invented extra, blurrier dots to look more detailed than it really is.
- **Pre-flight check** — an automated check the project runs before any expensive
  computing job, to catch problems early rather than waste time or money on a run
  that was doomed from the start.
- **Provenance** — the documented history of where a file actually came from and
  how it was produced. Better provenance means the project can trace a file back to
  its original source with more confidence.
- **Quarantine (folder)** — a folder set aside so that no part of the project's
  software will automatically read from it — used when a file's licensing terms
  aren't yet clear enough to trust it for use.
- **Staircase pattern** — a diagonal, step-shaped area with no photo data, tracing
  a shoreline — there's no land under open water for any photo to capture.
- **Study rectangle** — the fixed rectangular boundary the project uses so every
  year's photo lines up on the same grid. Because Edmonds sits on Puget Sound, part
  of this rectangle is always open water with no usable photo data — which is why
  the project also checks coverage against the actual city boundary, not just the
  rectangle.
- **Superseded** — labeled as replaced by a newer, better file. A superseded file is
  never deleted, just kept on hand and clearly marked so it's not used by mistake.
- **Tile cache** — small, pre-cut pieces of a photo, saved ahead of time so the
  computer-training process doesn't have to re-cut them on every run. Whenever the
  source photo changes, the project automatically notices and rebuilds these
  pieces — a bit of one-time extra work done automatically, not a sign of a
  problem.
- **Upload staging area (cache)** — a temporary holding folder on a computer's own
  hard drive where an app like Google Drive copies a file first, before slowly
  sending it up to the cloud in the background. On this project's laptop, that
  holding area sat on the small C: drive — which is what was actually filling up,
  not Google's cloud storage itself.
- **USGS** — the U.S. Geological Survey, the federal agency that conducted some of
  the original aerial photography this project tracked down, including the 2002
  flight.
- **WAGDA** — the Washington GIS Data Archive, a University of Washington service
  that hosts original, uncompressed government survey imagery for public download.
  It turned out to be the source of the 2002 photo's true original tiles.
