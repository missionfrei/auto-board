#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Board Generator (Missionfrei / GoRemote)
--------------------------------------------------
Baut die index.html aus (1) automatischen Job-Feeds und (2) einer
manuellen Schicht (manual-jobs.json), die NIE automatisch geloescht wird.

- Live-Lauf (auf GitHub Actions):   python build_auto.py
- Lokaler Demo-Lauf (Cowork, kein Netz): python build_auto.py --mock

Design: uebernimmt template.html (das aktuelle Board) unveraendert und
ersetzt nur die 7 Bereichs-Sektionen. Login-Gate, Chips, Favoriten-Sterne,
Freelance, Toolbox, Footer bleiben wie sie sind.
"""
import json, re, sys, os, datetime, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.html")
MANUAL   = os.path.join(HERE, "manual-jobs.json")
OUT      = os.path.join(HERE, "index.html")
MOCK     = "--mock" in sys.argv
TODAY    = datetime.date.today().strftime("%d.%m.%Y")

# ---------- 7 Bereiche: Reihenfolge, Farbe, Label ----------
BEREICHE = [
    ("service",  "#0e7a52", "🟢 Service"),
    ("buero",    "#b07d10", "🟡 Büro & Orga"),
    ("start",    "#c2610c", "🟠 Schnell-Start"),
    ("sprache",  "#6d3fb0", "🟣 Sprache & Text"),
    ("marketing","#1e57b0", "🔵 Marketing & Kreativ"),
    ("vertrieb", "#b3261e", "🔴 Vertrieb & Sales"),
    ("it",       "#33333b", "⚫ IT & Tech"),
]

# ---------- Bereich-Zuordnung nach Stichwoertern (Titel/Tags) ----------
BEREICH_KW = {
    "service":  ["kundenservice","kundenbetreu","customer support","customer service","customer care","customer success","support agent","service agent","reservation","booking","reise","travel","hospitality","concierge","call center","callcenter","kundenberat","beschwerde"],
    "buero":    ["buchhalt","accounting","accountant","finance","finanzbuch","lohn","payroll","steuerfach","controlling","sachbearbeit","backoffice","back office","back-office","assistenz","assistant","verwaltung","admin","office manager","datenerfassung","data entry","dateneingabe"],
    "start":    ["tester","testing","usability","umfrage","survey","data annotation","annotator","rater","transcrib","transcription","microtask","mikrojob","nebenjob","clickworker","crowdwork"],
    "sprache":  ["übersetz","ubersetz","translat","lektor","proofread","texter","content writer","copywriter","redaktion","tutor","nachhilfe","language teacher","sprachlehrer"],
    "marketing":["marketing","social media","seo","content creator","content manager","grafik","design","designer","creative","video","brand","paid ads","performance market","kampagne","community manager"],
    "vertrieb": ["sales","vertrieb","sdr","sales development","setter","closer","business development","account executive","akquise","inside sales"],
    "it":       ["developer","engineer","software","devops","entwickl","programmier","backend","frontend","fullstack","full stack","data scientist","data analyst","qa engineer","it-support","it support","system admin","kotlin","python","javascript","react"],
}
BEREICH_ORDER = [b[0] for b in BEREICHE]

DE_MARKERS = ["deutsch","german","(m/w/d)","m/w/d","mwd","stelle","mitarbeiter","kundenbetreu","buchhalt","vertrieb","home office","homeoffice"]
WORLD_MARKERS = ["worldwide","anywhere","weltweit","global","work from anywhere"]
EU_MARKERS = ["europe","eu ","emea","cet","european"]
EINSTEIGER_MARKERS = ["junior","entry","einsteiger","quereinstieg","quereinsteiger","no experience","keine erfahrung","berufseinsteiger","trainee","aushilfe","praktik"]
BLOCK = ["werkstud","working student"]   # Paul: keine Werkstudenten

def esc(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").strip()

def clean_text(s, n=170):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n].rsplit(" ",1)[0] + ("…" if len(s) > n else "")

def detect_bereich(text):
    t = text.lower()
    for ber in BEREICH_ORDER:
        for kw in BEREICH_KW[ber]:
            if kw in t:
                return ber
    return None   # kein Match -> nicht aufnehmen (haelt das Board fokussiert)

def detect(job):
    """Ergaenzt lang/region/level anhand des Textes."""
    t = (job["title"] + " " + job.get("raw_loc","") + " " + job.get("raw_tags","") + " " + job.get("info","")).lower()
    lang = "de" if any(m in t for m in DE_MARKERS) else "en"
    if any(m in t for m in WORLD_MARKERS): region = "world"
    elif any(m in t for m in EU_MARKERS):  region = "eu"
    elif "germany" in t or "deutschland" in t or lang == "de": region = "de"
    else: region = "world"
    level = "einsteiger" if any(m in t for m in EINSTEIGER_MARKERS) else "erfahren"
    return lang, region, level

# ---------- Feeds ----------
def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (MissionfreiBot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8","replace"))

def from_arbeitnow(raw):
    out=[]
    for j in raw.get("data", []):
        out.append(dict(title=j.get("title",""), company=j.get("company_name",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=" ".join(j.get("tags",[]) or [])+" "+" ".join(j.get("job_types",[]) or []),
            raw_loc=j.get("location","") + (" remote" if j.get("remote") else "")))
    return out

def from_remotive(raw):
    out=[]
    for j in raw.get("jobs", []):
        out.append(dict(title=j.get("title",""), company=j.get("company_name",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=(j.get("category","")+" "+" ".join(j.get("tags",[]) or [])),
            raw_loc=j.get("candidate_required_location","")))
    return out

SOURCES = [
    ("arbeitnow", "https://www.arbeitnow.com/api/job-board-api", from_arbeitnow),
    ("remotive",  "https://remotive.com/api/remote-jobs",        from_remotive),
    # M2: jobicy, remoteok, weworkremotely (RSS), himalayas, working nomads ...
]

def gather():
    jobs=[]
    if MOCK:
        for name in ("arbeitnow","remotive"):
            p=os.path.join(HERE,"mock",f"{name}.json")
            if os.path.exists(p):
                raw=json.load(open(p,encoding="utf-8"))
                fn={"arbeitnow":from_arbeitnow,"remotive":from_remotive}[name]
                jobs+=fn(raw); print(f"[mock] {name}: {len(fn(raw))}")
        return jobs
    for name,url,fn in SOURCES:
        try:
            raw=http_json(url); got=fn(raw); jobs+=got
            print(f"[feed] {name}: {len(got)}")
        except Exception as e:
            print(f"[feed] {name} FEHLER (uebersprungen): {e}")
    return jobs

# ---------- Aufbereiten ----------
def process(raw_jobs):
    seen=set(); result=[]
    for j in raw_jobs:
        if not j.get("url") or not j.get("title"): continue
        blob=(j["title"]+" "+j.get("raw_tags","")+" "+j.get("info","")).lower()
        if any(b in blob for b in BLOCK): continue
        ber=detect_bereich(j["title"]+" "+j.get("raw_tags",""))
        if not ber: continue
        lang,region,level=detect(j)
        # Fokus: deutschsprachig ODER weltweit/EU-Service/Einsteiger.
        # Englische IT/Sales/Marketing/Vertrieb raus (das ist nicht Pauls Publikum).
        keep = (lang=="de") or (region in ("world","eu") and ber in ("service","start","sprache","buero"))
        if not keep: continue
        if ber=="it" and lang!="de": continue          # IT nur deutschsprachig
        if ber=="vertrieb" and lang!="de": continue     # Sales nur deutschsprachig
        u=j["url"].rstrip("/")
        if u in seen: continue
        seen.add(u)
        result.append(dict(title=j["title"], company=j.get("company",""),
            url=j["url"], info=j.get("info","") or "Remote-Stelle - Details ueber den Link.",
            lang=lang, region=region, level=level, bereich=ber, date=TODAY, fd=False))
    return result

def load_manual():
    if not os.path.exists(MANUAL): return []
    try: data=json.load(open(MANUAL,encoding="utf-8"))
    except Exception as e: print("manual-jobs.json Fehler:",e); return []
    out=[]
    for j in data:
        out.append(dict(title=j["title"], company=j.get("company",""), url=j["url"],
            info=j.get("info",""), lang=j.get("lang","de"), region=j.get("region","de"),
            level=j.get("level","einsteiger"), bereich=j.get("bereich","service"),
            date=j.get("date",TODAY), fd=bool(j.get("fd", True))))
    return out

# ---------- Render ----------
def region_tag(r): return {"world":'<span class="tag world">🌍 Weltweit</span>',
    "eu":'<span class="tag eu">🇪🇺 EU</span>',"de":'<span class="tag de">🇩🇪 DE</span>'}.get(r,'')
def level_tag(l): return '<span class="tag lvl">🌱 Einsteiger</span>' if l=="einsteiger" else '<span class="tag">📈 Mit Erfahrung</span>'
def lang_tag(l):  return '<span class="tag delang">Deutsch</span>' if l=="de" else '<span class="tag">Englisch</span>'
def fd_tag(fd):   return '<span class="tag" style="background:#f3ead4;color:#a8842e;font-weight:650">⭐ Für dich</span>' if fd else ''

def card(j):
    return (f'<div class="card" data-bereich="{j["bereich"]}" data-level="{j["level"]}" data-lang="{j["lang"]}">\n'
            f'  <h3>{esc(j["title"])}</h3>\n  <div class="company">{esc(j["company"])}</div>\n'
            f'  <p class="info">{esc(j["info"])}</p>\n'
            f'  <div class="meta">{region_tag(j["region"])}{level_tag(j["level"])}{lang_tag(j["lang"])}{fd_tag(j["fd"])}'
            f'<span class="tag date">📅 {j["date"]}</span></div>\n'
            f'  <div class="go"><a href="{j["url"]}" target="_blank" rel="noopener">Zur Stelle →</a></div>\n</div>')

# Deckel pro Bereich - kippt den Mix Richtung Service/Buero statt IT-Flut
CAP={"service":70,"buero":50,"start":30,"sprache":30,"marketing":25,"vertrieb":25,"it":15}
def build_sections(jobs):
    by={b:[] for b in BEREICH_ORDER}
    for j in jobs: by[j["bereich"]].append(j)
    for b in by:  # manuelle (fd) immer behalten + zuerst, Rest gedeckelt
        by[b].sort(key=lambda x:(not x["fd"], x["date"]), reverse=False)
        fd=[j for j in by[b] if j["fd"]]; rest=[j for j in by[b] if not j["fd"]]
        by[b]=fd+rest[:max(0, CAP.get(b,40)-len(fd))]
    html=[]
    for ber,color,label in BEREICHE:
        cards=by[ber]
        if not cards: continue
        html.append(f'<section data-ber="{ber}"><h2 style="border-left:4px solid {color};padding-left:12px">{label} <span class="cnt">{len(cards)} Stellen</span></h2>\n<div class="grid">\n'
                    + "\n".join(card(c) for c in cards) + "\n</div>\n</div></section>")
    return "\n\n".join(html), by

def main():
    tpl=open(TEMPLATE,encoding="utf-8").read()
    i0=tpl.find('<section data-ber="service"')
    i1=tpl.find('<section id="freelance"')
    assert i0>0 and i1>0, "Template-Grenzen nicht gefunden"
    head, tail = tpl[:i0], tpl[i1:]

    auto=process(gather())
    manual=load_manual()
    man_urls={m["url"].rstrip("/") for m in manual}
    auto=[a for a in auto if a["url"].rstrip("/") not in man_urls]  # manuell gewinnt
    alljobs=manual+auto

    sections, by = build_sections(alljobs)
    total=len(alljobs); de=sum(1 for j in alljobs if j["lang"]=="de")
    world=sum(1 for j in alljobs if j["region"]=="world"); einst=sum(1 for j in alljobs if j["level"]=="einsteiger")

    # Stats im Head aktualisieren
    def setstat(label,val):
        nonlocal head
        head=re.sub(r'(<b>)\d+(</b><span>'+re.escape(label)+r')', r'\g<1>'+str(val)+r'\2', head, count=1)
    setstat("Positionen aktuell",total); setstat("weltweit machbar",world)
    setstat("Einsteiger-geeignet",einst); setstat("auf Deutsch",de)

    open(OUT,"w",encoding="utf-8").write(head+sections+"\n\n"+tail)
    print(f"\nGEBAUT: {total} Stellen (auto {len(auto)} + manuell {len(manual)}) | de={de} weltweit={world} einsteiger={einst}")
    for b,_,lbl in BEREICHE: print(f"   {lbl}: {len(by[b])}")
    print("->", OUT)

if __name__=="__main__":
    main()
