# Case 02: Payments Connectivity

A focused Kyriba transformation case study about removing manual file handling from Treasury payments by connecting Kyriba directly to the group's two core banks.

## Report

- [View the rendered report](../../docs/kyriba-transformation/Case_02_Payments_Connectivity/report.html)
- [Report source](report.qmd)
- [Presentation (PDF)](presentation/Case_02_-_Payments_Connectivity.pdf) / [PowerPoint](presentation/Case_02_-_Payments_Connectivity.pptx)

## Case summary

The case explains how Treasury payments are generated and how they moved from manual uploads, bank portals and faxes to direct bank connectivity:

1. Group entities and Treasury instruct transactions; intercompany payments are netted inside Kyriba.
2. The netting run in the Cash & Liquidity module is scheduled (or triggered manually) and produces netted payments.
3. Netted payments and treasury transfers are released to the Payments module; third party payments are instructed there using templates.
4. All payments are reviewed and approved in one place.
5. Kyriba sends pain.001 payment instructions to Bank A (or Bank B for transfers from Bank B to Bank A) and receives pain.002 status feedback.
6. The bank pays group entities and third parties.

The source presentation reports 2 core banks connected straight-through, approximately 6 hours saved per month (about 15 minutes per payment run plus at least 5 minutes per treasury transfer and third party payment) and 1 place to approve all payments. Those are source-reported estimates and are kept qualified in the report.

## Evidence boundary

The page is based on the supplied case presentation. Banks are anonymised as Bank A and Bank B. It does not add client or bank names, implementation dates, connectivity channel details or independently audited benefits. The only added context is a one-line note that pain.001 and pain.002 are ISO 20022 message types, flagged as such in the report's source traceability table.
