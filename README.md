# SHP Översikt

Publik översiktssida över leasingavtal, försäkringar och modellreleaser för
Shiny Happy People Concept Agency AB (559099-6285) och Shiny Happy People
Ad Agency AB (556787-8722).

## Bygga om

Sidan genereras från två register som ligger lokalt, utanför det här repot:

```
AGENTER/ASSISTENT/FILES/Shiny Admin/dokument.json
AGENTER/ASSISTENT/FILES/Shiny Admin/modellreleaser.json
```

```bash
python3 build.py
git add index.html && git commit -m "Uppdaterad översikt" && git push
```

Nedräkningarna ("4 mån kvar", "180 dgr kvar") räknas ut i webbläsaren, inte vid
bygget. Sidan visar därför rätt antal dagar även om den inte byggts om på
månader. Bygg bara om när innehållet faktiskt ändrats.

## Integritet

Sidan är publik. Två skydd finns inbyggda i `build.py`:

1. **`PUBLIKA_MODELLFALT`** släpper bara igenom modellens namn. Personnummer,
   e-post, telefon och adress lämnar aldrig det lokala registret.
2. **`maskera_pnr()`** ersätter personnummer i all fritext med
   `[personnr dolt]`. Noteringarna innehåller personnummer på styrelseledamöter,
   borgensmän och revisorer.

Ett sista skyddsnät i `main()` söker igenom den färdiga HTML:en efter
personnummer och avbryter bygget om något slunkit igenom. **Ta inte bort det.**

Lägg aldrig till fält i `PUBLIKA_MODELLFALT` utan att tänka efter. Det som
publiceras här kan inte tas tillbaka.
