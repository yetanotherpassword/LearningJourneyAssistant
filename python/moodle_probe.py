"""
moodle_probe.py — minimal Moodle Web Services client.

A Sprint 1 spike. Verifies connectivity to a self-hosted Moodle instance,
enumerates the functions the token is authorised to call, and pulls per-student
grade items with feedback for one course.

Deliberately not production code: no retries, no paging, no caching, no
concurrency. Its job is to answer "can we get the data, and what shape is it".

Usage:
    conda env create -f environment.yml
    conda activate lja
    cp .env.example .env      # then fill in MOODLE_URL and MOODLE_TOKEN
    python moodle_probe.py

Endpoint reference: Site administration -> Server -> Web services ->
API Documentation. That page is version-exact for your instance and is the
authoritative list of function names, parameters and return schemas.
"""

from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("MOODLE_URL", "").rstrip("/")
TOKEN = os.environ.get("MOODLE_TOKEN", "")

if not BASE_URL or not TOKEN:
    sys.exit("MOODLE_URL and MOODLE_TOKEN must be set. See .env.example.")

ENDPOINT = f"{BASE_URL}/webservice/rest/server.php"
TIMEOUT_SECONDS = 30


def call(function: str, **params) -> dict | list:
    """Invoke a Moodle web service function and return the parsed JSON.

    Moodle returns HTTP 200 even on application-level failure, signalling the
    error via an 'exception' key in the response body. Checking the status code
    alone is therefore not sufficient.

    Args:
        function: the wsfunction name, e.g. 'core_course_get_courses'.
        **params: function-specific parameters, passed through as form data.

    Raises:
        RuntimeError: if Moodle reports an application-level exception.
        requests.HTTPError: on a transport or HTTP-level failure.
    """
    payload = {
        "wstoken": TOKEN,
        "wsfunction": function,
        "moodlewsrestformat": "json",
        **params,
    }

    response = requests.post(ENDPOINT, data=payload, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()

    if isinstance(body, dict) and "exception" in body:
        raise RuntimeError(
            f"{function} failed: {body.get('errorcode')} — {body.get('message')}"
        )

    return body


def describe_site() -> dict:
    """Confirm the token works and report what this account may call."""
    site = call("core_webservice_get_site_info")
    print(f"Connected to {site['sitename']} (Moodle {site['release']})")
    print(f"Authenticated as {site['fullname']} (user id {site['userid']})")
    print(f"Authorised functions: {len(site['functions'])}\n")
    return site


def list_courses() -> list[dict]:
    """Return real courses, excluding the site-level pseudo-course (id 1)."""
    courses = [c for c in call("core_course_get_courses") if c["id"] != 1]

    print(f"{len(courses)} course(s) found:")
    for course in courses:
        print(f"  [{course['id']:>3}] {course['shortname']:<16} {course['fullname']}")
    print()

    return courses


def dump_grade_items(course_id: int, limit: int | None = 5) -> None:
    """Print grade items and feedback presence for students in one course.

    Args:
        course_id: the Moodle course id.
        limit: cap on students printed, to keep spike output readable.
               Pass None for all.
    """
    students = call("core_enrol_get_enrolled_users", courseid=course_id)
    if limit is not None:
        students = students[:limit]

    for student in students:
        report = call(
            "gradereport_user_get_grade_items",
            courseid=course_id,
            userid=student["id"],
        )

        for table in report.get("usergrades", []):
            print(f"{table['userfullname']} (user id {table['userid']})")

            for item in table["gradeitems"]:
                # 'feedback' carries the marker's comment as HTML. Note that
                # this is the overall item feedback only — per-criterion rubric
                # remarks are NOT exposed here. See the SQL bundle.
                has_feedback = bool(item.get("feedback"))
                print(
                    f"    {str(item['itemname']):<44} "
                    f"grade={item['graderaw']!s:<8} "
                    f"feedback={'yes' if has_feedback else 'no'}"
                )
            print()


def main() -> None:
    describe_site()
    courses = list_courses()

    if not courses:
        print("No courses to inspect. Seed the instance first — see the devenv bundle.")
        return

    dump_grade_items(courses[0]["id"])


if __name__ == "__main__":
    main()
