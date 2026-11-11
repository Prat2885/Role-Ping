from jobalert.llm_scan import indexes_from_llm, profile_from_llm
from jobalert.related import related_queries


def test_backend_intern_includes_related_engineering_titles():
    queries = related_queries("Backend Intern", "intern")
    assert "Backend Intern" in queries
    assert "Backend Engineer" in queries
    assert "Backend Developer" in queries
    assert "Full Stack Engineer" in queries
    assert "Full Stack Engineer Intern" in queries
    assert "Fullstack Engineer" in queries
    assert "Software Engineer" in queries


def test_senior_profile_drops_intern_titles():
    queries = related_queries("Senior Software Engineer", "senior")
    assert "Software Engineer" in queries
    assert all("intern" not in query.casefold() for query in queries)


def test_llm_json_becomes_a_profile():
    parsed = profile_from_llm(
        '{"level":"intern","years":0.3,"queries":["Backend Intern","Software Engineer"]}'
    )
    assert parsed == {
        "level": "intern",
        "years": 0.3,
        "queries": ["Backend Intern", "Software Engineer"],
    }


def test_llm_json_without_titles_is_ignored():
    assert profile_from_llm('{"level":"intern","years":1,"queries":[]}') is None


def test_match_indexes_stay_inside_the_batch():
    assert indexes_from_llm('{"matches": [1, 1, 4, "no"]}', 3) == [1]
