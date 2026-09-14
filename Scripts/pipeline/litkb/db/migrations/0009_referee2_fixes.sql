-- litkb 0009 — fixes after the second P1 referee (Reports/LITKB_P1_REFEREE2_2026-09-13.md, E-4).
-- Applied migrations are checksum-locked, so this file REPLACES the D-4 admissions constraint of
-- 0008 and the admitter checks of 0001. Those texts are now history: a mutation of them is dead code.
--
--   E-4  session and agent labels are compared TRIMMED and case-sensitive, on both sides.
--        "Trimmed" strips space, tab, LF, CR, FF and VT (btrim with no second argument strips
--        only spaces, so ' \t' would count as a label).
--        * the admitter's agent and session must be non-blank after trim (0001 checked only <> '');
--        * the approver's agent and session must be non-blank after trim (0008 checked neither);
--        * the approver's session must differ from the admitter's after trim on both, so
--          'sessA ' does not count as another session than 'sessA'. Case is kept: labels are
--          opaque ids, and 'SESSA' is a different label from 'sessA'.
--        The IS NOT NULL clauses stay load-bearing: btrim(NULL) <> '' is NULL, and a CHECK that
--        evaluates to NULL passes.

SET LOCAL search_path = litkb, public;

ALTER TABLE admissions DROP CONSTRAINT admissions_admitter_agent_check;
ALTER TABLE admissions DROP CONSTRAINT admissions_admitter_session_check;
-- BEGIN guard: admitter labels non-blank after trim
ALTER TABLE admissions ADD CONSTRAINT admissions_admitter_not_blank CHECK (
  btrim(admitter_agent, E' \t\n\r\f\x0b') <> '' AND btrim(admitter_session, E' \t\n\r\f\x0b') <> '');
-- END guard: admitter labels non-blank after trim

ALTER TABLE admissions DROP CONSTRAINT admissions_second_session_signs_off;
ALTER TABLE admissions ADD CONSTRAINT admissions_second_session_signs_off CHECK (
  (approver_agent IS NULL AND approver_session IS NULL AND approved_at IS NULL)
  OR (approver_agent IS NOT NULL AND approver_session IS NOT NULL AND approved_at IS NOT NULL
      AND btrim(approver_agent, E' \t\n\r\f\x0b') <> ''
      AND btrim(approver_session, E' \t\n\r\f\x0b') <> ''
      AND btrim(approver_session, E' \t\n\r\f\x0b') <> btrim(admitter_session, E' \t\n\r\f\x0b')));

-- end of 0009
