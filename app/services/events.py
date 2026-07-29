"""Domain events and the XP they pay.

Routers publish what happened; this module decides what it is worth and hands
off to the achievement engine. Keeping the rates here rather than scattered
through the API means rebalancing is one file, and `sdt recompute-xp` replays
against the same table.
"""

import enum


class DomainEvent(enum.StrEnum):
    starter_created = "starter.created"
    feeding_logged = "feeding.logged"
    observation_logged = "observation.logged"
    proof_completed = "proof.completed"
    bake_completed = "bake.completed"
    bake_rated = "bake.rated"
    photo_added = "photo.added"
    recipe_created = "recipe.created"
    recipe_published = "recipe.published"
    recipe_forked = "recipe.forked"
    recipe_starred = "recipe.starred"
    inventory_purchased = "inventory.purchased"
    achievement_earned = "achievement.earned"


# XP paid for each event, before achievements.
BASE_XP: dict[DomainEvent, int] = {
    DomainEvent.starter_created: 15,
    DomainEvent.feeding_logged: 4,
    DomainEvent.observation_logged: 3,
    DomainEvent.proof_completed: 8,
    DomainEvent.bake_completed: 25,
    DomainEvent.bake_rated: 5,
    DomainEvent.photo_added: 2,
    DomainEvent.recipe_created: 10,
    DomainEvent.recipe_published: 15,
    # Paid to the recipe's owner, not the person forking or starring.
    DomainEvent.recipe_forked: 12,
    DomainEvent.recipe_starred: 5,
    DomainEvent.inventory_purchased: 2,
    DomainEvent.achievement_earned: 0,  # the achievement carries its own award
}

# How many times a day an event can pay out.
#
# The unique key already stops the *same* bake paying twice; these caps stop a
# different kind of grinding, where genuinely distinct rows are created purely
# to farm. They are set well above what a real baking day looks like, so an
# honest user never notices — the action still succeeds, it just stops paying.
DAILY_CAPS: dict[DomainEvent, int] = {
    DomainEvent.starter_created: 3,
    DomainEvent.feeding_logged: 12,
    DomainEvent.observation_logged: 12,
    DomainEvent.proof_completed: 12,
    DomainEvent.bake_completed: 6,
    DomainEvent.bake_rated: 6,
    DomainEvent.photo_added: 20,
    DomainEvent.recipe_created: 5,
    DomainEvent.recipe_published: 5,
    DomainEvent.recipe_forked: 50,
    DomainEvent.recipe_starred: 50,
    DomainEvent.inventory_purchased: 10,
}
