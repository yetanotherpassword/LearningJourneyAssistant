<?php
// This file is part of the Learning Journey Assistant dev environment.
//
// mark_rubric_fixture.php — IOLG-56
//
// Gives the devenv Moodle something for SQL Query 2 to return: one rubric on one
// assignment, marked for five students, every filling carrying a remark. Route B
// of IOLG-56 ("build by hand in the generated subject") — there is no supplied
// .mbz in data-fixtures/, so the restore route is not available.
//
// This is the reproducible "script that replays the marking" the ticket's step 4
// asks for: after a fresh bootstrap.sh + seed.sh, running this rebuilds the exact
// fixture. It is idempotent — the rubric is only defined once, and re-running only
// re-grades (Moodle archives the superseded grading instances, so Query 2's
// status = 1 filter still returns one active row per criterion).
//
// It NEVER writes to the grade tables directly (the hard rule in devenv/README.md
// and the SQL header). The rubric is created through the grading controller API,
// and the marks go through assign::save_grade(), the same path the grading UI and
// the mod_assign_save_grade web service use — so grade aggregation, events and
// cache invalidation all happen in PHP as Moodle expects.
//
// Run inside the webserver container:
//     php /tmp/mark_rubric_fixture.php
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

// -----------------------------------------------------------------------------
// Fixture definition — edit here, nowhere else.
// -----------------------------------------------------------------------------

$COURSE_SHORTNAME = 'CSE1IOI';
$ASSIGN_NAME      = 'Assignment 1';
$RUBRIC_NAME      = 'LJA Foundations Rubric';
$NUM_STUDENTS     = 5;

// Three criteria, each mapped (in data-fixtures/criterion_silo_map_CSE1IOI.csv)
// to a subject SILO. Keep the descriptions here identical to the criterion_text
// column of that CSV — the map is joined to Query 2 on the criterion text.
$CRITERIA = [
    'Problem decomposition and algorithm design',
    'Correct implementation and testing',
    'Code quality and documentation',
];

// Shared level ladder for every criterion: score => descriptor.
$LEVELS = [
    0 => 'Not demonstrated',
    1 => 'Developing',
    2 => 'Proficient',
    3 => 'Exemplary',
];

// Per-student marking. Index 0..4 aligns with the first five enrolled students
// (ordered by user id). Each row is [c1_score, c2_score, c3_score]. The middle
// criterion deliberately spans the full 0..3 range across the cohort so at least
// one criterion varies, per the ticket.
$SCORES = [
    [3, 3, 2],
    [2, 1, 2],
    [1, 0, 1],
    [2, 2, 3],
    [0, 1, 1],
];

// One remark per filling — [student_index][criterion_index]. Every filling has a
// remark because it is a Query 2 output column and the point of the fixture is to
// give the parsing engine realistic feedback to chew on.
$REMARKS = [
    [
        'Clear breakdown of the problem into well-chosen sub-steps.',
        'All test cases pass and edge cases are handled thoughtfully.',
        'Readable, but a few functions would benefit from doc comments.',
    ],
    [
        'Decomposition is sound; some steps could be split further.',
        'Core logic works but two boundary cases fail — revisit input validation.',
        'Naming is consistent and the layout is easy to follow.',
    ],
    [
        'The overall approach is unclear; plan the algorithm before coding.',
        'Implementation does not yet produce correct output on the samples.',
        'Formatting is inconsistent; run the formatter and add comments.',
    ],
    [
        'Good decomposition, though one sub-problem is solved twice.',
        'Correct on all provided cases; add a couple of your own tests.',
        'Excellent documentation — clear docstrings and inline rationale.',
    ],
    [
        'Little evidence of decomposition; the solution is one long block.',
        'Partially working — the main loop terminates early on empty input.',
        'Some comments present but variable names are hard to follow.',
    ],
];

// -----------------------------------------------------------------------------
// Run as an administrator so capability checks and grading pass cleanly.
// -----------------------------------------------------------------------------

$admin = get_admin();
if (!$admin) {
    cli_error('No admin user found — is this a fully installed Moodle?');
}
\core\session\manager::set_user($admin);

// -----------------------------------------------------------------------------
// Resolve course, assignment, module context.
// -----------------------------------------------------------------------------

$course = $DB->get_record('course', ['shortname' => $COURSE_SHORTNAME], '*', MUST_EXIST);
$assignrec = $DB->get_record('assign', ['course' => $course->id, 'name' => $ASSIGN_NAME], '*', MUST_EXIST);
$cm = get_coursemodule_from_instance('assign', $assignrec->id, $course->id, false, MUST_EXIST);
$context = context_module::instance($cm->id);
$assign = new assign($context, $cm, $course);

cli_writeln("Course:     {$course->shortname} (id {$course->id})");
cli_writeln("Assignment: {$assignrec->name} (assign id {$assignrec->id}, cmid {$cm->id})");

// -----------------------------------------------------------------------------
// 1. Create the rubric definition (once) and make it the active grading method.
// -----------------------------------------------------------------------------

$gradingman = get_grading_manager($context, 'mod_assign', 'submissions');
$gradingman->set_active_method('rubric');
$controller = $gradingman->get_controller('rubric');

if ($controller->is_form_defined()) {
    cli_writeln('Rubric already defined — reusing it.');
} else {
    $criteriadef = [];
    foreach ($CRITERIA as $i => $description) {
        $leveldef = [];
        $li = 1;
        foreach ($LEVELS as $score => $descriptor) {
            $leveldef['NEWID' . $li] = ['definition' => $descriptor, 'score' => $score];
            $li++;
        }
        $criteriadef['NEWID' . ($i + 1)] = [
            'sortorder'   => $i + 1,
            'description' => $description,
            'levels'      => $leveldef,
        ];
    }

    $definition = (object) [
        'name'               => $RUBRIC_NAME,
        'description_editor' => [
            'text'   => 'Formative rubric for the LJA gap-detection fixture (IOLG-56).',
            'format' => FORMAT_HTML,
            'itemid' => 1,
        ],
        'rubric' => [
            'criteria' => $criteriadef,
            'options'  => [
                'sortlevelsasc'         => 1,
                'lockzeropoints'        => 1,
                'showdescriptionteacher' => 1,
                'showdescriptionstudent' => 1,
                'showscoreteacher'      => 1,
                'showscorestudent'      => 1,
                'enableremarks'         => 1,
                'showremarksstudent'    => 1,
            ],
        ],
        'saverubric' => 'Save rubric and make it ready',
        'status'     => gradingform_controller::DEFINITION_STATUS_READY,
    ];

    $controller->update_definition($definition);
    cli_writeln("Created rubric '{$RUBRIC_NAME}' with " . count($CRITERIA) . ' criteria.');
}

// Reload the persisted definition so we have the real criterion and level ids.
$definition = $controller->get_definition(true);

// description => criterionid, and (criterionid, score) => levelid.
$criterionidbytext = [];
$levelidbyscore = [];
foreach ($definition->rubric_criteria as $criterionid => $criterion) {
    $criterionidbytext[$criterion['description']] = $criterionid;
    foreach ($criterion['levels'] as $levelid => $level) {
        $levelidbyscore[$criterionid][(int) $level['score']] = $levelid;
    }
}

// -----------------------------------------------------------------------------
// 2. Resolve the first five enrolled students (by user id) and mark them.
// -----------------------------------------------------------------------------

$enrolled = get_enrolled_users($context, 'mod/assign:submit', 0, 'u.*', 'u.id ASC');
$students = array_slice(array_values($enrolled), 0, $NUM_STUDENTS);
if (count($students) < $NUM_STUDENTS) {
    cli_error('Need at least ' . $NUM_STUDENTS . ' enrolled students; found ' . count($students) .
        '. Run devenv/seed.sh first.');
}

foreach ($students as $si => $student) {
    $criteriafill = [];
    foreach ($CRITERIA as $ci => $description) {
        $criterionid = $criterionidbytext[$description];
        $score = $SCORES[$si][$ci];
        $levelid = $levelidbyscore[$criterionid][$score];
        $criteriafill[$criterionid] = [
            'levelid'      => $levelid,
            'remark'       => $REMARKS[$si][$ci],
            'remarkformat' => FORMAT_HTML,
        ];
    }

    $data = new stdClass();
    $data->attemptnumber = -1;
    $data->addattempt = true;
    // assignfeedback_comments is enabled by default on generated assignments; give
    // it an empty editor payload so its is_feedback_modified() check is a no-op.
    $data->assignfeedbackcomments_editor = ['text' => '', 'format' => FORMAT_HTML];
    $data->advancedgrading = ['criteria' => $criteriafill];

    $assign->save_grade($student->id, $data);

    $line = "  marked user {$student->id} ({$student->firstname} {$student->lastname}): "
        . implode('/', $SCORES[$si]);
    cli_writeln($line);
}

cli_writeln('Done. ' . count($students) . ' students marked against ' . count($CRITERIA) . ' criteria.');
