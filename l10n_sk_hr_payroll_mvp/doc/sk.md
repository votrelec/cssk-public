---
title: SK MVP — mesačný výkaz poistného a príspevkov
summary: Mesačný výkaz poistného a príspevkov pre Sociálnu poisťovňu zostavený z výplatných pások mesiaca — sumy za fondy a príloha po zamestnancoch, export do XML overený voči oficiálnej schéme.
verified: 19.0.1.3.0
---

## Na čo slúži {#purpose}

Zamestnávateľ každý mesiac vykazuje **Sociálnej poisťovni** poistné
a príspevky na starobné dôchodkové sporenie, ktoré za mesiac odvádza:
*Mesačný výkaz poistného a príspevkov* (**MVP**, elektronicky *MVPP*). Výkaz
obsahuje za každý fond sumu za zamestnávateľa a za zamestnanca a prílohu
s riadkom za každého zamestnanca.

Modul výkaz zostaví z výplatných pások mesiaca a vyexportuje ho do súboru XML,
ktorý nahráte na portál Sociálnej poisťovne. Výplatné pásky číta cez spoločný
modul
[module:l10n_cssk_payroll_declaration_base](module:l10n_cssk_payroll_declaration_base),
takže funguje s oboma mzdovými jadrami — pozri
[príručku slovenských miezd](module:l10n_sk_hr_payroll_base#declarations).

Dohody s nepravidelným príjmom sa vykazujú na inom výkaze, VPP — pozri
[module:l10n_sk_hr_payroll_vpp](module:l10n_sk_hr_payroll_vpp).

## Právny rámec {#legal}

Odkazy sú na [zákon o sociálnom poistení](law:sk/2003/461).

- **Povinnosť predložiť výkaz.** Podľa
  [§ 231 ods. 1 písm. g)](law:sk/2003/461#paragraf-231.odsek-1.pismeno-g)
  zamestnávateľ predkladá pobočke *výkaz poistného a príspevkov na starobné
  dôchodkové sporenie* za príslušný kalendárny mesiac **v lehote splatnosti
  ním odvádzaného poistného**, s uvedením dňa určeného na výplatu príjmov,
  ktoré sú vymeriavacím základom zamestnanca, v členení na jednotlivých
  zamestnancov a na jednotlivé fondy, a s určením fyzickej osoby, ktorá plní
  povinnosti voči Sociálnej poisťovni. Nesprávne údaje opravuje *opravným
  výkazom* (druhý bod toho istého písmena).
- **Splatnosť.** Poistné, ktoré platí a odvádza zamestnávateľ, je splatné
  v deň určený na výplatu príjmov; ak taký deň nie je určený, v posledný deň
  nasledujúceho kalendárneho mesiaca —
  [§ 143 ods. 2](law:sk/2003/461#paragraf-143.odsek-2).
- Obsah a spôsob zasielania tlačiva určuje podľa
  [§ 231 ods. 2](law:sk/2003/461#paragraf-231.odsek-2) Sociálna poisťovňa;
  ona zverejňuje aj schému XML, voči ktorej modul výkaz overuje.

## Nastavenie {#setup}

Pred prvým výkazom treba na spoločnosti vyplniť dva údaje:

| Údaj | Kde | Použije sa ako |
|---|---|---|
| *IČO*, 8 až 12 číslic | formulár spoločnosti | `<identifikator>` |
| *Variabilný symbol Sociálnej poisťovne*, presne 10 číslic | pozri nižšie | `<variabilnySymbol>` — číslo, ktoré zamestnávateľovi pridelila Sociálna poisťovňa |

*Variabilný symbol Sociálnej poisťovne* vyplňte priamo vo formulári MVP.
Ukladá sa na spoločnosti a je spoločný s modulmi VPP, ELDP a RLFO, takže sa
zadáva raz; na jeho zmenu treba právo upravovať spoločnosti.

Každý zamestnanec vo výkaze musí mať **rodné číslo** (9 alebo 10 číslic;
lomka a medzery sa ignorujú) v poli *Identifikačné č*.

Telefón a e-mail kontaktnej osoby sa berú zo spoločnosti, meno kontaktnej
osoby je meno užívateľa, ktorý výkaz generuje.

## Zostavenie výkazu {#usage}

*Mzdové hlásenia → SK MVP (sociálne poistenie)*, potom *Nové*.

1. Zvoľte **Rok** a **Mesiac**. *Dátum výplaty* je deň výplaty uvedený
   v `<denVyplaty>`; ak ho nevyplníte, použije sa posledný deň mesiaca.
2. Kliknite na **Generovať**. Modul zoberie výplatné pásky spoločnosti, ktorých
   obdobie leží v danom mesiaci, vytvorí riadok za každého zamestnanca,
   vygeneruje XML a overí ho voči priloženej schéme `MVPP-v2026.xsd`. XML sa
   priloží k záznamu (*Príloha XML*) a záznam prejde do stavu *Vygenerované*.
3. XML stiahnite, nahrajte na portál Sociálnej poisťovne a kliknite na
   **Označiť ako odoslané**. Podaná kópia sa uchová; odoslaný výkaz nemožno
   znova vygenerovať ani zmazať, kým ho nevrátite do konceptu.

**Vrátiť do konceptu** výkaz znova otvorí — napríklad po oprave výplatnej
pásky — a *Generovať* ho potom zostaví nanovo.

Generovanie sa zastaví s hlásením, ak spoločnosti chýba IČO alebo platný
variabilný symbol, ak zamestnanec nemá platné rodné číslo alebo ak za mesiac
neexistuje žiadna výplatná páska.

## Obsah výkazu {#output}

Každý fond sa berie z riadkov výplatných pások s pevným kódom mzdového
pravidla:

| Fond (element) | Zamestnávateľ | Zamestnanec |
|---|---|---|
| nemocenské poistenie (`np`) | SICKEMPLOYER | SICK |
| starobné poistenie (`sp`) | PENSIONEMPLOYER | PENSION |
| invalidné poistenie (`ip`) | DISABILITYEMPLOYER | DISABILITY |
| poistenie v nezamestnanosti (`pvn`) | UNEMPLOYMENTEMPLOYER | UNEMPLOYMENT |
| úrazové poistenie (`up`) | ACCIDENT | — |
| garančné poistenie (`gp`) | GUARANTEEEMPLOYER | — |
| rezervný fond solidarity (`rfs`) | RESERVEFUNDEMPLOYER | — |
| podpora v čase skrátenej práce (`pfp`) | SHORTTIMEEMPLOYER | — |

Úhrn (`spoluPoistne`) je súčet týchto riadkov. Zdravotné poistenie v ňom nie
je — vykazuje sa zdravotnej poisťovni v dávke 514
([module:l10n_sk_hr_payroll_health](module:l10n_sk_hr_payroll_health)).

Riadok prílohy obsahuje rodné číslo, dni poistenia, odpracované hodiny, poistné
a samostatné vymeriavacie základy fondov zamestnanca a zamestnávateľa. Základy
číta z uchovaného mzdového výpočtu: rozlišuje denný strop zamestnanca pri časti
mesiaca, strop zamestnávateľa, odpočítateľnú položku dohody a nestropovaný
úrazový základ. Neodvodzuje ich z hrubej mzdy ani z poistného. Natívne úplné
storno sa vylúči spolu s pôvodnou páskou; zdrojom zostane náhrada.

Ak historické fondové dôkazy chýbajú alebo nesúhlasia, riadny výkaz zachová pre
tieto podklady pôvodný postup z hrubej mzdy a pomenuje ich v upozornení. Presné
známe časti zachovajú skutočné základy. Engine bez voliteľnej evidencie pokračuje
pôvodným postupom. Pred tvrdením o presnom rozdelení fondov overte uvedené
historické podklady; už podané mzdy neprepočítavajte iba na vytvorenie dôkazov.

## Obmedzenia {#limitations}

- Modul ponúka len riadny výkaz (`typVykazu` R); úradné opravy zostávajú mimo
  jeho aktuálneho pracovného postupu.
- Potvrdené pásky sa vyberajú podľa koncového dátumu. Dohody s pravidelným
  príjmom patria do MVP, s nepravidelným príjmom do VPP.
- Príznak výnimky `vynimkaVZ` zostáva 0. Súbežné pracovné vzťahy vyžadujúce
  výnimku treba overiť osobitne.
- Dodáva sa formulár MVPP 2026. XML validácia overuje štruktúru, nie prijatie
  úradom. Pri evidencii podania uchovajte skutočnú potvrdenku portálu.

## Oprava podaného mesačného výkazu {#corrective}

Vyberte **Opravný** a uchovaný podaný MVP tej istej firmy a mzdového
obdobia. Jediný vhodný predchodca sa predvyplní; pri viacerých kandidátoch
vyberte konkrétny výkaz. Oprava exportuje **O** a všetkých aktuálnych
zamestnancov obdobia, nie iba rozdiel. Generovanie, reset, archív podaní
a overenie starších fondových podkladov vlastní spoločný rámec deklarácií.
Pôvodné podané XML zostáva zachované.

Kopírovanie opravy vymaže voľbu nahrádzaného výkazu. Pred zmenou identity
vygenerovanej opravy ju vráťte do návrhu. Ide o prípravu elektronického
opravného výkazu; oprava mzdy, vysporiadanie pohľadávky a skutočná platba
alebo vrátenie peňazí sú samostatné účtovné operácie.

Zdroje: [poučenie SP](https://www.socpoist.sk/api/idsp/download/d360c51e-c8c8-4554-8a3f-4a7344765bf5)
a [aktuálne poučenie prílohy](https://www.socpoist.sk/api/idsp/download/35cd0fa0-ef07-4adb-b296-a4c66b855904).
