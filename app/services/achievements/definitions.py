"""The achievement catalogue.

Code is authoritative; the `achievement` table is a projection refreshed by
`sdt seed-achievements`. Keeping the definitions here means rebalancing a target
is a code review, and `sdt recompute-xp` can rebuild every award from scratch.

Each definition is declarative: a metric, a target, and the events that could
plausibly move it. Listing the events keeps the engine cheap — logging a feeding
does not re-evaluate forty badges about recipes.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.models.gamification import AchievementCategory as Cat
from app.models.gamification import Rarity
from app.services.achievements.metrics import Metric
from app.services.events import DomainEvent as E

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class AchievementDef:
    code: str
    name: str
    description: str
    category: Cat
    rarity: Rarity
    xp_award: int
    icon: str
    metric: Metric
    target: float
    events: tuple[E, ...]
    # Anti-cheat: the flagship badges cannot be claimed on typed numbers alone.
    requires_photo: bool = False
    criteria: dict[str, object] = field(default_factory=dict)


BAKE_EVENTS = (E.bake_completed,)
FEED_EVENTS = (E.feeding_logged,)
PROOF_EVENTS = (E.proof_completed,)
RECIPE_EVENTS = (E.recipe_created, E.recipe_published)
SOCIAL_EVENTS = (E.recipe_forked, E.recipe_starred)

ACHIEVEMENTS: tuple[AchievementDef, ...] = (
    # --- baking -------------------------------------------------------------
    AchievementDef(
        "first_loaf",
        "First Loaf",
        "Complete your first bake.",
        Cat.baking,
        Rarity.common,
        50,
        "🍞",
        Metric.bakes_completed,
        1,
        BAKE_EVENTS,
    ),
    AchievementDef(
        "ten_bakes",
        "Getting the Hang of It",
        "Complete 10 bakes.",
        Cat.baking,
        Rarity.common,
        75,
        "🥖",
        Metric.bakes_completed,
        10,
        BAKE_EVENTS,
    ),
    AchievementDef(
        "fifty_bakes",
        "Weekly Ritual",
        "Complete 50 bakes.",
        Cat.baking,
        Rarity.uncommon,
        150,
        "🗓️",
        Metric.bakes_completed,
        50,
        BAKE_EVENTS,
    ),
    AchievementDef(
        "century_club",
        "Century Club",
        "Complete 100 bakes.",
        Cat.baking,
        Rarity.rare,
        400,
        "💯",
        Metric.bakes_completed,
        100,
        BAKE_EVENTS,
    ),
    AchievementDef(
        "five_hundred_bakes",
        "Bread Machine",
        "Complete 500 bakes.",
        Cat.baking,
        Rarity.legendary,
        1500,
        "⚙️",
        Metric.bakes_completed,
        500,
        BAKE_EVENTS,
    ),
    AchievementDef(
        "hundred_loaves",
        "Feeding the Street",
        "Bake 100 loaves.",
        Cat.baking,
        Rarity.uncommon,
        150,
        "🧺",
        Metric.loaves_baked,
        100,
        BAKE_EVENTS,
    ),
    AchievementDef(
        "night_owl",
        "Night Owl",
        "Finish 5 bakes between midnight and 5am.",
        Cat.baking,
        Rarity.uncommon,
        100,
        "🦉",
        Metric.night_bakes,
        5,
        BAKE_EVENTS,
    ),
    AchievementDef(
        "perfect_ten",
        "Perfect Ten",
        "Rate 10 bakes a perfect 5.",
        Cat.baking,
        Rarity.rare,
        250,
        "⭐",
        Metric.perfect_bakes,
        10,
        (E.bake_rated,),
    ),
    AchievementDef(
        "first_perfect",
        "Nailed It",
        "Rate a bake a perfect 5.",
        Cat.baking,
        Rarity.common,
        50,
        "✨",
        Metric.perfect_bakes,
        1,
        (E.bake_rated,),
    ),
    # --- hydration and technique (photo-gated) ------------------------------
    AchievementDef(
        "hydration_75",
        "Slack Dough",
        "A bake at 75%+ hydration rated 4 or better.",
        Cat.baking,
        Rarity.uncommon,
        100,
        "💧",
        Metric.max_hydration_success,
        75,
        (*BAKE_EVENTS, E.bake_rated),
    ),
    AchievementDef(
        "hydration_85",
        "Hydration Hero",
        "A bake at 85%+ hydration rated 4 or better.",
        Cat.baking,
        Rarity.rare,
        300,
        "🌊",
        Metric.max_hydration_success,
        85,
        (*BAKE_EVENTS, E.bake_rated),
        requires_photo=True,
    ),
    AchievementDef(
        "hydration_95",
        "Soup to Loaf",
        "A bake at 95%+ hydration rated 4 or better.",
        Cat.baking,
        Rarity.legendary,
        800,
        "🏊",
        Metric.max_hydration_success,
        95,
        (*BAKE_EVENTS, E.bake_rated),
        requires_photo=True,
    ),
    # --- starters -----------------------------------------------------------
    AchievementDef(
        "first_starter",
        "It's Alive",
        "Create your first starter.",
        Cat.starter,
        Rarity.common,
        30,
        "🫙",
        Metric.starters_kept,
        1,
        (E.starter_created,),
    ),
    AchievementDef(
        "three_starters",
        "Menagerie",
        "Keep 3 starters at once.",
        Cat.starter,
        Rarity.uncommon,
        100,
        "🏺",
        Metric.starters_kept,
        3,
        (E.starter_created,),
    ),
    AchievementDef(
        "first_feed",
        "Dinner Time",
        "Log your first feeding.",
        Cat.starter,
        Rarity.common,
        20,
        "🥄",
        Metric.feedings_logged,
        1,
        FEED_EVENTS,
    ),
    AchievementDef(
        "hundred_feeds",
        "Devoted",
        "Log 100 feedings.",
        Cat.starter,
        Rarity.uncommon,
        150,
        "🍽️",
        Metric.feedings_logged,
        100,
        FEED_EVENTS,
    ),
    AchievementDef(
        "thousand_feeds",
        "Keeper of the Flame",
        "Log 1000 feedings.",
        Cat.starter,
        Rarity.epic,
        750,
        "🔥",
        Metric.feedings_logged,
        1000,
        FEED_EVENTS,
    ),
    AchievementDef(
        "streak_7",
        "Steady Hand",
        "A 7-feeding streak.",
        Cat.dedication,
        Rarity.common,
        60,
        "📈",
        Metric.longest_feed_streak,
        7,
        FEED_EVENTS,
    ),
    AchievementDef(
        "streak_30",
        "Unbroken",
        "A 30-feeding streak.",
        Cat.dedication,
        Rarity.rare,
        300,
        "⛓️",
        Metric.longest_feed_streak,
        30,
        FEED_EVENTS,
    ),
    AchievementDef(
        "streak_60",
        "Metronome",
        "A 60-feeding streak.",
        Cat.dedication,
        Rarity.epic,
        600,
        "🎯",
        Metric.longest_feed_streak,
        60,
        FEED_EVENTS,
    ),
    AchievementDef(
        "streak_365",
        "A Year of Bread",
        "A 365-feeding streak.",
        Cat.dedication,
        Rarity.legendary,
        2000,
        "🏆",
        Metric.longest_feed_streak,
        365,
        FEED_EVENTS,
    ),
    AchievementDef(
        "observer",
        "Close Observer",
        "Log 25 starter observations.",
        Cat.starter,
        Rarity.uncommon,
        100,
        "🔬",
        Metric.observations_logged,
        25,
        (E.observation_logged,),
    ),
    AchievementDef(
        "observer_pro",
        "Lab Notebook",
        "Log 200 starter observations.",
        Cat.starter,
        Rarity.rare,
        300,
        "📓",
        Metric.observations_logged,
        200,
        (E.observation_logged,),
    ),
    # --- proofing -----------------------------------------------------------
    AchievementDef(
        "first_proof",
        "Watching Dough Rise",
        "Complete a proof session.",
        Cat.proofing,
        Rarity.common,
        30,
        "⏳",
        Metric.proofs_completed,
        1,
        PROOF_EVENTS,
    ),
    AchievementDef(
        "fifty_proofs",
        "Patience Practised",
        "Complete 50 proof sessions.",
        Cat.proofing,
        Rarity.uncommon,
        150,
        "🧘",
        Metric.proofs_completed,
        50,
        PROOF_EVENTS,
    ),
    AchievementDef(
        "three_hundred_proofs",
        "Time Lord",
        "Complete 300 proof sessions.",
        Cat.proofing,
        Rarity.epic,
        600,
        "🕰️",
        Metric.proofs_completed,
        300,
        PROOF_EVENTS,
    ),
    AchievementDef(
        "sub_zero",
        "Sub-Zero",
        "Retard a dough for 24 hours or more.",
        Cat.proofing,
        Rarity.uncommon,
        120,
        "❄️",
        Metric.longest_retard_hours,
        24,
        PROOF_EVENTS,
    ),
    AchievementDef(
        "deep_freeze",
        "The Long Cold",
        "Retard a dough for 48 hours or more.",
        Cat.proofing,
        Rarity.rare,
        300,
        "🧊",
        Metric.longest_retard_hours,
        48,
        PROOF_EVENTS,
    ),
    # --- recipes ------------------------------------------------------------
    AchievementDef(
        "first_recipe",
        "Written Down",
        "Create your first recipe.",
        Cat.recipes,
        Rarity.common,
        40,
        "📝",
        Metric.recipes_created,
        1,
        RECIPE_EVENTS,
    ),
    AchievementDef(
        "ten_recipes",
        "Collector",
        "Create 10 recipes.",
        Cat.recipes,
        Rarity.uncommon,
        120,
        "📚",
        Metric.recipes_created,
        10,
        RECIPE_EVENTS,
    ),
    AchievementDef(
        "first_publish",
        "Going Public",
        "Publish a recipe.",
        Cat.recipes,
        Rarity.common,
        60,
        "📢",
        Metric.recipes_published,
        1,
        RECIPE_EVENTS,
    ),
    AchievementDef(
        "five_published",
        "Open Book",
        "Publish 5 recipes.",
        Cat.recipes,
        Rarity.uncommon,
        150,
        "📖",
        Metric.recipes_published,
        5,
        RECIPE_EVENTS,
    ),
    AchievementDef(
        "golden_ratio",
        "Golden Ratio",
        "Log a bake at 20 distinct flours.",
        Cat.recipes,
        Rarity.rare,
        250,
        "🌾",
        Metric.distinct_flours,
        20,
        BAKE_EVENTS,
    ),
    AchievementDef(
        "rye_devotee",
        "Rye Devotee",
        "Bake with 5 distinct flours.",
        Cat.recipes,
        Rarity.common,
        60,
        "🌿",
        Metric.distinct_flours,
        5,
        BAKE_EVENTS,
    ),
    # --- community ----------------------------------------------------------
    AchievementDef(
        "first_fork",
        "Someone Baked Yours",
        "Have a recipe forked once.",
        Cat.community,
        Rarity.uncommon,
        100,
        "🍴",
        Metric.forks_received,
        1,
        SOCIAL_EVENTS,
    ),
    AchievementDef(
        "fork_lift",
        "Fork Lift",
        "Have your recipes forked 10 times.",
        Cat.community,
        Rarity.rare,
        300,
        "🔱",
        Metric.forks_received,
        10,
        SOCIAL_EVENTS,
    ),
    AchievementDef(
        "fork_legend",
        "Community Staple",
        "Have your recipes forked 100 times.",
        Cat.community,
        Rarity.legendary,
        1200,
        "🏛️",
        Metric.forks_received,
        100,
        SOCIAL_EVENTS,
    ),
    AchievementDef(
        "first_star",
        "Appreciated",
        "Receive a star on a recipe.",
        Cat.community,
        Rarity.common,
        50,
        "🌟",
        Metric.stars_received,
        1,
        SOCIAL_EVENTS,
    ),
    AchievementDef(
        "well_starred",
        "Crowd Favourite",
        "Receive 50 stars.",
        Cat.community,
        Rarity.epic,
        500,
        "💫",
        Metric.stars_received,
        50,
        SOCIAL_EVENTS,
    ),
    AchievementDef(
        "photographer",
        "Documented",
        "Upload 25 bake photos.",
        Cat.community,
        Rarity.uncommon,
        100,
        "📷",
        Metric.photos_uploaded,
        25,
        (E.photo_added,),
    ),
    # --- inventory ----------------------------------------------------------
    AchievementDef(
        "stocked_up",
        "Stocked Up",
        "Purchase 25 kg of flour.",
        Cat.inventory,
        Rarity.common,
        50,
        "📦",
        Metric.flour_purchased_kg,
        25,
        (E.inventory_purchased,),
    ),
    AchievementDef(
        "bulk_buyer",
        "Bulk Buyer",
        "Purchase 250 kg of flour.",
        Cat.inventory,
        Rarity.rare,
        250,
        "🚚",
        Metric.flour_purchased_kg,
        250,
        (E.inventory_purchased,),
    ),
    # --- meta ---------------------------------------------------------------
    AchievementDef(
        "collector_10",
        "Badge Collector",
        "Earn 10 achievements.",
        Cat.dedication,
        Rarity.uncommon,
        150,
        "🎖️",
        Metric.achievements_earned,
        10,
        (E.achievement_earned,),
    ),
    AchievementDef(
        "collector_25",
        "Trophy Shelf",
        "Earn 25 achievements.",
        Cat.dedication,
        Rarity.epic,
        500,
        "🏅",
        Metric.achievements_earned,
        25,
        (E.achievement_earned,),
    ),
)

BY_CODE: dict[str, AchievementDef] = {a.code: a for a in ACHIEVEMENTS}

BY_EVENT: dict[E, tuple[AchievementDef, ...]] = {
    event: tuple(a for a in ACHIEVEMENTS if event in a.events) for event in E
}


async def seed_catalogue(session: "AsyncSession") -> int:
    """Upsert the code catalogue into the `achievement` table.

    The table is a projection of ACHIEVEMENTS, not a second source of truth: it
    exists so `user_achievement` has something to point a foreign key at, and so
    the UI can list badges without importing Python. Shared by
    `sdt seed-achievements` and by the test-database setup, because a catalogue
    seeded two slightly different ways is a bug waiting to happen.

    Returns the number of definitions written.
    """
    from sqlalchemy.dialects.postgresql import insert

    from app.models.gamification import Achievement

    for definition in ACHIEVEMENTS:
        values = {
            "code": definition.code,
            "name": definition.name,
            "description": definition.description,
            "category": definition.category,
            "rarity": definition.rarity,
            "xp_award": definition.xp_award,
            "icon": definition.icon,
            "target": definition.target,
            "criteria": {"metric": definition.metric.value, **definition.criteria},
            "requires_photo": definition.requires_photo,
        }
        await session.execute(
            insert(Achievement)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["code"],
                set_={k: v for k, v in values.items() if k != "code"},
            )
        )
    await session.commit()
    return len(ACHIEVEMENTS)
