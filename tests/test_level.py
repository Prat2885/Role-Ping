from jobalert.level import job_fits


PROFILE = {"level": "senior", "years": 7}


def test_senior_profile_rejects_intern_and_director_titles():
    assert job_fits(PROFILE, "Intern Designer") is False
    assert job_fits(PROFILE, "Director of Engineering") is False


def test_senior_profile_keeps_nearby_levels():
    assert job_fits(PROFILE, "Senior Backend Engineer") is True
    assert job_fits(PROFILE, "Staff Backend Engineer") is True
    assert job_fits(PROFILE, "Software Engineer") is True


def test_years_requirement_can_reject_a_matching_title():
    assert job_fits(PROFILE, "Senior Engineer", "10+ years of experience") is False
    assert job_fits(PROFILE, "Senior Engineer", "5+ years of experience") is True

