# Screenshot Visual Review Log

Manual visual-review tracker for the UI captures in this directory.

**Status: 11 reviewed, 0 `NOT REVIEWED`.** A committed PNG existing in this
directory is **not** evidence that its contents were inspected — a row counts as
reviewed only once a human records observations below. Any row still marked
`NOT REVIEWED` must be treated as unreviewed, and no claim may be made about its
contents (including the absence of credentials or other sensitive data).

Review checklist per image:
- no credentials, tokens, or plaintext demo hints visible (see `login.png`);
- no clipping, blank regions, or unreadable text;
- DEMO/LIVE (and source) labelling consistent with `docs/demo.md`;
- charts/maps populated rather than empty; placeholder-only screens are as intended.

Record `PASS`, `WARN`, or `FAIL` with concrete observations. Do not edit the PNGs.

### Current File SHA-256 hashes

The `Current File SHA-256` column records the hash of each file **as it exists at
the time of this inventory**. For screenshots that had no recorded hash when they
were originally reviewed, adding a hash now does **not** retroactively prove that
the exact same bytes were present during that earlier human review — it only
fixes the current bytes for future comparison. A future hash mismatch means the
screenshot has changed and the row must be re-reviewed before its visual-review
entry is relied upon. Recording hashes does not by itself verify overall
screenshot visual QA.

| File | Intended page | Review status | Reviewer | Date | Current File SHA-256 | Notes |
| ---- | ------------- | ------------- | -------- | ---- | -------------------- | ----- |
| `admin.png` | `/admin` | REVIEWED | | 2026-10-14 | `AAA00CBA0606B8FBE34A3CC12230C80E807344E4F8CCDA18617006CBF9A6AF95` | Human-supplied review: layout and metrics readable; DEMO and SYNTHETIC TRAINING DATA labels visible; controls not functionally tested. |
| `ai-insights.png` | `/ai-insights` | REVIEWED | | 2026-10-14 | `A399D5A0CDED491CA2A84AB0527F5BEF67257503EF72F278DEB97C1AFA8D26AF` | Human-supplied review: model metadata and feature bars readable; demo/sample-data disclaimer visible; lower explanatory section cut off in the capture. |
| `alerts.png` | `/alerts` | REVIEWED | | 2026-10-14 | `D1A5B397B4A3531E93F3A31D3A4B9D0D2544AC2E1899DDBC429ED1843D503EA8` | Human-supplied review: filters, alert cards and action controls visible; functionality not tested. |
| `analytics.png` | `/analytics` | REVIEWED | | 2026-10-14 | `CE5BCF141B138CF5C6C978C3975547219CB78C1027B6A11A3A23B740EA88C7B8` | Human-supplied review: charts and legends readable; DEMO framing visible; figures not independently validated; lower chart partly below the viewport. |
| `dashboard.png` | `/dashboard` | REVIEWED | | 2026-10-14 | `F5B440B7A4C4EB7B9EB8EAD5DB1B8E85C6822AA1A494ECFBF10E5F1CCCC981F9` | Human-supplied review: risk cards and trigger factors visible; UI states confidence is not calibrated and DEMO DATA is visible; no operational accuracy claim. |
| `landing.png` | `/` | REVIEWED | | 2026-10-15 | `BD7EEBA601E351984BAF9115E6783DB085A11C7A67C76D417FACAD00FB160425` | Human visual inspection of the **current** image (1440×900, 258,396 bytes, SHA-256 `BD7EEBA601E351984BAF9115E6783DB085A11C7A67C76D417FACAD00FB160425`) after the Phase 28 copy change. Observed: the `DEMO DATA` pill is visible and readable; the hero subtitle clearly states the system is running on demo data until live feeds are connected; the headline, CTA buttons and four statistic cards are readable and aligned; `Per-request Risk Refresh` is visible. The Problem/Solution section continues below the captured viewport — noted, not a layout defect. Review covers **visual appearance only** — not functionality, live-data correctness, or scientific validity. Superseded 2026-10-15 review (previous image, retained for the record): SIH framing visible; `SIH26001`/`2,300+` NOT visible; 24×7 Continuous Monitoring stat; hero claimed real-time. |
| `locations.png` | `/locations` | REVIEWED | | 2026-10-14 | `31242643D85A633E145533FE1034FDEA4BC95E5B03443FA3106A37B4569FA39F` | Human-supplied review: human reviewer confirmed the capture is correct. |
| `login.png` | `/login` | REVIEWED | | 2026-10-14 | `C24082C89BEC15DBFED8A4C7948577DC777BB74077F3FD6B1F8672CFD3499AA8` | Human-supplied review: email `admin@landslideguard.ai` is visible (a visible demo-account identifier — must not be described as absent); password field is empty; no password or token is visible. **Re-capture provenance (2026-10-15):** freshly captured from a **production build preview** (`vite preview`, headless Chrome, 1440×900, DEMO data) using the current working-tree code; programmatic DOM check confirmed the email prefilled, the password field empty (`value=""`), the demo-credential hint absent, and no `admin123`/secret in the shipped bundle. This is capture/programmatic evidence, **not** human visual QA of the capture event. Two independent captures reproduced SHA-256 `C24082C8…` (19,285 bytes), **byte-identical** to the previously reviewed image — so the 2026-10-14 human review still applies to these exact bytes. |
| `prediction.png` | `/prediction` | REVIEWED | | 2026-10-14 | `DD1DF6494594B43CD12FD57F70B5E477BAEB6F118481096514A35C4E98073D95` | Human-supplied review: human reviewer confirmed the capture is correct. |
| `risk-map.png` | `/map` | REVIEWED | | 2026-10-14 | `2BB42CD1ABFF6E5D68D2DA4B0EAB83C9DFAE545DF5270724D4C68A1C0F62263D` | Human-supplied review: map, legend, location list and risk scores visible and generally readable; some markers overlap. `SYNTHETIC TRAINING DATA` and `DEMO DATA` labels visible. No geographic or scientific validity claimed. |
| `settings.png` | `/settings` | REVIEWED | | 2026-10-14 | `B9DC14CD3EBBB9B2F0C0981E51624CEFCFEDF08F8268573439D5D905E62DC795` | Human-supplied review: human reviewer confirmed the capture is correct. |
