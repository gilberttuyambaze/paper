# Academic taxonomy

`backend/services/academic_taxonomy.py` is the University of Rwanda source of truth. It models stable IDs for Institution → Campus → College → School → Programme and intentionally leaves schools with unverified programme groups empty. The UI then explains that no programme is currently listed rather than inventing one.

The public `GET /api/v1/academics/taxonomy` endpoint powers the shared selector used by registration, profile editing, and paper upload. Add or amend a programme only in that taxonomy file, retaining IDs once published.

Profiles and papers store normalized IDs (`institution_id`, `campus_id`, `college_id`, `school_id`, `programme_id`) as nullable fields. Existing records remain valid. Legacy `college_name` and `department_name` remain populated with display values for existing pages and recommendations. Profile and upload requests are checked on the server to ensure every selected node is the child of the prior one; invalid combinations are rejected.

## Programme discovery

`Programme not listed` never creates an official programme. The raw value is stored in `academic_programme_submissions`, alongside a deterministic normalized value and academic context. Normalization preserves the raw value, removes harmless degree/punctuation formatting for comparison, and retains meaningful tokens.

Recommendations compare official programmes, verified aliases, and prior submissions. Their confidence is 70% name similarity (token overlap plus edit similarity), 15% school, 10% college, and 5% campus. Scores under 70 are omitted; every result remains a recommendation, never an automatic merge. Student-facing responses contain aggregate usage only.

Administrators can review submissions with the admin-hub candidate endpoints. Mapping or merging to an existing taxonomy programme creates a verified alias while retaining the historical submission; verification alone marks the candidate for taxonomy review rather than altering the static official source.
