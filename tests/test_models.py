from soulmatch.models import PIPELINE_STAGE_GROUPS, PIPELINE_STAGES, stage_group_label


def test_stage_group_label_prefixes_group_name():
    assert stage_group_label("New") == "Screening — New"
    assert stage_group_label("Parents Contacted") == "Outreach — Parents Contacted"
    assert stage_group_label("Marriage") == "Outcome — Marriage"


def test_stage_group_label_falls_back_for_unknown_stage():
    assert stage_group_label("Not A Real Stage") == "Not A Real Stage"


def test_every_pipeline_stage_is_grouped_exactly_once():
    grouped_stages = [s for stages in PIPELINE_STAGE_GROUPS.values() for s in stages]
    assert sorted(grouped_stages) == sorted(PIPELINE_STAGES)
    assert len(grouped_stages) == len(set(grouped_stages))
