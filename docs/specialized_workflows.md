# Specialized accounting contracts

Every workflow uses immutable canonical records and Decimal calculations. `kind` now dispatches a separate algorithm, rather than merely labeling a generic match. Try the **Accounting workflows** screen or POST `/api/v1/demo/{kind}`.

| Workflow | Source | Target | Additional evidence and invariants |
| --- | --- | --- | --- |
| bank | Bank cash entries | Ledger cash entries | Compatible account, currency, sign, date, monetary tolerance; mutual uniqueness; reference or supporting counterparty/text evidence |
| ap | Invoices and credit notes | Vendor payments/refunds | Supporting purchase-order dataset; `invoice_id`, `po_id`, counterparty, currency; PO amount equals invoice; net credits/payments equal obligation |
| ar | Invoices and credit notes | Receipts/refunds | Explicit invoice allocation and counterparty; subtract credits from invoice amount and refunds from receipts; report short/over/unallocated payments |
| gateway | PAYMENT / REFUND / CHARGEBACK / FEE rows | Bank settlements | `batch_id`, supported document type, currency/date window; gross minus deductions equals deposits; optional expected fee independently checked |
| intercompany | Entity postings | Reciprocal entity postings | `entity_id` and `counterparty_entity` must reverse; reference unique, compatible currency/date; signed amounts sum to zero |
| gl | Subledger entries | GL or trial-balance records | Explicit source-to-target account mapping; group by account/currency/accounting period; every supplied journal balances; duplicate postings held for review |

All imports require transaction_id, date, account, currency and amount or debit/credit. Business fields are preserved in normalized canonical JSON. `document_type` values and entity/reference fields are interpreted as data, never instructions. Financial signs follow the canonical cash credit-minus-debit import convention; invoice/receipt allocation interprets explicit document types and absolute obligations rather than applying bank matching semantics.

AP rules take `supporting_dataset_ids` containing purchase orders. GL rules take `account_mapping`, for example `{"SUB":"CONTROL"}`. The API rejects supporting datasets outside the tenant or repeated source/target IDs. Missing or ambiguous POs, duplicate invoices, incompatible counterparties/currencies, missing settlements and unbalanced reciprocals stay visible.

Cross-ID duplicate fingerprints are held for review before matching. Explicit distinct payment_reference/payment_id values distinguish legitimate installments. Unusual amounts use a transparent IQR rule and are labeled as unusual, never as proven fraud. Large ambiguous subsets remain reviewable rather than receiving approximate automatic matches.

Manual bank matches must satisfy deterministic amount, currency, sign, account and date constraints. Membership uniqueness prevents reuse across accepted matches. Rejecting a match releases membership, updates counts and creates an auditable review exception. Re-acceptance cannot consume a record subsequently assigned elsewhere.

An exception can be resolved only by an authorized human referencing a separate completed reconciliation and a full accepted match preserving its original immutable source or target anchor. Neither AI output nor a simulated journal can close it.
