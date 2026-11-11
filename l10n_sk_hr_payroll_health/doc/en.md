---
title: SK Monthly Health Insurance Statement (dávka 514)
summary: Monthly Slovak health-insurance reporting from recorded payroll assessments, with historical insurers, XML and the published text batch format.
verified: 19.0.1.3.0
---

## What it is for {#purpose}

Prepare a monthly statement for VšZP (25), Dôvera (24) or Union (27) from confirmed payroll. Each statement addresses one insurer. Choose XML or **Text batch 514**; text uses the published UTF-8, pipe-separated interface and its prescribed filename.

The statement uses the assessments and statutory profile retained with payroll: actual employee and employer bases, tariffs, OP and the minimum top-up. Several payroll sources and HR records for the same insured person are consolidated by birth number, with distinct calendar days.

## Legal background {#legal}

The reporting obligation follows sections 20 and 24 of [Act 580/2004](https://static.slov-lex.sk/static/SK/ZZ/2004/580/20261231.html). The report keeps the section 13(17) downward assessment-base rounding separate from currency amounts already charged by payroll.

[Decree 159/2018, section 2](https://static.slov-lex.sk/static/SK/ZZ/2018/159/20240301.print.html) permits a full **O corrective statement** for errors in any section 1 data. O replaces the previous statement. A is a difference statement; the UI offers N and O while the difference collector remains separate work.

The text interface is published by [VšZP](https://www.vszp.sk/files/platitelia/tlaciva-platitelov/vykaz-preddavkov-zamestnavatela/struktura-vykazu-1.rtf). Its source checksum is recorded in the module. Choose the installed form edition applicable to the reporting period.

## Setting it up {#setup}

On the company payroll-reporting page, configure each insurer's assigned payer number and the company's bank account. The default insurer supplies the initial value for a new employee. On a statement, review the selected insurer and its payer number; the number is retained on that statement when company settings later change.

The employee's **Health insurer (SK)** belongs to the native historical employment version. Open **Records** to select and edit the applicable version. A later version or a change of company defaults leaves earlier versions intact. An upgrade preserves known current legacy values; unknown historical insurers require review.

Complete the monthly health calendar where actual registered agreement days, benefit periods, disability or concurrent-employment facts are needed. Contract duration and working hours do not establish registered 2D/2Y days. Record the written notice and actual other-employer facts before using the minimum opt-out.

## Preparing the statement {#usage}

Complete and confirm payroll for the month, including zero-premium months. A reviewed registered calendar without processed payroll is reported as missing work. Review excluded agreement income with nonzero payroll assessments before filing; it is not silently dropped.

The completeness check also finds ordinary employees from the historical employment versions and contract dates when neither payroll nor a calendar exists. It names the employee whose payroll must be completed, including employees insured elsewhere and archived employees active in the reporting month. A future exemption does not remove an earlier obligation. Agreement and irregular-income registrations use actual reviewed 2D/2Y days; the program does not create zero wages from a contract.

A partial payslip covers only its own dates. Complete payroll for any later registered interval in the same month; a full-month retained payroll profile remains valid after later HR edits. An empty reviewed calendar does not end an ordinary employment registration. Benefits can give zero premium days while registration continues; record an actual no-income exclusion as 2N with its supporting evidence.

[Dôvera's 514 instructions](https://www.dovera.sk/najcastejsie-otazky/elektronicka-pobocka/e-pobocka-platitel/1372-davka-514-struktura-vykazu) require the employee count even when no advance is due. [VšZP's registration instructions](https://www.vszp.sk/showdoc.do?docid=147) distinguish 2D agreement registration and 2Y irregular or post-employment income.

Create a statement for the insurer, select the period, applicable form edition and export format, then **Generate**. Check the employee rows and totals against payroll. Download the generated file and upload it through the insurer's electronic branch. Record **Mark Submitted** and retain the insurer's receipt with the filing.

Use a new **Corrective** statement for a full replacement of an already submitted statement for the same company, insurer and period. The shared workflow preserves the original submitted attachment and its history. Reset an unsubmitted statement to draft before changing its filing inputs or format.

## What the statement contains {#output}

Rows include income eligible for OP, other income, actual OP, separate employee/employer advances and the employee's minimum top-up. Tariffs are taken from recorded assessments. The summary distinguishes ordinary and disability groups and counts insured people across all insurers. One person with several HR records has one wire row and a union of calendar days.

XML remains the default for existing callers. Text batch 514 uses decimal commas, CRLF records and a filename such as `N5142606.001`; O uses the corresponding corrective prefix. Both formats use the same collected assessments and filing workflow.

## Limitations {#limitations}

The bundled XML schema contains contradictory field restrictions. XML is checked for well-formedness and structural consistency; its schema findings are nonfatal. The published text format has typed field and total checks. A local passing export is not an insurer receipt; reconcile the first actual filing and retain the response.

For older payroll without precise records, originals retain the framework's named gross-based fallback warning. A correction needs precise records or the framework's explicit, reasoned legacy review. Filed payroll is not recomputed merely to manufacture old evidence, and stored filed bytes are preserved.

This collector consumes payroll results. Multi-income calculation, paid financial corrections and registration evidence must be reconciled in their respective workflows. Enterprise has not been run for this contribution; its bridge must supply the same recorded-profile protocol.
