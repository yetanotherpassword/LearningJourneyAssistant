# LJA — Python bundle

Extraction-layer spike code for the Learning Journey Assistant.

## Contents

| File | Purpose |
| --- | --- |
| `moodle_probe.py` | Minimal Web Services client. Verifies the token, lists courses, dumps per-student grade items. |
| `environment.yml` | Conda environment definition. |
| `.env.example` | Template for credentials. Copy to `.env` and fill in. |
| `.gitignore` | Keeps `.env` out of version control. |

## Setup

```bash
conda env create -f environment.yml
conda activate lja
cp .env.example .env
vim .env                # fill in MOODLE_URL and MOODLE_TOKEN
python moodle_probe.py
```

## Enabling the API on the Moodle instance

1. Site administration → Advanced features → tick **Enable web services**.
2. Site administration → Server → Web services → **Manage protocols** → enable
   **REST**.
3. Server → Web services → **External services** → add a service containing only
   the functions we need, with "Authorised users only" ticked.
4. Create a service account and a role carrying just the required capabilities
   (`moodle/grade:viewall`, `gradereport/user:view`,
   `moodle/user:viewalldetails`), assigned at system level.
5. **Manage tokens** → generate a token scoped to that user and service.

Least privilege is deliberate. We do not use the admin token, and we should be
able to say so at the final presentation — Scott has been explicit about
DevSecOps being a differentiator.

## Functions the extraction layer relies on

| Purpose | Function |
| --- | --- |
| Verify token, enumerate available functions | `core_webservice_get_site_info` |
| Subjects and their structure | `core_course_get_courses`, `core_course_get_contents` |
| Enrolled students in a subject | `core_enrol_get_enrolled_users` |
| Per-student grade items plus feedback | `gradereport_user_get_grade_items` |
| Assignment metadata and marks | `mod_assign_get_assignments`, `mod_assign_get_grades` |
| Quiz attempts | `mod_quiz_get_user_attempts` |
| Rubric definitions (criteria and levels) | `core_grading_get_definitions` |
| Activity completion | `core_completion_get_activities_completion_status` |
| Competencies and user proficiency | the `core_competency_*` family |

Do not treat that table as final. The instance publishes its own version-exact
reference with full parameter and return schemas at **Site administration →
Server → Web services → API Documentation**. Read it there; the function set
changes between releases.

## The known coverage gap

Rubric **definitions** are exposed over web services. Rubric **fills** — which
level was selected on which criterion for which student, plus the marker's
per-criterion remark — are not.

Since per-criterion feedback is the signal our gap detection depends on, this is
a real architectural decision, not a detail. Three candidate routes:

1. **Read the fills directly from the database.** Fastest. Legitimate on a
   self-hosted instance, but not API-mediated, and the handover document has to
   say so plainly.
2. **Write a small local Moodle plugin** exposing a custom web service function
   that returns fills as JSON. More work, but a genuinely impressive deliverable
   and demonstrably production-shaped.
3. **Study the community `gradereport_rubrics` plugin** as a reference — it
   surfaces per-criterion grades and comments for all students and exports to CSV
   — then implement our own path.

Recommendation: option 1 now to unblock the model, option 2 as a stretch item if
Sprint 3 or 4 has capacity. Option 2 is the one that would stand out at the
showcase.

## Not yet written

- Typed models for grade items and rubric fills.
- Loader that populates `lja_criterion_score` (see the SQL bundle).
- Synthetic data seeder — see the devenv bundle for the approach.
