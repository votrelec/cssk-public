# Mesačné zdravotné preddavky

Viaceré potvrdené odmeny rovnakého zamestnanca, firmy, mesiaca, historického
profilu a vyriešeného natívneho pracovného vzťahu používajú OP, dni a minimum
raz mesačne. Aktuálny príjem a pravidlá sa výslovne zaznamenajú. Predchádzajúce
príjmy, základy, poistné, OP a doplatok sa čítajú z overených uchovaných údajov;
príjem sa spätne neodvodzuje z výšky poistného. Nevzniká ďalšia evidencia záväzkov.

Ďalšia páska obsahuje rozdiel medzi spoločným mesačným výpočtom a skutočne
účtovanými predchádzajúcimi sumami. V roku 2026 pri celomesačnom PP s OP
200 + 200 EUR znamená spoločný príjem 400, OP 340, základ zamestnanca 60,
jeho základné poistné 3, poistné zamestnávateľa 44 a doplatok 0 EUR. Prvý doplatok
23,45 EUR sa vráti kladným riadkom druhej pásky. Prvá potvrdená páska ani jej
uchované údaje sa nemenia. V roku 2027 je pri existujúcom dátovanom minime
295,22 EUR konečný doplatok 0,23 EUR.

Záporná čiastková OP alebo doplatok sú prípustné. Dávka 514 najprv zlúči mesačné
údaje osoby a až potom overí konečné sumy XML/TXT. Benefit skracuje dni minima,
2N aj dni OP. ZŤP a zákonné výnimky zachovávajú pôvodné pravidlá. Počet dní
preddavku nie je zánikom registrácie zamestnanca.

Všetky tri zdravotné pravidlá musia pred zmenou prejsť spoločným overením
kanonickej konfigurácie a Python AST proti dodanému XML. Samotné ID pravidla ani
zhoda vlastnej formulky s jej vlastnými metadátami nestačia. Zhodná kópia pravidla
je prípustná. Overuje sa aj skutočný natívny výpočet proti výslovne zaznamenaným
údajom. Odmietnutie prístupu sa nesmie potlačiť.

Natívne storno kopíruje presné čiastkové riadky vrátane vráteného doplatku.
Skorá identita zdroja používa natívny hook `_copy_refund_payslip()` (OCA payroll
PR 332). Nemení sa implementácia `refund_sheet()` ani už podané súbory.
Neznámy historický zdroj, odlišný profil, vlastná formulka alebo osamotený závislý
fragment sa neprepočítajú odhadom: ostávajú skutočné natívne sumy a požiadavka
na preskúmanie podľa spoločnej politiky pôvodného/opravného výkazu.

Rozdelenie medzi iných zamestnávateľov, viac HR kariet či odlišné pracovné vzťahy
je samostatnou hranicou. Výkaz viac HR kariet výslovne pomenuje na preskúmanie.
Overené skutočné sumy pri neoverenom mesačnom rozdelení ostávajú zachované;
pôvodný výkaz upozorní a oprava vyžaduje existujúce výslovné potvrdenie s auditom.
Nevymenia sa za sumu odvodenú z hrubej mzdy. Tento balík neuzatvára účtovnú hlavnú knihu ani mesačnú
daň, bonus a čistú mzdu. Právne zdroje a technický kontrakt sú v
[anglickej dokumentácii](monthly_health.md).
