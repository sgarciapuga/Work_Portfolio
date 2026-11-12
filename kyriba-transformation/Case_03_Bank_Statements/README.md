# Case 03: Bank Statements

A focused Kyriba transformation case study about moving prior-day bank statements from bank portal downloads and SharePoint files to automatic delivery into Kyriba, with transaction code mapping, automatic reconciliation and one daily cash position.

## Report

- [View the rendered report](../../docs/kyriba-transformation/Case_03_Bank_Statements/report.html)
- [Report source](report.qmd)
- [Presentation (PDF)](presentation/Case_03_-_Bank_Statements.pdf) / [PowerPoint](presentation/Case_03_-_Bank_Statements.pptx)

## Case summary

The case explains how bank statements reach Treasury each morning and how they become the daily cash position:

1. Banks send prior-day statements: Bank B directly through EBICS (camt.053); Bank A and about 20 other banks (MT940) through an external aggregator. About 300 bank accounts report in total.
2. AUTOINTEG loads the statements into the Cash & Liquidity module early each morning, with balances and transactions.
3. BTC mapping gives each statement line the correct flow code.
4. AUTOREC matches lines with forecasts already in Kyriba (netting, treasury transfers, collateral, RCF, fees, invoices, money market funds), creates the cash flow when there is no forecast, and puts unmatched lines on hold for manual reconciliation.
5. The cash position worksheet shows today's expected position, which Treasury uses to decide what to invest or divest after four daily checks.

The source presentation reports about 300 bank accounts reporting automatically, approximately 15 minutes saved every morning on reconciliation and 1 daily cash position in Kyriba. Those are source-reported estimates and are kept qualified in the report.

## Evidence boundary

The page is based on the supplied case presentation. Banks are anonymised as Bank A and Bank B (the same core banks as Case 02), and the aggregator is not named. It does not add client, bank or aggregator names, implementation dates or independently audited benefits. Added context (a one-line note on camt.053, MT940 and EBICS, and a monthly conversion of the daily time saving) is flagged as such in the report's source traceability table.
