# litkb binding fixtures — the arXiv/bioRxiv margin stamp (register E25)

Each `*_p1.txt` is the **first page as `litkb.admit.binding.first_page_text` itself reads it** —
`pdftotext -f 1 -l 1 -layout` — captured on 2026-09-21, stored LF-only (pinned by `.gitattributes`:
a CRLF checkout would change the bytes a title window is scored on).

The PDFs themselves are NOT copied here; they are named by sha256 so the capture can be redone.
Nothing in `qc/test_litkb_binding_stamps.py` opens a PDF, and nothing moves or writes one.

| fixture | PDF (sha256) | where it lives | why it is here |
|---|---|---|---|
| `gulrajani_2020_p1.txt` | `92ea5bb1b5beed6af39f54de49cec2e1acc5450b021410a518cd54cc56e60dd4` | `Literture/_quarantine/Gulrajani_2020_search-lost-domain-generalization__binding-failed__92ea5bb1b5be.pdf` | tracker 151, arXiv 2007.01434 — the right paper, refused at ratio 0.6842 |
| `kumar_2019_p1.txt` | `cc4e4bde39f530f9b873b79109d4d0f4908294d4303745db4f0e70ddc1dd05bf` | `Literture/_quarantine/Kumar_2019_verified-uncertainty-calibration__binding-failed__cc4e4bde39f5.pdf` | tracker 291, arXiv 1909.10155 — the right paper, refused at ratio 0.6410 |
| `mahoney_2023_p1.txt` | `b44fc2801458876e9826cb9801578b13bac18126f743c6f9398dbd569efe7a87` | `Literture/_litkb_staging/filed/Mahoney_2023_assessing-performance-spatial-cross.pdf` | arXiv 2303.07334, stamped the same way — the WRONG-PAPER control: the stamp strip must not let this page bind the two titles above |

To recapture one:

```bash
cd Scripts && PYTHONPATH=pipeline py -3.12 -c "
from litkb.admit import binding as B
t = B.first_page_text(r'<the pdf>').replace('\r\n','\n').replace('\r','\n')
open(r'qc/testdata/litkb_binding_stamps/<name>_p1.txt','wb').write(t.encode('utf-8'))"
```

Why the first line of all three matters: arXiv prints its identifier in a **rotated** strip down the
left margin, and `-layout` emits rotated text in the y-band it occupies — the title's band. So line 0
carries the stamp *and* the title, glued. The mechanism, and why dropping the line would have dropped
the title with it, is in `binding.py` above `_ARXIV_STAMP`.
