# Legal source hierarchy and conflict policy

Status: Phase 1 draft for review by an Israeli food-regulation specialist.

This hierarchy ranks sources only after they pass the active acquisition scope:
the source must be an FCS publication or an exact public source directly
referenced by one. Legal authority alone does not authorize independent crawling
under the current project decision.

## Retrieval priority

1. **Binding law** — statutes, regulations, orders, and official gazette
   publications. These control when another source conflicts with them.
2. **Legally adopted external provisions** — for example, EU provisions adopted
   into Israeli food law. Store the Israeli adoption instrument, incorporated
   version, exceptions, transition period, and effective date together.
3. **Official procedures and service instructions** — operational requirements
   issued by the responsible authority. These explain process but do not amend
   binding law.
4. **Official notices and circulars** — authoritative for the notice they convey;
   evaluate them against later amendments and effective dates.
5. **Official guides, translations, FAQs, and webinars** — explanatory sources.
   They may help interpretation but must never silently override levels 1–4.
6. **User-supplied or third-party material** — evidence for a specific case only,
   unless independently verified against an official source.

## Conflict-resolution rules

- Prefer the higher legal priority.
- At equal priority, prefer the source issued by the competent authority.
- Apply the version effective on the import or decision date, not merely the most
  recently downloaded version.
- Preserve amendments, repeals, transition periods, exceptions, and territorial
  or product scope as explicit metadata.
- When two current sources still conflict, show both passages and escalate to a
  qualified professional. Do not let the language model choose silently.
- A translation is retrieval assistance unless the publication expressly gives
  it controlling legal status.

## Required temporal fields

Every production document should carry, where available:

- publication date;
- effective-from and effective-to dates;
- retrieval timestamp;
- amendment/supersession links;
- transition-period start and end;
- legal priority and authority;
- current/superseded/unknown status.

## Answer policy

Each compliance answer must state the assumed product facts, applicable date,
likely route, missing facts, and citations. Classification or document readiness
must be phrased as preliminary when a competent authority or professional review
is required. If the corpus cannot establish a current answer, the system must
abstain and identify the proper escalation route.
