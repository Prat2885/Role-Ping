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


def test_one_year_profile_rejects_roles_above_junior():
    profile = {"level": "junior", "years": 1}
    assert job_fits(profile, "Associate Software Engineer") is True
    assert job_fits(profile, "Software Engineer Intern") is True
    assert job_fits(profile, "Software Engineer III") is False
    assert job_fits(profile, "Software Engineer II") is False
    assert job_fits(profile, "Senior Software Engineer") is False
    assert job_fits(profile, "Software Engineer", "3+ years of experience") is False
    assert job_fits(profile, "Software Engineer", "0-1 years") is True

