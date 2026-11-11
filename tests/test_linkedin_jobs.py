from jobalert.sources.linkedin_jobs import parse_linkedin

PAGE = """
<script type="application/ld+json">
{"@type":"ItemList","itemListElement":[
  {"@type":"ListItem","url":"https://in.linkedin.com/jobs/view/associate-software-engineer-at-northwind-4482225289","name":"Associate Software Engineer","disambiguatingDescription":"Northwind","description":"Telangana, India"},
  {"@type":"ListItem","url":"https://in.linkedin.com/jobs/view/nurse-1","name":"Nurse","disambiguatingDescription":"Clinic","description":"Mumbai"}
]}
</script>
"""


def test_linkedin_search_keeps_an_india_software_role():
    openings = parse_linkedin(PAGE, ["Software Engineer"])
    assert len(openings) == 1
    job = openings[0].job
    assert job.team == "Northwind"
    assert job.location == "Telangana, India"
    assert job.id == "4482225289"
    assert job.url.endswith("associate-software-engineer-at-northwind-4482225289")
