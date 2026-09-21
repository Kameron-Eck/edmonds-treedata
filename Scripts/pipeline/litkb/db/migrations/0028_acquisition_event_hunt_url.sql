-- litkb 0028 — the acquisition-event contract: `hunt-url` is a route.
--
-- WHY. Until now a PDF could reach litkb.file_versions by two doors and only one of them wrote
-- down how it got there. `litkb.acquire.run.acquire()` records EVERY attempt through
-- litkb.record_acquisition_attempt (0011); `litkb.hunt.hunt()`'s web-source block landed a file,
-- bound it through admit_web(pdf_path=...) and recorded nothing at all, so a bound file could have
-- no row anywhere naming the URL it came from. The Python half of the contract, its detail keys and
-- the verifier live in `pipeline/litkb/acquire/events.py`; this is the one thing that could not be
-- done in Python, because `route` is a closed CHECK.
--
-- WHY NOT `browser`. `browser` means a HUMAN fetched the file and handed it in
-- (`litkb acquire --from-file`, and the `manual-step` instruction row). The S2 acceptance counter
-- `operator_interventions` reads exactly that: a manual route on the new work is an intervention.
-- Folding an automated URL fetch into `browser` would make every hunted web source read as a human
-- having stepped in, which is the opposite of what the counter is for.
--
-- SCOPE. One CHECK constraint replaced. No function body is touched, so the
-- two-branches-one-function hazard `_reserved.txt` warns about does not apply; checked rather than
-- assumed on 2026-09-20 — `git log --all --diff-filter=A` over this directory shows no migration
-- numbered 0028 or above on any local or remote ref.

SET LOCAL search_path = litkb, public;

ALTER TABLE acquisition_attempts DROP CONSTRAINT acquisition_attempts_route_check;
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_route_check CHECK (route IN (
  'open_access', 'annas', 'scihub', 'browser', 'hunt-url'));

-- end of 0028
