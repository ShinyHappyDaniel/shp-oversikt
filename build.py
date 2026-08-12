#!/usr/bin/env python3
"""Bygger den publika SHP-översikten till index.html.

Läser dokument.json och modellreleaser.json i FILES/Shiny Admin/ och skriver en
fristående HTML-sida. Nedräkningar räknas ut i webbläsaren, inte här, så sidan
visar rätt antal dagar även långt efter bygget.

INTEGRITET: sidan publiceras publikt. Modellernas personnummer, e-post, telefon
och adress filtreras bort här och når aldrig HTML:en. Se PUBLIKA_MODELLFALT.

Kör:  python3 build.py
"""
import json
import re
from datetime import date
from html import escape
from pathlib import Path

ROT = Path(__file__).resolve().parent
ADMIN = ROT.parent.parent / "FILES" / "Shiny Admin"
DOKUMENT = ADMIN / "dokument.json"
RELEASER = ADMIN / "modellreleaser.json"
UT = ROT / "index.html"

# Enda modellfälten som får lämna maskinen. Allt annat om en modell är
# tredje parts personuppgift och stannar i det lokala registret.
PUBLIKA_MODELLFALT = {"namn"}

BOLAGSNAMN = {
    "concept": "Concept Agency",
    "ad": "Ad Agency",
    "båda": "Båda bolagen",
    "privat": "Privat",
    "": "Ospecificerat",
}

VARNING_GUL = 90   # dagar
VARNING_ROD = 30   # dagar

# Org.nr ser ut som personnummer men ska synas.
ORGNUMMER = {"559099-6285", "556787-8722"}
PNR = re.compile(r"\b(?:19|20)?\d{6}[-+]\d{4}\b")


def maskera_pnr(text: str) -> str:
    """Maskerar personnummer i fritext innan den publiceras.

    Noteringarna i dokument.json innehåller personnummer på styrelseledamöter,
    borgensmän och revisorer. Det är tredje parts personuppgifter och hör inte
    hemma på en publik sida, oavsett vad sidan i övrigt visar.
    """
    return PNR.sub(
        lambda m: m.group(0) if m.group(0) in ORGNUMMER else "[personnr dolt]", text
    )


# ---------------------------------------------------------------- villkor

def bedom_villkor(notering: str) -> dict:
    """Läser ut avslutsvillkoret ur noteringens fritext.

    Returnerar nivå 'ok' | 'atgard' | 'overifierat' plus en kort etikett.
    Motsvarar 180-dagarsanalysen i CLAUDE.md: larma aldrig utan att villkoret
    faktiskt är verifierat i avtalets särskilda villkor.
    """
    if "OVERIFIERADE" in notering or "overifierat" in notering.lower():
        return {"niva": "overifierat", "etikett": "Villkor ej verifierade"}
    if "anvisa köpare" in notering or "§16 gäller" in notering:
        return {"niva": "atgard", "etikett": "180-dagarsfrist gäller"}
    if "Avtalet avslutas per slutdatum" in notering:
        return {"niva": "ok", "etikett": "Avslutas per slutdatum"}
    if "lösa ut" in notering or "inlösen" in notering.lower() or "Löst ut" in notering:
        return {"niva": "atgard", "etikett": "Inlösen pågår"}
    return {"niva": "overifierat", "etikett": "Villkor ej granskade"}


def har_konflikt(notering: str) -> tuple[str, str]:
    """Delar upp noteringen i (konflikttext, resten).

    En DATUMKONFLIKT-notis lyfts ut och visas som egen varning, så den ska inte
    stå kvar i brödtexten och sägas två gånger.
    """
    trav = re.search(r"\s*DATUMKONFLIKT[^:]*:\s*(.+)$", notering, re.S)
    if not trav:
        return "", notering
    return trav.group(1).strip(), notering[: trav.start()].rstrip()


# ---------------------------------------------------------------- laddning

def las_dokument() -> list[dict]:
    return json.loads(DOKUMENT.read_text(encoding="utf-8"))


def las_releaser() -> dict:
    return json.loads(RELEASER.read_text(encoding="utf-8"))


def rensa_modell(release: dict) -> dict:
    """Kopierar en release utan känsliga personuppgifter."""
    ren = {k: v for k, v in release.items() if k != "modell"}
    ren["modell"] = {
        k: v for k, v in release["modell"].items() if k in PUBLIKA_MODELLFALT
    }
    return ren


def bygg_data() -> dict:
    dokument = las_dokument()
    reg = las_releaser()

    leasing, ovriga, forsakringar = [], [], []
    for d in dokument:
        d["notering"] = maskera_pnr(d["notering"])
        kat = d["kategori"]
        if kat == "Försäkring":
            forsakringar.append(d)
        elif kat == "Leasingavtal":
            post = dict(d)
            post["villkor"] = bedom_villkor(d["notering"])
            post["konflikt"], post["notering"] = har_konflikt(d["notering"])
            # Ett avtal är en leasing om det har en månadsavgift, eller om namnet
            # säger det. Zeekr-bilen saknar registrerad avgift men är en leasing.
            ar_leasing = d.get("manadsavgift_sek") or d["namn"].startswith("Leasing ")
            (leasing if ar_leasing else ovriga).append(post)

    # Utgångna avtal sist, aktiva sorterade på närmast förfall.
    leasing.sort(key=lambda d: (d["status"] == "utgången", d["slutdatum"] or "9999"))
    forsakringar.sort(key=lambda d: d["slutdatum"] or "9999")
    ovriga.sort(key=lambda d: d["namn"])

    releaser = [rensa_modell(r) for r in reg["releaser"]]
    for r in releaser:
        r["notering"] = maskera_pnr(r["notering"])
    releaser.sort(key=lambda r: (r["nyttjande"]["slut"] or "9999"))

    return {
        "byggd": date.today().isoformat(),
        "varning": {"gul": VARNING_GUL, "rod": VARNING_ROD},
        "bolagsnamn": BOLAGSNAMN,
        "leasing": leasing,
        "ovriga": ovriga,
        "forsakringar": forsakringar,
        "releaser": releaser,
        "luckor": reg["luckor"],
    }


# ---------------------------------------------------------------- mall


MALL = """<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>SHP Översikt</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@400;500&family=Red+Hat+Mono:wght@300;400;500;600&family=Red+Hat+Text:wght@400;500;700&display=swap" rel="stylesheet">
<style>
/* Designsystem hämtat från Face2Face-dashboarden. */
:root {
  --bg-primary: #1B1318;
  --bg-secondary: #211D1F;
  --border: #3a2a32;
  --header-bg: #7D2D49;
  --pink: #FD89B3;
  --text: #FFFFFF;
  --muted: #6F6E6E;
  /* Face2Face använder --muted till korta etiketter. Noteringarna här är
     långa stycken, och #6F6E6E blir för svagt mot #1B1318 i löptext. */
  --muted-text: #9C9799;
  --gron: #5DCA8A;
  --gul:  #F0A050;
  --rod:  #F07070;
  --bla:  #70A0F0;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg-primary); color: var(--text);
  font-family: 'Red Hat Text', sans-serif; font-size: 14px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.app { max-width: 1400px; margin: 0 auto; padding: 20px 20px 80px; }

/* ===== HEADER ===== */
.header { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 2px solid var(--pink); }
.header-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.header-logo img { height: 16px; opacity: .85; display: block; }
.header-user {
  font-family: 'Red Hat Mono', monospace; font-size: 11px; background: var(--header-bg);
  padding: 5px 10px; border-radius: 4px; text-transform: uppercase; letter-spacing: 1px;
}
.header-main {
  font-family: 'Red Hat Mono', monospace; font-size: 30px; font-weight: 300;
  letter-spacing: 4px; text-transform: uppercase; margin-bottom: 2px;
}
.header-sub {
  font-family: 'Red Hat Display', sans-serif; font-size: 16px; font-weight: 400;
  color: var(--muted); margin-bottom: 14px;
}

/* ===== TABS ===== */
.tabs { display: flex; gap: 8px; margin-bottom: 22px; flex-wrap: wrap; }
.tab-btn {
  padding: 12px 26px; background: transparent; border: 1px solid var(--border);
  border-radius: 5px; color: var(--text); font-family: 'Red Hat Mono', monospace;
  font-size: 13px; font-weight: 600; cursor: pointer; text-transform: uppercase;
  letter-spacing: 2px; transition: all .2s;
}
.tab-btn:hover { border-color: var(--pink); }
.tab-btn.active { background: var(--pink); border-color: var(--pink); color: #000; }
.tab-badge { font-size: 11px; opacity: .65; margin-left: 6px; }

/* ===== SEKTION ===== */
.sektion { margin-bottom: 40px; }
.sektion-rubrik {
  font-family: 'Red Hat Mono', monospace; font-size: 10px; color: var(--muted);
  margin-bottom: 14px; text-transform: uppercase; letter-spacing: .5px;
  padding-bottom: 10px; border-bottom: 1px solid var(--border);
}
.sektion-rubrik b { color: var(--pink); font-weight: 600; }

/* ===== KPI ===== */
.kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-bottom: 40px; }
.kpi > div { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 6px; padding: 16px 18px; }
.kpi .tal { font-family: 'Red Hat Mono', monospace; font-size: 26px; font-weight: 300; line-height: 1.15; }
.kpi .etikett {
  font-family: 'Red Hat Mono', monospace; font-size: 10px; color: var(--muted);
  text-transform: uppercase; letter-spacing: .5px; margin-top: 8px;
}

/* ===== KORT ===== */
.lista { display: flex; flex-direction: column; gap: 12px; }
.kort {
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-left: 3px solid var(--muted); border-radius: 6px; padding: 18px;
  transition: border-color .18s;
}
.kort:hover { border-color: var(--pink); }
.kort.niva-rod  { border-left-color: var(--rod); }
.kort.niva-gul  { border-left-color: var(--gul); }
.kort.niva-gron { border-left-color: var(--gron); }
.kort.niva-bla  { border-left-color: var(--bla); }
.kort-topp { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; justify-content: space-between; }
.kort h3 { font-size: 15px; font-weight: 500; line-height: 1.35; }
.meta {
  font-family: 'Red Hat Mono', monospace; font-size: 11px; letter-spacing: .3px;
  color: var(--muted); margin-top: 8px; line-height: 1.7;
}
.meta b { color: var(--text); font-weight: 400; }
.notering { color: var(--muted-text); font-size: 13px; margin-top: 12px; }
.notering b { color: var(--gul); }

/* ===== BADGE ===== */
.badge {
  font-family: 'Red Hat Mono', monospace; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .5px; padding: 3px 9px;
  border-radius: 20px; border: 1px solid var(--border); white-space: nowrap;
}
.b-gron { border-color: var(--gron); color: var(--gron); background: rgba(93,202,138,.12); }
.b-gul  { border-color: var(--gul);  color: var(--gul);  background: rgba(240,160,80,.12); }
.b-rod  { border-color: var(--rod);  color: var(--rod);  background: rgba(240,112,112,.12); }
.b-bla  { border-color: var(--bla);  color: var(--bla);  background: rgba(112,160,240,.12); }
.b-grå  { color: var(--muted); }

/* ===== RÄTTIGHETSRUTOR ===== */
.ratt { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-top: 14px; }
.ratt > div { background: var(--bg-primary); border: 1px solid var(--border); border-radius: 5px; padding: 12px 14px; }
.ratt .r-etikett {
  font-family: 'Red Hat Mono', monospace; font-size: 9.5px; text-transform: uppercase;
  letter-spacing: .5px; color: var(--pink); margin-bottom: 6px;
}
.ratt .r-varde { font-size: 13.5px; font-weight: 500; line-height: 1.4; }

/* ===== ÅTGÄRD ===== */
.atgard {
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-left: 3px solid var(--rod); border-radius: 6px; padding: 16px 18px;
}
.atgard.mild { border-left-color: var(--gul); }
.atgard h3 { font-size: 14px; font-weight: 500; }
.atgard p { color: var(--muted-text); font-size: 13px; margin-top: 6px; }

/* ===== LÄNKAR ===== */
.lankar { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.lankar a {
  font-family: 'Red Hat Mono', monospace; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .5px; text-decoration: none;
  color: var(--muted); border: 1px solid var(--border); border-radius: 20px;
  padding: 5px 12px; transition: all .15s;
}
.lankar a:hover { color: var(--pink); border-color: var(--pink); }

.tom { color: var(--muted); font-style: italic; padding: 8px 0; }
footer {
  margin-top: 50px; padding-top: 20px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 12px;
}
footer code { font-family: 'Red Hat Mono', monospace; font-size: 11px; }

@media (max-width: 640px) {
  .header-main { font-size: 22px; letter-spacing: 2px; }
  .tab-btn { padding: 10px 16px; font-size: 11px; letter-spacing: 1px; }
}
</style>
</head>
<body>
<div class="app">

<div class="header">
  <div class="header-top">
    <div class="header-logo"><img src="logo-vit.png" alt="Shiny Happy People"></div>
    <div class="header-user" id="byggd">__BYGGD__</div>
  </div>
  <div class="header-main">Översikt</div>
  <div class="header-sub">Leasing, försäkringar och modellreleaser</div>
</div>

<div class="tabs" id="tabs">
  <button class="tab-btn active" data-bolag="concept">
    Concept Agency <span class="tab-badge" id="badge-concept"></span>
  </button>
  <button class="tab-btn" data-bolag="ad">
    Ad Agency <span class="tab-badge" id="badge-ad"></span>
  </button>
</div>

<div id="innehall"></div>

<footer>
  Byggd __BYGGD__ från <code>dokument.json</code> och <code>modellreleaser.json</code>.
  Nedräkningar uppdateras i webbläsaren och är alltid aktuella.
  Poster utan bolagstillhörighet (gemensamma, privata, ospecificerade) visas i båda flikarna.
  Modellernas personnummer, e-post och telefon publiceras aldrig här.
</footer>

</div>

<script>
const DATA = __DATA__;

const idag = new Date(); idag.setHours(0, 0, 0, 0);

const dagarKvar = iso => {
  if (!iso || iso.length !== 10) return null;
  return Math.round((new Date(iso + 'T00:00:00') - idag) / 86400000);
};

const niva = d => {
  if (d === null) return 'ingen';
  if (d < 0) return 'utgangen';
  if (d <= DATA.varning.rod) return 'rod';
  if (d <= DATA.varning.gul) return 'gul';
  return 'gron';
};

const NIVA_KLASS = { utgangen: 'rod', rod: 'rod', gul: 'gul', gron: 'gron', ingen: 'grå' };

const dagText = d => {
  if (d === null) return 'Inget slutdatum';
  if (d < 0) return `Utgången för ${Math.abs(d)} dgr sedan`;
  if (d === 0) return 'Går ut idag';
  if (d < 90) return `${d} dgr kvar`;
  const man = Math.round(d / 30.44);
  return man < 24 ? `${man} mån kvar` : `${(d / 365.25).toFixed(1)} år kvar`;
};

const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

const kr = n => n == null ? '' : n.toLocaleString('sv-SE') + ' SEK';
const bolagsnamn = b => DATA.bolagsnamn[b] ?? b;

const gmail = t => t
  ? `<a href="https://mail.google.com/mail/u/0/#all/${t}" target="_blank" rel="noopener">Öppna i Gmail</a>` : '';
const drive = u => u
  ? `<a href="${esc(u)}" target="_blank" rel="noopener">Öppna i Drive</a>` : '';

let aktivtBolag = 'concept';

// Poster utan eget bolag (gemensamma, privata, ospecificerade) hör hemma i båda
// flikarna. Annars försvinner de helt när vyn bara har två bolag.
const GEMENSAMMA = new Set(['båda', 'privat', '']);
const passar = b => b === aktivtBolag || GEMENSAMMA.has(b);

/* ---------------------------------------------------------- renderare */

function kortLeasing(d) {
  const kvar = dagarKvar(d.slutdatum);
  const n = d.status === 'utgången' ? 'ingen' : niva(kvar);
  const villkorKlass = { ok: 'b-gron', atgard: 'b-gul', overifierat: 'b-bla' }[d.villkor.niva];
  return `
  <div class="kort niva-${NIVA_KLASS[n]}">
    <div class="kort-topp">
      <h3>${esc(d.namn)}</h3>
      <span class="badge b-${NIVA_KLASS[n]}">${d.status === 'utgången' ? 'Utgången' : esc(dagText(kvar))}</span>
    </div>
    <div class="meta">
      ${esc(bolagsnamn(d.bolag))} &nbsp;·&nbsp; ${esc(d.part)}
      ${d.avtalsnr ? ' &nbsp;·&nbsp; Avtal <b>' + esc(d.avtalsnr) + '</b>' : ''}
      ${d.manadsavgift_sek ? ' &nbsp;·&nbsp; <b>' + kr(d.manadsavgift_sek) + '</b>/mån exkl moms' : ''}
      <br>${esc(d.startdatum || '?')} &rarr; ${esc(d.slutdatum || '?')}
      &nbsp;·&nbsp; <span class="badge ${villkorKlass}">${esc(d.villkor.etikett)}</span>
    </div>
    ${d.konflikt ? `<p class="notering"><b>⚠ ${esc(d.konflikt)}</b></p>` : ''}
    <p class="notering">${esc(d.notering)}</p>
    <div class="lankar">${drive(d.drive_url)}${gmail(d.gmail_thread)}</div>
  </div>`;
}

function kortForsakring(d) {
  const kvar = dagarKvar(d.slutdatum);
  const n = niva(kvar);
  return `
  <div class="kort niva-${NIVA_KLASS[n]}">
    <div class="kort-topp">
      <h3>${esc(d.namn)}</h3>
      <span class="badge b-${NIVA_KLASS[n]}">${kvar === null ? 'Löpande' : esc(dagText(kvar))}</span>
    </div>
    <div class="meta">
      ${esc(bolagsnamn(d.bolag))} &nbsp;·&nbsp; ${esc(d.part)}
      ${d.avtalsnr ? ' &nbsp;·&nbsp; Nr <b>' + esc(d.avtalsnr) + '</b>' : ''}
      ${d.startdatum || d.slutdatum
        ? '<br>' + esc(d.startdatum || '?') + ' &rarr; ' + esc(d.slutdatum || 'tills vidare') : ''}
      ${d.kontakt ? '<br>' + esc(d.kontakt) : ''}
    </div>
    <p class="notering">${esc(d.notering)}</p>
    <div class="lankar">${drive(d.drive_url)}${gmail(d.gmail_thread)}</div>
  </div>`;
}

function kortRelease(r) {
  const slut = r.nyttjande.slut;
  const kvar = dagarKvar(slut);
  const saknas = r.status === 'saknas';
  const n = saknas ? 'rod' : (slut === null ? 'ingen' : niva(kvar));
  const badge = saknas
    ? '<span class="badge b-rod">Release saknas</span>'
    : `<span class="badge b-${NIVA_KLASS[n]}">${slut === null ? 'Eviga rättigheter' : esc(dagText(kvar))}</span>`;
  return `
  <div class="kort niva-${NIVA_KLASS[n]}">
    <div class="kort-topp">
      <h3>${esc(r.modell.namn)}</h3>
      ${badge}
    </div>
    <div class="meta">
      ${esc(bolagsnamn(r.bolag))} &nbsp;·&nbsp; Slutkund <b>${esc(r.slutkund)}</b>
      &nbsp;·&nbsp; ${esc(r.produktion)}
      <br>Fotograferat ${esc(r.fotodatum)}${r.plats ? ', ' + esc(r.plats) : ''}
      ${r.ersattning_sek ? ' &nbsp;·&nbsp; Ersättning <b>' + kr(r.ersattning_sek) + '</b>' : ''}
      &nbsp;·&nbsp; ${r.signerat
        ? '<span class="badge b-gron">Signerat ' + esc(r.signeringsdatum) + '</span>'
        : '<span class="badge b-rod">Ej signerat</span>'}
    </div>
    <div class="ratt">
      <div><div class="r-etikett">Marknad</div><div class="r-varde">${esc(r.marknad.join(', '))}</div></div>
      <div><div class="r-etikett">Tid</div><div class="r-varde">${esc(r.nyttjande.beskrivning)}</div></div>
      <div><div class="r-etikett">Medier</div><div class="r-varde">${esc(r.medier.join(', '))}</div></div>
      <div><div class="r-etikett">Går ut</div><div class="r-varde">${slut ? esc(slut) : 'Aldrig'}</div></div>
    </div>
    ${r.exklusivitet ? '<p class="notering"><b>Exklusivitet gäller.</b></p>' : ''}
    <p class="notering">${esc(r.notering)}</p>
    <div class="lankar">${gmail(r.gmail_thread)}</div>
  </div>`;
}

function kortOvrig(d) {
  return `
  <div class="kort niva-bla">
    <div class="kort-topp">
      <h3>${esc(d.namn)}</h3>
      <span class="badge b-grå">${esc(bolagsnamn(d.bolag))}</span>
    </div>
    <div class="meta">${esc(d.part)}${d.avtalsnr ? ' &nbsp;·&nbsp; ' + esc(d.avtalsnr) : ''}</div>
    <p class="notering">${esc(d.notering)}</p>
    <div class="lankar">${drive(d.drive_url)}${gmail(d.gmail_thread)}</div>
  </div>`;
}

function kortLucka(l) {
  return `
  <div class="kort niva-gul">
    <div class="kort-topp">
      <h3>${esc(l.produktion)}</h3>
      <span class="badge b-gul">${esc(l.datum)}</span>
    </div>
    <p class="notering">${esc(l.beskrivning)}</p>
    <div class="lankar">${gmail(l.gmail_thread)}</div>
  </div>`;
}

/* ---------------------------------------------------------- åtgärder */

function byggAtgarder(leasing, forsakringar, releaser) {
  const ut = [];

  for (const d of leasing) {
    const kvar = dagarKvar(d.slutdatum);
    if (d.status !== 'utgången' && kvar !== null && kvar <= DATA.varning.gul) {
      ut.push({ akut: kvar <= DATA.varning.rod, rubrik: d.namn,
        text: `Leasingen går ut ${d.slutdatum} (${dagText(kvar)}). ${d.villkor.etikett}.` });
    }
    if (d.villkor.niva === 'overifierat' && d.status === 'aktiv') {
      ut.push({ akut: false, rubrik: d.namn,
        text: 'Avslutsvillkoren är inte verifierade mot avtalets särskilda villkor. Läs framsidan innan du utgår från något slutdatum.' });
    }
    // En konflikt är alltid mer konkret än den generiska villkorsflaggan.
    if (d.konflikt) {
      ut.push({ akut: true, rubrik: d.namn, text: d.konflikt });
    } else if (d.villkor.niva === 'atgard' && d.status === 'aktiv') {
      ut.push({ akut: false, rubrik: d.namn, text: d.villkor.etikett + '. Kontrollera fristen i god tid.' });
    }
  }

  for (const d of forsakringar) {
    const kvar = dagarKvar(d.slutdatum);
    if (kvar !== null && kvar <= DATA.varning.gul) {
      ut.push({ akut: kvar <= DATA.varning.rod, rubrik: d.namn,
        text: `Försäkringen går ut ${d.slutdatum} (${dagText(kvar)}). Bevaka förnyelsen hos ${d.part}.` });
    }
  }

  for (const r of releaser) {
    if (r.status === 'saknas') {
      ut.push({ akut: true, rubrik: `${r.slutkund} — modellrelease saknas`, text: r.notering });
      continue;
    }
    const kvar = dagarKvar(r.nyttjande.slut);
    if (kvar !== null && kvar <= DATA.varning.gul) {
      ut.push({ akut: kvar <= DATA.varning.rod, rubrik: `${r.modell.namn} (${r.slutkund})`,
        text: `Nyttjanderätten går ut ${r.nyttjande.slut} (${dagText(kvar)}). Materialet måste tas ur ${r.medier.join(', ').toLowerCase()} i ${r.marknad.join(', ')}, eller så måste avtalet förlängas.` });
    }
  }

  ut.sort((a, b) => Number(b.akut) - Number(a.akut));
  return ut;
}

/* ---------------------------------------------------------- rendering */

function sektion(titel, antal, innehall, tomText) {
  return `
  <div class="sektion">
    <div class="sektion-rubrik">${esc(titel)} <b>${antal}</b></div>
    <div class="lista">${innehall || `<p class="tom">${esc(tomText)}</p>`}</div>
  </div>`;
}

function rendera() {
  const leasing = DATA.leasing.filter(d => passar(d.bolag));
  const forsakringar = DATA.forsakringar.filter(d => passar(d.bolag));
  const releaser = DATA.releaser.filter(r => passar(r.bolag));
  const ovriga = DATA.ovriga.filter(d => passar(d.bolag));

  const aktivLeasing = leasing.filter(d => d.status === 'aktiv');
  const manad = aktivLeasing.reduce((s, d) => s + (d.manadsavgift_sek || 0), 0);
  const releaserUtgar = releaser.filter(r => {
    const k = dagarKvar(r.nyttjande.slut);
    return k !== null && k <= 365;
  }).length;

  const atgarder = byggAtgarder(leasing, forsakringar, releaser);

  const kpi = [
    [manad.toLocaleString('sv-SE'), 'SEK/mån leasing exkl moms'],
    [aktivLeasing.length, 'Aktiva leasingavtal'],
    [forsakringar.length, 'Försäkringar'],
    [releaser.filter(r => r.signerat).length, 'Signerade releaser'],
    [releaserUtgar, 'Releaser ut inom 1 år'],
    [atgarder.length, 'Punkter att agera på'],
  ].map(([tal, etikett]) =>
    `<div><div class="tal">${esc(tal)}</div><div class="etikett">${esc(etikett)}</div></div>`
  ).join('');

  document.getElementById('innehall').innerHTML =
    `<div class="kpi">${kpi}</div>` +
    sektion('Action required', atgarder.length,
      atgarder.map(a => `<div class="atgard ${a.akut ? '' : 'mild'}">
          <h3>${esc(a.rubrik)}</h3><p>${esc(a.text)}</p></div>`).join(''),
      'Inget kräver åtgärd just nu.') +
    sektion('Leasing', leasing.length, leasing.map(kortLeasing).join(''),
      'Inga leasingavtal för det här bolaget.') +
    sektion('Insurance', forsakringar.length, forsakringar.map(kortForsakring).join(''),
      'Inga försäkringar för det här bolaget.') +
    sektion('Model releases', releaser.length, releaser.map(kortRelease).join(''),
      'Inga modellreleaser för det här bolaget.') +
    sektion('Missing releases', DATA.luckor.length, DATA.luckor.map(kortLucka).join(''),
      'Inga kända luckor.') +
    sektion('Other agreements', ovriga.length, ovriga.map(kortOvrig).join(''),
      'Inga övriga avtal för det här bolaget.');
}

function antalFor(bolag) {
  const t = b => b === bolag || GEMENSAMMA.has(b);
  return DATA.leasing.filter(d => t(d.bolag)).length
       + DATA.forsakringar.filter(d => t(d.bolag)).length
       + DATA.releaser.filter(r => t(r.bolag)).length
       + DATA.ovriga.filter(d => t(d.bolag)).length;
}

document.getElementById('tabs').addEventListener('click', e => {
  const knapp = e.target.closest('button');
  if (!knapp) return;
  aktivtBolag = knapp.dataset.bolag;
  for (const b of document.querySelectorAll('#tabs button')) {
    b.classList.toggle('active', b === knapp);
  }
  rendera();
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

document.getElementById('badge-concept').textContent = antalFor('concept');
document.getElementById('badge-ad').textContent = antalFor('ad');
rendera();
</script>
</body>
</html>
"""


def main() -> None:
    data = bygg_data()
    html = (
        MALL
        .replace("__DATA__", json.dumps(data, ensure_ascii=False))
        .replace("__BYGGD__", escape(data["byggd"]))
    )
    UT.write_text(html, encoding="utf-8")

    # Skyddsnät: personnummer får aldrig hamna i den publicerade filen.
    lackor = [t for t in PNR.findall(html) if t not in ORGNUMMER]
    if lackor:
        raise SystemExit(f"AVBRYTER: personnummer i utdata: {sorted(set(lackor))}")

    print(f"Skrev {UT} ({UT.stat().st_size:,} byte)")
    print(f"  {len(data['leasing'])} leasingavtal, {len(data['forsakringar'])} försäkringar, "
          f"{len(data['releaser'])} releaser, {len(data['luckor'])} luckor")


if __name__ == "__main__":
    main()
