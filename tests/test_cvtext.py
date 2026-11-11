import pytest

from jobalert.cvtext import ProfileError, build_queries, infer_profile, read_cv

SENIOR_CV = """
Senior Software Engineer
Example Systems
January 2019 - Present

Software Engineer
Example Systems
June 2016 - December 2018

Built Python services for payment platforms and led a small team.
"""


def test_senior_cv_uses_the_latest_title_and_related_searches():
    profile = infer_profile(SENIOR_CV, "cv.txt")
    assert profile["level"] == "senior"
    assert profile["titles"][0] == "Senior Software Engineer"
    assert profile["years"] > 8
    assert "Software Engineer" in profile["queries"]
    assert "Full Stack Engineer" in profile["queries"]
    assert all("intern" not in query.casefold() for query in profile["queries"])


def test_title_level_wins_over_a_short_tenure():
    text = "Junior Accountant\nMarch 2025 - Present\nPrepared monthly reports for the finance team."
    profile = infer_profile(text, "cv.txt")
    assert profile["level"] == "junior"


def test_cv_without_a_role_is_rejected():
    with pytest.raises(ProfileError):
        infer_profile("This file has no jobs or dates in it at all, only a short note.", "cv.txt")


def test_experience_section_beats_the_degree_line():
    text = """
EDUCATION
Vishwakarma Institute of Technology 2021 - 2025
Computer Engineering -8.31 Pune, Maharashtra
EXPERIENCE
Backend Intern Oct 2025 - Jan 2026
Spring Money Pune
Built REST APIs using NestJS for onboarding automation and reliability.
"""
    profile = infer_profile(text, "cv.txt")
    assert profile["level"] == "intern"
    assert profile["titles"][0] == "Backend Intern"
    assert "Backend Intern" in profile["queries"]
    assert "Backend Engineer" in profile["queries"]
    assert "Full Stack Engineer" in profile["queries"]
    assert "Full Stack Engineer Intern" in profile["queries"]
    assert "Software Engineer" in profile["queries"]


def test_build_queries_drops_the_seniority_word():
    assert build_queries("Staff Data Scientist") == ["Staff Data Scientist", "Data Scientist"]


def test_read_txt_cv(tmp_path):
    path = tmp_path / "cv.txt"
    path.write_text(SENIOR_CV, encoding="utf-8")
    assert "Senior Software Engineer" in read_cv(path)
