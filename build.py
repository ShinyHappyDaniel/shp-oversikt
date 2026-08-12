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
            (leasing if d.get("manadsavgift_sek") else ovriga).append(post)

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
<link href="https://fonts.googleapis.com/css2?family=Red+Hat+Mono:wght@300;400;500&family=Red+Hat+Text:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root {
  --plum: #7D2D49;
  --plum-djup: #5D1D35;
  --plum-kort: #8B3854;
  --rosa: #FD89B3;
  --gron: #5DCA8A;
  --gul: #F0A050;
  --rod: #F07070;
  --bla: #70A0F0;
  --dis: rgba(255,255,255,.62);
  --linje: rgba(255,255,255,.14);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--plum);
  color: #fff;
  font-family: 'Red Hat Text', system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  padding: 0 0 80px;
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 0 24px; }

/* ---- header ---- */
header { padding: 48px 0 32px; border-bottom: 1px solid var(--linje); margin-bottom: 36px; }
header img { height: 34px; display: block; margin-bottom: 30px; }
h1 {
  font-family: 'Red Hat Mono', monospace; font-weight: 300;
  font-size: clamp(30px, 6vw, 50px); text-transform: uppercase;
  letter-spacing: .16em; line-height: 1.1;
}
.underrubrik { color: var(--dis); margin-top: 12px; font-size: 14px; }

/* ---- filter ---- */
.filter { display: flex; flex-wrap: wrap; gap: 8px; margin: 26px 0 0; }
.filter button {
  font-family: 'Red Hat Mono', monospace; font-size: 11px; font-weight: 400;
  text-transform: uppercase; letter-spacing: .14em;
  background: transparent; color: var(--dis);
  border: 1px solid var(--linje); border-radius: 100px;
  padding: 9px 18px; cursor: pointer; transition: .16s;
}
.filter button:hover { color: #fff; border-color: rgba(255,255,255,.4); }
.filter button[aria-pressed="true"] {
  background: var(--rosa); color: var(--plum-djup);
  border-color: var(--rosa); font-weight: 500;
}

/* ---- sektioner ---- */
section { margin-bottom: 52px; scroll-margin-top: 20px; }
h2 {
  font-family: 'Red Hat Mono', monospace; font-weight: 400; font-size: 13px;
  text-transform: uppercase; letter-spacing: .2em; color: var(--rosa);
  padding-bottom: 12px; border-bottom: 1px solid var(--linje); margin-bottom: 22px;
}
h2 .rakning { color: var(--dis); margin-left: 10px; font-weight: 300; }

/* ---- kpi ---- */
.kpi { display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: 12px; }
.kpi div { background: var(--plum-kort); border-radius: 12px; padding: 20px 18px; }
.kpi .tal {
  font-family: 'Red Hat Mono', monospace; font-weight: 300;
  font-size: 32px; line-height: 1.1; letter-spacing: -.01em;
}
.kpi .etikett {
  font-family: 'Red Hat Mono', monospace; font-size: 10px; text-transform: uppercase;
  letter-spacing: .15em; color: var(--dis); margin-top: 8px;
}

/* ---- kort ---- */
.kort {
  background: var(--plum-kort); border-radius: 12px; padding: 20px 22px;
  margin-bottom: 10px; border-left: 3px solid transparent;
}
.kort.niva-rod { border-left-color: var(--rod); }
.kort.niva-gul { border-left-color: var(--gul); }
.kort.niva-gron { border-left-color: var(--gron); }
.kort.niva-bla { border-left-color: var(--bla); }
.kort-topp { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; justify-content: space-between; }
.kort h3 { font-size: 16px; font-weight: 500; line-height: 1.35; }
.meta {
  font-family: 'Red Hat Mono', monospace; font-size: 11px; letter-spacing: .07em;
  color: var(--dis); margin-top: 7px;
}
.meta b { color: rgba(255,255,255,.85); font-weight: 400; }
.notering { color: var(--dis); font-size: 13.5px; margin-top: 12px; }

/* ---- badge ---- */
.badge {
  font-family: 'Red Hat Mono', monospace; font-size: 10px; font-weight: 500;
  text-transform: uppercase; letter-spacing: .12em;
  padding: 4px 11px; border-radius: 100px; white-space: nowrap;
}
.b-gron { background: rgba(93,202,138,.18); color: var(--gron); }
.b-gul  { background: rgba(240,160,80,.18);  color: var(--gul); }
.b-rod  { background: rgba(240,112,112,.2);  color: var(--rod); }
.b-bla  { background: rgba(112,160,240,.18); color: var(--bla); }
.b-grå  { background: rgba(255,255,255,.1);  color: var(--dis); }

/* ---- rättighetsrutor för modellreleaser ---- */
.ratt { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-top: 15px; }
.ratt div { background: rgba(0,0,0,.16); border-radius: 8px; padding: 12px 14px; }
.ratt .r-etikett {
  font-family: 'Red Hat Mono', monospace; font-size: 9.5px; text-transform: uppercase;
  letter-spacing: .16em; color: var(--rosa); margin-bottom: 5px;
}
.ratt .r-varde { font-size: 14px; font-weight: 500; line-height: 1.35; }

/* ---- åtgärdslista ---- */
.atgard {
  background: rgba(240,112,112,.12); border: 1px solid rgba(240,112,112,.3);
  border-radius: 12px; padding: 18px 22px; margin-bottom: 10px;
}
.atgard.mild { background: rgba(240,160,80,.1); border-color: rgba(240,160,80,.28); }
.atgard h3 { font-size: 15px; font-weight: 500; }
.atgard p { color: rgba(255,255,255,.8); font-size: 13.5px; margin-top: 7px; }

/* ---- länkar ---- */
.lankar { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.lankar a {
  font-family: 'Red Hat Mono', monospace; font-size: 10px; text-transform: uppercase;
  letter-spacing: .13em; text-decoration: none;
  color: var(--dis); border: 1px solid var(--linje);
  border-radius: 100px; padding: 6px 14px; transition: .16s;
}
.lankar a:hover { color: var(--plum-djup); background: var(--rosa); border-color: var(--rosa); }

.tom { color: var(--dis); font-style: italic; padding: 6px 0; }
footer {
  margin-top: 56px; padding-top: 22px; border-top: 1px solid var(--linje);
  color: var(--dis); font-size: 12px;
}
footer code { font-family: 'Red Hat Mono', monospace; font-size: 11px; }
</style>
</head>
<body>
<div class="wrap">

<header>
  <img src="logo-vit.png" alt="Shiny Happy People">
  <h1>Översikt</h1>
  <p class="underrubrik">
    Leasing, försäkringar och modellreleaser för Concept Agency (559099-6285)
    och Ad Agency (556787-8722).
  </p>
  <div class="filter" id="filter">
    <button data-bolag="alla" aria-pressed="true">Alla</button>
    <button data-bolag="concept" aria-pressed="false">Concept Agency</button>
    <button data-bolag="ad" aria-pressed="false">Ad Agency</button>
  </div>
</header>

<section id="kpi-sektion"><div class="kpi" id="kpi"></div></section>

<section>
  <h2>Action required <span class="rakning" id="antal-atgard"></span></h2>
  <div id="atgarder"></div>
</section>

<section>
  <h2>Leasing <span class="rakning" id="antal-leasing"></span></h2>
  <div id="leasing"></div>
</section>

<section>
  <h2>Insurance <span class="rakning" id="antal-forsakring"></span></h2>
  <div id="forsakringar"></div>
</section>

<section>
  <h2>Model releases <span class="rakning" id="antal-release"></span></h2>
  <div id="releaser"></div>
</section>

<section>
  <h2>Missing releases</h2>
  <div id="luckor"></div>
</section>

<section>
  <h2>Other agreements &amp; subscriptions <span class="rakning" id="antal-ovriga"></span></h2>
  <div id="ovriga"></div>
</section>

<footer>
  Byggd __BYGGD__ från <code>dokument.json</code> och <code>modellreleaser.json</code>.
  Nedräkningar uppdateras i webbläsaren och är alltid aktuella.
  Modellernas personnummer, e-post och telefon publiceras aldrig här, de finns bara
  i det lokala registret.
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

let aktivtBolag = 'alla';
const passar = b => aktivtBolag === 'alla' || b === aktivtBolag || b === 'båda';

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
    // En konflikt är alltid mer konkret än den generiska villkorsflaggan,
    // så de dubbleras inte på samma avtal.
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

  document.getElementById('kpi').innerHTML = [
    [manad.toLocaleString('sv-SE'), 'SEK/mån leasing exkl moms'],
    [aktivLeasing.length, 'Aktiva leasingavtal'],
    [forsakringar.length, 'Försäkringar'],
    [releaser.filter(r => r.signerat).length, 'Signerade releaser'],
    [releaserUtgar, 'Releaser ut inom 1 år'],
    [atgarder.length, 'Punkter att agera på'],
  ].map(([tal, etikett]) =>
    `<div><div class="tal">${esc(tal)}</div><div class="etikett">${esc(etikett)}</div></div>`
  ).join('');

  const satt = (id, html, tomText) => {
    document.getElementById(id).innerHTML = html || `<p class="tom">${tomText}</p>`;
  };

  satt('atgarder', atgarder.map(a =>
    `<div class="atgard ${a.akut ? '' : 'mild'}">
       <h3>${esc(a.rubrik)}</h3><p>${esc(a.text)}</p>
     </div>`).join(''), 'Inget kräver åtgärd just nu.');

  satt('leasing', leasing.map(kortLeasing).join(''), 'Inga leasingavtal för valt bolag.');
  satt('forsakringar', forsakringar.map(kortForsakring).join(''), 'Inga försäkringar för valt bolag.');
  satt('releaser', releaser.map(kortRelease).join(''), 'Inga modellreleaser för valt bolag.');
  satt('ovriga', ovriga.map(kortOvrig).join(''), 'Inga övriga avtal för valt bolag.');
  satt('luckor', DATA.luckor.map(kortLucka).join(''), 'Inga kända luckor.');

  document.getElementById('antal-atgard').textContent = atgarder.length;
  document.getElementById('antal-leasing').textContent = leasing.length;
  document.getElementById('antal-forsakring').textContent = forsakringar.length;
  document.getElementById('antal-release').textContent = releaser.length;
  document.getElementById('antal-ovriga').textContent = ovriga.length;
}

document.getElementById('filter').addEventListener('click', e => {
  const knapp = e.target.closest('button');
  if (!knapp) return;
  aktivtBolag = knapp.dataset.bolag;
  for (const b of document.querySelectorAll('#filter button')) {
    b.setAttribute('aria-pressed', String(b === knapp));
  }
  rendera();
});

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
