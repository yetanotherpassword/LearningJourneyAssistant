-- =============================================================================
-- Learning Journey Assistant — Moodle attainment extraction (PostgreSQL)
--
-- Target:  Moodle 5.2.x, default table prefix `mdl_`, PostgreSQL backend.
-- Purpose: pull the per-criterion rubric detail and per-outcome attainment that
--          the Web Services API does not fully expose, for use by the
--          competency model and gap-detection layer.
--
-- SAFETY:  every statement here is read-only. Never write to Moodle tables
--          directly — grade aggregation, event triggers and cache invalidation
--          all live in PHP, and a direct UPDATE will silently desynchronise the
--          gradebook. Writes go through the Web Services API or gradelib.php.
--
-- Create a dedicated read-only role before running any of this:
--
--   CREATE ROLE lja_reader LOGIN PASSWORD '<from .env, not committed>';
--   GRANT CONNECT ON DATABASE moodle TO lja_reader;
--   GRANT USAGE ON SCHEMA public TO lja_reader;
--   GRANT SELECT ON ALL TABLES IN SCHEMA public TO lja_reader;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA public
--       GRANT SELECT ON TABLES TO lja_reader;
--
-- If your instance uses a different prefix, check $CFG->prefix in config.php.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Reference: how advanced grading hangs together
--
--   grading_areas          one row per gradable area (one per activity)
--     -> grading_definitions   the rubric itself (criteria + levels)
--          -> gradingform_rubric_criteria
--               -> gradingform_rubric_levels
--     -> grading_instances     one row per act of grading one submission
--          -> gradingform_rubric_fillings   the level chosen per criterion
--
-- grading_instances.status uses gradingform_instance constants:
--     0 = NEEDUPDATE   rubric was edited after this grading; stale
--     1 = ACTIVE       the current, authoritative grading
--     2 = INCOMPLETE   draft, not yet saved
--     3 = ARCHIVE      superseded by a later grading
-- Always filter on status = 1 unless you deliberately want grading history.
--
-- grading_instances.itemid is NOT a user id. For assignments it is
-- mdl_assign_grades.id — the grade record — which is where userid lives.
-- This is the join people most often get wrong.
--
-- grading_areas.contextid points at a CONTEXT_MODULE row (contextlevel = 70),
-- whose instanceid is the course module id. That is the hop from the grading
-- subsystem back out to a subject.
-- -----------------------------------------------------------------------------


-- =============================================================================
-- QUERY 1 — Rubric definitions
--
-- Every criterion and every level for each rubric in the instance. Run this
-- first: it is the vocabulary your competency mapping table has to cover, and
-- it tells you what the parsing engine will be fed before any student data
-- exists.
-- =============================================================================

SELECT
    c.shortname                                   AS subject_code,
    a.name                                        AS assessment_name,
    gd.name                                       AS rubric_name,
    gd.status                                     AS definition_status,  -- 20 = ready
    rc.sortorder                                  AS criterion_order,
    rc.description                                AS criterion,
    rl.score                                      AS level_score,
    rl.definition                                 AS level_descriptor,
    MAX(rl.score) OVER (PARTITION BY rc.id)       AS criterion_max_score
FROM mdl_gradingform_rubric_criteria rc
JOIN mdl_gradingform_rubric_levels   rl  ON rl.criterionid = rc.id
JOIN mdl_grading_definitions         gd  ON gd.id          = rc.definitionid
JOIN mdl_grading_areas               ga  ON ga.id          = gd.areaid
JOIN mdl_context                     ctx ON ctx.id          = ga.contextid
                                        AND ctx.contextlevel = 70
JOIN mdl_course_modules              cm  ON cm.id          = ctx.instanceid
JOIN mdl_modules                     m   ON m.id           = cm.module
JOIN mdl_assign                      a   ON a.id           = cm.instance
JOIN mdl_course                      c   ON c.id           = cm.course
WHERE gd.method = 'rubric'
  AND m.name    = 'assign'
ORDER BY c.shortname, a.name, rc.sortorder, rl.score;


-- =============================================================================
-- QUERY 2 — Per-criterion rubric fills, per student
--
-- THE query for this project. One row per student, per assessment, per rubric
-- criterion: the level awarded, its score, the criterion ceiling, a normalised
-- percentage, and the marker's free-text remark.
--
-- The remark column is the signal the gap detector actually needs. It is stored
-- as HTML (remarkformat = 1) so strip tags downstream rather than in SQL.
-- =============================================================================

SELECT
    c.shortname                              AS subject_code,
    c.fullname                               AS subject_name,
    a.id                                     AS assignment_id,
    a.name                                   AS assessment_name,
    u.id                                     AS user_id,
    u.idnumber                               AS student_id_number,
    gd.name                                  AS rubric_name,
    rc.sortorder                             AS criterion_order,
    rc.description                           AS criterion,
    rl.definition                            AS level_awarded,
    rl.score                                 AS level_score,
    lvl.max_score                            AS criterion_max_score,
    ROUND(
        (rl.score / NULLIF(lvl.max_score, 0)) * 100,
        1
    )                                        AS criterion_pct,
    rf.remark                                AS marker_remark,
    gi.rawgrade                              AS rubric_total_normalised,
    ag.grade                                 AS gradebook_grade,
    a.grade                                  AS assessment_max_grade,
    to_timestamp(gi.timemodified)            AS graded_at,
    grader.id                                AS grader_user_id
FROM mdl_gradingform_rubric_fillings rf
JOIN mdl_grading_instances           gi     ON gi.id           = rf.instanceid
JOIN mdl_gradingform_rubric_criteria rc     ON rc.id           = rf.criterionid
-- LEFT JOIN: a filling can exist with levelid NULL if the marker left a remark
-- without selecting a level. Those rows matter — they are feedback with no mark.
LEFT JOIN mdl_gradingform_rubric_levels rl  ON rl.id           = rf.levelid
JOIN mdl_grading_definitions         gd     ON gd.id           = gi.definitionid
JOIN mdl_grading_areas               ga     ON ga.id           = gd.areaid
JOIN mdl_context                     ctx    ON ctx.id          = ga.contextid
                                           AND ctx.contextlevel = 70
JOIN mdl_course_modules              cm     ON cm.id           = ctx.instanceid
JOIN mdl_modules                     m      ON m.id            = cm.module
                                           AND m.name          = 'assign'
JOIN mdl_assign                      a      ON a.id            = cm.instance
JOIN mdl_assign_grades               ag     ON ag.id           = gi.itemid
                                           AND ag.assignment   = a.id
JOIN mdl_user                        u      ON u.id            = ag.userid
JOIN mdl_user                        grader ON grader.id        = gi.raterid
JOIN mdl_course                      c      ON c.id            = cm.course
-- Criterion ceiling, computed once per criterion rather than per row.
CROSS JOIN LATERAL (
    SELECT MAX(score) AS max_score
    FROM mdl_gradingform_rubric_levels
    WHERE criterionid = rc.id
) lvl
WHERE gi.status = 1          -- ACTIVE grading only
  AND u.deleted = 0
ORDER BY c.shortname, a.name, u.id, rc.sortorder;


-- =============================================================================
-- QUERY 3 — Legacy Outcomes attainment
--
-- If the instance uses Moodle Outcomes ($CFG->enableoutcomes = 1), outcome
-- scores are stored as ordinary grade items whose outcomeid is set. This is the
-- cheapest possible path to per-SILO attainment, because the mapping already
-- exists in the schema — no bridging table needed.
--
-- Returns nothing if outcomes are disabled or none are attached to activities.
-- =============================================================================

SELECT
    c.shortname                         AS subject_code,
    o.shortname                         AS outcome_code,
    o.fullname                          AS outcome_statement,
    gi.itemmodule                       AS activity_type,
    gi.itemname                         AS activity_name,
    u.id                                AS user_id,
    u.idnumber                          AS student_id_number,
    gg.finalgrade                       AS outcome_score,
    gi.grademax                         AS outcome_max,
    s.scale                             AS scale_values,   -- comma-separated
    gg.feedback                         AS outcome_feedback,
    to_timestamp(gg.timemodified)       AS scored_at
FROM mdl_grade_items    gi
JOIN mdl_grade_outcomes o  ON o.id  = gi.outcomeid
JOIN mdl_grade_grades   gg ON gg.itemid = gi.id
JOIN mdl_user           u  ON u.id  = gg.userid
JOIN mdl_course         c  ON c.id  = gi.courseid
LEFT JOIN mdl_scale     s  ON s.id  = gi.scaleid
WHERE gi.outcomeid IS NOT NULL
  AND gg.finalgrade IS NOT NULL
  AND u.deleted = 0
ORDER BY u.id, c.shortname, o.shortname;


-- =============================================================================
-- QUERY 4 — Competency framework attainment
--
-- The modern equivalent. Competencies live in a framework, link to courses via
-- competency_coursecomp and to individual activities via competency_modulecomp,
-- and per-user proficiency accumulates in competency_usercomp with an audit
-- trail in competency_evidence.
--
-- proficiency: NULL = not yet rated, 0 = not proficient, 1 = proficient
-- =============================================================================

SELECT
    f.shortname                         AS framework,
    f.idnumber                          AS framework_idnumber,
    comp.idnumber                       AS competency_idnumber,
    comp.shortname                      AS competency,
    comp.path                           AS competency_path,   -- /0/parent/child
    u.id                                AS user_id,
    u.idnumber                          AS student_id_number,
    uc.proficiency                      AS is_proficient,
    uc.grade                            AS competency_grade,
    uc.status                           AS review_status,
    c.shortname                         AS linked_subject,
    to_timestamp(uc.timemodified)       AS rated_at
FROM mdl_competency_usercomp   uc
JOIN mdl_competency            comp ON comp.id = uc.competencyid
JOIN mdl_competency_framework  f    ON f.id    = comp.competencyframeworkid
JOIN mdl_user                  u    ON u.id    = uc.userid
-- A competency can be linked to several subjects; this fans out deliberately.
LEFT JOIN mdl_competency_coursecomp cc ON cc.competencyid = comp.id
LEFT JOIN mdl_course                c  ON c.id            = cc.courseid
WHERE u.deleted = 0
ORDER BY u.id, f.shortname, comp.path;


-- =============================================================================
-- QUERY 5 — Activity-to-competency linkage
--
-- Which assessments in which subjects are declared to evidence which
-- competencies. This is the schema-level version of the "assessment to outcome
-- map" — read it before building your own bridging table, because anything
-- already declared here should not be duplicated.
-- =============================================================================

SELECT
    c.shortname            AS subject_code,
    m.name                 AS activity_type,
    cm.id                  AS course_module_id,
    comp.idnumber          AS competency_idnumber,
    comp.shortname         AS competency,
    mc.ruleoutcome         AS completion_rule   -- 0 none, 1 evidence,
                                                -- 2 recommend, 3 complete
FROM mdl_competency_modulecomp mc
JOIN mdl_competency      comp ON comp.id = mc.competencyid
JOIN mdl_course_modules  cm   ON cm.id   = mc.cmid
JOIN mdl_modules         m    ON m.id    = cm.module
JOIN mdl_course          c    ON c.id    = cm.course
ORDER BY c.shortname, cm.id;


-- =============================================================================
-- OUR SCHEMA — the bridging table
--
-- Create this in the Learning Journey Assistant's own database, NOT inside
-- Moodle. It is the artefact Scott said last semester's teams did not build:
-- the explicit link from a rubric criterion to a subject intended learning
-- outcome, with a weight expressing how strongly that criterion evidences it.
--
-- Keep it data, not code. It has to be editable by an academic without a
-- deployment, and auditable when the assistant explains why it flagged a gap.
-- =============================================================================

CREATE TABLE IF NOT EXISTS lja_criterion_silo_map (
    id                  BIGSERIAL PRIMARY KEY,

    -- Source side: identify the Moodle rubric criterion. Store the natural key
    -- as well as the id, because ids are not stable across instance rebuilds.
    subject_code        TEXT        NOT NULL,
    assessment_name     TEXT        NOT NULL,
    criterion_text      TEXT        NOT NULL,
    moodle_criterion_id BIGINT,

    -- Target side: the SILO, addressed by the same idnumber used in the
    -- competency framework CSV so the two representations stay reconcilable.
    silo_idnumber       TEXT        NOT NULL,
    silo_statement      TEXT        NOT NULL,

    -- How strongly this criterion evidences that SILO. Multiple criteria may
    -- map to one SILO and vice versa; weights within a SILO need not sum to 1,
    -- but the aggregation query should normalise.
    weight              NUMERIC(4,3) NOT NULL DEFAULT 1.000
                            CHECK (weight > 0 AND weight <= 1),

    -- Provenance. Recommendations that cannot be traced to a human-approved
    -- mapping should be presented differently in the UI.
    mapped_by           TEXT        NOT NULL DEFAULT 'manual'
                            CHECK (mapped_by IN ('manual', 'llm', 'imported')),
    confirmed_by_staff  BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (subject_code, assessment_name, criterion_text, silo_idnumber)
);

CREATE INDEX IF NOT EXISTS idx_criterion_silo_map_silo
    ON lja_criterion_silo_map (silo_idnumber);


-- =============================================================================
-- QUERY 6 — Gap detection across subjects
--
-- The aggregation Scott described: a weakness in one subject is one data point,
-- a weakness recurring across subjects is actionable. Assumes Query 2's output
-- has been loaded into the assistant's database as lja_criterion_score, joined
-- to the bridging table above.
--
-- Expected upstream table:
--   lja_criterion_score(user_id, subject_code, assessment_name,
--                       criterion_text, criterion_pct, marker_remark, graded_at)
--
-- Tune the two thresholds with the project owner; do not hardcode them in
-- application logic.
--
-- -----------------------------------------------------------------------------
-- DIVERGENCE NOTICE (2026-08-26, Sprint 3 WP2 / S3-6) -- READ BEFORE USING THIS
--
-- The 50 / 65 thresholds below are now LEGACY. Classification semantics moved
-- to Python in lja/model/gap_detection.py, and they are no longer absolute:
-- a competency is judged against the variability within that individual
-- student's own profile -- median and median absolute deviation across their
-- competencies -- which is what the lodged tender's requirement 4 actually
-- promises ("rather than raw pass or fail thresholds"). Two absolute guards
-- remain, a floor and a ceiling, to catch the uniformly weak and uniformly
-- strong students that pure relative logic handles badly.
--
-- This query was DELIBERATELY NOT UPDATED. The Moodle path is not wired to
-- code until Sprint 4, and porting an algorithm whose thresholds the team has
-- not yet ratified would mean maintaining two implementations of a moving
-- target. An annotated divergence is fine; a silent one is not.
--
-- Consequence: running this query and running `python -m lja.cli` against the
-- same underlying data WILL produce different gap_classification values. That
-- is expected, not a bug, until the reconciliation below happens.
--
-- Reconciling the two is a SPRINT 4 TASK, owned with the rest of the Moodle
-- extraction work. Whoever picks it up should read
-- docs/adr/0001-relative-gap-detection.md first -- in particular the finding
-- that the supplied dataset's profiles are nearly flat, which affects whether
-- a SQL port is even worth doing before there is better data.
-- -----------------------------------------------------------------------------
-- =============================================================================

WITH scored AS (
    SELECT
        s.user_id,
        m.silo_idnumber,
        m.silo_statement,
        s.subject_code,
        s.criterion_pct,
        m.weight
    FROM lja_criterion_score s
    JOIN lja_criterion_silo_map m
      ON  m.subject_code    = s.subject_code
      AND m.assessment_name = s.assessment_name
      AND m.criterion_text  = s.criterion_text
    WHERE m.confirmed_by_staff        -- only staff-approved mappings drive advice
),
per_silo AS (
    SELECT
        user_id,
        silo_idnumber,
        silo_statement,
        -- Weighted attainment: criteria that evidence a SILO more strongly
        -- pull the estimate harder.
        SUM(criterion_pct * weight) / NULLIF(SUM(weight), 0) AS attainment_pct,
        COUNT(DISTINCT subject_code)                          AS subjects_evidencing,
        COUNT(*)                                              AS criteria_observed
    FROM scored
    GROUP BY user_id, silo_idnumber, silo_statement
)
SELECT
    user_id,
    silo_idnumber,
    silo_statement,
    ROUND(attainment_pct, 1) AS attainment_pct,
    subjects_evidencing,
    criteria_observed,
    CASE
        WHEN attainment_pct < 50 AND subjects_evidencing >= 2
            THEN 'persistent gap'
        WHEN attainment_pct < 50
            THEN 'isolated gap'
        WHEN attainment_pct < 65
            THEN 'developing'
        ELSE 'proficient'
    END AS gap_classification
FROM per_silo
-- Only surface a judgement when there is enough evidence to support one.
WHERE criteria_observed >= 2
ORDER BY user_id, attainment_pct ASC;
