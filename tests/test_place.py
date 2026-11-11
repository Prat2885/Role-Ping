from jobalert.place import place_fits


def test_india_roles_are_kept():
    assert place_fits("Backend Engineer", "Bengaluru, KA, IN")
    assert place_fits("Software Engineer", "Pune, India")
    assert place_fits("Full Stack Engineer", "Mumbai")


def test_open_remote_roles_are_kept():
    assert place_fits("Software Engineer", "Remote")
    assert place_fits("Software Engineer", "Worldwide")
    assert place_fits("Backend Engineer", "Remote - Global / Remote (US)")
    assert place_fits("Software Engineer", "Work from home")


def test_office_jobs_outside_india_are_left_out():
    assert place_fits("Software Engineer", "San Francisco, CA") is False
    assert place_fits("Software Engineer", "Shanghai, China") is False
    assert place_fits("Software Engineer", "New York, NY, US") is False
    assert place_fits("Software Engineer", "Remote (US)") is False
    assert place_fits("Software Engineer", "US / CA / Remote (US; CA)") is False
    assert place_fits("Software Engineer", "Remote, United States") is True
    assert place_fits("Software Engineer", "") is True
