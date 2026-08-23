"""Gate v1: every verbatim_quote / alt_verbatim_quote on PUBLISHED/INFERRED/MEASURED rows must appear (whitespace-normalised,
ellipsis-split) in SOME saved fetch under the agent/verify dirs or the session's own saved files."""
import csv, re, os, sys, html, json
CSV=r"D:\edmonds-pipeline\treedata\Scripts\qc\imagery_pixelsize_and_date.csv"
ROOTS=[r"C:/Users/Kameron/AppData/Local/Temp/claude/D--edmonds-pipeline-treedata-Scripts/38ce7527-5e87-4d98-b55b-f039524783e8/scratchpad/agents", r"C:/Users/Kameron/AppData/Local/Temp/claude/D--edmonds-pipeline-treedata-Scripts/38ce7527-5e87-4d98-b55b-f039524783e8/scratchpad/snoco", r"D:/edmonds-pipeline/treedata/Scripts/qc/imagery_date_evidence/raw_records", r"D:/edmonds-pipeline/treedata/Scripts/qc/imagery_date_evidence/king2000"]
def norm(s):
    s=html.unescape(s); s=s.replace("\\\"","\"").replace("\\\\","\\").replace("\u2019","'").replace("\u201c","\"").replace("\u201d","\"")
    s=re.sub(r"\s+","",s); return s.strip().lower()
corpus=[]
for root in ROOTS:
    for dp,dn,fn in os.walk(root):
        if "__pycache__" in dp or dp.replace(chr(92),"/").endswith("snoco/win"): continue
        for f in fn:
            p=os.path.join(dp,f)
            if os.path.getsize(p)>60_000_000: continue
            if re.search(r"(?i)finding|prediction|provenance|results?\.json|notes|summary|report|deliverable|\.md$|\.py$|scored|shortlist|flyable|criteria|known\.json|request_urls|accept|gated|constraint|gradient|ctrl", f): continue
            if f.lower().endswith((".tif",".png",".jpg",".npy",".gpkg",".pdf",".zip",".bin",".pyc",".dbf",".sid",".gif",".jar")): continue
            try: t=open(p,"rb").read().decode("utf-8","replace")
            except Exception: continue
            # also strip html tags to a text version
            corpus.append((p,norm(t),norm(re.sub(r"<[^>]+>"," ",t))))
print("corpus files:",len(corpus))
def find(frag):
    f=norm(frag)
    if len(f)<12: return "short"
    hits=[p for p,t,tt in corpus if f in t or f in tt]
    return hits
rows=list(csv.DictReader(open(CSV,encoding="utf-8")))
bad=0
for r in rows:
    for col in ("verbatim_quote","alt_verbatim_quote"):
        q=r.get(col,"") or ""
        if not q.strip("-( ") or q.startswith("(") and ":" not in q: continue
        # measured/local descriptions are not page quotes
        if re.match(r"^(SHOTDATE|ShotDate|DATE_STR|Identity MEASURED|MEASURED|\(measured|\(photo|SDATE|density)",q) and "http" not in (r["source_url"] if col=="verbatim_quote" else r["alt_source_url"]): 
            pass
        frags=[x for x in re.split(r"\s*(?:\.\.\.|\[[^\]]*\]|\((?:first of|city|= |date-only|the DOQQ|King County|stray|also|callout)[^)]*\)|Layer description:|Dates transfer because[^.]*\.|\u2026|\[and, in Appendix[^\]]*\]|\[sic[^\]]*\]|\(callout[^)]*\)|\(stray[^)]*\)|\(photo-centre[^)]*\)|\(date field[^)]*\))\s*",q) if x.strip()]
        res=[]
        for fr in frags:
            # strip leading/trailing parenthetical commentary and quotes
            fr=fr.strip(" '\"")
            h=find(fr)
            res.append((fr[:70],"short" if h=="short" else len(h)))
        miss=[x for x in res if x[1]==0]
        status="OK" if not miss else "MISS"
        if miss: bad+=1
        print(f"{status:4s} {r['file'][:34]:34s} {col:18s} frags={len(frags)} " + (" | ".join(f"'{m[0]}'" for m in miss) if miss else ""))
print("rows with unmatched fragments:",bad)
