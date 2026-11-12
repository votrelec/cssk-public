---
title: SK Prehľad o zrazených a odvedených preddavkoch na daň
summary: Mesačný prehľad o preddavkoch na daň zrazených zamestnancom a o vyplatenom daňovom bonuse, zostavený z výplatných pások mesiaca ako XML pre finančnú správu.
verified: 19.0.2.1.3
---

## Na čo slúži {#purpose}

Každý zamestnávateľ, ktorý zráža zamestnancom preddavky na daň zo mzdy,
podáva správcovi dane každý mesiac **Prehľad o zrazených a odvedených
preddavkoch na daň**. Modul ho zostaví z výplatných pások mesiaca a vyexportuje
ako XML vo formáte finančnej správy, pripravené na nahratie na jej portál.

Funguje s oboma mzdovými jadrami — mzdami Odoo Enterprise aj aplikáciou
mzdy OCA — lebo číta len to, čo obe uvádzajú na výplatnej páske (pozri
[skupinu modulov slovenských miezd](module:l10n_sk_hr_payroll_base#declarations)).
Ročným náprotivkom je
[module:l10n_sk_hr_payroll_annual_tax_report](module:l10n_sk_hr_payroll_annual_tax_report).
Obrazovky, stavy a kontrolu XML zdieľa s ostatnými mzdovými hláseniami
prostredníctvom
[module:l10n_cssk_payroll_declaration_base](module:l10n_cssk_payroll_declaration_base).

## Právny rámec {#legal}

Odkazy sú na [zákon o dani z príjmov](law:sk/2003/595).

- **Povinnosť.** Zamestnávateľ, ktorý je platiteľom dane, predkladá správcovi
  dane prehľad o zrazených a odvedených preddavkoch na daň z príjmov zo
  závislej činnosti, ktoré zamestnancom vyplatil, o zamestnaneckej prémii, o
  daňovom bonuse a o daňovom bonuse na zaplatené úroky za uplynulý kalendárny
  mesiac —
  [§ 39 ods. 9 písm. a)](law:sk/2003/595#paragraf-39.odsek-9.pismeno-a).
- **Lehota.** Prehľad sa podáva do konca kalendárneho mesiaca za predchádzajúci
  kalendárny mesiac — [§ 49 ods. 2](law:sk/2003/595#paragraf-49.odsek-2).
  Prehľad za október treba podať do 30. novembra.
- **Odvod preddavkov.** Nezávisle od prehľadu treba preddavky znížené o
  daňový bonus odviesť najneskôr do piatich dní po dni výplaty zdaniteľnej
  mzdy — [§ 35 ods. 6](law:sk/2003/595#paragraf-35.odsek-6). Túto platbu
  modul nevytvára.
- **Daňový bonus** upravuje [§ 33](law:sk/2003/595#paragraf-33); vypočítajú
  ho mzdy, tento modul len vykáže, čo bolo na výplatných páskach vyplatené.

## Nastavenie {#setup}

- **DIČ spoločnosti.** Na spoločnosti vyplňte *DIČ* (10-miestne daňové
  identifikačné číslo). Kým chýba, generovanie skončí chybou.
- **Adresa, telefón a e-mail spoločnosti** idú do hlavičky prehľadu. Číslo domu sa
  berie z konca poľa *Ulica* (*Hlavná 12*, *Hlavná 1141/11*); *Ulica 2* sa
  použije, len ak obsahuje iba číslo — budova, poschodie či c/o sa ako číslo
  domu nikdy nepodávajú.
- **Bankový účet.** Do III. časti sa ako účet na vrátenie zapíše prvý bankový
  účet partnera spoločnosti. Ak o poukázanie žiadate, je povinný (pozri
  [Vrátenie rozdielu daňového bonusu](#bonus-refund)).
- Verzia tlačiva **Monthly tax overview 2026** (platná od 1. 1. 2026) sa
  nainštaluje spolu s modulom a vyberie automaticky. Nájdete ju v
  *Mzdové hlásenia → Konfigurácia → Verzie hlásenia*.

## Podanie za mesiac {#usage}

*Mzdové hlásenia → SK prehľad o zrazených preddavkoch na daň*, potom *Nové*.

1. Zvoľte **Rok** a **Mesiac**. *Dátum výplaty* je dátum výplaty uvedený v
   r. 01; ak ho nevyplníte, použije sa posledný deň mesiaca.
2. **Typ opravy** nechajte na *Regular* (riadny prehľad).
3. Kliknite na **Generovať**. Modul zoberie všetky výplatné pásky
   spoločnosti, ktorých obdobie spadá do mesiaca a ktoré **nie sú zrušené** —
   vrátane konceptov —, sčíta výsledky pravidiel, vykreslí XML a overí ho
   voči oficiálnej schéme `prehlad2026.xsd`. Ak niečo zlyhá, nič sa nepriloží
   a chybové hlásenie povie prečo.
4. XML sa objaví v poli *Príloha XML* a stav sa zmení na *Vygenerované*.
   Stiahnite ho a na portál finančnej správy ho nahrajte sami.
5. Po podaní kliknite na **Označiť ako odoslané**. Podaná kópia sa uchová v
   poliach *Podané XML* a *História podaní* a záznam sa uzamkne; *Vrátiť do
   konceptu* ho odomkne na opätovné vygenerovanie, podaná kópia zostane.

Zoznam zamestnancov na formulári ukazuje, kto do súčtov prispel, a jeho
hrubú mzdu; samotný prehľad je len za zamestnávateľa a údaje o jednotlivých
zamestnancoch neobsahuje.

## Čo sa vyplní do tlačiva {#mapping}

| Riadok prehľadu | Čím sa vyplní |
|---|---|
| r. 00 — úhrn zúčtovaných a vyplatených zdaniteľných príjmov | súčet pravidla `GROSS` z výplatných pások mesiaca |
| r. 01 — preddavky na daň (dátum a suma) | *Dátum výplaty* a zrazený preddavok pred bonusom: `INCOMETAX19` + `INCOMETAX25` pri Enterprise, `INCOMETAX` pri jadre OCA |
| r. 04 | rovná sa r. 01 (r. 02 a 03 zostanú prázdne) |
| r. 05 — vyplatený daňový bonus | súčet `CHILD_BONUS`, **najviac do výšky r. 04**, v XML ako záporné zníženie |
| r. 08 — odvodová povinnosť | r. 04 + riadky 05, 06 a 07 so znamienkami XML |
| II. časť, r. A / B / C | bonus vyplatený spolu / časť pokrytá v r. 05 / zvyšok |

Riadky 01b, 02, 03, 06 a 07, riadky D – F II. časti a žiadosti
III. časti o poukázanie zamestnaneckej prémie a daňového bonusu na zaplatené
úroky zostanú prázdne alebo nulové. Žiadosť o poukázanie daňového bonusu sa
vyplní len na požiadanie — pozri nižšie.

Úradný elektronický formulár sčítava riadky 05–07 so znamienkami: vyplatený
bonus znižuje odvod a je záporný; vybratá suma je kladná. Vnútorné sumy
pokrytia, kladné rekapitulácie II. časti a výpočty žiadostí sa nemenia.
Rozšírenia riadkov 06/07 môžu použiť rovnaký formátovač šablóny
`prehlad_reduction`. Uchované podané XML sa neprepisuje; prípadná oprava
použije existujúci natívny opravný postup.

Finančná správa výslovne povoľuje PREHLADv26 pre roky 2026 aj 2027.
Elektronická schéma už obsahuje všetky riadky publikovaného papierového
vzoru PREHLADv27. Papierové znenie 2027 rozširuje riadok 1b na úpravy
podielu dane pre rodičov so znamienkom pri osobitných verejných zamestnávateľoch;
bežný súkromný zamestnávateľ ho nevyplní. Odlišné označenie papierového
vzoru nemení názov XML schémy. Primárne zdroje a presné hashe obsahuje
`data/SCHEMA_VERSION`; neskoršie publikované zmeny vyžadujú bežnú aktualizáciu.

## Vrátenie rozdielu daňového bonusu {#bonus-refund}

V r. 05 sa daňový bonus uvádza najviac do výšky zrazených preddavkov (r. 04).
Čo spoločnosť vyplatila nad túto sumu, vyplatila z vlastných prostriedkov a
objaví sa v II. časti v r. C. Poučenie na vyplnenie prehľadu pripúšťa dve
cesty: znížiť o rozdiel odvod preddavkov v nasledujúcich mesiacoch, alebo
požiadať správcu dane o jeho poukázanie žiadosťou v **III. časti** — po
skončení kalendárneho štvrťroka, v prehľade za jeho posledný mesiac, za
všetky tri mesiace spolu.

V prehľade za **marec, jún, september alebo december** pred generovaním
zaškrtnite **Žiadať o poukázanie rozdielu daňového bonusu**. III. časť potom
obsahuje žiadosť so súčtom r. C za tri mesiace štvrťroka, každý prepočítaný z
nezrušených výplatných pások daného mesiaca. Spoločnosť potrebuje bankový
účet na vrátenie; bez neho sa prehľad nevygeneruje. V iných mesiacoch sa pole
zaškrtnúť nedá. Ak ho nezaškrtnete, rozdiel si odpočítate neskôr a súbor sa
nezmení.

## Opravy {#corrections}

Prehľad pozná dva druhy: *riadny* a *opravný*. Na opravný prehľad nastavte
**Typ opravy** na *Corrective*. Modul opravný prehľad nevygeneruje, kým nie je
riadny prehľad za tú istú spoločnosť, rok a mesiac označený ako odoslaný.
Dodatočný ani stornovací prehľad vytvoriť nemožno.

## Overené údaje formulára {#form-facts}

Zadajte **Dátum vyhotovenia** uvedený na prehľade. Opravný prehľad vyžaduje
skutočný **Dátum zistenia chyby**, od prvého dňa vykazovaného mesiaca do dátumu
vyhotovenia. Pri riadnom prehľade zostáva prázdny. Dátum zistenia sa nikdy
neodvodzuje zo systémového času ani vytvorenia záznamu. Uveďte **Podklady údajov
formulára** a zvoľte **Overiť údaje formulára**. Akcia uchová používateľa, čas
a odtlačok vstupov. Zmena obdobia, typu alebo údajov overenie zruší. Vygenerovaný
prehľad pred úpravou vráťte do návrhu; kópia začína v návrhu bez XML, dátumu
zistenia a podmienených údajov či overenia. Podané bajty zostávajú zachované.

Pre riadok 1a podľa § 5 ods. 4 zadajte overený preddavok, prvý deň mesiaca
prijatia dokladu (bezprostredne nasledujúci mesiac; XML uvedie MM.RRRR) a zdroj sumy. Voľba **Už zahrnutý** presunie
sumu z riadka 1 do 1a; voľba **Navyše** pridá preddavok z externého dokladu.
Riadok 4 a krytie bonusov používajú výsledný súčet len raz. Mzdy a účtovníctvo
sa nemenia. Štvrťročná žiadosť použije dokončené mesačné údaje: posledný lokálne
evidovaný podaný prehľad, prípadne posledný vygenerovaný. Návrh nenahrádza
dokončený mesiac. Rozšírenia môžu použiť spoločné hooks
`_prehlad_advance_rows`, `_prehlad_quarter_inputs` a `_prehlad_form_facts`.

Riadok 8b zaškrtnite len pri skutočnom znížení odvodu za tento mesiac o skoršie
nadmerné odvody podľa § 40 ods. 8. Ide o overený príznak, nie automatický výpočet
vratky alebo platby. Žiadosť o vrátenie od úradu ho nevyznačuje. Riadok 1b je
vyhradený zákonným verejným a vojenským profilom zamestnávateľa; pri bežnej
súkromnej spoločnosti zostáva prázdny.

[FS výslovne povoľuje](https://podpora.financnasprava.sk/879943-Pod%C3%A1vanie-mesa%C4%8Dn%C3%BDch-preh%C4%BEadov)
XML PREHLADv26 na roky 2026 aj 2027. Listinný vzor a poučenie 2027 vydáva
[MF/014307/2026-721](https://www.mfsr.sk/files/archiv/70/oznamenie_mfsr_mf_014307.zip).
[Úradný eForm](https://pfseform.financnasprava.sk/Formulare/eFormVzor/INE/form.624.html)
vyžaduje dátum zistenia pri opravnom prehľade, hoci nezmenené XSD dovolí prázdny
nepovinný dátum. XSD nie je prijatie úradom. Overené 12. novembra 2026; nijaká
nepublikovaná budúca XML verzia sa nevymýšľa.

## Obmedzenia {#limitations}

- **Sumy pred podaním skontrolujte.** Kontrola voči schéme overí tvar súboru,
  nie správnosť súm. Žiadny prehľad z tohto modulu zatiaľ nebol overený
  skutočným podaním; prvý odsúhlaste ručne.
- **Započítavajú sa aj koncepty.** Zahrnie sa každá nezrušená výplatná páska
  mesiaca. Pred generovaním pásky potvrďte alebo zrušte.
- Výplatné pásky sa vyberajú podľa **obdobia**, nie podľa dňa výplaty, o
  ktorom hovorí zákon. Mzda za september vyplatená v októbri sa vykáže za
  september.
- R. 01 nesie **jeden** dátum výplaty. Ak sa mzdy mesiaca vyplácali v rôznych
  dňoch, riadky podľa dátumov treba rozdeliť ručne.
- **Neskoršie odpočítanie rozdielu bonusu nie je automatické.** Ak o
  poukázanie nežiadate, nič neprenesie r. C do nasledujúcich mesiacov; odvod
  preddavkov v nich znížte sami. R. 08 nikdy nie je záporný.
- Zamestnanecká prémia, daňový bonus na zaplatené úroky (§ 33a) a opravy z
  ročného zúčtovania (r. 02 a 03) nemajú v mzdách zdroj a treba ich doplniť
  ručne.
- Element **právnej formy** v hlavičke: *Právna forma* zapísaná na kontakte spoločnosti modulom `l10n_sk_trade_registry`; bez tohto modulu alebo pri prázdnom poli zostáva element prázdny.
- Verzia tlačiva sa vyberá podľa vykazovaného obdobia; nepodporované historické
  obdobie potrebuje svoj publikovaný vzor.
- Úradu sa nič neposiela: *Označiť ako odoslané* len zaznamená, že ste
  prehľad podali.
