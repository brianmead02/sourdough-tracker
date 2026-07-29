"""Tiers, seasons and the achievement catalogue. Pure — no database."""

import itertools
import uuid
from datetime import UTC, datetime

import pytest

from app.api.v1.leaderboard import _row
from app.models.gamification import LeaderboardEntry
from app.services.achievements import ACHIEVEMENTS, BY_CODE
from app.services.achievements.definitions import BY_EVENT
from app.services.achievements.metrics import METRIC_FUNCTIONS
from app.services.events import BASE_XP, DAILY_CAPS, DomainEvent
from app.services.xp import TIERS, quarter_bounds, source_id_for, tier_for, tier_progress

# --- tiers --------------------------------------------------------------------


def test_a_new_baker_is_a_novice() -> None:
    assert tier_for(0).name == "Novice"


def test_tiers_are_ordered_and_reachable() -> None:
    thresholds = [t.threshold for t in TIERS]
    assert thresholds == sorted(thresholds)
    assert thresholds[0] == 0


@pytest.mark.parametrize("tier", TIERS)
def test_each_threshold_awards_its_own_tier(tier: object) -> None:
    assert tier_for(tier.threshold).name == tier.name  # type: ignore[attr-defined]


def test_tier_holds_until_the_next_threshold() -> None:
    assert tier_for(249).name == "Novice"
    assert tier_for(250).name == "Home Baker"


def test_progress_points_at_the_next_tier() -> None:
    progress = tier_progress(500)
    assert progress.tier == "Home Baker"
    assert progress.next_tier == "Levain Keeper"
    assert progress.xp_to_next == 500
    assert 0 < progress.progress_pct < 100


def test_the_top_tier_has_nowhere_further_to_go() -> None:
    progress = tier_progress(1_000_000)
    assert progress.tier == "Master Baker"
    assert progress.next_tier is None
    assert progress.progress_pct == 100.0


# --- seasons ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("month", "expected"),
    [(1, "Q1"), (3, "Q1"), (4, "Q2"), (6, "Q2"), (7, "Q3"), (9, "Q3"), (10, "Q4"), (12, "Q4")],
)
def test_quarters_are_derived_from_the_calendar(month: int, expected: str) -> None:
    name, _, _ = quarter_bounds(datetime(2026, month, 15, tzinfo=UTC))
    assert name == f"2026 {expected}"


def test_quarter_windows_are_contiguous_and_do_not_overlap() -> None:
    bounds = [quarter_bounds(datetime(2026, m, 1, tzinfo=UTC)) for m in (1, 4, 7, 10)]
    for (_, _, ends), (_, next_starts, _) in itertools.pairwise(bounds):
        assert ends == next_starts


def test_q4_rolls_into_the_next_year() -> None:
    _, _, ends = quarter_bounds(datetime(2026, 11, 20, tzinfo=UTC))
    assert ends == datetime(2027, 1, 1, tzinfo=UTC)


# --- award identity -----------------------------------------------------------


def test_source_ids_are_stable_and_distinct() -> None:
    """Awards with no natural row still need a key the unique constraint can use."""
    assert source_id_for("first_loaf") == source_id_for("first_loaf")
    assert source_id_for("first_loaf") != source_id_for("century_club")


# --- catalogue integrity ------------------------------------------------------


def test_catalogue_has_the_promised_breadth() -> None:
    assert len(ACHIEVEMENTS) >= 40


def test_achievement_codes_are_unique() -> None:
    codes = [a.code for a in ACHIEVEMENTS]
    assert len(codes) == len(set(codes))


def test_every_achievement_has_a_working_metric() -> None:
    """A badge whose metric has no implementation could never be earned."""
    for definition in ACHIEVEMENTS:
        assert definition.metric in METRIC_FUNCTIONS, definition.code


def test_every_achievement_is_reachable_from_some_event() -> None:
    """An achievement no event evaluates is dead weight."""
    reachable = {a.code for defs in BY_EVENT.values() for a in defs}
    assert {a.code for a in ACHIEVEMENTS} == reachable


def test_every_achievement_has_a_positive_target_and_award() -> None:
    for definition in ACHIEVEMENTS:
        assert definition.target > 0, definition.code
        assert definition.xp_award > 0, definition.code


def test_rarer_badges_pay_more() -> None:
    """Within a metric, a harder target must not be worth less."""
    by_metric: dict[str, list[tuple[float, int]]] = {}
    for definition in ACHIEVEMENTS:
        by_metric.setdefault(definition.metric, []).append((definition.target, definition.xp_award))
    for metric, entries in by_metric.items():
        ordered = sorted(entries)
        awards = [award for _, award in ordered]
        assert awards == sorted(awards), f"{metric} pays less for a harder target"


def test_flagship_badges_require_photographic_evidence() -> None:
    """The anti-cheat rule: the biggest claims cannot rest on typed numbers."""
    gated = {a.code for a in ACHIEVEMENTS if a.requires_photo}
    assert "hydration_85" in gated
    assert "hydration_95" in gated


def test_by_code_covers_the_catalogue() -> None:
    assert set(BY_CODE) == {a.code for a in ACHIEVEMENTS}


# --- event rates --------------------------------------------------------------


def test_every_event_has_a_defined_rate() -> None:
    for event in DomainEvent:
        assert event in BASE_XP, event


def test_paying_events_are_capped() -> None:
    """An uncapped paying event is a grinding opportunity."""
    for event, amount in BASE_XP.items():
        if amount > 0:
            assert event in DAILY_CAPS, event


def test_caps_are_above_a_plausible_day() -> None:
    """Caps exist to blunt farming, not to punish a busy baking day."""
    assert DAILY_CAPS[DomainEvent.bake_completed] >= 3
    assert DAILY_CAPS[DomainEvent.feeding_logged] >= 6


def test_a_bake_is_worth_more_than_a_feeding() -> None:
    assert BASE_XP[DomainEvent.bake_completed] > BASE_XP[DomainEvent.feeding_logged]


# --- leaderboard visibility ---------------------------------------------------
#
# Tested here rather than through the API because the board spans every account
# on the service: a page of the top N is not a deterministic place to look for
# one specific baker, but the rule itself is a pure function.


def _entry(user_id: uuid.UUID) -> LeaderboardEntry:
    return LeaderboardEntry(
        user_id=user_id,
        season_xp=100,
        lifetime_xp=100,
        bake_count=1,
        longest_streak=0,
        average_crumb=None,
        achievement_count=1,
        rank=1,
    )


def test_a_public_profile_is_named_on_the_board() -> None:
    viewer, subject = uuid.uuid4(), uuid.uuid4()
    row = _row(_entry(subject), "loafwright", "Loaf Wright", True, viewer, 1)
    assert row.handle == "loafwright"
    assert row.display_name == "Loaf Wright"
    assert row.is_you is False


def test_a_private_profile_is_anonymised_to_others() -> None:
    """Ranking is not opting in to being named."""
    viewer, subject = uuid.uuid4(), uuid.uuid4()
    row = _row(_entry(subject), "shybaker", "Shy Baker", False, viewer, 4)
    assert row.handle is None
    assert row.display_name == "Anonymous Baker"
    assert row.rank == 4, "they still hold a position"
    assert row.season_xp == 100, "and their score is still shown"


def test_you_always_see_your_own_name() -> None:
    me = uuid.uuid4()
    row = _row(_entry(me), "shybaker", "Shy Baker", False, me, 4)
    assert row.handle == "shybaker"
    assert row.is_you is True


def test_tier_is_derived_from_lifetime_not_season_xp() -> None:
    entry = _entry(uuid.uuid4())
    entry.lifetime_xp = 1200
    entry.season_xp = 5
    assert _row(entry, "h", "n", True, uuid.uuid4(), 1).tier == "Levain Keeper"
