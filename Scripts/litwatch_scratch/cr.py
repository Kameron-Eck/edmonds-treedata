import json, urllib.request, urllib.parse, sys
def A(x):
    return str(x).encode('ascii','replace').decode('ascii')
def q(s, n=3):
    u = 'https://api.crossref.org/works?rows=%d&query.bibliographic=%s' % (n, urllib.parse.quote(s))
    r = urllib.request.Request(u, headers={'User-Agent':'edmonds-litreview/1.0 (mailto:kameron4321@gmail.com)'})
    d = json.load(urllib.request.urlopen(r, timeout=45))
    for it in d['message']['items']:
        au = it.get('author', [])
        a = (au[0].get('family','?') + (' et al.' if len(au) > 1 else '')) if au else '?'
        yr = it.get('issued',{}).get('date-parts',[[None]])[0][0]
        print(f"  {A(a)} ({yr}) | {A(it.get("title",["?"])[0])[:95]}")
        print(f"     {A(it.get("container-title",["?"])[0])[:70]} | doi:{it.get("DOI")}")
    print()
for s in ["Automatic radiometric normalization of multitemporal satellite imagery with the iteratively re-weighted MAD transformation",
          "Relaxation-Based Radiometric Normalization for Multitemporal Cross-Sensor Satellite Images",
          "pseudo-invariant features relative radiometric normalization multitemporal imagery Schott"]:
    print("QUERY:", s[:70]); q(s)
