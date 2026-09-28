<?php
// This file is part of the Learning Journey Assistant dev environment.
//
// mark_rubric_from_json.php — IOLG-113
//
// Data-driven successor to the IOLG-56 fixture (mark_rubric_fixture.php, which
// bakes one rubric and five students into PHP constants). This one replays a
// marking plan from a JSON file written by the Python catalogue generator:
//
//     python -m lja.data.catalogue_generator ../data-fixtures/subject_catalogue.yaml \
//         --students 300 --out ... --moodle-out ../data-fixtures/moodle-generated
//
// so the courses, assignments, rubric criteria, per-student levels and remarks
// all come from the same catalogue and the same generated cohort as the Excel
// workbook. One definition, both paths.
//
// The JSON is a list of fixtures, each:
//   { "course": "CSE1IOI", "assignment": "Assignment 1", "rubric_name": "...",
//     "criteria": ["...", "..."], "levels": {"0": "Not demonstrated", ...},
//     "students": [ {"scores": [2, 1], "remarks": ["...", "..."]}, ... ] }
//
// Rules carried over from the IOLG-56 script, unchanged:
//   - Never writes to the grade tables directly. The rubric goes through the
//     grading controller API and marks through assign::save_grade(), the same
//     path as the grading UI and the mod_assign_save_grade web service.
//   - Idempotent. A rubric is defined once; re-runs re-grade and Moodle archives
//     the superseded grading instances (status = 3), so Query 2's status = 1
//     filter keeps returning one active row per (student, criterion).
//   - A course or assignment that is missing is reported and skipped, not
//     fatal: seed.sh at size XS makes one assignment per course, and a
//     catalogue subject with four assessments will only find "Assignment 1".
//   - An existing rubric whose criteria differ from the fixture is NOT
//     redefined (that would orphan gradings); it is reported and skipped.
//
// Run inside the webserver container:
//     php /tmp/mark_rubric_from_json.php /tmp/rubric_fixture.json
//
// @package    local_ljadev
// @copyright  2026 LJA team (CSE5IDP)
// @license    http://www.gnu.org/copyleft/gpl.html GNU GPL v3 or later

define('CLI_SCRIPT', true);

require('/var/www/html/config.php');
require_once($CFG->dirroot . '/mod/assign/locallib.php');
require_once($CFG->dirroot . '/grade/grading/lib.php');
require_once($CFG->libdir . '/gradelib.php');
require_once($CFG->libdir . '/clilib.php');

if ($argc < 2 || !is_readable($argv[1])) {
    cli_error("Usage: php mark_rubric_from_json.php <rubric_fixture.json>");
}
$fixtures = json_decode(file_get_contents($argv[1]), true);
if (!is_array($fixtures)) {
    cli_error("Could not parse {$argv[1]} as a JSON list of fixtures.");
}

$admin = get_admin();
if (!$admin) {
    cli_error('No admin user found — is this a fully installed Moodle?');
}
\core\session\manager::set_user($admin);

$summary = ['marked' => 0, 'rubrics' => 0, 'skipped' => 0];

foreach ($fixtures as $fixture) {
    $shortname = $fixture['course'];
    $assignname = $fixture['assignment'];
    $label = "{$shortname} / {$assignname}";

    $course = $DB->get_record('course', ['shortname' => $shortname]);
    if (!$course) {
        cli_writeln("SKIP {$label}: course not found (run devenv/seed.sh with this shortname first).");
        $summary['skipped']++;
        continue;
    }
    $assignrec = $DB->get_record('assign', ['course' => $course->id, 'name' => $assignname]);
    if (!$assignrec) {
        cli_writeln("SKIP {$label}: assignment not found (seed size too small, or set moodle_assignment in the catalogue).");
        $summary['skipped']++;
        continue;
    }
    $cm = get_coursemodule_from_instance('assign', $assignrec->id, $course->id, false, MUST_EXIST);
    $context = context_module::instance($cm->id);
    $assign = new assign($context, $cm, $course);

    // ------------------------------------------------------------------ rubric
    $gradingman = get_grading_manager($context, 'mod_assign', 'submissions');
    $gradingman->set_active_method('rubric');
    $controller = $gradingman->get_controller('rubric');

    $criteria = array_values($fixture['criteria']);
    $levels = $fixture['levels'];
    ksort($levels, SORT_NUMERIC);

    if ($controller->is_form_defined()) {
        $existing = $controller->get_definition(true);
        $existingtexts = [];
        foreach ($existing->rubric_criteria as $criterion) {
            $existingtexts[] = $criterion['description'];
        }
        if ($existingtexts !== $criteria) {
            cli_writeln("SKIP {$label}: a rubric with different criteria already exists; not redefining it.");
            $summary['skipped']++;
            continue;
        }
    } else {
        $criteriadef = [];
        foreach ($criteria as $i => $description) {
            $leveldef = [];
            $li = 1;
            foreach ($levels as $score => $descriptor) {
                $leveldef['NEWID' . $li] = ['definition' => $descriptor, 'score' => (int) $score];
                $li++;
            }
            $criteriadef['NEWID' . ($i + 1)] = [
                'sortorder'   => $i + 1,
                'description' => $description,
                'levels'      => $leveldef,
            ];
        }
        $definition = (object) [
            'name'               => $fixture['rubric_name'],
            'description_editor' => [
                'text'   => 'Rubric generated from the LJA subject catalogue (IOLG-113).',
                'format' => FORMAT_HTML,
                'itemid' => 1,
            ],
            'rubric' => [
                'criteria' => $criteriadef,
                'options'  => [
                    'sortlevelsasc'          => 1,
                    'lockzeropoints'         => 1,
                    'showdescriptionteacher' => 1,
                    'showdescriptionstudent' => 1,
                    'showscoreteacher'       => 1,
                    'showscorestudent'       => 1,
                    'enableremarks'          => 1,
                    'showremarksstudent'     => 1,
                ],
            ],
            'saverubric' => 'Save rubric and make it ready',
            'status'     => gradingform_controller::DEFINITION_STATUS_READY,
        ];
        $controller->update_definition($definition);
        $summary['rubrics']++;
        cli_writeln("{$label}: created rubric '{$fixture['rubric_name']}' with " . count($criteria) . ' criteria.');
    }

    $definition = $controller->get_definition(true);
    $criterionidbytext = [];
    $levelidbyscore = [];
    foreach ($definition->rubric_criteria as $criterionid => $criterion) {
        $criterionidbytext[$criterion['description']] = $criterionid;
        foreach ($criterion['levels'] as $levelid => $level) {
            $levelidbyscore[$criterionid][(int) $level['score']] = $levelid;
        }
    }

    // ----------------------------------------------------------------- marking
    $plan = array_values($fixture['students']);
    $enrolled = get_enrolled_users($context, 'mod/assign:submit', 0, 'u.*', 'u.id ASC');
    $students = array_slice(array_values($enrolled), 0, count($plan));
    if (count($students) < count($plan)) {
        cli_writeln("{$label}: only " . count($students) . ' of ' . count($plan) . ' planned students are enrolled; marking those.');
    }

    foreach ($students as $si => $student) {
        $criteriafill = [];
        foreach ($criteria as $ci => $description) {
            $criterionid = $criterionidbytext[$description];
            $score = (int) $plan[$si]['scores'][$ci];
            if (!isset($levelidbyscore[$criterionid][$score])) {
                cli_error("{$label}: level score {$score} is not in the rubric's ladder.");
            }
            $criteriafill[$criterionid] = [
                'levelid'      => $levelidbyscore[$criterionid][$score],
                'remark'       => $plan[$si]['remarks'][$ci],
                'remarkformat' => FORMAT_HTML,
            ];
        }
        $data = new stdClass();
        $data->attemptnumber = -1;
        $data->addattempt = true;
        $data->assignfeedbackcomments_editor = ['text' => '', 'format' => FORMAT_HTML];
        $data->advancedgrading = ['criteria' => $criteriafill];
        $assign->save_grade($student->id, $data);
        $summary['marked']++;
    }
    cli_writeln("{$label}: marked " . count($students) . ' students.');
}

cli_writeln("Done. {$summary['rubrics']} rubrics created, {$summary['marked']} gradings saved, {$summary['skipped']} fixtures skipped.");
