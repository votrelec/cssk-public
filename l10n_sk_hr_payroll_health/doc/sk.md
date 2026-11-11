---
title: Mesačný výkaz zdravotného poistenia (dávka 514)
summary: Mesačné vykazovanie zdravotného poistenia z uložených mzdových podkladov, s historickou poisťovňou, XML a zverejneným textovým formátom.
verified: 19.0.1.3.0
---

## Na čo slúži {#purpose}

Pripraví mesačný výkaz pre VšZP (25), Dôveru (24) alebo Union (27) z potvrdených miezd. Každý výkaz patrí jednej poisťovni. Vyberte XML alebo **Textovú dávku 514**; text používa zverejnené kódovanie UTF-8, oddeľovač zvislá čiara a predpísaný názov súboru.

Výkaz používa základy, sadzby, OP, poistné a doplatok do minima uložené pri mzde spolu s poistným profilom. Viaceré mzdové podklady a pracovné záznamy tej istej osoby sa zlúčia podľa rodného čísla; kalendárne dni sa započítajú bez prekrývania.

## Právny rámec {#legal}

Povinnosť vykazovania upravujú §20 a §24 [zákona 580/2004](https://static.slov-lex.sk/static/SK/ZZ/2004/580/20261231.html). Výkaz odlišuje zaokrúhlenie vymeriavacieho základu nadol podľa §13(17) od peňažných súm, ktoré už vypočítala mzda.

[Vyhláška 159/2018, §2](https://static.slov-lex.sk/static/SK/ZZ/2018/159/20240301.print.html) umožňuje úplný **opravný výkaz O** pri chybách všetkých údajov podľa §1. Nahrádza pôvodný výkaz v plnom rozsahu. A je rozdielový výkaz; používateľské rozhranie ponúka N a O, kým rozdielový zber údajov zostáva samostatnou úlohou.

Textové rozhranie zverejňuje [VšZP](https://www.vszp.sk/files/platitelia/tlaciva-platitelov/vykaz-preddavkov-zamestnavatela/struktura-vykazu-1.rtf). Kontrolný súčet zdroja je uložený v module. Vyberte nainštalovanú verziu formulára platnú pre vykazované obdobie.

## Nastavenie {#setup}

Na firemnej stránke mzdových výkazov nastavte pridelené číslo platiteľa pre každú poisťovňu a bankový účet firmy. Predvolená poisťovňa je počiatočnou hodnotou nového zamestnanca. Na výkaze skontrolujte poisťovňu a jej číslo platiteľa; číslo zostáva uložené pri výkaze aj po neskoršej zmene firemných nastavení.

Pole **Zdravotná poisťovňa (SK)** patrí natívnej historickej verzii pracovných údajov. Cez **Záznamy** vyberte a upravte príslušnú verziu. Novšia verzia ani zmena firemných predvolieb neprepisuje staršie údaje. Aktualizácia zachová známe aktuálne pôvodné hodnoty; neznáme historické poisťovne treba skontrolovať.

Mesačný zdravotný kalendár doplňte tam, kde treba skutočné dni dohody, dávkové obdobia, invaliditu alebo súbeh. Trvanie zmluvy a pracovné hodiny samy neurčujú prihlásené dni 2D/2Y. Neuplatnenie minima potrebuje písomné oznámenie a overené údaje o súbehu iných zamestnávateľov.

## Zostavenie výkazu {#usage}

Spracujte a potvrďte mzdy za mesiac vrátane mesiacov s nulovým poistným. Overený registračný kalendár bez spracovanej mzdy vyvolá požiadavku dokončiť chýbajúcu prácu. Vyňatý príjem s nenulovými zdravotnými odvodmi treba skontrolovať pred podaním; program ho potichu nevynechá.

Vytvorte výkaz pre poisťovňu, zvoľte obdobie, platnú verziu formulára a formát exportu a použite **Generovať**. Porovnajte osoby a súčty so mzdami. Stiahnutý súbor nahrajte cez elektronickú pobočku poisťovne. Zaevidujte **Označiť ako podané** a doručenku poisťovne uchovajte spolu s podaním.

Úplnú náhradu už podaného výkazu rovnakej firmy, poisťovne a obdobia pripravte ako nový **Opravný** výkaz. Spoločný postup zachová pôvodnú podanú prílohu a jej históriu. Pred zmenou vstupov alebo formátu vráťte nepodaný výkaz do návrhu.

## Obsah výkazu {#output}

Riadky obsahujú príjem pre OP, ostatný príjem, skutočnú OP, oddelené poistné zamestnanca a zamestnávateľa a doplatok zamestnanca do minima. Sadzby pochádzajú z uloženého výpočtu. Súhrn odlišuje bežnú a invalidnú skupinu a obsahuje počty poistených osôb všetkých poisťovní. Jedna osoba s viacerými pracovnými záznamami má jeden výstupný riadok a zjednotené kalendárne dni.

XML zostáva predvoleným formátom existujúcich volaní. Textová dávka 514 používa desatinné čiarky, riadky CRLF a názov napríklad `N5142606.001`; opravný výkaz má predponu O. Oba formáty používajú rovnaké podklady a spoločný postup evidencie podania.

## Obmedzenia {#limitations}

Pribalená XML schéma obsahuje protirečivé obmedzenia polí. Kontroluje sa platnosť XML zápisu a štruktúrna konzistencia; hlásenia tejto schémy nie sú blokujúce. Zverejnený textový formát má kontroly typov, polí a súčtov. Úspešný miestny export nie je doručenkou poisťovne; prvé skutočné podanie porovnajte a odpoveď uchovajte.

Pri starších mzdách bez presných uložených podkladov pôvodný výkaz zachová pomenované upozornenie na výpočet z hrubého príjmu. Oprava potrebuje presné podklady alebo výslovnú kontrolu pôvodného postupu s dôvodom v spoločnom systéme. Podané mzdy sa neprepočítavajú iba kvôli dodatočnému vytvoreniu starých dôkazov a podané súbory zostávajú zachované.

Tento zber údajov preberá výsledky miezd. Výpočty viacerých príjmov, vyplatené finančné opravy a registračné podklady treba zosúladiť v príslušných postupoch. Enterprise sa v tomto príspevku nespúšťal; jeho prepojovací modul potrebuje rovnaké rozhranie uloženého profilu.
