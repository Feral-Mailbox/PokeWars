"""Gen 3/4/5/6/7/8/9 ability combat helpers for PokéTactics.

Reads ability effects from ``Ability.effect`` string token lists (with slug
fallbacks). Designed for import from ``games.py`` without circular imports —
pass callables via a ``helpers`` dict where game-layer side effects are needed.

Caching is light and per-call only (via optional ``_cache`` dicts), never global
across requests.

Gen 5 notes (tactics approximations):
- Analytic uses ``is_last_move`` from the caller (no remaining allies with can_move).
- Regenerator heals on switch-out via ``process_switch_out_or_faint`` (not on faint);
  wire a withdraw path when the game adds recall.
- Zen Mode / Illusion / Imposter are best-effort stubs (flags + partial transform).
- Prankster exposes ``status_move_priority_bonus``; games has no priority sort yet.

Gen 6 notes (tactics approximations):
- Gale Wings exposes ``flying_move_priority_bonus``; games has no priority sort yet.
- Primal weathers use IDs 5/6/7 (harsh_sun / heavy_rain / strong_winds).
- Parental Bond second hit is 0.25 power (Gen 7+ value; Gen 6 was 0.5).

Gen 7 notes (tactics approximations):
- Queenly Majesty / Dazzling / Triage / Gale Wings expose priority helpers; games
  has no priority sort yet — document-only wire for priority blocking.
- Emergency Exit / Wimp Out set ``wants_switch_out`` (no withdraw system).
- Dancer copies raise_stat effects from dance moves onto living Dancer units.
- Schooling / Shields Down / Power Construct update forme flags from HP thresholds.

Gen 8 notes (tactics approximations):
- Quick Draw exposes a same-priority helper; games has no priority sort yet.
- Unseen Fist needs Protect enforcement (stub helper only until Protect exists).
- Ball Fetch / Gulp Missile / Ripen berry auto-eat are partial stubs.
- Neutralizing Gas suppresses other units' abilities while a holder is alive.
- Ice Face / Hunger Switch use forme flags (no full sprite/stat swaps).

Gen 9 notes (tactics approximations):
- Armor Tail / Piercing Drill need priority + Protect systems (helpers only).
- Move traits (sound/wind/slicing/biting/punching/pulse/powder/ball_bomb) use
  ``Move.move_trait`` with slug-set fallbacks.
- Protosynthesis / Quark Drive boost highest stat; Booster Energy sets a flag.
- Tera Shift / Zero to Hero / Commander are forme/adjacency stubs.
- Charge state doubles next Electric move when wired in games.
"""

from __future__ import annotations

import random
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.models import Ability, GameUnit
from app.move_traits import (
    MOVE_TRAIT_BALL_BOMB,
    MOVE_TRAIT_BITING,
    MOVE_TRAIT_POWDER,
    MOVE_TRAIT_PULSE,
    MOVE_TRAIT_PUNCHING,
    MOVE_TRAIT_SLICING,
    MOVE_TRAIT_SOUND,
    MOVE_TRAIT_WIND,
    move_has_trait,
)

# ---------------------------------------------------------------------------
# Constants (duplicated lightly so this module never imports games.py)
# ---------------------------------------------------------------------------

WEATHER_TO_ID: dict[str, int] = {
    "sun": 1,
    "rain": 2,
    "sandstorm": 3,
    "hail": 4,
    "harsh_sun": 5,
    "heavy_rain": 6,
    "strong_winds": 7,
}
ID_TO_WEATHER: dict[int, str] = {v: k for k, v in WEATHER_TO_ID.items()}

TERRAIN_TO_ID: dict[str, int] = {
    "electric": 1,
    "psychic": 2,
    "grassy": 3,
    "misty": 4,
}

STATUS_ALIASES: dict[str, str] = {
    "badly_poison": "badly_poisoned",
    "badly_poisoned": "badly_poisoned",
    "freeze": "frozen",
    "frozen": "frozen",
    "para": "paralysis",
    "paralysis": "paralysis",
    "burn": "burn",
    "sleep": "sleep",
    "poison": "poison",
}

STAT_ALIASES: dict[str, str] = {
    "atk": "attack",
    "attack": "attack",
    "def": "defense",
    "defense": "defense",
    "spa": "sp_attack",
    "spatk": "sp_attack",
    "special_attack": "sp_attack",
    "sp_attack": "sp_attack",
    "spd": "sp_defense",
    "spdef": "sp_defense",
    "special_defense": "sp_defense",
    "sp_defense": "sp_defense",
    "spe": "speed",
    "speed": "speed",
    "accuracy": "accuracy",
    "evasion": "evasion",
    "crit": "crit",
}

EXPLOSION_MOVE_SLUGS: frozenset[str] = frozenset(
    {
        "explosion",
        "self-destruct",
        "self_destruct",
        "selfdestruct",
        "mind-blown",
        "mind_blown",
        "misty-explosion",
        "misty_explosion",
    }
)

PUNCH_MOVE_SLUGS: frozenset[str] = frozenset(
    {
        "comet_punch",
        "mega_punch",
        "fire_punch",
        "ice_punch",
        "thunder_punch",
        "dizzy_punch",
        "mach_punch",
        "dynamic_punch",
        "focus_punch",
        "meteor_mash",
        "shadow_punch",
        "sky_uppercut",
        "hammer_arm",
        "drain_punch",
        "bullet_punch",
        "power_up_punch",
        "poweruppunch",
        "ice_hammer",
        "plasma_fists",
        "double_iron_bash",
        "wicked_blow",
        "surging_strikes",
        "surge_strikes",
        "headlong_rush",
        "jet_punch",
        "rage_fist",
    }
)

BITE_MOVE_SLUGS: frozenset[str] = frozenset(
    {
        "bite",
        "crunch",
        "thunder_fang",
        "thunderfang",
        "ice_fang",
        "icefang",
        "fire_fang",
        "firefang",
        "hyper_fang",
        "hyperfang",
        "poison_fang",
        "poisonfang",
        "psychic_fangs",
        "psychicfangs",
        "fishious_rend",
        "fishiousrend",
        "jaw_lock",
        "jawlock",
    }
)

PULSE_MOVE_SLUGS: frozenset[str] = frozenset(
    {
        "water_pulse",
        "waterpulse",
        "dark_pulse",
        "darkpulse",
        "dragon_pulse",
        "dragonpulse",
        "aura_sphere",
        "aurasphere",
        "origin_pulse",
        "originpulse",
        "terrain_pulse",
        "terrainpulse",
        "heal_pulse",
        "healpulse",
    }
)

BALL_BOMB_MOVE_SLUGS: frozenset[str] = frozenset(
    {
        "egg_bomb",
        "eggbomb",
        "barrage",
        "sludge_bomb",
        "sludgebomb",
        "octazooka",
        "zap_cannon",
        "zapcannon",
        "shadow_ball",
        "shadowball",
        "mist_ball",
        "mistball",
        "ice_ball",
        "iceball",
        "weather_ball",
        "weatherball",
        "bullet_seed",
        "bulletseed",
        "rock_blast",
        "rockblast",
        "gyro_ball",
        "gyroball",
        "aura_sphere",
        "aurasphere",
        "seed_bomb",
        "seedbomb",
        "focus_blast",
        "focusblast",
        "energy_ball",
        "energyball",
        "mud_bomb",
        "mudbomb",
        "rock_wrecker",
        "rockwrecker",
        "magnet_bomb",
        "magnetbomb",
        "electro_ball",
        "electroball",
        "acid_spray",
        "acidspray",
        "searing_shot",
        "searingshot",
        "pollen_puff",
        "pollenpuff",
        "beak_blast",
        "beakblast",
        "pyro_ball",
        "pyroball",
        "syrup_bomb",
        "syrupbomb",
    }
)

# Slug tokens used when Ability.effect is missing/empty.
_SLUG_EFFECT_FALLBACKS: dict[str, list[str]] = {
    "air_lock": ["suppress_weather"],
    "cloud_nine": ["suppress_weather"],
    "drizzle": ["on_switch_in:weather:rain"],
    "drought": ["on_switch_in:weather:sun"],
    "sand_stream": ["on_switch_in:weather:sandstorm"],
    "intimidate": ["on_switch_in:opponents:lower_stat:attack:1"],
    "trace": ["on_switch_in:self:copy_ability:opponent"],
    "levitate": ["immune:ground"],
    "volt_absorb": ["immune:electric", "on_hit:electric:self:heal_fraction:4"],
    "water_absorb": ["immune:water", "on_hit:water:self:heal_fraction:4"],
    "flash_fire": ["immune:fire", "on_hit:fire:self:apply_state:flash_fire"],
    "lightning_rod": [
        "redirect:electric",
        "immune:electric",
        "on_hit:electric:self:raise_stat:special_attack:1",
    ],
    "wonder_guard": ["only_super_effective_hits"],
    "sturdy": ["endure_ohko_at_full_hp", "immune_category:ohko"],
    "soundproof": ["immune_category:sound"],
    "damp": ["suppress_field:explosion"],
    "rock_head": ["immune_recoil"],
    "liquid_ooze": ["on_drained:attacker:damage_instead_of_heal"],
    "sticky_hold": ["immune_item_removal"],
    "pressure": ["on_targeted:attacker:extra_pp_cost:1"],
    "natural_cure": ["on_switch_out:self:cure_status"],
    "truant": ["alternate_turn:loaf"],
    "forecast": ["on_weather:change_type:water_fire_ice"],
    "serene_grace": ["self:boost_secondary_effect_chance:2"],
    "shield_dust": ["immune_additional_effects"],
    "early_bird": ["self:halve_sleep_duration"],
    "compound_eyes": ["self:boost_accuracy:1.3"],
    "battle_armor": ["immune_crit"],
    "shell_armor": ["immune_crit"],
    "inner_focus": ["immune_flinch", "immune_intimidate"],
    "own_tempo": ["immune_status:confusion", "immune_intimidate"],
    "oblivious": ["immune_status:infatuation", "immune_status:taunt", "immune_intimidate"],
    "clear_body": ["immune_stat_drop"],
    "white_smoke": ["immune_stat_drop"],
    "hyper_cutter": ["immune_stat_drop:attack"],
    "keen_eye": ["ignore_target_evasion", "immune_stat_drop:accuracy"],
    "illuminate": ["ignore_target_evasion", "immune_stat_drop:accuracy"],
    # Gen 4
    "technician": ["on_move_power_at_most:60:self:boost_power:1.5"],
    "iron_fist": ["on_move_flag:punch:self:boost_power:1.2"],
    "reckless": ["on_move_flag:recoil:self:boost_power:1.2", "on_move_flag:crash:self:boost_power:1.2"],
    "rivalry": ["on_same_gender:self:boost_power:1.25", "on_opposite_gender:self:boost_power:0.75"],
    "normalize": ["convert_move_type:normal", "on_converted_type:self:boost_power:1.2"],
    "adaptability": ["boost_stab:2"],
    "filter": ["on_super_effective:self:resist:0.75"],
    "solid_rock": ["on_super_effective:self:resist:0.75"],
    "heatproof": ["on_hit_type:fire:self:resist:0.5", "halve_burn_damage"],
    "sniper": ["boost_crit_damage:2.25"],
    "super_luck": ["self:raise_stat:crit:1"],
    "tinted_lens": ["boost_not_very_effective_to_neutral"],
    "scrappy": ["hit_ghost_with:normal", "hit_ghost_with:fighting", "immune_intimidate"],
    "mold_breaker": ["ignore_target_ability"],
    "magic_guard": ["immune_indirect_damage"],
    "poison_heal": [
        "on_status:poison:on_turn_end:self:heal_fraction:8",
        "on_status:badly_poison:on_turn_end:self:heal_fraction:8",
        "ignore_poison_damage",
    ],
    "quick_feet": ["on_status:any:self:boost_stat_mult:speed:1.5", "ignore_paralysis_speed_halve"],
    "no_guard": ["moves_never_miss", "opponent_moves_never_miss"],
    "skill_link": ["multi_hit:always_max"],
    "simple": ["double_stat_changes"],
    "unaware": [
        "ignore_target_stat_changes_when_attacking",
        "ignore_attacker_stat_changes_when_defending",
    ],
    "klutz": ["suppress_held_item"],
    "gluttony": ["berry_threshold:50"],
    "unburden": ["on_item_lost:self:boost_stat_mult:speed:2"],
    "leaf_guard": ["on_weather:sun:immune_status:all"],
    "tangled_feet": ["on_status:confusion:self:boost_stat_mult:evasion:2"],
    "storm_drain": [
        "redirect:water",
        "immune:water",
        "on_hit:water:self:raise_stat:special_attack:1",
    ],
    "motor_drive": ["immune:electric", "on_hit:electric:self:raise_stat:speed:1"],
    "download": ["on_switch_in:self:raise_stat:attack_or_special_attack:better_vs_opponent"],
    "anticipation": ["on_switch_in:sense:super_effective_or_ohko"],
    "forewarn": ["on_switch_in:reveal:strongest_opponent_move"],
    "frisk": ["on_switch_in:reveal:opponent_held_items"],
    "slow_start": ["on_switch_in:self:apply_state:slow_start:5"],
    "hydration": ["on_weather:rain:on_turn_end:self:cure_status"],
    "bad_dreams": ["on_turn_end:opponents:if_asleep:damage_fraction:8"],
    "aftermath": ["on_faint_from_contact:attacker:damage_fraction:4"],
    "anger_point": ["on_crit_received:self:raise_stat:attack:6"],
    "steadfast": ["on_flinch:self:raise_stat:speed:1"],
    "flower_gift": [
        "on_weather:sun:self:boost_stat_mult:attack:1.5",
        "on_weather:sun:self:boost_stat_mult:special_defense:1.5",
        "on_weather:sun:allies:boost_stat_mult:attack:1.5",
        "on_weather:sun:allies:boost_stat_mult:special_defense:1.5",
    ],
    "solar_power": [
        "on_weather:sun:self:boost_stat_mult:special_attack:1.5",
        "on_weather:sun:on_turn_end:self:damage_fraction:8",
    ],
    "dry_skin": [
        "immune:water",
        "on_hit:water:self:heal_fraction:4",
        "on_hit_type:fire:self:resist:1.25",
        "on_weather:rain:on_turn_end:self:heal_fraction:8",
        "on_weather:sun:on_turn_end:self:damage_fraction:8",
    ],
    "multitype": ["change_type:held_plate"],
    "stall": ["force_last_among_priority"],
    "honey_gather": ["after_battle:gather_honey"],
    # Gen 5
    "sand_force": [
        "on_weather:sandstorm:on_move_type:rock:self:boost_power:1.3",
        "on_weather:sandstorm:on_move_type:ground:self:boost_power:1.3",
        "on_weather:sandstorm:on_move_type:steel:self:boost_power:1.3",
    ],
    "flare_boost": ["on_status:burn:on_move_category:special:self:boost_power:1.5"],
    "toxic_boost": [
        "on_status:poison:on_move_category:physical:self:boost_power:1.5",
        "on_status:badly_poison:on_move_category:physical:self:boost_power:1.5",
    ],
    "sheer_force": ["remove_secondary_effects", "on_moves_with_secondary:self:boost_power:1.3"],
    "analytic": ["on_move_last:self:boost_power:1.3"],
    "multiscale": ["on_hp_full:self:resist:0.5"],
    "friend_guard": ["allies:resist_damage:0.75"],
    "defeatist": [
        "on_hp_below:50:self:boost_stat_mult:attack:0.5",
        "on_hp_below:50:self:boost_stat_mult:special_attack:0.5",
    ],
    "victory_star": ["self:boost_accuracy:1.1", "allies:boost_accuracy:1.1"],
    "wonder_skin": ["self:boost_status_move_evasion"],
    "overcoat": ["immune_weather_damage", "immune_category:powder"],
    "regenerator": ["on_switch_out:self:heal_fraction:3"],
    "mummy": ["on_contact:attacker:set_ability:mummy"],
    "pickpocket": ["on_contact:self:steal_item"],
    "poison_touch": ["on_contact_deal:target:status:poison:30"],
    "justified": ["on_hit_type:dark:self:raise_stat:attack:1"],
    "rattled": [
        "on_hit_type:dark:self:raise_stat:speed:1",
        "on_hit_type:ghost:self:raise_stat:speed:1",
        "on_hit_type:bug:self:raise_stat:speed:1",
        "on_intimidate:self:raise_stat:speed:1",
    ],
    "weak_armor": [
        "on_hit_category:physical:self:lower_stat:defense:1",
        "on_hit_category:physical:self:raise_stat:speed:2",
    ],
    "cursed_body": ["on_damage_taken:attacker:apply_state:disable:30"],
    "moxie": ["on_ko:self:raise_stat:attack:1"],
    "contrary": ["reverse_stat_changes"],
    "defiant": ["on_stat_lowered_by_opponent:self:raise_stat:attack:2"],
    "infiltrator": ["ignore_screens", "ignore_safeguard", "ignore_substitute"],
    "magic_bounce": ["reflect_status_moves"],
    "telepathy": ["immune_ally_attacks"],
    "unnerve": ["prevent_opponent_berry_eat"],
    "harvest": [
        "on_turn_end:self:recycle_berry:50",
        "on_weather:sun:on_turn_end:self:recycle_berry:100",
    ],
    "healer": ["on_turn_end:allies:cure_status:50"],
    "moody": [
        "on_turn_end:self:raise_random_stat:2",
        "on_turn_end:self:lower_other_random_stat:1",
    ],
    "zen_mode": ["on_hp_below:50:change_forme:zen"],
    "illusion": ["on_switch_in:disguise_as:last_party_member"],
    "imposter": ["on_switch_in:transform:opponent"],
    "prankster": ["priority_status:1"],
    "heavy_metal": ["self:boost_weight:2"],
    "light_metal": ["self:boost_weight:0.5"],
    "sand_rush": ["on_weather:sandstorm:self:boost_stat_mult:speed:2"],
    "big_pecks": ["immune_stat_drop:defense"],
    "iron_barbs": ["on_contact:attacker:damage_fraction:8"],
    "sap_sipper": ["immune:grass", "on_hit:grass:self:raise_stat:attack:1"],
    "teravolt": ["ignore_target_ability"],
    "turboblaze": ["ignore_target_ability"],
    # Gen 6
    "aerilate": ["convert_move_type:normal:to:flying", "on_converted_type:self:boost_power:1.2"],
    "refrigerate": ["convert_move_type:normal:to:ice", "on_converted_type:self:boost_power:1.2"],
    "pixilate": ["convert_move_type:normal:to:fairy", "on_converted_type:self:boost_power:1.2"],
    "tough_claws": ["on_move_flag:contact:self:boost_power:1.3"],
    "strong_jaw": ["on_move_flag:bite:self:boost_power:1.5"],
    "mega_launcher": ["on_move_flag:pulse:self:boost_power:1.5"],
    "fur_coat": ["on_move_category:physical:self:resist:0.5"],
    "gooey": ["on_contact:attacker:lower_stat:speed:1"],
    "competitive": ["on_stat_lowered_by_opponent:self:raise_stat:special_attack:2"],
    "dark_aura": ["field:on_move_type:dark:boost_power:1.33"],
    "fairy_aura": ["field:on_move_type:fairy:boost_power:1.33"],
    "aura_break": ["reverse_aura_abilities"],
    "sweet_veil": ["self_and_allies:immune_status:sleep"],
    "aroma_veil": [
        "self_and_allies:immune_status:infatuation,taunt,encore,disable,torment,heal_block"
    ],
    "flower_veil": ["grass_allies:immune_status:all", "grass_allies:immune_stat_drop"],
    "grass_pelt": ["on_terrain:grassy:self:boost_stat_mult:defense:1.5"],
    "bulletproof": ["immune_category:ball_bomb"],
    "parental_bond": ["multi_hit:2", "second_hit_power:0.25"],
    "cheek_pouch": ["on_berry_eat:self:heal_fraction:3"],
    "magician": ["on_damage_dealt:self:steal_item"],
    "symbiosis": ["on_ally_item_consumed:self:give_held_item"],
    "protean": ["on_move_use:self:change_type:move_type:once_per_switch_in"],
    "primordial_sea": ["on_switch_in:weather:heavy_rain", "nullify_move_type:fire"],
    "desolate_land": ["on_switch_in:weather:harsh_sun", "nullify_move_type:water"],
    "delta_stream": ["on_switch_in:weather:strong_winds", "negate_flying_weaknesses"],
    "gale_wings": ["on_hp_full:on_move_type:flying:priority:1"],
    "stance_change": ["on_attack:change_forme:blade", "on_kings_shield:change_forme:shield"],
    # Gen 7
    "steelworker": ["on_move_type:steel:self:boost_power:1.5"],
    "water_bubble": [
        "on_hit_type:fire:self:resist:0.5",
        "on_move_type:water:self:boost_power:2",
        "immune_status:burn",
    ],
    "fluffy": ["on_move_flag:contact:self:resist:0.5", "on_hit_type:fire:self:resist:2"],
    "neuroforce": ["on_super_effective_deal:self:boost_power:1.25"],
    "battery": ["allies:on_move_category:special:boost_power:1.3"],
    "stamina": ["on_damage_taken:self:raise_stat:defense:1"],
    "beast_boost": ["on_ko:self:raise_stat:highest:1"],
    "liquid_voice": ["convert_move_category:sound:to_type:water"],
    "electric_surge": ["on_switch_in:terrain:electric"],
    "psychic_surge": ["on_switch_in:terrain:psychic"],
    "grassy_surge": ["on_switch_in:terrain:grassy"],
    "misty_surge": ["on_switch_in:terrain:misty"],
    "long_reach": ["remove_contact_flag"],
    "merciless": [
        "on_target_status:poison:guaranteed_crit",
        "on_target_status:badly_poison:guaranteed_crit",
    ],
    "corrosion": ["can_poison:steel", "can_poison:poison"],
    "innards_out": ["on_faint_from_move:attacker:damage_equal_to_hp_lost"],
    "soul_heart": ["on_any_faint:self:raise_stat:special_attack:1"],
    "stakeout": ["on_target_switched_in:self:boost_power:2"],
    "berserk": ["on_hp_cross_below:50:self:raise_stat:special_attack:1"],
    "disguise": [
        "on_first_hit:block_damage",
        "on_disguise_break:self:damage_fraction:8",
        "change_forme:busted",
    ],
    "comatose": ["permanent_status:sleep", "can_act_while_asleep", "immune_status:all_other"],
    "queenly_majesty": ["self_and_allies:immune_category:priority"],
    "dazzling": ["self_and_allies:immune_category:priority"],
    "triage": ["priority_healing:3"],
    "galvanize": ["convert_move_type:normal:to:electric", "on_converted_type:self:boost_power:1.2"],
    "shadow_shield": ["on_hp_full:self:resist:0.5"],
    "prism_armor": ["on_super_effective:self:resist:0.75"],
    "full_metal_body": ["immune_stat_drop"],
    "rks_system": ["change_type:held_memory"],
    "battle_bond": [
        "on_ko:self:raise_stat:attack:1",
        "on_ko:self:raise_stat:special_attack:1",
        "on_ko:self:raise_stat:speed:1",
        "on_ko:change_forme:ash",
    ],
    "schooling": ["on_hp_above:25:change_forme:school", "on_hp_below:25:change_forme:solo"],
    "shields_down": ["on_hp_below:50:change_forme:core", "on_hp_above:50:change_forme:meteor"],
    "power_construct": ["on_hp_below:50:change_forme:complete"],
    "receiver": ["on_ally_faint:self:copy_ability:fainted_ally"],
    "power_of_alchemy": ["on_ally_faint:self:copy_ability:fainted_ally"],
    "emergency_exit": ["on_hp_below:50:force_switch_out"],
    "wimp_out": ["on_hp_below:50:force_switch_out"],
    "dancer": ["on_dance_move_used:copy_immediately"],
    "surge_surfer": ["on_terrain:electric:self:boost_stat_mult:speed:2"],
    "slush_rush": ["on_weather:hail:self:boost_stat_mult:speed:2"],
    "tangling_hair": ["on_contact:attacker:lower_stat:speed:1"],
    "water_compaction": ["on_hit_type:water:self:raise_stat:defense:2"],
    # Gen 8
    "intrepid_sword": ["on_switch_in:self:raise_stat:attack:1:once_per_battle"],
    "dauntless_shield": ["on_switch_in:self:raise_stat:defense:1:once_per_battle"],
    "libero": ["on_move_use:self:change_type:move_type:once_per_switch_in"],
    "transistor": ["on_move_type:electric:self:boost_power:1.5"],
    "dragons_maw": ["on_move_type:dragon:self:boost_power:1.5"],
    "ice_scales": ["on_move_category:special:self:resist:0.5"],
    "punk_rock": [
        "on_move_category:sound:self:boost_power:1.3",
        "on_hit_category:sound:self:resist:0.5",
    ],
    "gorilla_tactics": ["self:boost_stat_mult:attack:1.5", "lock_move:first_selected"],
    "chilling_neigh": ["on_ko:self:raise_stat:attack:1"],
    "grim_neigh": ["on_ko:self:raise_stat:special_attack:1"],
    "as_one_glastrier": [
        "prevent_opponent_berry_eat",
        "on_ko:self:raise_stat:attack:1",
    ],
    "as_one_spectrier": [
        "prevent_opponent_berry_eat",
        "on_ko:self:raise_stat:special_attack:1",
    ],
    "pastel_veil": [
        "self_and_allies:immune_status:poison",
        "self_and_allies:immune_status:badly_poison",
    ],
    "steam_engine": [
        "on_hit_type:fire:self:raise_stat:speed:6",
        "on_hit_type:water:self:raise_stat:speed:6",
    ],
    "propeller_tail": ["ignore_redirect"],
    "stalwart": ["ignore_redirect"],
    "power_spot": ["adjacent_allies:boost_power:1.3"],
    "steely_spirit": ["self_and_allies:on_move_type:steel:boost_power:1.5"],
    "cotton_down": ["on_damage_taken:others:lower_stat:speed:1"],
    "sand_spit": ["on_damage_taken:weather:sandstorm"],
    "screen_cleaner": ["on_switch_in:clear_screens"],
    "curious_medicine": ["on_switch_in:allies:clear_stat_changes"],
    "mirror_armor": ["reflect_stat_drops"],
    "neutralizing_gas": ["suppress_other_abilities"],
    "wandering_spirit": ["on_contact:swap_abilities"],
    "perish_body": ["on_contact:both:apply_state:perish:3"],
    "hunger_switch": ["on_turn_end:toggle_forme:full_belly_hangry"],
    "mimicry": ["on_terrain:change_type:terrain"],
    "ice_face": [
        "on_physical_hit:block_and_change_forme:noice",
        "on_weather:hail:restore_forme:ice",
    ],
    "unseen_fist": ["contact_bypass_protect:0.25"],
    "quick_draw": ["on_same_priority:go_first:30"],
    "ripen": ["double_berry_effects"],
    "ball_fetch": ["on_failed_pokeball:self:pickup_pokeball"],
    "gulp_missile": ["on_surf_or_dive:catch_prey", "on_damage_taken:spit_prey"],
    # Gen 9
    "anger_shell": [
        "on_hp_cross_below:50:self:lower_stat:defense:1",
        "on_hp_cross_below:50:self:lower_stat:special_defense:1",
        "on_hp_cross_below:50:self:raise_stat:attack:1",
        "on_hp_cross_below:50:self:raise_stat:special_attack:1",
        "on_hp_cross_below:50:self:raise_stat:speed:1",
    ],
    "armor_tail": ["self_and_allies:immune_category:priority"],
    "beads_of_ruin": ["field_others:boost_stat_mult:special_defense:0.75"],
    "commander": ["on_switch_in:enter_ally:dondozo"],
    "costar": ["on_switch_in:self:copy_stat_changes:ally"],
    "cud_chew": ["on_berry_eat:reuse_next_turn"],
    "dragonize": ["convert_move_type:normal:to:dragon", "on_converted_type:self:boost_power:1.2"],
    "earth_eater": ["immune:ground", "on_hit:ground:self:heal_fraction:4"],
    "eelevate": [
        "immune:ground",
        "immune_hazard:spikes",
        "immune_hazard:toxic_spikes",
        "immune_hazard:sticky_web",
        "on_ko:self:raise_stat:highest:1",
    ],
    "electromorphosis": ["on_damage_taken:self:apply_state:charge"],
    "embody_aspect_cornerstone_mask": ["on_switch_in:self:raise_stat:defense:1"],
    "embody_aspect_hearthflame_mask": ["on_switch_in:self:raise_stat:attack:1"],
    "embody_aspect_teal_mask": ["on_switch_in:self:raise_stat:speed:1"],
    "embody_aspect_wellspring_mask": ["on_switch_in:self:raise_stat:special_defense:1"],
    "fire_mane": ["on_move_type:fire:self:boost_power:1.5"],
    "good_as_gold": ["immune_category:status_moves"],
    "guard_dog": ["on_intimidate:self:raise_stat:attack:1", "immune_forced_switch"],
    "hadron_engine": [
        "on_switch_in:terrain:electric",
        "on_terrain:electric:self:boost_stat_mult:special_attack:1.333",
    ],
    "hospitality": ["on_switch_in:ally:heal_fraction:4"],
    "lingering_aroma": ["on_contact:attacker:set_ability:lingering_aroma"],
    "mega_sol": ["treat_weather_as:sun"],
    "minds_eye": [
        "ignore_target_evasion",
        "immune_stat_drop:accuracy",
        "hit_ghost_with:normal",
        "hit_ghost_with:fighting",
    ],
    "mycelium_might": ["status_moves:force_last", "status_moves:ignore_target_ability"],
    "opportunist": ["on_opponent_stat_boost:copy_stat_boosts"],
    "orichalcum_pulse": [
        "on_switch_in:weather:sun",
        "on_weather:sun:self:boost_stat_mult:attack:1.333",
    ],
    "piercing_drill": ["contact_bypass_protect:0.25"],
    "poison_puppeteer": ["on_poison_dealt:also:apply_state:confusion"],
    "protosynthesis": [
        "on_weather:sun:boost_highest_stat:1.3",
        "on_held_item:booster_energy:boost_highest_stat:1.3",
    ],
    "purifying_salt": ["on_hit_type:ghost:self:resist:0.5", "immune_status:all"],
    "quark_drive": [
        "on_terrain:electric:boost_highest_stat:1.3",
        "on_held_item:booster_energy:boost_highest_stat:1.3",
    ],
    "rocky_payload": ["on_move_type:rock:self:boost_power:1.5"],
    "seed_sower": ["on_damage_taken:terrain:grassy"],
    "sharpness": ["on_move_flag:slicing:self:boost_power:1.5"],
    "spicy_spray": ["on_damage_taken:attacker:status:burn"],
    "supersweet_syrup": ["on_switch_in:opponents:lower_stat:evasion:1:once_per_battle"],
    "supreme_overlord": ["on_switch_in:boost_power_per_fainted_ally:0.1:max:0.5"],
    "sword_of_ruin": ["field_others:boost_stat_mult:defense:0.75"],
    "tablets_of_ruin": ["field_others:boost_stat_mult:attack:0.75"],
    "tera_shell": ["on_hp_full:all_damaging_moves:not_very_effective"],
    "tera_shift": ["on_switch_in:change_forme:terastal"],
    "teraform_zero": ["on_stellar_forme:suppress_weather", "on_stellar_forme:suppress_terrain"],
    "thermal_exchange": ["on_hit_type:fire:self:raise_stat:attack:1", "immune_status:burn"],
    "toxic_chain": ["on_damage_dealt:target:status:badly_poison:30"],
    "toxic_debris": ["on_hit_category:physical:field_hazard:toxic_spikes:opponent_side"],
    "vessel_of_ruin": ["field_others:boost_stat_mult:special_attack:0.75"],
    "well_baked_body": ["immune:fire", "on_hit:fire:self:raise_stat:defense:2"],
    "wind_power": ["on_hit_category:wind:self:apply_state:charge"],
    "wind_rider": [
        "immune_category:wind",
        "on_tailwind:self:raise_stat:attack:1",
        "on_hit_category:wind:self:raise_stat:attack:1",
    ],
    "zero_to_hero": ["on_switch_out:change_forme:hero"],
}

TERRAIN_DEFAULT_DURATION = 5

BEAST_BOOST_STATS: tuple[str, ...] = (
    "attack",
    "defense",
    "sp_attack",
    "sp_defense",
    "speed",
)

DANCE_MOVE_SLUGS: frozenset[str] = frozenset(
    {
        "sword_dance",
        "swords_dance",
        "feather_dance",
        "featherdance",
        "quiver_dance",
        "petra_dance",
        "petaldance",
        "petal_dance",
        "dragon_dance",
        "teeter_dance",
        "fiery_dance",
        "revelation_dance",
        "lunar_dance",
        "victory_dance",
        "aqua_step",
    }
)

POWDER_MOVE_SLUGS: frozenset[str] = frozenset(
    {
        "spore",
        "sleep_powder",
        "stun_spore",
        "poison_powder",
        "poisonpowder",
        "powder",
        "rage_powder",
        "cotton_spore",
        "magic_powder",
        "magicpowder",
    }
)

SLICING_MOVE_SLUGS: frozenset[str] = frozenset(
    {
        "cut",
        "razor_leaf",
        "slash",
        "fury_cutter",
        "metal_claw",
        "crush_claw",
        "air_cutter",
        "aerial_ace",
        "dragon_claw",
        "leaf_blade",
        "night_slash",
        "air_slash",
        "x_scissor",
        "shadow_claw",
        "psycho_cut",
        "cross_poison",
        "sacred_sword",
        "razor_shell",
        "secret_sword",
        "solar_blade",
        "behemoth_blade",
        "dire_claw",
        "stone_axe",
        "ceaseless_edge",
        "population_bomb",
        "kowtow_cleave",
        "psyblade",
        "bitter_blade",
        "aqua_cutter",
        "mighty_cleave",
        "tachyon_cutter",
    }
)

WIND_MOVE_SLUGS: frozenset[str] = frozenset(
    {
        "gust",
        "whirlwind",
        "blizzard",
        "aeroblast",
        "icy_wind",
        "sandstorm",
        "twister",
        "heat_wave",
        "air_cutter",
        "tailwind",
        "hurricane",
        "petal_blizzard",
        "fairy_wind",
        "springtide_storm",
        "bleakwind_storm",
        "wildbolt_storm",
        "sandsear_storm",
    }
)


MOODY_STATS: tuple[str, ...] = (
    "attack",
    "defense",
    "sp_attack",
    "sp_defense",
    "speed",
)


# ---------------------------------------------------------------------------
# Internal flag / status helpers (no games.py dependency)
# ---------------------------------------------------------------------------


def _unit_flags(unit: GameUnit) -> dict:
    raw = getattr(unit, "flags", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _set_unit_flags(unit: GameUnit, flags: dict, db: Session) -> None:
    unit.flags = dict(flags)
    db.add(unit)


def _get_unit_ability_id(unit: GameUnit) -> int | None:
    ability_id = _unit_flags(unit).get("ability_id")
    if ability_id is not None:
        try:
            return int(ability_id)
        except (TypeError, ValueError):
            pass
    unit_info = getattr(unit, "unit", None)
    if unit_info and isinstance(getattr(unit_info, "ability_ids", None), list) and unit_info.ability_ids:
        try:
            return int(unit_info.ability_ids[0])
        except (TypeError, ValueError):
            return None
    return None


def _normalize_states(raw: Any) -> list:
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str) and raw:
        return [raw, 1]
    return []


def _raw_ability_effect_tokens(unit: GameUnit, db: Session, *, _cache: dict | None = None) -> list[str]:
    """Parse ability effects ignoring Gastro Acid / Neutralizing Gas suppression."""
    if unit is None or getattr(unit, "is_fainted", False):
        return []
    cache = _cache if _cache is not None else {}
    ability_id = _get_unit_ability_id(unit)
    cache_key = ("raw_effects", getattr(unit, "id", None), ability_id)
    if cache_key in cache:
        return list(cache[cache_key])
    if ability_id is None:
        cache[cache_key] = []
        return []
    ability = db.query(Ability).filter(Ability.id == ability_id).first()
    if ability is None:
        cache[cache_key] = []
        return []
    effects = parse_effects(getattr(ability, "effect", None))
    if not effects:
        slug = str(getattr(ability, "slug", "") or "").lower().strip()
        effects = list(_SLUG_EFFECT_FALLBACKS.get(slug, []))
        if not effects and slug:
            effects = [slug]
    cache[cache_key] = list(effects)
    return list(effects)


def _unit_has_gastro_acid(unit: GameUnit) -> bool:
    try:
        states = _normalize_states(getattr(unit, "states", None))
        return bool(states and str(states[0]).lower() == "gastro_acid" and int(states[1]) > 0)
    except Exception:
        return False


def _unit_is_neutralizing_gas_holder(unit: GameUnit, db: Session, *, _cache: dict | None = None) -> bool:
    if _unit_has_gastro_acid(unit):
        return False
    for token in _raw_ability_effect_tokens(unit, db, _cache=_cache):
        parts = _token_parts(token)
        if parts and parts[0] == "suppress_other_abilities":
            return True
        if token.lower() == "neutralizing_gas":
            return True
    return False


def field_has_neutralizing_gas(game_id: int, db: Session, *, _cache: dict | None = None) -> bool:
    """True if any living non-suppressed unit has Neutralizing Gas."""
    if not game_id:
        return False
    cache = _cache if _cache is not None else {}
    units = (
        db.query(GameUnit)
        .filter(GameUnit.game_id == game_id, GameUnit.is_fainted.is_(False))
        .all()
    )
    for unit in units:
        if _unit_is_neutralizing_gas_holder(unit, db, _cache=cache):
            return True
    return False


def _is_ability_suppressed(unit: GameUnit, db: Session | None = None) -> bool:
    """True if Gastro Acid or Neutralizing Gas (from another unit) suppresses this unit."""
    if _unit_has_gastro_acid(unit):
        return True
    if db is None:
        return False
    game_id = getattr(unit, "game_id", None)
    if not isinstance(game_id, int):
        return False
    if _unit_is_neutralizing_gas_holder(unit, db):
        return False
    return field_has_neutralizing_gas(game_id, db)


def _normalize_status_name(status: str) -> str:
    key = str(status or "").lower().strip()
    return STATUS_ALIASES.get(key, key)


def _normalize_stat_name(stat: str) -> str:
    key = str(stat or "").lower().strip()
    return STAT_ALIASES.get(key, key)


def _active_status(unit: GameUnit) -> str | None:
    raw = getattr(unit, "status_effects", None)
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    try:
        if int(raw[1]) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    return _normalize_status_name(str(raw[0]))


def _has_any_status(unit: GameUnit) -> bool:
    return _active_status(unit) is not None


def _max_hp(unit: GameUnit) -> int:
    stats = getattr(unit, "current_stats", None)
    if isinstance(stats, dict):
        try:
            return int(stats.get("hp", 0) or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _hp_percent(unit: GameUnit) -> float:
    max_hp = _max_hp(unit)
    if max_hp <= 0:
        return 100.0
    try:
        return (float(unit.current_hp or 0) / float(max_hp)) * 100.0
    except (TypeError, ValueError):
        return 100.0


def _move_type(move: Any) -> str:
    return str(getattr(move, "type", "") or "").lower().strip()


def _move_category(move: Any) -> str:
    return str(getattr(move, "category", "") or "").lower().strip()


def _move_slug(move: Any) -> str:
    for attr in ("slug", "name"):
        value = getattr(move, attr, None)
        if value:
            return str(value).lower().strip().replace(" ", "_").replace("'", "")
    return ""


def _unit_display_name(unit: GameUnit) -> str:
    unit_info = getattr(unit, "unit", None)
    if unit_info and getattr(unit_info, "name", None):
        return str(unit_info.name)
    return f"Unit {getattr(unit, 'id', '?')}"


def _get_unit_gender(unit: GameUnit) -> str | None:
    flags = _unit_flags(unit)
    if flags.get("gender") is not None:
        return str(flags["gender"]).lower().strip() or None
    unit_info = getattr(unit, "unit", None)
    if unit_info is not None and getattr(unit_info, "gender", None) is not None:
        return str(unit_info.gender).lower().strip() or None
    return None


def _weather_id_at(weather_tiles: list | None, x: int, y: int) -> int:
    if not isinstance(weather_tiles, list) or y < 0 or x < 0 or y >= len(weather_tiles):
        return 0
    row = weather_tiles[y]
    if not isinstance(row, list) or x >= len(row):
        return 0
    try:
        return int(row[x] or 0)
    except (TypeError, ValueError):
        return 0


def _unit_weather_id(unit: GameUnit, weather_tiles: list | None) -> int:
    try:
        x = int(getattr(unit, "current_x", 0) or 0)
        y = int(getattr(unit, "current_y", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return _weather_id_at(weather_tiles, x, y)


def _terrain_id_at(terrain_tiles: list | None, x: int, y: int) -> int:
    if not isinstance(terrain_tiles, list) or y < 0 or x < 0 or y >= len(terrain_tiles):
        return 0
    row = terrain_tiles[y]
    if not isinstance(row, list) or x >= len(row):
        return 0
    cell = row[x]
    try:
        if isinstance(cell, (list, tuple)) and cell:
            return int(cell[0] or 0)
        return int(cell or 0)
    except (TypeError, ValueError):
        return 0


def _unit_terrain_id(unit: GameUnit, terrain_tiles: list | None, db: Session | None = None) -> int:
    tiles = terrain_tiles
    if tiles is None and db is not None:
        game_id = getattr(unit, "game_id", None)
        if isinstance(game_id, int):
            try:
                from app.db.models import GameMapState

                map_state = db.query(GameMapState).filter(GameMapState.game_id == game_id).first()
                if map_state and isinstance(map_state.terrain_effect_tiles, list):
                    tiles = map_state.terrain_effect_tiles
            except Exception:
                tiles = None
    try:
        x = int(getattr(unit, "current_x", 0) or 0)
        y = int(getattr(unit, "current_y", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return _terrain_id_at(tiles, x, y)


def _default_get_unit_types(unit: GameUnit, db: Session) -> set[str]:
    """Fallback type lookup using battle type override, then species types."""
    flags = _unit_flags(unit)
    battle_types = flags.get("battle_types")
    if isinstance(battle_types, list) and battle_types:
        return {str(t).lower() for t in battle_types if t}

    unit_info = getattr(unit, "unit", None)
    if unit_info and isinstance(getattr(unit_info, "types", None), list):
        return {str(t).lower() for t in unit_info.types}

    if getattr(unit, "unit_id", None):
        from app.db.models import Unit

        row = db.query(Unit).filter_by(id=unit.unit_id).first()
        if row and isinstance(row.types, list):
            return {str(t).lower() for t in row.types}
    return set()


# ---------------------------------------------------------------------------
# Effect token parsing / ability lookup
# ---------------------------------------------------------------------------


def parse_effects(effects: list | None) -> list[str]:
    """Normalize a raw Ability.effect JSON value into a list of token strings."""
    if not effects:
        return []
    if isinstance(effects, str):
        token = effects.strip()
        return [token] if token else []
    if not isinstance(effects, list):
        return []
    out: list[str] = []
    for item in effects:
        if item is None:
            continue
        token = str(item).strip()
        if token:
            out.append(token)
    return out


def get_active_ability(unit: GameUnit, db: Session, *, _cache: dict | None = None) -> Ability | None:
    """Return the unit's active Ability row, or None if suppressed / missing."""
    if unit is None or getattr(unit, "is_fainted", False):
        return None
    if _is_ability_suppressed(unit, db):
        return None

    cache = _cache if _cache is not None else {}
    cache_key = ("ability", getattr(unit, "id", None), _get_unit_ability_id(unit))
    if cache_key in cache:
        return cache[cache_key]

    ability_id = _get_unit_ability_id(unit)
    if ability_id is None:
        cache[cache_key] = None
        return None

    ability = db.query(Ability).filter(Ability.id == ability_id).first()
    cache[cache_key] = ability
    return ability


def get_ability_effects(unit: GameUnit, db: Session, *, _cache: dict | None = None) -> list[str]:
    """Return effect tokens for the unit's active ability (empty if none)."""
    cache = _cache if _cache is not None else {}
    unit_key = ("effects", getattr(unit, "id", None))
    if unit_key in cache:
        return list(cache[unit_key])

    ability = get_active_ability(unit, db, _cache=cache)
    if ability is None:
        cache[unit_key] = []
        return []

    effects = parse_effects(getattr(ability, "effect", None))
    if not effects:
        slug = str(getattr(ability, "slug", "") or "").lower().strip()
        effects = list(_SLUG_EFFECT_FALLBACKS.get(slug, []))
        # Last resort: treat slug itself as a recognizable token.
        if not effects and slug:
            effects = [slug]
    cache[unit_key] = list(effects)
    return list(effects)


def ability_has_token(unit: GameUnit, db: Session, *prefixes: str, _cache: dict | None = None) -> bool:
    """True if any ability effect token starts with any of the given prefixes."""
    if not prefixes:
        return False
    effects = get_ability_effects(unit, db, _cache=_cache)
    norms = [str(p).lower() for p in prefixes if p]
    for effect in effects:
        el = effect.lower()
        for prefix in norms:
            if el == prefix or el.startswith(prefix):
                return True
    return False


def _token_parts(token: str) -> list[str]:
    return [p for p in str(token).lower().split(":") if p != ""]


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------


def weather_is_suppressed(game_id: int, db: Session) -> bool:
    """True if any living unit in the game has ``suppress_weather`` (Air Lock / Cloud Nine / Teraform Zero)."""
    if not game_id:
        return False
    units = (
        db.query(GameUnit)
        .filter(GameUnit.game_id == game_id, GameUnit.is_fainted.is_(False))
        .all()
    )
    cache: dict = {}
    for unit in units:
        if ability_has_token(unit, db, "suppress_weather", _cache=cache):
            return True
        if ability_has_token(unit, db, "on_stellar_forme:suppress_weather", "teraform_zero", _cache=cache):
            if str(_unit_flags(unit).get("forme") or "").lower() == "stellar":
                return True
    return False


def terrain_is_suppressed(game_id: int, db: Session) -> bool:
    """True if any living unit suppresses terrain (Teraform Zero in Stellar forme)."""
    if not game_id:
        return False
    units = (
        db.query(GameUnit)
        .filter(GameUnit.game_id == game_id, GameUnit.is_fainted.is_(False))
        .all()
    )
    cache: dict = {}
    for unit in units:
        if ability_has_token(unit, db, "on_stellar_forme:suppress_terrain", "teraform_zero", _cache=cache):
            if str(_unit_flags(unit).get("forme") or "").lower() == "stellar":
                return True
    return False


def weather_id_matches(weather_id: int, weather_name: str) -> bool:
    """Match weather tiles to effect tokens; sun/rain also match primal variants."""
    name = str(weather_name or "").lower().strip()
    expected = WEATHER_TO_ID.get(name)
    if expected is None or not weather_id:
        return False
    if int(weather_id) == expected:
        return True
    if name == "sun" and int(weather_id) == WEATHER_TO_ID["harsh_sun"]:
        return True
    if name == "rain" and int(weather_id) == WEATHER_TO_ID["heavy_rain"]:
        return True
    return False


def set_weather_on_map(map_state: Any, weather_name: str) -> None:
    """Paint every weather tile on ``map_state`` with the given weather name."""
    weather_id = WEATHER_TO_ID.get(str(weather_name or "").lower().strip())
    if weather_id is None:
        return
    tiles = getattr(map_state, "weather_tiles", None)
    if not isinstance(tiles, list) or not tiles:
        return
    new_tiles: list[list[int]] = []
    for row in tiles:
        if not isinstance(row, list):
            new_tiles.append([])
            continue
        new_tiles.append([weather_id for _ in row])
    map_state.weather_tiles = new_tiles


def set_terrain_on_map(
    map_state: Any,
    terrain_name: str,
    *,
    duration: int = TERRAIN_DEFAULT_DURATION,
    terrain_map: dict | None = None,
) -> None:
    """Paint every terrain tile as timed ``[id, duration]`` cells (Electric Surge etc.)."""
    id_map = terrain_map or TERRAIN_TO_ID
    terrain_id = id_map.get(str(terrain_name or "").lower().strip())
    if terrain_id is None:
        return
    try:
        turns = max(1, int(duration))
    except (TypeError, ValueError):
        turns = TERRAIN_DEFAULT_DURATION

    tiles = getattr(map_state, "terrain_effect_tiles", None)
    if not isinstance(tiles, list) or not tiles:
        weather = getattr(map_state, "weather_tiles", None)
        if isinstance(weather, list) and weather:
            tiles = weather
        else:
            return

    new_tiles: list[list[list[int]]] = []
    for row in tiles:
        if not isinstance(row, list):
            new_tiles.append([])
            continue
        new_tiles.append([[int(terrain_id), turns] for _ in row])
    map_state.terrain_effect_tiles = new_tiles


# ---------------------------------------------------------------------------
# Battle types / Forecast / Flash Fire / Truant
# ---------------------------------------------------------------------------


def set_battle_types(unit: GameUnit, types: list[str], db: Session) -> None:
    """Override the unit's in-battle types via flags."""
    flags = _unit_flags(unit)
    cleaned = [str(t).lower().strip() for t in types if t]
    if cleaned:
        flags["battle_types"] = cleaned
    else:
        flags.pop("battle_types", None)
    _set_unit_flags(unit, flags, db)


def get_battle_types(unit: GameUnit, db: Session, fallback_fn: Callable | None = None) -> set[str]:
    """Return battle type override if set, otherwise call ``fallback_fn`` or default."""
    flags = _unit_flags(unit)
    battle_types = flags.get("battle_types")
    if isinstance(battle_types, list) and battle_types:
        return {str(t).lower() for t in battle_types if t}
    if callable(fallback_fn):
        result = fallback_fn(unit, db)
        return {str(t).lower() for t in (result or set())}
    return _default_get_unit_types(unit, db)


def has_flash_fire_boost(unit: GameUnit) -> bool:
    """True if Flash Fire has activated for this unit."""
    flags = _unit_flags(unit)
    return bool(flags.get("flash_fire_boost") or flags.get("flash_fire"))


def update_forecast_types(unit: GameUnit, weather_id: int, db: Session) -> bool:
    """Update Castform-style Forecast battle types from weather. Returns True if changed."""
    if not ability_has_token(unit, db, "on_weather:change_type", "forecast"):
        return False

    if weather_id_matches(weather_id, "rain") or weather_id == WEATHER_TO_ID["heavy_rain"]:
        new_types = ["water"]
    elif weather_id_matches(weather_id, "sun") or weather_id == WEATHER_TO_ID["harsh_sun"]:
        new_types = ["fire"]
    elif weather_id == WEATHER_TO_ID["hail"]:
        new_types = ["ice"]
    else:
        new_types = ["normal"]

    flags = _unit_flags(unit)
    current_override = flags.get("battle_types")
    current = (
        [str(t).lower() for t in current_override]
        if isinstance(current_override, list) and current_override
        else sorted(_default_get_unit_types(unit, db))
    )
    if sorted(current) == sorted(new_types):
        return False

    if new_types == ["normal"]:
        # Clear override so species types apply in clear/sand weather.
        flags.pop("battle_types", None)
        _set_unit_flags(unit, flags, db)
        return True

    set_battle_types(unit, new_types, db)
    return True


def update_mimicry_types(unit: GameUnit, terrain_id: int, db: Session) -> bool:
    """Mimicry: change type to match active terrain. Returns True if changed."""
    if not ability_has_token(unit, db, "on_terrain:change_type", "mimicry"):
        return False

    if terrain_id == TERRAIN_TO_ID.get("electric"):
        new_types = ["electric"]
    elif terrain_id == TERRAIN_TO_ID.get("psychic"):
        new_types = ["psychic"]
    elif terrain_id == TERRAIN_TO_ID.get("grassy"):
        new_types = ["grass"]
    elif terrain_id == TERRAIN_TO_ID.get("misty"):
        new_types = ["fairy"]
    else:
        # Clear override so species types apply with no terrain.
        flags = _unit_flags(unit)
        if "battle_types" not in flags:
            return False
        flags.pop("battle_types", None)
        _set_unit_flags(unit, flags, db)
        return True

    flags = _unit_flags(unit)
    current_override = flags.get("battle_types")
    current = (
        [str(t).lower() for t in current_override]
        if isinstance(current_override, list) and current_override
        else sorted(_default_get_unit_types(unit, db))
    )
    if sorted(current) == sorted(new_types):
        return False
    set_battle_types(unit, new_types, db)
    return True


def restore_ice_face_on_hail(unit: GameUnit, weather_id: int, db: Session) -> bool:
    """Ice Face: restore ice forme in hail/snow. Returns True if restored."""
    if not ability_has_token(unit, db, "on_weather:hail:restore_forme", "ice_face"):
        return False
    if not weather_id_matches(weather_id, "hail") and weather_id != WEATHER_TO_ID.get("hail"):
        return False
    flags = _unit_flags(unit)
    if flags.get("forme") != "noice" and not flags.get("ice_face_broken"):
        return False
    flags["forme"] = "ice"
    flags.pop("ice_face_broken", None)
    _set_unit_flags(unit, flags, db)
    return True


def should_skip_turn_due_to_truant(unit: GameUnit, db: Session) -> bool:
    """Toggle Truant loafing each action. Returns True if this action should be skipped."""
    if not ability_has_token(unit, db, "alternate_turn:loaf", "truant"):
        return False
    flags = _unit_flags(unit)
    loafing = bool(flags.get("truant_loafing"))
    flags["truant_loafing"] = not loafing
    _set_unit_flags(unit, flags, db)
    return loafing


def process_switch_out_or_faint(
    unit: GameUnit,
    db: Session,
    *,
    fainted: bool = False,
) -> bool:
    """Natural Cure + Regenerator on switch-out.

    Natural Cure clears status on switch-out or faint.
    Regenerator heals 1/3 max HP on switch-out only (not on faint).
    Returns True if any effect applied.
    """
    applied = False
    if ability_has_token(unit, db, "on_switch_out:self:cure_status", "natural_cure"):
        if _has_any_status(unit):
            unit.status_effects = []
            db.add(unit)
            applied = True

    # Zero to Hero: on_switch_out:change_forme:hero
    if not fainted:
        for token in get_ability_effects(unit, db):
            parts = _token_parts(token)
            if (
                len(parts) >= 3
                and parts[0] == "on_switch_out"
                and parts[1] == "change_forme"
            ):
                flags = _unit_flags(unit)
                flags["forme"] = parts[2]
                _set_unit_flags(unit, flags, db)
                applied = True
                break

    # Regenerator: heal on switch-out only — call from withdraw/recall when available.
    if not fainted and ability_has_token(
        unit, db, "on_switch_out:self:heal_fraction", "regenerator"
    ):
        max_hp = _max_hp(unit)
        if max_hp > 0:
            fraction = 3
            for token in get_ability_effects(unit, db):
                parts = _token_parts(token)
                if (
                    len(parts) >= 4
                    and parts[0] == "on_switch_out"
                    and parts[1] == "self"
                    and parts[2] == "heal_fraction"
                ):
                    try:
                        fraction = int(parts[3])
                    except (TypeError, ValueError):
                        fraction = 3
                    break
            heal = max(1, max_hp // fraction)
            cur = int(unit.current_hp or 0)
            if cur < max_hp:
                unit.current_hp = min(max_hp, cur + heal)
                db.add(unit)
                applied = True
    return applied


def blocks_item_removal(unit: GameUnit, db: Session) -> bool:
    """Sticky Hold: prevent item theft/removal."""
    return ability_has_token(unit, db, "immune_item_removal", "sticky_hold")


def extra_pp_cost_against(targets: list[GameUnit], db: Session) -> int:
    """Pressure: extra PP cost equal to number of opposing targets with Pressure."""
    cache: dict = {}
    total = 0
    for target in targets or []:
        if target is None or getattr(target, "is_fainted", False):
            continue
        if ability_has_token(target, db, "on_targeted:attacker:extra_pp_cost", "pressure", _cache=cache):
            total += 1
    return total


# ---------------------------------------------------------------------------
# Damage / type modifiers
# ---------------------------------------------------------------------------


def _move_has_recoil_or_crash(move: Any, flag: str) -> bool:
    """True if move effects include recoil / failure_damage (crash)."""
    effects = getattr(move, "effects", None)
    if not isinstance(effects, list):
        return False
    flag_n = str(flag or "").lower().strip()
    for eff in effects:
        token = str(eff or "").lower()
        if flag_n == "recoil" and ("recoil" in token or token.startswith("self:recoil")):
            return True
        if flag_n == "crash" and (
            "failure_damage" in token
            or "crash" in token
            or token.startswith("self:crash")
        ):
            return True
    return False


def _move_is_punch(move: Any) -> bool:
    if move_has_trait(move, MOVE_TRAIT_PUNCHING):
        return True
    slug = _move_slug(move)
    if slug in PUNCH_MOVE_SLUGS:
        return True
    # Also accept hyphenated forms.
    if slug.replace("-", "_") in PUNCH_MOVE_SLUGS:
        return True
    name = str(getattr(move, "name", "") or "").lower().replace(" ", "_").replace("-", "_")
    return name in PUNCH_MOVE_SLUGS


def _move_is_bite(move: Any) -> bool:
    if move_has_trait(move, MOVE_TRAIT_BITING):
        return True
    slug = _move_slug(move).replace("-", "_")
    if slug in BITE_MOVE_SLUGS:
        return True
    name = str(getattr(move, "name", "") or "").lower().replace(" ", "_").replace("-", "_")
    return name in BITE_MOVE_SLUGS


def _move_is_pulse(move: Any) -> bool:
    if move_has_trait(move, MOVE_TRAIT_PULSE):
        return True
    slug = _move_slug(move).replace("-", "_")
    if slug in PULSE_MOVE_SLUGS:
        return True
    name = str(getattr(move, "name", "") or "").lower().replace(" ", "_").replace("-", "_")
    return name in PULSE_MOVE_SLUGS


def _move_is_ball_bomb(move: Any) -> bool:
    if move_has_trait(move, MOVE_TRAIT_BALL_BOMB):
        return True
    slug = _move_slug(move).replace("-", "_")
    if slug in BALL_BOMB_MOVE_SLUGS:
        return True
    name = str(getattr(move, "name", "") or "").lower().replace(" ", "_").replace("-", "_")
    return name in BALL_BOMB_MOVE_SLUGS


def _move_is_slicing(move: Any) -> bool:
    if move_has_trait(move, MOVE_TRAIT_SLICING):
        return True
    slug = _move_slug(move).replace("-", "_")
    if slug in SLICING_MOVE_SLUGS:
        return True
    name = str(getattr(move, "name", "") or "").lower().replace(" ", "_").replace("-", "_")
    return name in SLICING_MOVE_SLUGS


def _move_is_wind(move: Any) -> bool:
    if move_has_trait(move, MOVE_TRAIT_WIND):
        return True
    slug = _move_slug(move).replace("-", "_")
    if slug in WIND_MOVE_SLUGS:
        return True
    name = str(getattr(move, "name", "") or "").lower().replace(" ", "_").replace("-", "_")
    return name in WIND_MOVE_SLUGS


def _move_is_sound(move: Any) -> bool:
    return move_has_trait(move, MOVE_TRAIT_SOUND)


def _move_is_powder(move: Any) -> bool:
    if move_has_trait(move, MOVE_TRAIT_POWDER):
        return True
    slug = _move_slug(move).replace("-", "_")
    if slug in POWDER_MOVE_SLUGS:
        return True
    name = str(getattr(move, "name", "") or "").lower().replace(" ", "_").replace("-", "_")
    return name in POWDER_MOVE_SLUGS


def _lookup_unit_weather_tiles(unit: GameUnit, db: Session, weather_tiles: list | None = None) -> list | None:
    if weather_tiles is not None:
        return weather_tiles
    game_id = getattr(unit, "game_id", None)
    if not isinstance(game_id, int):
        return None
    try:
        from app.db.models import GameMapState

        map_state = db.query(GameMapState).filter(GameMapState.game_id == game_id).first()
        if map_state and isinstance(map_state.weather_tiles, list):
            return map_state.weather_tiles
    except Exception:
        return None
    return None


def _is_status_move(move: Any) -> bool:
    category = _move_category(move)
    if category == "status":
        return True
    try:
        power = getattr(move, "power", None)
        power_i = int(power) if power is not None else 0
    except (TypeError, ValueError):
        power_i = 0
    if category in {"physical", "special"}:
        return False
    return power_i <= 0


def move_has_secondary_effects(move: Any) -> bool:
    """True if move effects include secondary status/stat/state chance tokens."""
    effects = getattr(move, "effects", None)
    if not isinstance(effects, list):
        return False
    for eff in effects:
        token = str(eff or "").lower().strip()
        if not token:
            continue
        parts = [p for p in token.split(":") if p]
        if len(parts) < 2:
            continue
        recipient = parts[0]
        effect_type = parts[1]
        if recipient not in {"target", "self", "opponents", "allies"}:
            continue
        if effect_type in {
            "status",
            "raise_stat",
            "lower_stat",
            "apply_state",
            "flinch",
            "confuse",
            "confusion",
        }:
            return True
        if "flinch" in token or "confuse" in token:
            return True
    return False


def removes_secondary_effects(attacker: GameUnit, db: Session) -> bool:
    """Sheer Force: strip secondary effects from the attacker's moves."""
    return ability_has_token(
        attacker, db, "remove_secondary_effects", "sheer_force"
    )


def attacker_power_multiplier(
    attacker: GameUnit,
    move: Any,
    db: Session,
    *,
    weather_tiles: list | None = None,
    target: GameUnit | None = None,
    is_last_move: bool | None = None,
    type_multiplier: float | None = None,
) -> float:
    """Ability-based attack power multiplier (default 1.0).

    Covers Blaze/Torrent/Overgrow/Swarm, Hustle, Huge/Pure Power, Flash Fire
    boost, Technician, Iron Fist, Reckless, Rivalry, Normalize, Sand Force,
    Flare/Toxic Boost, Sheer Force, Analytic, Steelworker, Water Bubble,
    Neuroforce, Battery, Stakeout.
    """
    effects = get_ability_effects(attacker, db)

    mult = 1.0
    move_type = _move_type(move)
    category = _move_category(move)
    hp_pct = _hp_percent(attacker)
    active_status = _active_status(attacker)
    try:
        move_power = int(getattr(move, "power", 0) or 0)
    except (TypeError, ValueError):
        move_power = 0

    weather_id = _unit_weather_id(attacker, weather_tiles)
    game_id = getattr(attacker, "game_id", None)
    if isinstance(game_id, int) and weather_is_suppressed(game_id, db):
        weather_id = 0

    # Normalize / convert_move_type: boost only when type actually changed
    original_move_type = move_type
    converted_to = convert_move_type(attacker, move, db)
    converted = converted_to is not None and converted_to != original_move_type
    if converted_to is not None:
        move_type = converted_to
    if not converted:
        flags = _unit_flags(attacker)
        converted = bool(flags.get("normalize_active") or flags.get("convert_move_type"))

    has_secondary = move_has_secondary_effects(move)
    applied_status_cat_boosts: set[tuple[str, str]] = set()

    for token in effects:
        parts = _token_parts(token)

        # on_hp_below:N:on_move_type:TYPE:self:boost_power:X
        if (
            len(parts) >= 7
            and parts[0] == "on_hp_below"
            and parts[2] == "on_move_type"
            and parts[4] == "self"
            and parts[5] == "boost_power"
        ):
            try:
                threshold = float(parts[1])
                boost = float(parts[6])
            except (TypeError, ValueError):
                continue
            if hp_pct <= threshold and move_type == parts[3]:
                mult *= boost
            continue

        # on_weather:sandstorm:on_move_type:TYPE:self:boost_power:X (Sand Force)
        if (
            len(parts) >= 7
            and parts[0] == "on_weather"
            and parts[2] == "on_move_type"
            and parts[4] == "self"
            and parts[5] == "boost_power"
        ):
            try:
                boost = float(parts[6])
            except (TypeError, ValueError):
                continue
            if weather_id_matches(weather_id, parts[1]) and move_type == parts[3]:
                mult *= boost
            continue

        # on_status:burn|poison|badly_poison:on_move_category:CAT:self:boost_power:X
        if (
            len(parts) >= 7
            and parts[0] == "on_status"
            and parts[2] == "on_move_category"
            and parts[4] == "self"
            and parts[5] == "boost_power"
        ):
            status_cond = _normalize_status_name(parts[1])
            try:
                boost = float(parts[6])
            except (TypeError, ValueError):
                continue
            if active_status is None:
                continue
            poison_family = {"poison", "badly_poisoned"}
            if status_cond in poison_family:
                if active_status not in poison_family:
                    continue
                # Deduplicate poison + badly_poison tokens (Toxic Boost)
                boost_key = ("poison_family", parts[3])
            else:
                if active_status != status_cond:
                    continue
                boost_key = (status_cond, parts[3])
            if boost_key in applied_status_cat_boosts:
                continue
            if category == parts[3]:
                applied_status_cat_boosts.add(boost_key)
                mult *= boost
            continue

        # on_moves_with_secondary:self:boost_power:1.3 (Sheer Force)
        if (
            len(parts) >= 4
            and parts[0] == "on_moves_with_secondary"
            and parts[1] == "self"
            and parts[2] == "boost_power"
        ):
            try:
                boost = float(parts[3])
            except (TypeError, ValueError):
                continue
            if has_secondary:
                mult *= boost
            continue

        # on_move_last:self:boost_power:1.3 (Analytic)
        if (
            len(parts) >= 4
            and parts[0] == "on_move_last"
            and parts[1] == "self"
            and parts[2] == "boost_power"
        ):
            try:
                boost = float(parts[3])
            except (TypeError, ValueError):
                continue
            if is_last_move is True:
                mult *= boost
            continue

        # on_move_type:TYPE:self:boost_power:X (Steelworker / Water Bubble)
        if (
            len(parts) >= 5
            and parts[0] == "on_move_type"
            and parts[2] == "self"
            and parts[3] == "boost_power"
        ):
            try:
                boost = float(parts[4])
            except (TypeError, ValueError):
                continue
            if move_type == parts[1]:
                mult *= boost
            continue

        # on_super_effective_deal:self:boost_power:1.25 (Neuroforce)
        if (
            len(parts) >= 4
            and parts[0] == "on_super_effective_deal"
            and parts[1] == "self"
            and parts[2] == "boost_power"
        ):
            try:
                boost = float(parts[3])
            except (TypeError, ValueError):
                continue
            if type_multiplier is not None and float(type_multiplier) > 1.0:
                mult *= boost
            continue

        # on_target_switched_in:self:boost_power:2 (Stakeout)
        if (
            len(parts) >= 4
            and parts[0] == "on_target_switched_in"
            and parts[1] == "self"
            and parts[2] == "boost_power"
        ):
            try:
                boost = float(parts[3])
            except (TypeError, ValueError):
                continue
            if target is not None and bool(_unit_flags(target).get("just_switched_in")):
                mult *= boost
            continue

        # on_move_category:physical|special|sound:self:boost_power:X
        if (
            len(parts) >= 5
            and parts[0] == "on_move_category"
            and parts[2] == "self"
            and parts[3] == "boost_power"
        ):
            try:
                boost = float(parts[4])
            except (TypeError, ValueError):
                continue
            cat = parts[1]
            if cat == "sound":
                if _move_is_sound(move):
                    mult *= boost
            elif category == cat:
                mult *= boost
            continue

        # on_move_power_at_most:60:self:boost_power:1.5 (Technician)
        if (
            len(parts) >= 5
            and parts[0] == "on_move_power_at_most"
            and parts[2] == "self"
            and parts[3] == "boost_power"
        ):
            try:
                threshold = int(parts[1])
                boost = float(parts[4])
            except (TypeError, ValueError):
                continue
            if move_power > 0 and move_power <= threshold:
                mult *= boost
            continue

        # on_move_flag:punch|recoil|crash|contact|bite|pulse:self:boost_power:X
        if (
            len(parts) >= 5
            and parts[0] == "on_move_flag"
            and parts[2] == "self"
            and parts[3] == "boost_power"
        ):
            try:
                boost = float(parts[4])
            except (TypeError, ValueError):
                continue
            flag = parts[1]
            if flag == "punch" and _move_is_punch(move):
                mult *= boost
            elif flag in {"recoil", "crash"} and _move_has_recoil_or_crash(move, flag):
                mult *= boost
            elif flag == "contact" and bool(getattr(move, "makes_contact", False)):
                mult *= boost
            elif flag == "bite" and _move_is_bite(move):
                mult *= boost
            elif flag == "pulse" and _move_is_pulse(move):
                mult *= boost
            elif flag == "slicing" and _move_is_slicing(move):
                mult *= boost
            continue

        # on_same_gender / on_opposite_gender (Rivalry) — needs target
        if (
            len(parts) >= 4
            and parts[0] in {"on_same_gender", "on_opposite_gender"}
            and parts[1] == "self"
            and parts[2] == "boost_power"
        ):
            try:
                boost = float(parts[3])
            except (TypeError, ValueError):
                continue
            if target is None:
                continue
            g1 = _get_unit_gender(attacker)
            g2 = _get_unit_gender(target)
            if not g1 or not g2 or g1 == "genderless" or g2 == "genderless":
                continue
            if parts[0] == "on_same_gender" and g1 == g2:
                mult *= boost
            elif parts[0] == "on_opposite_gender" and g1 != g2:
                mult *= boost
            continue

        # on_converted_type:self:boost_power:1.2 (Normalize / -ate abilities)
        if (
            len(parts) >= 4
            and parts[0] == "on_converted_type"
            and parts[1] == "self"
            and parts[2] == "boost_power"
        ):
            try:
                boost = float(parts[3])
            except (TypeError, ValueError):
                continue
            if converted:
                mult *= boost
            continue

        # self:boost_power:X (generic)
        if len(parts) >= 3 and parts[0] == "self" and parts[1] == "boost_power":
            try:
                mult *= float(parts[2])
            except (TypeError, ValueError):
                pass

    # Supreme Overlord: on_switch_in:boost_power_per_fainted_ally stored as flag
    flags = _unit_flags(attacker)
    so_boost = flags.get("supreme_overlord_boost")
    if so_boost is not None:
        try:
            mult *= 1.0 + float(so_boost)
        except (TypeError, ValueError):
            pass

    # Flash Fire activated boost for Fire moves
    if has_flash_fire_boost(attacker) and move_type == "fire":
        mult *= 1.5

    # Battery / Power Spot / Steely Spirit from allies
    if isinstance(game_id, int):
        user_id = getattr(attacker, "user_id", None)
        if user_id is not None:
            allies = (
                db.query(GameUnit)
                .filter(
                    GameUnit.game_id == game_id,
                    GameUnit.user_id == user_id,
                    GameUnit.is_fainted.is_(False),
                )
                .all()
            )
            cache: dict = {}
            ax = int(getattr(attacker, "current_x", -1) or -1)
            ay = int(getattr(attacker, "current_y", -1) or -1)
            for ally in allies:
                ally_is_self = getattr(ally, "id", None) == getattr(attacker, "id", None)
                for token in get_ability_effects(ally, db, _cache=cache):
                    parts = _token_parts(token)
                    # Battery: allies:on_move_category:special:boost_power:X
                    if (
                        not ally_is_self
                        and len(parts) >= 5
                        and parts[0] == "allies"
                        and parts[1] == "on_move_category"
                        and parts[3] == "boost_power"
                    ):
                        if category == parts[2]:
                            try:
                                mult *= float(parts[4])
                            except (TypeError, ValueError):
                                pass
                    # Power Spot: adjacent_allies:boost_power:1.3
                    if (
                        not ally_is_self
                        and len(parts) >= 3
                        and parts[0] == "adjacent_allies"
                        and parts[1] == "boost_power"
                    ):
                        ox = int(getattr(ally, "current_x", -1) or -1)
                        oy = int(getattr(ally, "current_y", -1) or -1)
                        if ax >= 0 and ay >= 0 and ox >= 0 and oy >= 0:
                            if abs(ax - ox) + abs(ay - oy) == 1:
                                try:
                                    mult *= float(parts[2])
                                except (TypeError, ValueError):
                                    pass
                    # Steely Spirit: self_and_allies:on_move_type:steel:boost_power:1.5
                    if (
                        len(parts) >= 5
                        and parts[0] == "self_and_allies"
                        and parts[1] == "on_move_type"
                        and parts[3] == "boost_power"
                    ):
                        if move_type == parts[2]:
                            try:
                                mult *= float(parts[4])
                            except (TypeError, ValueError):
                                pass

    return mult


def defender_damage_multiplier(
    defender: GameUnit,
    move: Any,
    move_type: str,
    type_multiplier: float,
    db: Session,
    *,
    makes_contact: bool | None = None,
) -> float:
    """Defender-side damage multiplier after type calc (Thick Fat, Wonder Guard, Filter, Multiscale, Friend Guard, Fluffy)."""
    effects = get_ability_effects(defender, db)
    mult = 1.0
    mt = str(move_type or _move_type(move)).lower()
    contact = (
        bool(makes_contact)
        if makes_contact is not None
        else bool(getattr(move, "makes_contact", False))
    )

    for token in effects:
        parts = _token_parts(token)

        # on_hit_type:fire:self:resist:0.5
        if (
            len(parts) >= 5
            and parts[0] == "on_hit_type"
            and parts[2] == "self"
            and parts[3] == "resist"
        ):
            if mt == parts[1]:
                try:
                    mult *= float(parts[4])
                except (TypeError, ValueError):
                    pass
            continue

        # on_super_effective:self:resist:0.75 (Filter / Solid Rock)
        if (
            len(parts) >= 4
            and parts[0] == "on_super_effective"
            and parts[1] == "self"
            and parts[2] == "resist"
        ):
            if type_multiplier > 1.0:
                try:
                    mult *= float(parts[3])
                except (TypeError, ValueError):
                    pass
            continue

        # on_hp_full:self:resist:0.5 (Multiscale)
        if (
            len(parts) >= 4
            and parts[0] == "on_hp_full"
            and parts[1] == "self"
            and parts[2] == "resist"
        ):
            max_hp = _max_hp(defender)
            if max_hp > 0 and int(defender.current_hp or 0) >= max_hp:
                try:
                    mult *= float(parts[3])
                except (TypeError, ValueError):
                    pass
            continue

        # on_move_flag:contact:self:resist:0.5 (Fluffy)
        if (
            len(parts) >= 5
            and parts[0] == "on_move_flag"
            and parts[2] == "self"
            and parts[3] == "resist"
        ):
            if parts[1] == "contact" and contact:
                try:
                    mult *= float(parts[4])
                except (TypeError, ValueError):
                    pass
            continue

        # on_move_category:physical|special|sound:self:resist:0.5 (Fur Coat / Ice Scales / Punk Rock)
        if (
            len(parts) >= 5
            and parts[0] == "on_move_category"
            and parts[2] == "self"
            and parts[3] == "resist"
        ):
            cat = parts[1]
            matched = False
            if cat == "sound":
                matched = _move_is_sound(move)
            else:
                matched = _move_category(move) == cat
            if matched:
                try:
                    mult *= float(parts[4])
                except (TypeError, ValueError):
                    pass
            continue

        # on_hit_category:sound:self:resist:0.5 (Punk Rock)
        if (
            len(parts) >= 5
            and parts[0] == "on_hit_category"
            and parts[2] == "self"
            and parts[3] == "resist"
        ):
            cat = parts[1]
            matched = False
            if cat == "sound":
                matched = _move_is_sound(move)
            elif cat == "physical":
                matched = _move_category(move) == "physical"
            elif cat == "special":
                matched = _move_category(move) == "special"
            if matched:
                try:
                    mult *= float(parts[4])
                except (TypeError, ValueError):
                    pass
            continue

        # only_super_effective_hits (Wonder Guard)
        if parts == ["only_super_effective_hits"] or parts[0] == "only_super_effective_hits":
            if type_multiplier <= 1.0:
                return 0.0
            continue

    # Friend Guard: living ally with allies:resist_damage:0.75
    game_id = getattr(defender, "game_id", None)
    user_id = getattr(defender, "user_id", None)
    if isinstance(game_id, int) and user_id is not None:
        allies = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id == user_id,
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        cache: dict = {}
        for ally in allies:
            if getattr(ally, "id", None) == getattr(defender, "id", None):
                continue
            ally_effects = get_ability_effects(ally, db, _cache=cache)
            for token in ally_effects:
                parts = _token_parts(token)
                if len(parts) >= 3 and parts[0] == "allies" and parts[1] == "resist_damage":
                    try:
                        mult *= float(parts[2])
                    except (TypeError, ValueError):
                        pass

    return mult


def get_stab_multiplier(
    attacker: GameUnit,
    move_type: str,
    attacker_types: set[str] | list[str] | None,
    db: Session,
) -> float:
    """Return STAB multiplier: 2.0 with Adaptability, 1.5 normal STAB, else 1.0."""
    mt = str(move_type or "").lower().strip()
    types = {str(t).lower() for t in (attacker_types or []) if t}
    if not mt or mt not in types:
        return 1.0
    effects = get_ability_effects(attacker, db)
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 2 and parts[0] == "boost_stab":
            try:
                return float(parts[1])
            except (TypeError, ValueError):
                return 2.0
        if token.lower() == "adaptability":
            return 2.0
    return 1.5


def crit_damage_multiplier(attacker: GameUnit, db: Session) -> float:
    """Sniper → 2.25, else standard 1.5."""
    effects = get_ability_effects(attacker, db)
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 2 and parts[0] == "boost_crit_damage":
            try:
                return float(parts[1])
            except (TypeError, ValueError):
                return 2.25
        if token.lower() == "sniper":
            return 2.25
    return 1.5


def crit_stage_bonus(attacker: GameUnit, db: Session) -> int:
    """Super Luck → +1 crit stage."""
    effects = get_ability_effects(attacker, db)
    bonus = 0
    for token in effects:
        parts = _token_parts(token)
        # self:raise_stat:crit:1 used as a passive stage bonus for Super Luck
        if (
            len(parts) >= 4
            and parts[0] == "self"
            and parts[1] == "raise_stat"
            and _normalize_stat_name(parts[2]) == "crit"
        ):
            try:
                bonus += int(parts[3])
            except (TypeError, ValueError):
                bonus += 1
        elif token.lower() in {"super_luck", "self:raise_stat:crit:1"}:
            bonus += 1
    return bonus


def tinted_lens_multiplier(attacker: GameUnit, type_multiplier: float, db: Session) -> float:
    """Tinted Lens doubles not-very-effective damage (0 < mult < 1)."""
    if not (0 < type_multiplier < 1):
        return type_multiplier
    if ability_has_token(attacker, db, "boost_not_very_effective_to_neutral", "tinted_lens"):
        return type_multiplier * 2.0
    return type_multiplier


def scrappy_allows_hit(
    attacker: GameUnit,
    move_type: str,
    defender_types: set[str] | list[str] | None,
    db: Session,
) -> bool:
    """True if Scrappy lets Normal/Fighting hit Ghost."""
    mt = str(move_type or "").lower().strip()
    types = {str(t).lower() for t in (defender_types or []) if t}
    if "ghost" not in types:
        return False
    effects = get_ability_effects(attacker, db)
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 2 and parts[0] == "hit_ghost_with" and parts[1] == mt:
            return True
        if token.lower() == "scrappy" and mt in {"normal", "fighting"}:
            return True
    return False


def should_ignore_target_ability(attacker: GameUnit, db: Session) -> bool:
    """Mold Breaker / Teravolt / Turboblaze — ignore target ability effects."""
    return ability_has_token(
        attacker, db, "ignore_target_ability", "mold_breaker", "teravolt", "turboblaze"
    )


def should_ignore_indirect_damage(unit: GameUnit, db: Session) -> bool:
    """Magic Guard — blocks residual/indirect damage (weather, status, hazards, recoil, confusion)."""
    return ability_has_token(unit, db, "immune_indirect_damage", "magic_guard")


def should_ignore_weather_damage(unit: GameUnit, db: Session) -> bool:
    """Overcoat / Magic Guard — skip sandstorm/hail chip."""
    if should_ignore_indirect_damage(unit, db):
        return True
    return ability_has_token(unit, db, "immune_weather_damage", "overcoat")


def blocks_powder_move(defender: GameUnit, move: Any, db: Session) -> bool:
    """Overcoat: immune to powder moves (spore, sleep powder, etc.)."""
    if not ability_has_token(defender, db, "immune_category:powder", "overcoat"):
        return False
    if _move_is_powder(move):
        return True
    effects = getattr(move, "effects", None)
    if isinstance(effects, list):
        for eff in effects:
            token = str(eff or "").lower()
            if "powder" in token or token.startswith("category:powder"):
                return True
    return False


def should_ignore_poison_damage(unit: GameUnit, db: Session) -> bool:
    """Poison Heal — skip poison residual (heals instead via EOT ability)."""
    return ability_has_token(unit, db, "ignore_poison_damage", "poison_heal")


def should_halve_burn_damage(unit: GameUnit, db: Session) -> bool:
    """Heatproof."""
    return ability_has_token(unit, db, "halve_burn_damage", "heatproof")


def should_ignore_paralysis_speed(unit: GameUnit, db: Session) -> bool:
    """Quick Feet."""
    return ability_has_token(unit, db, "ignore_paralysis_speed_halve", "quick_feet")


def force_move_never_miss(attacker: GameUnit, target: GameUnit | None, db: Session) -> bool:
    """No Guard on either side forces moves to never miss."""
    if ability_has_token(attacker, db, "moves_never_miss", "no_guard"):
        return True
    if target is not None and ability_has_token(
        target, db, "opponent_moves_never_miss", "moves_never_miss", "no_guard"
    ):
        return True
    return False


def force_max_multi_hit(attacker: GameUnit, db: Session) -> bool:
    """Skill Link."""
    return ability_has_token(attacker, db, "multi_hit:always_max", "skill_link")


def double_stat_changes(unit: GameUnit, db: Session) -> bool:
    """Simple."""
    return ability_has_token(unit, db, "double_stat_changes", "simple")


def ignores_target_stat_boosts_when_attacking(attacker: GameUnit, db: Session) -> bool:
    """Unaware (attacker side)."""
    return ability_has_token(
        attacker, db, "ignore_target_stat_changes_when_attacking", "unaware"
    )


def ignores_attacker_stat_boosts_when_defending(defender: GameUnit, db: Session) -> bool:
    """Unaware (defender side)."""
    return ability_has_token(
        defender, db, "ignore_attacker_stat_changes_when_defending", "unaware"
    )


def convert_move_type(attacker: GameUnit, move: Any, db: Session) -> str | None:
    """Return converted type for Normalize / Refrigerate / Pixilate / Aerilate / Liquid Voice.

    - ``convert_move_type:normal`` → always ``normal`` (Normalize)
    - ``convert_move_type:normal:to:ice`` → convert only when move is Normal
    - ``convert_move_category:sound:to_type:water`` → sound moves become Water
    """
    effects = get_ability_effects(attacker, db)
    original = _move_type(move)
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 4 and parts[0] == "convert_move_category" and parts[2] == "to_type":
            category = parts[1]
            to_type = parts[3].split("|")[0]
            if category == "sound" and _move_is_sound(move):
                return to_type
            continue
        if len(parts) >= 4 and parts[0] == "convert_move_type" and parts[2] == "to":
            from_type = parts[1]
            to_type = parts[3].split("|")[0]
            if original == from_type:
                return to_type
            continue
        if len(parts) >= 2 and parts[0] == "convert_move_type":
            # Normalize-style: always become the listed type
            return parts[1].split("|")[0]
        if token.lower() == "normalize":
            return "normal"
    return None


def process_aftermath(
    fainted: GameUnit,
    attacker: GameUnit,
    *,
    makes_contact: bool,
    db: Session,
) -> list[str]:
    """Aftermath: damage attacker for 1/4 max HP when KO'd by a contact move."""
    messages: list[str] = []
    if not makes_contact or fainted is None or attacker is None:
        return messages
    if getattr(attacker, "is_fainted", False):
        return messages
    if not ability_has_token(fainted, db, "on_faint_from_contact", "aftermath"):
        return messages
    # Magic Guard blocks Aftermath
    if should_ignore_indirect_damage(attacker, db):
        return messages

    fraction = 4
    for token in get_ability_effects(fainted, db):
        parts = _token_parts(token)
        if (
            len(parts) >= 4
            and parts[0] == "on_faint_from_contact"
            and parts[1] == "attacker"
            and parts[2] == "damage_fraction"
        ):
            try:
                fraction = int(parts[3])
            except (TypeError, ValueError):
                fraction = 4
            break

    max_hp = _max_hp(attacker)
    dmg = max(1, max_hp // fraction) if max_hp > 0 else 0
    if dmg <= 0:
        return messages
    new_hp = max(0, int(attacker.current_hp or 0) - dmg)
    attacker.current_hp = new_hp
    if new_hp <= 0:
        attacker.is_fainted = True
    db.add(attacker)
    name = _unit_display_name(fainted)
    atk_name = _unit_display_name(attacker)
    messages.append(f"{atk_name} was hurt by {name}'s Aftermath!")
    return messages


def process_anger_point(
    defender: GameUnit,
    *,
    was_crit: bool,
    db: Session,
    current_turn: int,
    apply_stat_change: Callable | None = None,
) -> list[str]:
    """Anger Point: max Attack (+6) when hit by a critical hit."""
    messages: list[str] = []
    if not was_crit or defender is None or getattr(defender, "is_fainted", False):
        return messages
    if not ability_has_token(defender, db, "on_crit_received", "anger_point"):
        return messages

    stages = 6
    for token in get_ability_effects(defender, db):
        parts = _token_parts(token)
        if (
            len(parts) >= 5
            and parts[0] == "on_crit_received"
            and parts[1] == "self"
            and parts[2] == "raise_stat"
            and _normalize_stat_name(parts[3]) == "attack"
        ):
            try:
                stages = int(parts[4])
            except (TypeError, ValueError):
                stages = 6
            break

    if apply_stat_change:
        apply_stat_change(defender, "attack", stages, current_turn, db)
    else:
        boosts = getattr(defender, "stat_boosts", None)
        if not isinstance(boosts, dict):
            boosts = {}
        instances = list(boosts.get("attack") or [])
        instances.append({"magnitude": stages, "expires_turn": 4})
        boosts = dict(boosts)
        boosts["attack"] = instances
        defender.stat_boosts = boosts
        db.add(defender)

    name = _unit_display_name(defender)
    messages.append(f"{name}'s Anger Point maxed its Attack!")
    return messages


def process_steadfast(
    unit: GameUnit,
    db: Session,
    current_turn: int,
    apply_stat_change: Callable | None = None,
) -> list[str]:
    """Steadfast: +1 Speed when flinched."""
    messages: list[str] = []
    if unit is None or getattr(unit, "is_fainted", False):
        return messages
    if not ability_has_token(unit, db, "on_flinch", "steadfast"):
        return messages

    stages = 1
    for token in get_ability_effects(unit, db):
        parts = _token_parts(token)
        if (
            len(parts) >= 5
            and parts[0] == "on_flinch"
            and parts[1] == "self"
            and parts[2] == "raise_stat"
            and _normalize_stat_name(parts[3]) == "speed"
        ):
            try:
                stages = int(parts[4])
            except (TypeError, ValueError):
                stages = 1
            break

    if apply_stat_change:
        apply_stat_change(unit, "speed", stages, current_turn, db)
    else:
        boosts = getattr(unit, "stat_boosts", None)
        if not isinstance(boosts, dict):
            boosts = {}
        instances = list(boosts.get("speed") or [])
        instances.append({"magnitude": stages, "expires_turn": 4})
        boosts = dict(boosts)
        boosts["speed"] = instances
        unit.stat_boosts = boosts
        db.add(unit)

    name = _unit_display_name(unit)
    messages.append(f"{name}'s Steadfast raised its Speed!")
    return messages


def mark_unburden(unit: GameUnit, db: Session) -> None:
    """Set Unburden boost flag when a held item is lost."""
    if not ability_has_token(unit, db, "on_item_lost", "unburden"):
        return
    flags = _unit_flags(unit)
    flags["unburden_boost"] = True
    _set_unit_flags(unit, flags, db)


def has_unburden_boost(unit: GameUnit, db: Session) -> bool:
    """True if Unburden is active (item lost, still no item)."""
    if not ability_has_token(unit, db, "on_item_lost", "unburden"):
        return False
    flags = _unit_flags(unit)
    if not flags.get("unburden_boost"):
        return False
    held = flags.get("held_item")
    return not held


def is_klutz(unit: GameUnit, db: Session) -> bool:
    """Klutz suppresses held item effects."""
    return ability_has_token(unit, db, "suppress_held_item", "klutz")


def berry_hp_threshold_percent(unit: GameUnit, db: Session) -> int:
    """Gluttony → 50, else 25."""
    effects = get_ability_effects(unit, db)
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 2 and parts[0] == "berry_threshold":
            try:
                return int(parts[1])
            except (TypeError, ValueError):
                return 50
        if token.lower() == "gluttony":
            return 50
    return 25


def apply_multitype_from_held_item(
    unit: GameUnit,
    db: Session,
    get_held_item_slug: Callable | None = None,
    resolve_item: Callable | None = None,
) -> bool:
    """Multitype: set battle type from held plate's boost_type. Returns True if changed."""
    if not ability_has_token(unit, db, "change_type:held_plate", "multitype"):
        return False
    return _apply_held_item_type_change(unit, db, get_held_item_slug, resolve_item)


def apply_rks_from_held_item(
    unit: GameUnit,
    db: Session,
    get_held_item_slug: Callable | None = None,
    resolve_item: Callable | None = None,
) -> bool:
    """RKS System: set battle type from held memory disc's boost_type."""
    if not ability_has_token(unit, db, "change_type:held_memory", "rks_system"):
        return False
    return _apply_held_item_type_change(unit, db, get_held_item_slug, resolve_item)


def _apply_held_item_type_change(
    unit: GameUnit,
    db: Session,
    get_held_item_slug: Callable | None = None,
    resolve_item: Callable | None = None,
) -> bool:
    """Shared Multitype / RKS type change from held item boost_type."""
    slug = None
    if get_held_item_slug:
        try:
            slug = get_held_item_slug(unit)
        except TypeError:
            slug = get_held_item_slug(unit, db)
    else:
        slug = _unit_flags(unit).get("held_item")

    if not slug:
        return False

    item = None
    if resolve_item:
        try:
            item = resolve_item(slug, db)
        except TypeError:
            item = resolve_item(slug)

    if item is None:
        try:
            from app.db.models import Item

            item = db.query(Item).filter((Item.slug == str(slug)) | (Item.name == str(slug))).first()
        except Exception:
            return False

    boost_type = getattr(item, "boost_type", None) if item is not None else None
    if not boost_type:
        effects = getattr(item, "effects", None) if item is not None else None
        if isinstance(effects, list):
            for eff in effects:
                parts = _token_parts(str(eff))
                if len(parts) >= 2 and parts[0] == "on_move_type":
                    boost_type = parts[1]
                    break
    if not boost_type:
        return False

    new_type = str(boost_type).lower().strip()
    current = get_battle_types(unit, db)
    if current == {new_type}:
        return False
    set_battle_types(unit, [new_type], db)
    return True


def _simple_type_multiplier(move_type: str, defender_types: set[str] | list[str]) -> float:
    """Minimal type chart for Anticipation (avoids importing games.py)."""
    # Subset covering common SE / immunity checks.
    chart: dict[str, dict[str, list[str]]] = {
        "normal": {"immune": ["ghost"], "weak": [], "resist": ["rock", "steel"]},
        "fire": {
            "immune": [],
            "weak": ["grass", "ice", "bug", "steel"],
            "resist": ["fire", "water", "rock", "dragon"],
        },
        "water": {
            "immune": [],
            "weak": ["fire", "ground", "rock"],
            "resist": ["water", "grass", "dragon"],
        },
        "electric": {
            "immune": ["ground"],
            "weak": ["water", "flying"],
            "resist": ["electric", "grass", "dragon"],
        },
        "grass": {
            "immune": [],
            "weak": ["water", "ground", "rock"],
            "resist": ["fire", "grass", "poison", "flying", "bug", "dragon", "steel"],
        },
        "ice": {
            "immune": [],
            "weak": ["grass", "ground", "flying", "dragon"],
            "resist": ["fire", "water", "ice", "steel"],
        },
        "fighting": {
            "immune": ["ghost"],
            "weak": ["normal", "ice", "rock", "dark", "steel"],
            "resist": ["poison", "flying", "psychic", "bug", "fairy"],
        },
        "poison": {
            "immune": ["steel"],
            "weak": ["grass", "fairy"],
            "resist": ["poison", "ground", "rock", "ghost"],
        },
        "ground": {
            "immune": ["flying"],
            "weak": ["fire", "electric", "poison", "rock", "steel"],
            "resist": ["grass", "bug"],
        },
        "flying": {
            "immune": [],
            "weak": ["grass", "fighting", "bug"],
            "resist": ["electric", "rock", "steel"],
        },
        "psychic": {
            "immune": ["dark"],
            "weak": ["fighting", "poison"],
            "resist": ["psychic", "steel"],
        },
        "bug": {
            "immune": [],
            "weak": ["grass", "psychic", "dark"],
            "resist": ["fire", "fighting", "poison", "flying", "ghost", "steel", "fairy"],
        },
        "rock": {
            "immune": [],
            "weak": ["fire", "ice", "flying", "bug"],
            "resist": ["fighting", "ground", "steel"],
        },
        "ghost": {
            "immune": ["normal"],
            "weak": ["psychic", "ghost"],
            "resist": ["dark"],
        },
        "dragon": {
            "immune": ["fairy"],
            "weak": ["dragon"],
            "resist": ["steel"],
        },
        "dark": {
            "immune": [],
            "weak": ["psychic", "ghost"],
            "resist": ["fighting", "dark", "fairy"],
        },
        "steel": {
            "immune": [],
            "weak": ["ice", "rock", "fairy"],
            "resist": ["fire", "water", "electric", "steel"],
        },
        "fairy": {
            "immune": [],
            "weak": ["fighting", "dragon", "dark"],
            "resist": ["fire", "poison", "steel"],
        },
    }
    mt = str(move_type or "").lower().strip()
    entry = chart.get(mt)
    if not entry:
        return 1.0
    mult = 1.0
    for dtype in defender_types or []:
        key = str(dtype).lower()
        if key in entry.get("immune", []):
            return 0.0
        if key in entry.get("weak", []):
            mult *= 2.0
        elif key in entry.get("resist", []):
            mult *= 0.5
    return mult


def blocks_critical_hit(defender: GameUnit, db: Session) -> bool:
    """Battle Armor / Shell Armor."""
    return ability_has_token(defender, db, "immune_crit", "battle_armor", "shell_armor")


def modify_type_multiplier(
    defender: GameUnit,
    move_type: str,
    type_multiplier: float,
    db: Session,
) -> float:
    """Apply ability immunities / Wonder Guard to the type effectiveness multiplier."""
    mt = str(move_type or "").lower().strip()
    effects = get_ability_effects(defender, db)
    if not effects:
        return type_multiplier

    for token in effects:
        parts = _token_parts(token)

        # immune:ground / immune:fire / immune:electric / immune:water
        if len(parts) >= 2 and parts[0] == "immune" and parts[1] == mt:
            return 0.0

        # immune_category:sound handled elsewhere for sound moves
        if len(parts) >= 2 and parts[0] == "immune_category" and parts[1] == "ohko":
            continue

        if parts[0] == "only_super_effective_hits":
            if type_multiplier <= 1.0:
                return 0.0

    return type_multiplier


def handle_type_absorb(
    defender: GameUnit,
    move_type: str,
    db: Session,
    game: Any = None,
    game_state: Any = None,
) -> dict | None:
    """Handle Volt Absorb / Water Absorb / Flash Fire / Lightning Rod / Storm Drain / Motor Drive.

    Returns ``{"absorbed": True, "message": ...}`` when the hit is absorbed,
    else None. Mutates HP / flags / stats as appropriate.
    """
    del game, game_state  # reserved for callers that want log context
    mt = str(move_type or "").lower().strip()
    if not mt:
        return None

    effects = get_ability_effects(defender, db)
    if not effects:
        return None

    name = _unit_display_name(defender)
    ability = get_active_ability(defender, db)
    ability_name = getattr(ability, "name", None) or "ability"

    absorbed = False
    messages: list[str] = []
    raise_stat: tuple[str, int] | None = None

    has_immune = any((_token_parts(t)[:2] == ["immune", mt]) for t in effects)
    if not has_immune:
        return None

    for token in effects:
        parts = _token_parts(token)
        if len(parts) < 4 or parts[0] != "on_hit" or parts[1] != mt:
            continue

        if len(parts) >= 5 and parts[2] == "self" and parts[3] == "heal_fraction":
            try:
                fraction = int(parts[4])
            except (TypeError, ValueError):
                fraction = 4
            max_hp = _max_hp(defender)
            heal = max(1, max_hp // fraction) if max_hp > 0 else 0
            if heal > 0:
                new_hp = min(max_hp, int(defender.current_hp or 0) + heal)
                defender.current_hp = new_hp
                db.add(defender)
            absorbed = True
            messages.append(f"{name}'s {ability_name} restored HP!")
            continue

        if (
            len(parts) >= 5
            and parts[2] == "self"
            and parts[3] == "apply_state"
            and parts[4] in {"flash_fire", "flash_fire_boost"}
        ):
            flags = _unit_flags(defender)
            flags["flash_fire_boost"] = True
            flags["flash_fire"] = True
            _set_unit_flags(defender, flags, db)
            absorbed = True
            messages.append(f"{name}'s {ability_name} raised its Fire power!")
            continue

        if len(parts) >= 6 and parts[2] == "self" and parts[3] == "raise_stat":
            stat = _normalize_stat_name(parts[4])
            try:
                stages = int(parts[5])
            except (TypeError, ValueError):
                stages = 1
            raise_stat = (stat, stages)
            absorbed = True
            messages.append(f"{name}'s {ability_name} raised its {stat.replace('_', ' ')}!")
            continue

    if not absorbed and has_immune:
        has_on_hit = any(_token_parts(t)[:2] == ["on_hit", mt] for t in effects)
        if not has_on_hit:
            return None
        absorbed = True
        messages.append(f"{name}'s {ability_name} made it immune!")

    if absorbed:
        result = {
            "absorbed": True,
            "message": " ".join(messages) if messages else f"{name}'s {ability_name} absorbed the attack!",
            "messages": messages,
        }
        if raise_stat is not None:
            result["raise_stat"] = raise_stat
        return result
    return None


def apply_sturdy(
    defender: GameUnit,
    damage: int,
    was_full_hp: bool,
    is_ohko: bool,
    db: Session,
) -> int:
    """Clamp damage so Sturdy leaves the defender at 1 HP when conditions met."""
    if damage <= 0:
        return 0

    effects = get_ability_effects(defender, db)
    if not effects:
        return damage

    has_sturdy = any(
        t.startswith("endure_ohko_at_full_hp") or t == "sturdy" or "immune_category:ohko" in t
        for t in (e.lower() for e in effects)
    )
    if not has_sturdy:
        return damage

    current_hp = int(getattr(defender, "current_hp", 0) or 0)
    if current_hp <= 0:
        return damage

    if is_ohko:
        if was_full_hp or ability_has_token(defender, db, "immune_category:ohko"):
            return 0

    if was_full_hp and damage >= current_hp:
        return max(0, current_hp - 1)

    return damage


def blocks_ohko(defender: GameUnit, db: Session) -> bool:
    """True if defender's ability blocks OHKO moves (Sturdy)."""
    return ability_has_token(defender, db, "immune_category:ohko", "endure_ohko_at_full_hp", "sturdy")


def blocks_sound_move(defender: GameUnit, db: Session) -> bool:
    """Soundproof: block sound moves (``move_trait`` sound / immune_category:sound)."""
    return ability_has_token(defender, db, "immune_category:sound", "soundproof")


def blocks_explosion(game_id: int, db: Session) -> bool:
    """Damp: prevent Explosion / Self-Destruct style moves anywhere on the field."""
    if not game_id:
        return False
    units = (
        db.query(GameUnit)
        .filter(GameUnit.game_id == game_id, GameUnit.is_fainted.is_(False))
        .all()
    )
    cache: dict = {}
    for unit in units:
        if ability_has_token(unit, db, "suppress_field:explosion", "damp", _cache=cache):
            return True
    return False


def move_is_explosion_like(move: Any) -> bool:
    """True if the move is blocked by Damp."""
    slug = _move_slug(move)
    if slug in EXPLOSION_MOVE_SLUGS:
        return True
    name = str(getattr(move, "name", "") or "").lower().replace(" ", "-")
    if name in EXPLOSION_MOVE_SLUGS or name.replace("-", "_") in EXPLOSION_MOVE_SLUGS:
        return True
    effects = getattr(move, "effects", None)
    if isinstance(effects, list):
        for eff in effects:
            token = str(eff).lower()
            if "explosion" in token or "self-destruct" in token or "self_destruct" in token:
                return True
            if token.startswith("suppress_field:explosion"):
                return True
    return False


# ---------------------------------------------------------------------------
# Accuracy / evasion
# ---------------------------------------------------------------------------


def attacker_accuracy_multiplier(attacker: GameUnit, move: Any, db: Session) -> float:
    """Compound Eyes (+30%), Hustle physical accuracy penalty, Victory Star allies."""
    effects = get_ability_effects(attacker, db)
    mult = 1.0
    category = _move_category(move)

    for token in effects:
        parts = _token_parts(token)

        # self:boost_accuracy:1.3
        if len(parts) >= 3 and parts[0] == "self" and parts[1] == "boost_accuracy":
            try:
                mult *= float(parts[2])
            except (TypeError, ValueError):
                pass
            continue

        # on_move_category:physical:self:boost_accuracy:0.8
        if (
            len(parts) >= 5
            and parts[0] == "on_move_category"
            and parts[2] == "self"
            and parts[3] == "boost_accuracy"
        ):
            if category == parts[1]:
                try:
                    mult *= float(parts[4])
                except (TypeError, ValueError):
                    pass
            continue

    # Victory Star from allies: allies:boost_accuracy
    game_id = getattr(attacker, "game_id", None)
    user_id = getattr(attacker, "user_id", None)
    if isinstance(game_id, int) and user_id is not None:
        allies = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id == user_id,
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        cache: dict = {}
        for ally in allies:
            if getattr(ally, "id", None) == getattr(attacker, "id", None):
                continue
            ally_effects = get_ability_effects(ally, db, _cache=cache)
            for token in ally_effects:
                parts = _token_parts(token)
                if len(parts) >= 3 and parts[0] == "allies" and parts[1] == "boost_accuracy":
                    try:
                        mult *= float(parts[2])
                    except (TypeError, ValueError):
                        pass

    return mult


def wonder_skin_accuracy_multiplier(defender: GameUnit, move: Any, db: Session) -> float:
    """Wonder Skin: halve accuracy threshold of status moves (mainline ~50% max)."""
    if not ability_has_token(defender, db, "self:boost_status_move_evasion", "wonder_skin"):
        return 1.0
    if not _is_status_move(move):
        return 1.0
    return 0.5


def defender_evasion_multiplier(
    defender: GameUnit,
    db: Session,
    *,
    weather_tiles: list | None = None,
) -> float:
    """Sand Veil / Snow Cloak / Tangled Feet evasion multipliers."""
    effects = get_ability_effects(defender, db)
    if not effects:
        return 1.0

    weather_id = _unit_weather_id(defender, weather_tiles)
    # If weather is suppressed globally, treat as clear.
    game_id = getattr(defender, "game_id", None)
    if isinstance(game_id, int) and weather_is_suppressed(game_id, db):
        weather_id = 0

    # Confusion state for Tangled Feet (stored in unit.states, not status_effects)
    states = _normalize_states(getattr(defender, "states", None))
    is_confused = bool(states and str(states[0]).lower() == "confusion" and int(states[1]) > 0)

    mult = 1.0
    for token in effects:
        parts = _token_parts(token)
        # on_weather:sandstorm:self:boost_stat_mult:evasion:1.25
        if (
            len(parts) >= 6
            and parts[0] == "on_weather"
            and parts[2] == "self"
            and parts[3] == "boost_stat_mult"
            and _normalize_stat_name(parts[4]) == "evasion"
        ):
            weather_name = parts[1]
            if weather_id_matches(weather_id, weather_name):
                try:
                    mult *= float(parts[5])
                except (TypeError, ValueError):
                    pass
            continue

        # on_status:confusion:self:boost_stat_mult:evasion:2 (Tangled Feet)
        if (
            len(parts) >= 6
            and parts[0] == "on_status"
            and parts[2] == "self"
            and parts[3] == "boost_stat_mult"
            and _normalize_stat_name(parts[4]) == "evasion"
        ):
            status_cond = parts[1]
            if status_cond == "confusion" and is_confused:
                try:
                    mult *= float(parts[5])
                except (TypeError, ValueError):
                    pass
            elif status_cond != "confusion" and _active_status(defender) == _normalize_status_name(status_cond):
                try:
                    mult *= float(parts[5])
                except (TypeError, ValueError):
                    pass
            continue
    return mult


def ignore_target_evasion(attacker: GameUnit, db: Session) -> bool:
    """Keen Eye / Illuminate."""
    return ability_has_token(attacker, db, "ignore_target_evasion", "keen_eye", "illuminate")


# ---------------------------------------------------------------------------
# Status / state immunities
# ---------------------------------------------------------------------------


def can_apply_status(unit: GameUnit, status: str, db: Session) -> bool:
    """False if the unit's ability (or ally veil) blocks the given status condition."""
    status_n = _normalize_status_name(status)
    if not status_n:
        return False

    effects = get_ability_effects(unit, db)
    weather_tiles = _lookup_unit_weather_tiles(unit, db)
    weather_id = _unit_weather_id(unit, weather_tiles)
    game_id = getattr(unit, "game_id", None)
    if isinstance(game_id, int) and weather_is_suppressed(game_id, db):
        weather_id = 0

    for token in effects:
        parts = _token_parts(token)
        if not parts:
            continue
        if parts[0] == "immune_status" and len(parts) >= 2:
            blocked = _normalize_status_name(parts[1])
            if parts[1] == "all_other":
                # Comatose: block every status except sleep
                if status_n != "sleep":
                    return False
                continue
            if blocked == status_n or blocked == "all":
                return False
            # immunity ability also blocks badly_poisoned via poison token variants
            if status_n == "badly_poisoned" and blocked == "poison":
                return False

        # Leaf Guard: on_weather:sun:immune_status:all
        if (
            len(parts) >= 4
            and parts[0] == "on_weather"
            and parts[2] == "immune_status"
        ):
            if weather_id_matches(weather_id, parts[1]):
                blocked = _normalize_status_name(parts[3])
                if blocked in {"all", status_n}:
                    return False
                if status_n == "badly_poisoned" and blocked == "poison":
                    return False

    # Ally / self veils (Sweet Veil, Aroma Veil, Flower Veil)
    if _ally_veil_blocks_status(unit, status_n, db):
        return False

    return True


def _parse_status_list(raw: str) -> set[str]:
    out: set[str] = set()
    for piece in str(raw or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        out.add(_normalize_status_name(piece) if piece != "all" else "all")
        # Also keep raw state-like names (taunt, etc.)
        out.add(piece.lower())
    return out


def _living_allies_including_self(unit: GameUnit, db: Session) -> list[GameUnit]:
    game_id = getattr(unit, "game_id", None)
    user_id = getattr(unit, "user_id", None)
    if not isinstance(game_id, int) or user_id is None:
        return [unit]
    return (
        db.query(GameUnit)
        .filter(
            GameUnit.game_id == game_id,
            GameUnit.user_id == user_id,
            GameUnit.is_fainted.is_(False),
        )
        .all()
    )


def _ally_veil_blocks_status(unit: GameUnit, status_n: str, db: Session) -> bool:
    """Sweet Veil / Aroma Veil / Flower Veil ally scans."""
    allies = _living_allies_including_self(unit, db)
    unit_types = _default_get_unit_types(unit, db)
    cache: dict = {}
    for ally in allies:
        for token in get_ability_effects(ally, db, _cache=cache):
            parts = _token_parts(token)
            if not parts:
                continue
            # self_and_allies:immune_status:sleep or comma list
            if len(parts) >= 3 and parts[0] == "self_and_allies" and parts[1] == "immune_status":
                blocked = _parse_status_list(parts[2])
                if "all" in blocked or status_n in blocked:
                    return True
                if status_n == "badly_poisoned" and "poison" in blocked:
                    return True
            # grass_allies:immune_status:all (Flower Veil) — grass types only
            if len(parts) >= 3 and parts[0] == "grass_allies" and parts[1] == "immune_status":
                if "grass" not in unit_types:
                    continue
                blocked = _parse_status_list(parts[2])
                if "all" in blocked or status_n in blocked:
                    return True
    return False


def can_apply_state(unit: GameUnit, state: str, db: Session) -> bool:
    """False if ability blocks confusion / flinch / taunt / infatuation."""
    state_n = str(state or "").lower().strip()
    if not state_n:
        return False

    effects = get_ability_effects(unit, db)
    for token in effects:
        parts = _token_parts(token)
        if not parts:
            continue
        if parts[0] == "immune_flinch" and state_n == "flinch":
            return False
        if parts[0] == "immune_status" and len(parts) >= 2:
            blocked = parts[1]
            # own_tempo stores confusion under immune_status
            if blocked == state_n:
                return False
            if blocked == "infatuation" and state_n in {"infatuation", "attract"}:
                return False
        if parts[0] == "immune_intimidate" and state_n == "intimidate":
            return False

    # Aroma Veil / Sweet Veil style ally immunities for states
    allies = _living_allies_including_self(unit, db)
    cache: dict = {}
    for ally in allies:
        for token in get_ability_effects(ally, db, _cache=cache):
            parts = _token_parts(token)
            if len(parts) >= 3 and parts[0] == "self_and_allies" and parts[1] == "immune_status":
                blocked = _parse_status_list(parts[2])
                if state_n in blocked or (state_n in {"infatuation", "attract"} and "infatuation" in blocked):
                    return False
            if len(parts) >= 3 and parts[0] == "grass_allies" and parts[1] == "immune_status":
                if "grass" in _default_get_unit_types(unit, db):
                    blocked = _parse_status_list(parts[2])
                    if "all" in blocked or state_n in blocked:
                        return False
    return True


def immune_to_intimidate(unit: GameUnit, db: Session) -> bool:
    """Inner Focus / Own Tempo / Oblivious, or any ability that blocks Attack drops."""
    if ability_has_token(unit, db, "immune_intimidate"):
        return True
    # Clear Body / White Smoke / Hyper Cutter all block Intimidate's Attack drop.
    return blocks_stat_drop(unit, "attack", db, from_opponent=True)


def secondary_effect_chance_multiplier(attacker: GameUnit, db: Session) -> float:
    """Serene Grace → 2.0."""
    effects = get_ability_effects(attacker, db)
    for token in effects:
        parts = _token_parts(token)
        if (
            len(parts) >= 3
            and parts[0] == "self"
            and parts[1] == "boost_secondary_effect_chance"
        ):
            try:
                return float(parts[2])
            except (TypeError, ValueError):
                return 2.0
        if token.lower() in {"serene_grace", "self:boost_secondary_effect_chance:2"}:
            return 2.0
    return 1.0


def blocks_additional_effects(defender: GameUnit, db: Session) -> bool:
    """Shield Dust."""
    return ability_has_token(defender, db, "immune_additional_effects", "shield_dust")


def reverse_stat_changes(unit: GameUnit, db: Session) -> bool:
    """Contrary: reverse incoming stat changes."""
    return ability_has_token(unit, db, "reverse_stat_changes", "contrary")


def ignores_screens(attacker: GameUnit, db: Session) -> bool:
    """Infiltrator."""
    return ability_has_token(attacker, db, "ignore_screens", "infiltrator")


def ignores_safeguard(attacker: GameUnit, db: Session) -> bool:
    """Infiltrator."""
    return ability_has_token(attacker, db, "ignore_safeguard", "infiltrator")


def ignores_substitute(attacker: GameUnit, db: Session) -> bool:
    """Infiltrator."""
    return ability_has_token(attacker, db, "ignore_substitute", "infiltrator")


def reflects_status_moves(defender: GameUnit, db: Session) -> bool:
    """Magic Bounce."""
    return ability_has_token(defender, db, "reflect_status_moves", "magic_bounce")


def immune_to_ally_attacks(defender: GameUnit, db: Session) -> bool:
    """Telepathy."""
    return ability_has_token(defender, db, "immune_ally_attacks", "telepathy")


def prevents_opponent_berry_eat(unit: GameUnit, db: Session) -> bool:
    """True if this unit's Unnerve prevents opposing berry consumption."""
    return ability_has_token(unit, db, "prevent_opponent_berry_eat", "unnerve")


def opponent_unnerve_blocks_berry(unit: GameUnit, db: Session) -> bool:
    """True if any opposing living unit has Unnerve."""
    game_id = getattr(unit, "game_id", None)
    user_id = getattr(unit, "user_id", None)
    if not isinstance(game_id, int) or user_id is None:
        return False
    opponents = (
        db.query(GameUnit)
        .filter(
            GameUnit.game_id == game_id,
            GameUnit.user_id != user_id,
            GameUnit.is_fainted.is_(False),
        )
        .all()
    )
    cache: dict = {}
    for opp in opponents:
        if prevents_opponent_berry_eat(opp, db) or ability_has_token(
            opp, db, "prevent_opponent_berry_eat", "unnerve", _cache=cache
        ):
            return True
    return False


def status_move_priority_bonus(attacker: GameUnit, db: Session, move: Any | None = None) -> int:
    """Prankster: +1 priority for status moves. Games has no priority sort yet."""
    if move is not None and not _is_status_move(move):
        return 0
    effects = get_ability_effects(attacker, db)
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 2 and parts[0] == "priority_status":
            try:
                return int(parts[1])
            except (TypeError, ValueError):
                return 1
        if token.lower() == "prankster":
            return 1
    return 0


def unit_weight_multiplier(unit: GameUnit, db: Session) -> float:
    """Heavy Metal / Light Metal weight multipliers."""
    effects = get_ability_effects(unit, db)
    mult = 1.0
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 3 and parts[0] == "self" and parts[1] == "boost_weight":
            try:
                mult *= float(parts[2])
            except (TypeError, ValueError):
                pass
    return mult


def sleep_duration_multiplier(unit: GameUnit, db: Session) -> float:
    """Early Bird → 0.5."""
    if ability_has_token(unit, db, "self:halve_sleep_duration", "early_bird"):
        return 0.5
    return 1.0


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def blocks_stat_drop(
    unit: GameUnit,
    stat: str,
    db: Session,
    *,
    from_opponent: bool = True,
) -> bool:
    """Clear Body / White Smoke / Hyper Cutter / Keen Eye / Flower Veil etc."""
    del from_opponent  # Gen 3 Clear Body blocks all drops; reserved for later gens
    stat_n = _normalize_stat_name(stat)
    effects = get_ability_effects(unit, db)
    for token in effects:
        parts = _token_parts(token)
        if not parts:
            continue
        if parts[0] != "immune_stat_drop":
            continue
        if len(parts) == 1:
            return True
        if len(parts) >= 2 and _normalize_stat_name(parts[1]) == stat_n:
            return True

    # Flower Veil: grass allies immune to stat drops
    if "grass" in _default_get_unit_types(unit, db):
        for ally in _living_allies_including_self(unit, db):
            for token in get_ability_effects(ally, db):
                parts = _token_parts(token)
                if len(parts) >= 2 and parts[0] == "grass_allies" and parts[1] == "immune_stat_drop":
                    return True
    return False


def reflects_stat_drops(unit: GameUnit, db: Session) -> bool:
    """Mirror Armor: reflect opponent-caused stat drops onto the source."""
    return ability_has_token(unit, db, "reflect_stat_drops", "mirror_armor")


def modify_effective_stats(
    unit: GameUnit,
    stats: dict,
    db: Session,
    *,
    weather_tiles: list | None = None,
    terrain_tiles: list | None = None,
    ally_units: list[GameUnit] | None = None,
) -> dict:
    """Return a copy of ``stats`` with ability modifiers applied.

    Applies Chlorophyll / Swift Swim speed, Guts attack (+ ignore burn flag),
    Marvel Scale defense, Plus/Minus SpA, Flower Gift, Slow Start, Unburden,
    Quick Feet ignore-paralysis, Grass Pelt. Huge/Pure Power are intended for
    ``attacker_power_multiplier`` at damage time, not here.
    """
    result = dict(stats or {})
    effects = get_ability_effects(unit, db)

    weather_id = _unit_weather_id(unit, weather_tiles)
    game_id = getattr(unit, "game_id", None)
    if isinstance(game_id, int) and weather_is_suppressed(game_id, db):
        weather_id = 0
    if ability_has_token(unit, db, "treat_weather_as:sun", "mega_sol"):
        weather_id = WEATHER_TO_ID["sun"]

    terrain_id = _unit_terrain_id(unit, terrain_tiles, db)
    if isinstance(game_id, int) and terrain_is_suppressed(game_id, db):
        terrain_id = 0

    has_status = _has_any_status(unit)

    allies = ally_units
    if allies is None and isinstance(game_id, int):
        allies = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id == getattr(unit, "user_id", None),
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )

    for token in effects:
        parts = _token_parts(token)

        # self:boost_stat_mult:attack:1.5 (Gorilla Tactics)
        if (
            len(parts) >= 4
            and parts[0] == "self"
            and parts[1] == "boost_stat_mult"
        ):
            stat = _normalize_stat_name(parts[2])
            try:
                boost = float(parts[3])
            except (TypeError, ValueError):
                continue
            if stat in result:
                try:
                    result[stat] = int(float(result[stat]) * boost)
                except (TypeError, ValueError):
                    pass
            continue

        # on_weather:sun:self:boost_stat_mult:speed:2
        if (
            len(parts) >= 6
            and parts[0] == "on_weather"
            and parts[2] == "self"
            and parts[3] == "boost_stat_mult"
        ):
            if weather_id_matches(weather_id, parts[1]):
                stat = _normalize_stat_name(parts[4])
                try:
                    boost = float(parts[5])
                except (TypeError, ValueError):
                    continue
                if stat in result:
                    try:
                        result[stat] = int(float(result[stat]) * boost)
                    except (TypeError, ValueError):
                        pass
            continue

        # on_terrain:grassy:self:boost_stat_mult:defense:1.5 (Grass Pelt)
        if (
            len(parts) >= 6
            and parts[0] == "on_terrain"
            and parts[2] == "self"
            and parts[3] == "boost_stat_mult"
        ):
            expected_terrain = TERRAIN_TO_ID.get(parts[1])
            if expected_terrain is not None and terrain_id == expected_terrain:
                stat = _normalize_stat_name(parts[4])
                try:
                    boost = float(parts[5])
                except (TypeError, ValueError):
                    continue
                if stat in result:
                    try:
                        result[stat] = int(float(result[stat]) * boost)
                    except (TypeError, ValueError):
                        pass
            continue

        # on_status:any:self:boost_stat_mult:attack:1.5
        if (
            len(parts) >= 6
            and parts[0] == "on_status"
            and parts[2] == "self"
            and parts[3] == "boost_stat_mult"
        ):
            status_cond = parts[1]
            if status_cond == "any" and not has_status:
                continue
            if status_cond == "confusion":
                states = _normalize_states(getattr(unit, "states", None))
                if not (states and str(states[0]).lower() == "confusion" and int(states[1]) > 0):
                    continue
            elif status_cond != "any" and _active_status(unit) != _normalize_status_name(status_cond):
                continue
            stat = _normalize_stat_name(parts[4])
            try:
                boost = float(parts[5])
            except (TypeError, ValueError):
                continue
            if stat in result:
                try:
                    result[stat] = int(float(result[stat]) * boost)
                except (TypeError, ValueError):
                    pass
            continue

        # on_hp_below:50:self:boost_stat_mult:attack|spa:0.5 (Defeatist)
        if (
            len(parts) >= 6
            and parts[0] == "on_hp_below"
            and parts[2] == "self"
            and parts[3] == "boost_stat_mult"
        ):
            try:
                threshold = float(parts[1])
                boost = float(parts[5])
            except (TypeError, ValueError):
                continue
            if _hp_percent(unit) > threshold:
                continue
            # Support attack|spa style multi-stat tokens
            for stat_raw in parts[4].split("|"):
                stat = _normalize_stat_name(stat_raw)
                if stat in result:
                    try:
                        result[stat] = int(float(result[stat]) * boost)
                    except (TypeError, ValueError):
                        pass
            continue

        # on_hp_below:50:change_forme:zen (Zen Mode — best-effort)
        if (
            len(parts) >= 4
            and parts[0] == "on_hp_below"
            and parts[2] == "change_forme"
        ):
            try:
                threshold = float(parts[1])
            except (TypeError, ValueError):
                threshold = 50.0
            flags = _unit_flags(unit)
            if _hp_percent(unit) <= threshold:
                if flags.get("forme") != parts[3]:
                    flags["forme"] = parts[3]
                    _set_unit_flags(unit, flags, db)
            elif flags.get("forme") == parts[3] and not ability_has_token(
                unit, db, "on_hp_above"
            ):
                flags.pop("forme", None)
                _set_unit_flags(unit, flags, db)
            continue

        # on_hp_above:25:change_forme:school (Schooling / Shields Down)
        if (
            len(parts) >= 4
            and parts[0] == "on_hp_above"
            and parts[2] == "change_forme"
        ):
            try:
                threshold = float(parts[1])
            except (TypeError, ValueError):
                threshold = 50.0
            flags = _unit_flags(unit)
            if _hp_percent(unit) > threshold:
                if flags.get("forme") != parts[3]:
                    flags["forme"] = parts[3]
                    _set_unit_flags(unit, flags, db)
            continue

        # ignore_burn_attack_halve — signal via flag for games.py burn handling
        if parts[0] == "ignore_burn_attack_halve":
            result["_ignore_burn_attack_halve"] = True
            continue

        # ignore_paralysis_speed_halve — Quick Feet
        if parts[0] == "ignore_paralysis_speed_halve":
            result["_ignore_paralysis_speed_halve"] = True
            continue

        # on_ally_ability:plus_or_minus:self:boost_stat_mult:special_attack:1.5
        if (
            len(parts) >= 6
            and parts[0] == "on_ally_ability"
            and parts[2] == "self"
            and parts[3] == "boost_stat_mult"
        ):
            if parts[1] != "plus_or_minus":
                continue
            ally_match = False
            cache: dict = {}
            for ally in allies or []:
                if getattr(ally, "id", None) == getattr(unit, "id", None):
                    continue
                if ability_has_token(ally, db, "on_ally_ability:plus_or_minus", "plus", "minus", _cache=cache):
                    ally_match = True
                    break
            if ally_match:
                stat = _normalize_stat_name(parts[4])
                try:
                    boost = float(parts[5])
                except (TypeError, ValueError):
                    continue
                if stat in result:
                    try:
                        result[stat] = int(float(result[stat]) * boost)
                    except (TypeError, ValueError):
                        pass

    # Flower Gift from allies: on_weather:sun:allies:boost_stat_mult:...
    cache_fg: dict = {}
    for ally in allies or []:
        if getattr(ally, "id", None) == getattr(unit, "id", None):
            continue
        ally_effects = get_ability_effects(ally, db, _cache=cache_fg)
        for token in ally_effects:
            parts = _token_parts(token)
            if (
                len(parts) >= 6
                and parts[0] == "on_weather"
                and parts[2] == "allies"
                and parts[3] == "boost_stat_mult"
            ):
                if not weather_id_matches(weather_id, parts[1]):
                    continue
                # Ally's tile weather should also be sun; use unit's weather_id
                # (field weather is typically uniform).
                stat = _normalize_stat_name(parts[4])
                try:
                    boost = float(parts[5])
                except (TypeError, ValueError):
                    continue
                if stat in result:
                    try:
                        result[stat] = int(float(result[stat]) * boost)
                    except (TypeError, ValueError):
                        pass

    # Slow Start: halve Attack and Speed while remaining turns > 0
    flags = _unit_flags(unit)
    slow_remaining = flags.get("slow_start_remaining")
    try:
        slow_remaining = int(slow_remaining) if slow_remaining is not None else 0
    except (TypeError, ValueError):
        slow_remaining = 0
    states = _normalize_states(getattr(unit, "states", None))
    if states and str(states[0]).lower() == "slow_start" and int(states[1]) > 0:
        slow_remaining = max(slow_remaining, int(states[1]))
    if slow_remaining > 0:
        for stat in ("attack", "speed"):
            if stat in result:
                try:
                    result[stat] = int(float(result[stat]) * 0.5)
                except (TypeError, ValueError):
                    pass

    # Unburden: double Speed when boost flag set and no held item
    if has_unburden_boost(unit, db) and "speed" in result:
        try:
            result["speed"] = int(float(result["speed"]) * 2)
        except (TypeError, ValueError):
            pass

    # Zen Mode (partial): slight SpA boost while forme=zen for UI/tactics distinction
    if _unit_flags(unit).get("forme") == "zen" and "sp_attack" in result:
        try:
            result["sp_attack"] = int(float(result["sp_attack"]) * 1.5)
        except (TypeError, ValueError):
            pass

    # Protosynthesis / Quark Drive: boost highest stat
    proto_boost = _protosynthesis_or_quark_boost(unit, db, weather_id=weather_id, terrain_id=terrain_id)
    if proto_boost:
        stat, mult_v = proto_boost
        if stat in result:
            try:
                result[stat] = int(float(result[stat]) * mult_v)
            except (TypeError, ValueError):
                pass

    # Ruin abilities: field_others:boost_stat_mult:STAT:0.75 (from OTHER living units)
    if isinstance(game_id, int):
        cache_ruin: dict = {}
        others = (
            db.query(GameUnit)
            .filter(GameUnit.game_id == game_id, GameUnit.is_fainted.is_(False))
            .all()
        )
        for other in others:
            if getattr(other, "id", None) == getattr(unit, "id", None):
                continue
            for token in get_ability_effects(other, db, _cache=cache_ruin):
                parts = _token_parts(token)
                if not (
                    len(parts) >= 4
                    and parts[0] == "field_others"
                    and parts[1] == "boost_stat_mult"
                ):
                    continue
                stat = _normalize_stat_name(parts[2])
                try:
                    boost = float(parts[3])
                except (TypeError, ValueError):
                    continue
                if stat in result:
                    try:
                        result[stat] = int(float(result[stat]) * boost)
                    except (TypeError, ValueError):
                        pass

    return result

# ---------------------------------------------------------------------------
# Contact / after-hit
# ---------------------------------------------------------------------------


def process_contact_abilities(
    attacker: GameUnit,
    defender: GameUnit,
    *,
    makes_contact: bool,
    damage: int,
    db: Session,
    game: Any = None,
    game_state: Any = None,
    helpers: dict | None = None,
) -> list[str]:
    """Resolve Rough Skin / Static / Flame Body / Poison Point / Effect Spore / Cute Charm.

    Returns log message strings. Applies HP/status mutations to attacker when triggered.
    """
    helpers = helpers or {}
    apply_status: Callable | None = helpers.get("apply_status_effect")
    messages: list[str] = []
    if not makes_contact or damage <= 0:
        return messages
    if attacker is None or defender is None:
        return messages
    if getattr(attacker, "is_fainted", False) or getattr(defender, "is_fainted", False):
        return messages

    effects = get_ability_effects(defender, db)
    if not effects:
        return messages

    def_name = _unit_display_name(defender)
    atk_name = _unit_display_name(attacker)
    ability = get_active_ability(defender, db)
    ability_name = getattr(ability, "name", None) or "ability"

    for token in effects:
        parts = _token_parts(token)
        if len(parts) < 2 or parts[0] != "on_contact":
            continue

        # on_contact:swap_abilities (Wandering Spirit)
        if len(parts) >= 2 and parts[1] == "swap_abilities":
            atk_aid = _get_unit_ability_id(attacker)
            def_aid = _get_unit_ability_id(defender)
            if atk_aid is None and def_aid is None:
                continue
            aflags = _unit_flags(attacker)
            dflags = _unit_flags(defender)
            if def_aid is not None:
                aflags["ability_id"] = int(def_aid)
            else:
                aflags.pop("ability_id", None)
            if atk_aid is not None:
                dflags["ability_id"] = int(atk_aid)
            else:
                dflags.pop("ability_id", None)
            _set_unit_flags(attacker, aflags, db)
            _set_unit_flags(defender, dflags, db)
            messages.append(
                f"{atk_name} and {def_name} swapped Abilities from {ability_name}!"
            )
            continue

        # on_contact:both:apply_state:perish:3 (Perish Body)
        if (
            len(parts) >= 5
            and parts[1] == "both"
            and parts[2] == "apply_state"
        ):
            state_name = parts[3]
            try:
                duration = int(parts[4])
            except (TypeError, ValueError):
                duration = 3
            apply_state = helpers.get("apply_state_effect")
            for subject, subject_name in ((attacker, atk_name), (defender, def_name)):
                if subject is None or getattr(subject, "is_fainted", False):
                    continue
                states = _normalize_states(getattr(subject, "states", None))
                if states and str(states[0]).lower() == state_name and int(states[1]) > 0:
                    continue
                applied = False
                if apply_state:
                    try:
                        applied = bool(apply_state(subject, state_name, db, duration=duration))
                    except TypeError:
                        try:
                            applied = bool(apply_state(subject, state_name, db))
                        except TypeError:
                            applied = False
                if not applied:
                    states = _normalize_states(getattr(subject, "states", None))
                    if states and int(states[1]) > 0:
                        continue
                    subject.states = [state_name, duration]
                    db.add(subject)
                    applied = True
                if applied:
                    messages.append(
                        f"{subject_name} will perish in {duration} turns from {ability_name}!"
                    )
            continue

        # on_contact:attacker:...
        if len(parts) < 3 or parts[1] != "attacker":
            continue

        # on_contact:attacker:damage_fraction:8  (Rough Skin)
        if len(parts) >= 4 and parts[2] == "damage_fraction":
            try:
                fraction = int(parts[3])
            except (TypeError, ValueError):
                fraction = 8
            max_hp = _max_hp(attacker)
            dmg = max(1, max_hp // fraction) if max_hp > 0 else 0
            if dmg > 0:
                new_hp = max(0, int(attacker.current_hp or 0) - dmg)
                attacker.current_hp = new_hp
                if new_hp <= 0:
                    attacker.is_fainted = True
                db.add(attacker)
                messages.append(f"{atk_name} was hurt by {def_name}'s {ability_name}!")
            continue

        # on_contact:attacker:lower_stat:speed:1 (Gooey)
        if len(parts) >= 5 and parts[2] == "lower_stat":
            stat = _normalize_stat_name(parts[3])
            try:
                stages = int(parts[4])
            except (TypeError, ValueError):
                stages = 1
            apply_stat = helpers.get("apply_stat_change")
            if apply_stat:
                try:
                    apply_stat(attacker, stat, -abs(stages), helpers.get("current_turn", 1), db, from_opponent=True)
                except TypeError:
                    try:
                        apply_stat(attacker, stat, -abs(stages), helpers.get("current_turn", 1), db)
                    except TypeError:
                        apply_stat(attacker, stat, -abs(stages), 1, db)
            else:
                boosts = getattr(attacker, "stat_boosts", None)
                if not isinstance(boosts, dict):
                    boosts = {}
                instances = list(boosts.get(stat) or [])
                instances.append({"magnitude": -abs(stages), "expires_turn": 4})
                boosts = dict(boosts)
                boosts[stat] = instances
                attacker.stat_boosts = boosts
                db.add(attacker)
            messages.append(
                f"{atk_name}'s {stat.replace('_', ' ')} fell from {def_name}'s {ability_name}!"
            )
            continue

        # on_contact:attacker:status:STATUS:CHANCE[:opposite_gender]
        if len(parts) >= 5 and parts[2] == "status":
            status_spec = parts[3]
            try:
                chance = int(parts[4])
            except (TypeError, ValueError):
                chance = 30

            require_opposite = "opposite_gender" in parts[5:]

            if require_opposite:
                g1 = _get_unit_gender(attacker)
                g2 = _get_unit_gender(defender)
                if not g1 or not g2:
                    continue  # no gender model — skip Cute Charm
                if g1 == g2 or g1 == "genderless" or g2 == "genderless":
                    continue

            if random.randint(1, 100) > chance:
                continue

            # Effect Spore: poison_or_sleep_or_paralysis
            if "or" in status_spec:
                options = [s.strip() for s in status_spec.split("_or_")]
                # Also handle poison_or_sleep_or_paralysis tokenized without extra underscores issues
                if status_spec == "poison_or_sleep_or_paralysis":
                    options = ["poison", "sleep", "paralysis"]
                status_choice = random.choice(options) if options else None
            else:
                status_choice = status_spec

            if not status_choice:
                continue

            if status_choice in {"infatuation", "attract"}:
                # Store as a state-like flag; games.py may promote to proper state.
                flags = _unit_flags(attacker)
                flags["infatuated_with"] = getattr(defender, "id", None)
                _set_unit_flags(attacker, flags, db)
                messages.append(f"{atk_name} fell in love from {def_name}'s {ability_name}!")
                continue

            status_n = _normalize_status_name(status_choice)
            if not can_apply_status(attacker, status_n, db):
                continue
            if _has_any_status(attacker):
                continue

            applied = False
            if apply_status:
                try:
                    applied = bool(
                        apply_status(
                            attacker,
                            status_n,
                            db,
                            source=defender,
                            game=game,
                            game_state=game_state,
                        )
                    )
                except TypeError:
                    applied = bool(apply_status(attacker, status_n, db))
            else:
                duration = random.randint(2, 4) if status_n in {"sleep", "frozen"} else random.randint(4, 7)
                attacker.status_effects = [status_n, duration]
                db.add(attacker)
                applied = True

            if applied:
                messages.append(
                    f"{def_name}'s {ability_name} inflicted {status_n.replace('_', ' ')} on {atk_name}!"
                )
            continue

        # on_contact:attacker:set_ability:mummy (Mummy)
        if len(parts) >= 4 and parts[2] == "set_ability":
            ability_slug = parts[3]
            mummy_row = (
                db.query(Ability)
                .filter(Ability.slug == ability_slug)
                .first()
            )
            if mummy_row is None:
                mummy_row = ability  # fall back to defender's ability row
            if mummy_row is not None:
                flags = _unit_flags(attacker)
                flags["ability_id"] = int(mummy_row.id)
                _set_unit_flags(attacker, flags, db)
                messages.append(
                    f"{atk_name}'s Ability became {getattr(mummy_row, 'name', None) or ability_slug}!"
                )
            continue

    # Pickpocket: on_contact:self:steal_item (token target is defender/self)
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_contact"
            and parts[1] == "self"
            and parts[2] == "steal_item"
        ):
            continue
        get_held = helpers.get("get_unit_held_item")
        set_held = helpers.get("set_unit_held_item")
        def_item = None
        atk_item = None
        if get_held:
            def_item = get_held(defender)
            atk_item = get_held(attacker)
        else:
            def_item = _unit_flags(defender).get("held_item")
            atk_item = _unit_flags(attacker).get("held_item")
        if def_item or not atk_item:
            continue
        if blocks_item_removal(attacker, db):
            continue
        if set_held:
            set_held(defender, atk_item, db)
            set_held(attacker, None, db)
        else:
            dflags = _unit_flags(defender)
            aflags = _unit_flags(attacker)
            dflags["held_item"] = atk_item
            aflags.pop("held_item", None)
            _set_unit_flags(defender, dflags, db)
            _set_unit_flags(attacker, aflags, db)
        messages.append(f"{def_name} stole {atk_name}'s item with {ability_name}!")

    return messages


def process_attacker_contact_on_hit(
    attacker: GameUnit,
    defender: GameUnit,
    *,
    makes_contact: bool,
    damage: int,
    db: Session,
    game: Any = None,
    game_state: Any = None,
    helpers: dict | None = None,
) -> list[str]:
    """Attacker-side contact abilities (Poison Touch)."""
    helpers = helpers or {}
    apply_status: Callable | None = helpers.get("apply_status_effect")
    messages: list[str] = []
    if not makes_contact or damage <= 0:
        return messages
    if attacker is None or defender is None:
        return messages
    if getattr(attacker, "is_fainted", False) or getattr(defender, "is_fainted", False):
        return messages

    effects = get_ability_effects(attacker, db)
    if not effects:
        return messages

    atk_name = _unit_display_name(attacker)
    def_name = _unit_display_name(defender)
    ability = get_active_ability(attacker, db)
    ability_name = getattr(ability, "name", None) or "ability"

    for token in effects:
        parts = _token_parts(token)
        # on_contact_deal:target:status:poison:30
        if not (
            len(parts) >= 5
            and parts[0] == "on_contact_deal"
            and parts[1] == "target"
            and parts[2] == "status"
        ):
            continue
        status_spec = parts[3]
        try:
            chance = int(parts[4])
        except (TypeError, ValueError):
            chance = 30
        if random.randint(1, 100) > chance:
            continue
        status_n = _normalize_status_name(status_spec)
        if not can_apply_status(defender, status_n, db):
            continue
        if _has_any_status(defender):
            continue
        applied = False
        if apply_status:
            try:
                applied = bool(
                    apply_status(
                        defender,
                        status_n,
                        db,
                        source=attacker,
                        game=game,
                        game_state=game_state,
                    )
                )
            except TypeError:
                applied = bool(apply_status(defender, status_n, db))
        else:
            duration = random.randint(4, 7)
            defender.status_effects = [status_n, duration]
            db.add(defender)
            applied = True
        if applied:
            messages.append(
                f"{atk_name}'s {ability_name} poisoned {def_name}!"
                if status_n == "poison"
                else f"{atk_name}'s {ability_name} inflicted {status_n.replace('_', ' ')} on {def_name}!"
            )
    return messages


def process_defender_hit_reactions(
    attacker: GameUnit,
    defender: GameUnit,
    move: Any,
    *,
    damage: int,
    move_type: str,
    is_physical: bool,
    was_crit: bool,
    db: Session,
    current_turn: int,
    helpers: dict | None = None,
    before_hp: int | None = None,
) -> list[str]:
    """Justified / Rattled / Weak Armor / Cursed Body / Stamina / Berserk after taking damage."""
    del was_crit  # reserved
    helpers = helpers or {}
    apply_stat: Callable | None = helpers.get("apply_stat_change")
    apply_state: Callable | None = helpers.get("apply_state_effect")
    messages: list[str] = []
    if damage <= 0 or defender is None or getattr(defender, "is_fainted", False):
        return messages

    effects = get_ability_effects(defender, db)
    if not effects:
        return messages

    def_name = _unit_display_name(defender)
    atk_name = _unit_display_name(attacker) if attacker else "foe"
    ability = get_active_ability(defender, db)
    ability_name = getattr(ability, "name", None) or "ability"
    mt = str(move_type or _move_type(move) or "").lower()

    def _raise(stat: str, stages: int) -> None:
        if apply_stat:
            try:
                apply_stat(defender, stat, stages, current_turn, db)
            except TypeError:
                apply_stat(defender, stat, stages, current_turn, db)
        else:
            boosts = getattr(defender, "stat_boosts", None)
            if not isinstance(boosts, dict):
                boosts = {}
            instances = list(boosts.get(stat) or [])
            instances.append({"magnitude": stages, "expires_turn": 4})
            boosts = dict(boosts)
            boosts[stat] = instances
            defender.stat_boosts = boosts
            db.add(defender)

    for token in effects:
        parts = _token_parts(token)

        # on_hit_type:dark:self:raise_stat:attack:1 (Justified / Rattled)
        if (
            len(parts) >= 6
            and parts[0] == "on_hit_type"
            and parts[2] == "self"
            and parts[3] == "raise_stat"
        ):
            if mt != parts[1]:
                continue
            stat = _normalize_stat_name(parts[4])
            try:
                stages = int(parts[5])
            except (TypeError, ValueError):
                stages = 1
            _raise(stat, stages)
            messages.append(
                f"{def_name}'s {ability_name} raised its {stat.replace('_', ' ')}!"
            )
            continue

        # on_hit_category:physical:self:lower_stat / raise_stat (Weak Armor)
        if (
            len(parts) >= 6
            and parts[0] == "on_hit_category"
            and parts[2] == "self"
            and parts[3] in {"lower_stat", "raise_stat"}
        ):
            if parts[1] == "physical" and not is_physical:
                continue
            if parts[1] == "special" and is_physical:
                continue
            stat = _normalize_stat_name(parts[4])
            try:
                stages = int(parts[5])
            except (TypeError, ValueError):
                stages = 1
            magnitude = -abs(stages) if parts[3] == "lower_stat" else abs(stages)
            _raise(stat, magnitude)
            verb = "lowered" if magnitude < 0 else "raised"
            messages.append(
                f"{def_name}'s {ability_name} {verb} its {stat.replace('_', ' ')}!"
            )
            continue

        # on_damage_taken:self:raise_stat:defense:1 (Stamina)
        if (
            len(parts) >= 5
            and parts[0] == "on_damage_taken"
            and parts[1] == "self"
            and parts[2] == "raise_stat"
        ):
            stat = _normalize_stat_name(parts[3])
            try:
                stages = int(parts[4])
            except (TypeError, ValueError):
                stages = 1
            _raise(stat, stages)
            messages.append(
                f"{def_name}'s {ability_name} raised its {stat.replace('_', ' ')}!"
            )
            continue

        # on_hp_cross_below:50:self:raise_stat|lower_stat:... (Berserk / Anger Shell)
        if (
            len(parts) >= 6
            and parts[0] == "on_hp_cross_below"
            and parts[2] == "self"
            and parts[3] in {"raise_stat", "lower_stat"}
        ):
            try:
                threshold = float(parts[1])
                stages = int(parts[5])
            except (TypeError, ValueError):
                continue
            max_hp = _max_hp(defender)
            if max_hp <= 0 or before_hp is None:
                continue
            after_hp = int(defender.current_hp or 0)
            threshold_hp = max_hp * (threshold / 100.0)
            if before_hp > threshold_hp and after_hp <= threshold_hp:
                stat = _normalize_stat_name(parts[4])
                magnitude = -abs(stages) if parts[3] == "lower_stat" else abs(stages)
                _raise(stat, magnitude)
                verb = "lowered" if magnitude < 0 else "raised"
                messages.append(
                    f"{def_name}'s {ability_name} {verb} its {stat.replace('_', ' ')}!"
                )
            continue

        # on_damage_taken:attacker:apply_state:disable:30 (Cursed Body)
        if (
            len(parts) >= 5
            and parts[0] == "on_damage_taken"
            and parts[1] == "attacker"
            and parts[2] == "apply_state"
        ):
            if attacker is None or getattr(attacker, "is_fainted", False):
                continue
            state_name = parts[3]
            try:
                chance = int(parts[4]) if len(parts) >= 5 else 30
            except (TypeError, ValueError):
                chance = 30
            if random.randint(1, 100) > chance:
                continue
            applied = False
            if apply_state:
                try:
                    applied = bool(apply_state(attacker, state_name, db))
                except TypeError:
                    applied = False
            else:
                states = _normalize_states(getattr(attacker, "states", None))
                if not (states and int(states[1]) > 0):
                    attacker.states = [state_name, 4]
                    db.add(attacker)
                    applied = True
            if applied and state_name == "disable":
                move_id = getattr(move, "id", None)
                if move_id is not None:
                    flags = _unit_flags(attacker)
                    flags["disabled_move_id"] = int(move_id)
                    _set_unit_flags(attacker, flags, db)
                messages.append(
                    f"{atk_name}'s {getattr(move, 'name', None) or 'move'} was disabled by {def_name}'s {ability_name}!"
                )
            elif applied:
                messages.append(
                    f"{atk_name} was affected by {def_name}'s {ability_name}!"
                )
            continue

        # on_damage_taken:others:lower_stat:speed:1 (Cotton Down)
        if (
            len(parts) >= 5
            and parts[0] == "on_damage_taken"
            and parts[1] == "others"
            and parts[2] == "lower_stat"
        ):
            stat = _normalize_stat_name(parts[3])
            try:
                stages = int(parts[4])
            except (TypeError, ValueError):
                stages = 1
            magnitude = -abs(stages)
            game_id = getattr(defender, "game_id", None)
            if not isinstance(game_id, int):
                continue
            others = (
                db.query(GameUnit)
                .filter(
                    GameUnit.game_id == game_id,
                    GameUnit.is_fainted.is_(False),
                    GameUnit.id != getattr(defender, "id", None),
                )
                .all()
            )
            for other in others:
                if apply_stat:
                    try:
                        apply_stat(
                            other,
                            stat,
                            magnitude,
                            current_turn,
                            db,
                            from_opponent=True,
                            source=defender,
                        )
                    except TypeError:
                        try:
                            apply_stat(other, stat, magnitude, current_turn, db, from_opponent=True)
                        except TypeError:
                            apply_stat(other, stat, magnitude, current_turn, db)
                else:
                    boosts = getattr(other, "stat_boosts", None)
                    if not isinstance(boosts, dict):
                        boosts = {}
                    instances = list(boosts.get(stat) or [])
                    instances.append({"magnitude": magnitude, "expires_turn": 4})
                    boosts = dict(boosts)
                    boosts[stat] = instances
                    other.stat_boosts = boosts
                    db.add(other)
            messages.append(
                f"{def_name}'s {ability_name} lowered other Pokémon's {stat.replace('_', ' ')}!"
            )
            continue

        # on_damage_taken:weather:sandstorm (Sand Spit)
        if (
            len(parts) >= 3
            and parts[0] == "on_damage_taken"
            and parts[1] == "weather"
        ):
            weather_name = parts[2]
            map_state = helpers.get("map_state")
            set_weather = helpers.get("set_weather_on_map") or set_weather_on_map
            if map_state is not None and weather_name in WEATHER_TO_ID:
                set_weather(map_state, weather_name)
                try:
                    db.add(map_state)
                except Exception:
                    pass
                messages.append(
                    f"{def_name}'s {ability_name} whipped up a sandstorm!"
                )
            continue

        # on_damage_taken:terrain:grassy (Seed Sower)
        if (
            len(parts) >= 3
            and parts[0] == "on_damage_taken"
            and parts[1] == "terrain"
        ):
            terrain_name = parts[2]
            map_state = helpers.get("map_state")
            if map_state is not None and terrain_name in TERRAIN_TO_ID:
                set_terrain_on_map(map_state, terrain_name, duration=TERRAIN_DEFAULT_DURATION)
                try:
                    db.add(map_state)
                except Exception:
                    pass
                messages.append(
                    f"{def_name}'s {ability_name} created {terrain_name} terrain!"
                )
            continue

        # on_damage_taken:self:apply_state:charge (Electromorphosis)
        if (
            len(parts) >= 4
            and parts[0] == "on_damage_taken"
            and parts[1] == "self"
            and parts[2] == "apply_state"
        ):
            state_name = parts[3]
            applied = False
            if apply_state:
                try:
                    applied = bool(apply_state(defender, state_name, db))
                except TypeError:
                    applied = False
            if not applied:
                states = _normalize_states(getattr(defender, "states", None))
                if not (states and int(states[1]) > 0):
                    defender.states = [state_name, 2]
                    db.add(defender)
                    applied = True
            if applied:
                messages.append(
                    f"{def_name}'s {ability_name} charged it with power!"
                )
            continue

        # on_damage_taken:attacker:status:burn (Spicy Spray)
        if (
            len(parts) >= 4
            and parts[0] == "on_damage_taken"
            and parts[1] == "attacker"
            and parts[2] == "status"
        ):
            if attacker is None or getattr(attacker, "is_fainted", False):
                continue
            status_n = _normalize_status_name(parts[3])
            apply_status = helpers.get("apply_status_effect")
            if not can_apply_status(attacker, status_n, db):
                continue
            if _has_any_status(attacker):
                continue
            applied = False
            if apply_status:
                try:
                    applied = bool(
                        apply_status(attacker, status_n, db, source=defender)
                    )
                except TypeError:
                    applied = bool(apply_status(attacker, status_n, db))
            else:
                attacker.status_effects = [status_n, random.randint(4, 7)]
                db.add(attacker)
                applied = True
            if applied:
                messages.append(
                    f"{atk_name} was burned by {def_name}'s {ability_name}!"
                    if status_n == "burn"
                    else f"{atk_name} was afflicted by {def_name}'s {ability_name}!"
                )
            continue

        # on_hit_category:wind:self:apply_state|raise_stat (Wind Power / Wind Rider)
        if (
            len(parts) >= 5
            and parts[0] == "on_hit_category"
            and parts[1] == "wind"
            and parts[2] == "self"
        ):
            if not _move_is_wind(move):
                continue
            if parts[3] == "apply_state" and len(parts) >= 5:
                state_name = parts[4]
                applied = False
                if apply_state:
                    try:
                        applied = bool(apply_state(defender, state_name, db))
                    except TypeError:
                        applied = False
                if not applied:
                    states = _normalize_states(getattr(defender, "states", None))
                    if not (states and int(states[1]) > 0):
                        defender.states = [state_name, 2]
                        db.add(defender)
                        applied = True
                if applied:
                    messages.append(f"{def_name}'s {ability_name} charged it with power!")
            elif parts[3] == "raise_stat" and len(parts) >= 6:
                stat = _normalize_stat_name(parts[4])
                try:
                    stages = int(parts[5])
                except (TypeError, ValueError):
                    stages = 1
                _raise(stat, stages)
                messages.append(
                    f"{def_name}'s {ability_name} raised its {stat.replace('_', ' ')}!"
                )
            continue

        # on_hit_category:physical:field_hazard:toxic_spikes:opponent_side (Toxic Debris)
        if (
            len(parts) >= 5
            and parts[0] == "on_hit_category"
            and parts[3] == "field_hazard"
        ):
            cat = parts[1]
            if cat == "physical" and not is_physical:
                continue
            if cat == "special" and is_physical:
                continue
            hazard_name = parts[4]
            place_hazard = helpers.get("place_field_hazard")
            if callable(place_hazard):
                try:
                    place_hazard(defender, hazard_name, "opponent_side", db)
                    messages.append(
                        f"{def_name}'s {ability_name} scattered {hazard_name.replace('_', ' ')}!"
                    )
                except TypeError:
                    pass
            else:
                flags = _unit_flags(defender)
                flags["pending_hazard"] = hazard_name
                _set_unit_flags(defender, flags, db)
                messages.append(
                    f"{def_name}'s {ability_name} scattered {hazard_name.replace('_', ' ')}!"
                )
            continue

    return messages


def process_on_ko(
    attacker: GameUnit,
    fainted: GameUnit,
    db: Session,
    current_turn: int,
    helpers: dict | None = None,
) -> list[str]:
    """Moxie / Beast Boost / Battle Bond when knocking out a target."""
    helpers = helpers or {}
    apply_stat: Callable | None = helpers.get("apply_stat_change")
    messages: list[str] = []
    if attacker is None or fainted is None:
        return messages
    if getattr(attacker, "is_fainted", False):
        return messages
    if getattr(attacker, "user_id", None) == getattr(fainted, "user_id", None):
        return messages

    effects = get_ability_effects(attacker, db)
    atk_name = _unit_display_name(attacker)
    ability = get_active_ability(attacker, db)
    ability_name = getattr(ability, "name", None) or "ability"

    for token in effects:
        parts = _token_parts(token)
        # on_ko:change_forme:ash (Battle Bond)
        if len(parts) >= 3 and parts[0] == "on_ko" and parts[1] == "change_forme":
            flags = _unit_flags(attacker)
            flags["forme"] = parts[2]
            flags["battle_bond_ash"] = True
            _set_unit_flags(attacker, flags, db)
            messages.append(f"{atk_name}'s {ability_name} transformed it!")
            continue
        if not (
            len(parts) >= 5
            and parts[0] == "on_ko"
            and parts[1] == "self"
            and parts[2] == "raise_stat"
        ):
            continue
        raw_stat = parts[3]
        if raw_stat == "highest":
            stat = _highest_battle_stat(attacker)
        else:
            stat = _normalize_stat_name(raw_stat)
        try:
            stages = int(parts[4])
        except (TypeError, ValueError):
            stages = 1
        if apply_stat:
            try:
                apply_stat(attacker, stat, stages, current_turn, db)
            except TypeError:
                apply_stat(attacker, stat, stages, current_turn, db)
        else:
            boosts = getattr(attacker, "stat_boosts", None)
            if not isinstance(boosts, dict):
                boosts = {}
            instances = list(boosts.get(stat) or [])
            instances.append({"magnitude": stages, "expires_turn": 4})
            boosts = dict(boosts)
            boosts[stat] = instances
            attacker.stat_boosts = boosts
            db.add(attacker)
        messages.append(
            f"{atk_name}'s {ability_name} raised its {stat.replace('_', ' ')}!"
        )
    return messages


def _highest_battle_stat(unit: GameUnit) -> str:
    """Pick highest among attack/defense/spa/spd/speed from current_stats (Beast Boost)."""
    stats = getattr(unit, "current_stats", None) or {}
    best = "attack"
    best_val = -1
    for stat in BEAST_BOOST_STATS:
        try:
            val = int(stats.get(stat, 0) or 0)
        except (TypeError, ValueError):
            val = 0
        if val > best_val:
            best_val = val
            best = stat
    return best


def clear_illusion_on_damage(defender: GameUnit, damage: int, db: Session) -> bool:
    """Break Illusion disguise when damage is taken."""
    if damage <= 0:
        return False
    flags = _unit_flags(defender)
    if "illusion_of" not in flags:
        return False
    flags.pop("illusion_of", None)
    _set_unit_flags(defender, flags, db)
    return True


def process_stench_flinch(attacker: GameUnit, target: GameUnit, damage: int, db: Session) -> bool:
    """Stench: 10% chance to flinch the target after dealing damage."""
    if damage <= 0 or target is None or getattr(target, "is_fainted", False):
        return False
    if not ability_has_token(attacker, db, "on_damage_dealt:target:apply_state:flinch", "stench"):
        return False
    if not can_apply_state(target, "flinch", db):
        return False

    chance = 10
    for token in get_ability_effects(attacker, db):
        parts = _token_parts(token)
        if (
            len(parts) >= 5
            and parts[0] == "on_damage_dealt"
            and parts[2] == "apply_state"
            and parts[3] == "flinch"
        ):
            try:
                chance = int(parts[4])
            except (TypeError, ValueError):
                chance = 10
            break

    if random.randint(1, 100) > chance:
        return False

    target.states = ["flinch", 1]
    db.add(target)
    return True


def process_color_change(defender: GameUnit, move_type: str, db: Session) -> bool:
    """Color Change: set battle types to the move's type. Returns True if changed."""
    mt = str(move_type or "").lower().strip()
    if not mt or mt == "???":
        return False
    if not ability_has_token(defender, db, "on_hit:self:change_type", "color_change"):
        return False
    current = get_battle_types(defender, db)
    if current == {mt}:
        return False
    set_battle_types(defender, [mt], db)
    return True


def process_recoil_allowed(attacker: GameUnit, db: Session) -> bool:
    """False if Rock Head or Magic Guard prevents recoil damage."""
    if ability_has_token(attacker, db, "immune_recoil", "rock_head"):
        return False
    if should_ignore_indirect_damage(attacker, db):
        return False
    return True


def process_drain(
    attacker: GameUnit,
    target: GameUnit,
    heal_amount: int,
    db: Session,
) -> int:
    """Apply drain healing. Liquid Ooze damages the attacker instead.

    Returns the signed HP delta applied to the attacker (positive heal, negative damage).
    """
    if heal_amount <= 0 or attacker is None:
        return 0

    if target is not None and ability_has_token(
        target, db, "on_drained:attacker:damage_instead_of_heal", "liquid_ooze"
    ):
        new_hp = max(0, int(attacker.current_hp or 0) - int(heal_amount))
        attacker.current_hp = new_hp
        if new_hp <= 0:
            attacker.is_fainted = True
        db.add(attacker)
        return -int(heal_amount)

    max_hp = _max_hp(attacker)
    cur = int(attacker.current_hp or 0)
    if max_hp > 0:
        new_hp = min(max_hp, cur + int(heal_amount))
    else:
        new_hp = cur + int(heal_amount)
    actual = new_hp - cur
    attacker.current_hp = new_hp
    db.add(attacker)
    return actual


# ---------------------------------------------------------------------------
# Targeting: Lightning Rod / Storm Drain
# ---------------------------------------------------------------------------


def redirect_targets_for_move(
    move: Any,
    attacker: GameUnit,
    targets: list[GameUnit],
    all_units: list[GameUnit],
    db: Session,
) -> list[GameUnit]:
    """Redirect typed moves to an opposing redirect:TYPE user when present."""
    # Propeller Tail / Stalwart / move ignore_redirect skip redirection.
    if ability_has_token(attacker, db, "ignore_redirect", "propeller_tail", "stalwart"):
        return list(targets or [])
    move_effects = getattr(move, "effects", None) or []
    if any(str(e or "").lower().strip() == "ignore_redirect" for e in move_effects):
        return list(targets or [])

    move_type = _move_type(move)
    if not move_type:
        return list(targets or [])

    cache: dict = {}
    candidates: list[GameUnit] = []
    redirect_token = f"redirect:{move_type}"
    for unit in all_units or []:
        if unit is None or getattr(unit, "is_fainted", False):
            continue
        if getattr(unit, "user_id", None) == getattr(attacker, "user_id", None):
            continue
        if ability_has_token(unit, db, redirect_token, _cache=cache):
            candidates.append(unit)
        elif move_type == "electric" and ability_has_token(
            unit, db, "lightning_rod", _cache=cache
        ):
            candidates.append(unit)
        elif move_type == "water" and ability_has_token(
            unit, db, "storm_drain", _cache=cache
        ):
            candidates.append(unit)

    if not candidates:
        return list(targets or [])

    def _dist(u: GameUnit) -> float:
        try:
            ax, ay = int(attacker.current_x), int(attacker.current_y)
            ux, uy = int(u.current_x), int(u.current_y)
            return abs(ax - ux) + abs(ay - uy)
        except Exception:
            return 9999.0

    candidates.sort(key=_dist)
    return [candidates[0]]


# ---------------------------------------------------------------------------
# Switch-in
# ---------------------------------------------------------------------------


def process_switch_in(
    unit: GameUnit,
    db: Session,
    *,
    game: Any,
    game_state: Any,
    map_state: Any,
    current_turn: int,
    helpers: dict | None = None,
) -> list[str]:
    """Resolve Drizzle/Drought/Sand Stream, Intimidate, and Trace on switch-in.

    ``helpers`` may include:
      apply_stat_change, publish_system_log_event, get_unit_display_name,
      get_unit_types, set_unit_ability_id, get_unit_ability_id, WEATHER_TO_ID
    """
    helpers = helpers or {}
    messages: list[str] = []
    if unit is None or getattr(unit, "is_fainted", False):
        return messages

    # Stakeout: every switch-in is marked, regardless of this unit's ability
    mark_just_switched_in(unit, db)

    # Protean: reset once-per-switch-in flag
    flags = _unit_flags(unit)
    if "protean_used" in flags:
        flags = dict(flags)
        flags.pop("protean_used", None)
        _set_unit_flags(unit, flags, db)
    # Gorilla Tactics / Choice-style lock clears on switch-in
    flags = _unit_flags(unit)
    if "locked_move_id" in flags:
        flags = dict(flags)
        flags.pop("locked_move_id", None)
        _set_unit_flags(unit, flags, db)

    effects = get_ability_effects(unit, db)
    if not effects:
        return messages

    get_name: Callable = helpers.get("get_unit_display_name") or (
        lambda u, _db: _unit_display_name(u)
    )
    apply_stat: Callable | None = helpers.get("apply_stat_change")
    publish: Callable | None = helpers.get("publish_system_log_event")
    set_ability: Callable | None = helpers.get("set_unit_ability_id")
    weather_map: dict = helpers.get("WEATHER_TO_ID") or WEATHER_TO_ID

    unit_name = get_name(unit, db)
    ability = get_active_ability(unit, db)
    ability_name = getattr(ability, "name", None) or "ability"

    def _log(msg: str) -> None:
        messages.append(msg)
        if publish and game is not None:
            try:
                publish(getattr(game, "link", None), msg, game_state, db)
            except Exception:
                pass

    # Weather setters
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 3 and parts[0] == "on_switch_in" and parts[1] == "weather":
            weather_name = parts[2]
            if weather_name not in weather_map:
                continue
            if map_state is not None:
                set_weather_on_map(map_state, weather_name)
                try:
                    db.add(map_state)
                except Exception:
                    pass
            _log(f"{unit_name}'s {ability_name} made it {weather_name}!")

    # Terrain surges (Electric / Psychic / Grassy / Misty)
    terrain_map: dict = helpers.get("TERRAIN_TO_ID") or TERRAIN_TO_ID
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 3 and parts[0] == "on_switch_in" and parts[1] == "terrain":
            terrain_name = parts[2]
            if terrain_name not in terrain_map:
                continue
            if map_state is not None:
                set_terrain_on_map(
                    map_state,
                    terrain_name,
                    duration=TERRAIN_DEFAULT_DURATION,
                    terrain_map=terrain_map,
                )
                try:
                    db.add(map_state)
                except Exception:
                    pass
            _log(f"{unit_name}'s {ability_name} created {terrain_name} terrain!")

    # Intimidate / Supersweet Syrup
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 5
            and parts[0] == "on_switch_in"
            and parts[1] == "opponents"
            and parts[2] == "lower_stat"
        ):
            continue
        once = "once_per_battle" in parts[5:]
        flag_key = f"switch_in_opp_lower_{parts[3]}_used"
        flags_once = _unit_flags(unit)
        if once and flags_once.get(flag_key):
            continue
        stat = _normalize_stat_name(parts[3])
        try:
            stages = int(parts[4])
        except (TypeError, ValueError):
            stages = 1
        magnitude = -abs(stages)

        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        opponents = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id != getattr(unit, "user_id", None),
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        cache: dict = {}
        for opp in opponents:
            if immune_to_intimidate(opp, db):
                continue
            if blocks_stat_drop(opp, stat, db, from_opponent=True):
                continue
            if apply_stat:
                try:
                    apply_stat(opp, stat, magnitude, current_turn, db, from_opponent=True, source=unit)
                except TypeError:
                    try:
                        apply_stat(opp, stat, magnitude, current_turn, db, from_opponent=True)
                    except TypeError:
                        apply_stat(opp, stat, magnitude, current_turn, db)
            else:
                boosts = getattr(opp, "stat_boosts", None)
                if isinstance(boosts, dict):
                    instances = list(boosts.get(stat) or [])
                    instances.append({"magnitude": magnitude, "expires_turn": 4})
                    boosts = dict(boosts)
                    boosts[stat] = instances
                    opp.stat_boosts = boosts
                    db.add(opp)
            opp_name = get_name(opp, db)
            _log(f"{unit_name}'s {ability_name} cut {opp_name}'s {stat.replace('_', ' ')}!")

            # Rattled: on_intimidate:self:raise_stat:speed:1
            opp_effects = get_ability_effects(opp, db, _cache=cache)
            for otok in opp_effects:
                oparts = _token_parts(otok)
                if not (
                    len(oparts) >= 5
                    and oparts[0] == "on_intimidate"
                    and oparts[1] == "self"
                    and oparts[2] == "raise_stat"
                ):
                    continue
                raise_stat = _normalize_stat_name(oparts[3])
                try:
                    raise_stages = int(oparts[4])
                except (TypeError, ValueError):
                    raise_stages = 1
                if apply_stat:
                    try:
                        apply_stat(opp, raise_stat, raise_stages, current_turn, db)
                    except TypeError:
                        apply_stat(opp, raise_stat, raise_stages, current_turn, db)
                else:
                    boosts = getattr(opp, "stat_boosts", None)
                    if not isinstance(boosts, dict):
                        boosts = {}
                    instances = list(boosts.get(raise_stat) or [])
                    instances.append({"magnitude": raise_stages, "expires_turn": 4})
                    boosts = dict(boosts)
                    boosts[raise_stat] = instances
                    opp.stat_boosts = boosts
                    db.add(opp)
                _log(
                    f"{opp_name}'s Rattled raised its {raise_stat.replace('_', ' ')}!"
                )

        if once:
            flags_once = dict(_unit_flags(unit))
            flags_once[flag_key] = True
            _set_unit_flags(unit, flags_once, db)

    # Trace — copy a random opposing ability
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 4
            and parts[0] == "on_switch_in"
            and parts[1] == "self"
            and parts[2] == "copy_ability"
        ):
            continue
        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        opponents = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id != getattr(unit, "user_id", None),
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        # Prefer an opponent that still has an ability
        sources = []
        for opp in opponents:
            if _is_ability_suppressed(opp, db):
                continue
            aid = _get_unit_ability_id(opp)
            if aid is not None:
                sources.append((opp, aid))
        if not sources:
            continue
        source, source_id = random.choice(sources)
        if set_ability:
            set_ability(unit, source_id, db)
        else:
            flags = _unit_flags(unit)
            flags["ability_id"] = int(source_id)
            _set_unit_flags(unit, flags, db)
        traced = db.query(Ability).filter(Ability.id == source_id).first()
        traced_name = getattr(traced, "name", None) or "ability"
        source_name = get_name(source, db)
        _log(f"{unit_name}'s Trace copied {source_name}'s {traced_name}!")

        # After tracing, optionally re-trigger weather/intimidate from the new ability.
        # Keep simple: do not recurse; games.py can call again if desired.

    # Download: raise Attack or SpA based on opponent Def vs SpDef
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 5
            and parts[0] == "on_switch_in"
            and parts[1] == "self"
            and parts[2] == "raise_stat"
            and parts[3] == "attack_or_special_attack"
        ):
            continue
        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        opponents = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id != getattr(unit, "user_id", None),
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        if not opponents:
            continue
        opp = opponents[0]
        opp_stats = getattr(opp, "current_stats", None) or {}
        try:
            opp_def = int(opp_stats.get("defense", 0) or 0)
        except (TypeError, ValueError):
            opp_def = 0
        try:
            opp_spd = int(opp_stats.get("sp_defense", 0) or 0)
        except (TypeError, ValueError):
            opp_spd = 0
        # Raise the offensive stat that targets the weaker defense
        raise_stat = "sp_attack" if opp_spd <= opp_def else "attack"
        if apply_stat:
            apply_stat(unit, raise_stat, 1, current_turn, db)
        else:
            boosts = getattr(unit, "stat_boosts", None)
            if not isinstance(boosts, dict):
                boosts = {}
            instances = list(boosts.get(raise_stat) or [])
            instances.append({"magnitude": 1, "expires_turn": 4})
            boosts = dict(boosts)
            boosts[raise_stat] = instances
            unit.stat_boosts = boosts
            db.add(unit)
        _log(
            f"{unit_name}'s {ability_name} raised its {raise_stat.replace('_', ' ')}!"
        )

    # Intrepid Sword / Dauntless Shield: on_switch_in:self:raise_stat:STAT:N[:once_per_battle]
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 5
            and parts[0] == "on_switch_in"
            and parts[1] == "self"
            and parts[2] == "raise_stat"
            and parts[3] != "attack_or_special_attack"
        ):
            continue
        once = "once_per_battle" in parts[5:]
        flags = _unit_flags(unit)
        flag_key = f"switch_in_raise_{parts[3]}_used"
        if once and flags.get(flag_key):
            continue
        stat = _normalize_stat_name(parts[3])
        try:
            stages = int(parts[4])
        except (TypeError, ValueError):
            stages = 1
        if apply_stat:
            try:
                apply_stat(unit, stat, stages, current_turn, db)
            except TypeError:
                apply_stat(unit, stat, stages, current_turn, db)
        else:
            boosts = getattr(unit, "stat_boosts", None)
            if not isinstance(boosts, dict):
                boosts = {}
            instances = list(boosts.get(stat) or [])
            instances.append({"magnitude": stages, "expires_turn": 4})
            boosts = dict(boosts)
            boosts[stat] = instances
            unit.stat_boosts = boosts
            db.add(unit)
        if once:
            flags = dict(flags)
            flags[flag_key] = True
            _set_unit_flags(unit, flags, db)
        _log(f"{unit_name}'s {ability_name} raised its {stat.replace('_', ' ')}!")

    # Screen Cleaner: on_switch_in:clear_screens
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 2
            and parts[0] == "on_switch_in"
            and parts[1] == "clear_screens"
        ):
            continue
        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        all_units = (
            db.query(GameUnit)
            .filter(GameUnit.game_id == game_id)
            .all()
        )
        cleared = False
        for u in all_units:
            states = _normalize_states(getattr(u, "states", None))
            if states and str(states[0]).lower() in {"reflect", "light_screen", "aurora_veil"}:
                u.states = []
                db.add(u)
                cleared = True
        if cleared:
            _log(f"{unit_name}'s {ability_name} cleared the screens!")

    # Curious Medicine: on_switch_in:allies:clear_stat_changes
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_switch_in"
            and parts[1] == "allies"
            and parts[2] == "clear_stat_changes"
        ):
            continue
        for ally in _living_allies_including_self(unit, db):
            if getattr(ally, "id", None) == getattr(unit, "id", None):
                continue
            ally.stat_boosts = {}
            db.add(ally)
            _log(
                f"{unit_name}'s {ability_name} reset {get_name(ally, db)}'s stat changes!"
            )

    # Neutralizing Gas activation message
    for token in effects:
        parts = _token_parts(token)
        if parts and parts[0] == "suppress_other_abilities":
            _log(f"Neutralizing Gas filled the area!")
            break

    # Hospitality: on_switch_in:ally:heal_fraction:4
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 4
            and parts[0] == "on_switch_in"
            and parts[1] == "ally"
            and parts[2] == "heal_fraction"
        ):
            continue
        try:
            fraction = int(parts[3])
        except (TypeError, ValueError):
            fraction = 4
        allies = [
            a for a in _living_allies_including_self(unit, db)
            if getattr(a, "id", None) != getattr(unit, "id", None)
        ]
        if not allies:
            continue
        # Heal lowest-HP ally
        def _hp_ratio(u):
            m = _max_hp(u)
            return (float(u.current_hp or 0) / m) if m > 0 else 1.0
        ally = min(allies, key=_hp_ratio)
        max_hp = _max_hp(ally)
        if max_hp <= 0:
            continue
        heal = max(1, max_hp // fraction)
        ally.current_hp = min(max_hp, int(ally.current_hp or 0) + heal)
        db.add(ally)
        _log(f"{unit_name}'s {ability_name} restored {get_name(ally, db)}'s HP!")

    # Costar: on_switch_in:self:copy_stat_changes:ally
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 4
            and parts[0] == "on_switch_in"
            and parts[1] == "self"
            and parts[2] == "copy_stat_changes"
        ):
            continue
        allies = [
            a for a in _living_allies_including_self(unit, db)
            if getattr(a, "id", None) != getattr(unit, "id", None)
        ]
        if not allies:
            continue
        ally = allies[0]
        src = getattr(ally, "stat_boosts", None)
        if isinstance(src, dict):
            unit.stat_boosts = dict(src)
            db.add(unit)
            _log(f"{unit_name}'s {ability_name} copied {get_name(ally, db)}'s stat changes!")

    # Supreme Overlord: count fainted allies and store power boost
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_switch_in"
            and parts[1] == "boost_power_per_fainted_ally"
        ):
            continue
        try:
            per = float(parts[2])
        except (TypeError, ValueError):
            per = 0.1
        max_boost = 0.5
        if "max" in parts:
            try:
                max_boost = float(parts[parts.index("max") + 1])
            except (ValueError, IndexError, TypeError):
                max_boost = 0.5
        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        fainted_allies = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id == getattr(unit, "user_id", None),
                GameUnit.is_fainted.is_(True),
            )
            .count()
        )
        boost = min(max_boost, per * int(fainted_allies))
        flags = _unit_flags(unit)
        flags["supreme_overlord_boost"] = boost
        _set_unit_flags(unit, flags, db)
        if boost > 0:
            _log(f"{unit_name}'s {ability_name} powered up from fallen allies!")

    # Tera Shift: on_switch_in:change_forme:terastal
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_switch_in"
            and parts[1] == "change_forme"
        ):
            continue
        flags = _unit_flags(unit)
        flags["forme"] = parts[2]
        _set_unit_flags(unit, flags, db)
        _log(f"{unit_name}'s {ability_name} transformed it!")

    # Commander stub: on_switch_in:enter_ally:dondozo
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_switch_in"
            and parts[1] == "enter_ally"
        ):
            continue
        ally_slug = parts[2]
        allies = [
            a for a in _living_allies_including_self(unit, db)
            if getattr(a, "id", None) != getattr(unit, "id", None)
        ]
        host = None
        for ally in allies:
            uname = str(getattr(getattr(ally, "unit", None), "name", "") or "").lower()
            uspecies = str(getattr(getattr(ally, "unit", None), "species", "") or "").lower()
            if ally_slug in uname.replace(" ", "_") or ally_slug in uspecies.replace(" ", "_"):
                host = ally
                break
        flags = _unit_flags(unit)
        if host is not None:
            flags["commander_host_id"] = getattr(host, "id", None)
            flags["forme"] = "commanding"
            _set_unit_flags(unit, flags, db)
            _log(f"{unit_name}'s {ability_name} entered {get_name(host, db)}!")
        else:
            flags["commander_waiting"] = ally_slug
            _set_unit_flags(unit, flags, db)

    # Anticipation: shudder if any opposing move is SE or OHKO
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_switch_in"
            and parts[1] == "sense"
            and "super_effective" in parts[2]
        ):
            continue
        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        get_types = helpers.get("get_unit_types") or _default_get_unit_types
        get_type_mult = helpers.get("get_type_multiplier") or _simple_type_multiplier
        unit_types = get_types(unit, db) if callable(get_types) else set()
        opponents = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id != getattr(unit, "user_id", None),
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        shuddered = False
        from app.db.models import Move, Unit as UnitModel

        for opp in opponents:
            unit_info = getattr(opp, "unit", None)
            if unit_info is None and getattr(opp, "unit_id", None):
                unit_info = db.query(UnitModel).filter_by(id=opp.unit_id).first()
            move_ids = getattr(unit_info, "equipped_moves", None) if unit_info else None
            if not isinstance(move_ids, list):
                continue
            for mid in move_ids:
                try:
                    mid_i = int(mid)
                except (TypeError, ValueError):
                    continue
                mv = db.query(Move).filter(Move.id == mid_i).first()
                if mv is None:
                    continue
                # OHKO detection
                mv_effects = getattr(mv, "effects", None) or []
                if any("instant_ko" in str(e).lower() or "ohko" in str(e).lower() for e in mv_effects):
                    shuddered = True
                    break
                if str(getattr(mv, "category", "") or "").lower() == "ohko":
                    shuddered = True
                    break
                mt = str(getattr(mv, "type", "") or "").lower()
                if not mt:
                    continue
                try:
                    mult = get_type_mult(mt, list(unit_types))
                except TypeError:
                    mult = get_type_mult(mt, unit_types)
                if mult and float(mult) > 1.0:
                    shuddered = True
                    break
            if shuddered:
                break
        if shuddered:
            _log(f"{unit_name}'s {ability_name} shuddered!")

    # Forewarn: reveal strongest power move of a random opponent
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_switch_in"
            and parts[1] == "reveal"
            and parts[2] == "strongest_opponent_move"
        ):
            continue
        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        opponents = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id != getattr(unit, "user_id", None),
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        if not opponents:
            continue
        from app.db.models import Move, Unit as UnitModel

        opp = random.choice(opponents)
        unit_info = getattr(opp, "unit", None)
        if unit_info is None and getattr(opp, "unit_id", None):
            unit_info = db.query(UnitModel).filter_by(id=opp.unit_id).first()
        move_ids = getattr(unit_info, "equipped_moves", None) if unit_info else None
        best_name = None
        best_power = -1
        if isinstance(move_ids, list):
            for mid in move_ids:
                try:
                    mid_i = int(mid)
                except (TypeError, ValueError):
                    continue
                mv = db.query(Move).filter(Move.id == mid_i).first()
                if mv is None:
                    continue
                try:
                    power = int(getattr(mv, "power", 0) or 0)
                except (TypeError, ValueError):
                    power = 0
                # Status moves count as power 0; OHKO as high
                mv_effects = getattr(mv, "effects", None) or []
                if any("instant_ko" in str(e).lower() or "ohko" in str(e).lower() for e in mv_effects):
                    power = 150
                if power > best_power:
                    best_power = power
                    best_name = getattr(mv, "name", None) or "a move"
        if best_name:
            opp_name = get_name(opp, db)
            _log(f"{unit_name}'s {ability_name} alerted it to {opp_name}'s {best_name}!")

    # Frisk: reveal held items of opponents
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_switch_in"
            and parts[1] == "reveal"
            and parts[2] == "opponent_held_items"
        ):
            continue
        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        get_held = helpers.get("get_unit_held_item")
        opponents = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id != getattr(unit, "user_id", None),
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        for opp in opponents:
            held = None
            if get_held:
                held = get_held(opp)
            else:
                held = _unit_flags(opp).get("held_item")
            if held:
                opp_name = get_name(opp, db)
                _log(f"{unit_name}'s {ability_name} found {opp_name}'s {held}!")

    # Slow Start: set flags slow_start_remaining
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 5
            and parts[0] == "on_switch_in"
            and parts[1] == "self"
            and parts[2] == "apply_state"
            and parts[3] == "slow_start"
        ):
            continue
        try:
            turns = int(parts[4])
        except (TypeError, ValueError):
            turns = 5
        flags = _unit_flags(unit)
        flags["slow_start_remaining"] = turns
        _set_unit_flags(unit, flags, db)
        _log(f"{unit_name} can't get it going because of its {ability_name}!")

    # Multitype from held plate
    get_held = helpers.get("get_unit_held_item")
    resolve_item = helpers.get("resolve_item")
    if apply_multitype_from_held_item(unit, db, get_held, resolve_item):
        _log(f"{unit_name}'s {ability_name} changed its type!")

    # RKS System from held memory
    if apply_rks_from_held_item(unit, db, get_held, resolve_item):
        _log(f"{unit_name}'s {ability_name} changed its type!")

    # Comatose: ensure permanent sleep without locking actions
    ensure_comatose_sleep(unit, db)

    # Schooling / Shields Down / Power Construct initial forme from HP
    update_hp_threshold_formes(unit, db)

    # Forecast / Mimicry / Ice Face on switch-in
    if map_state is not None:
        weather_id = _unit_weather_id(unit, getattr(map_state, "weather_tiles", None))
        if update_forecast_types(unit, weather_id, db):
            _log(f"{unit_name}'s Forecast adapted to the weather!")
        if restore_ice_face_on_hail(unit, weather_id, db):
            _log(f"{unit_name}'s Ice Face was restored!")
        terrain_id = _unit_terrain_id(unit, getattr(map_state, "terrain_effect_tiles", None), db)
        if update_mimicry_types(unit, terrain_id, db):
            _log(f"{unit_name}'s Mimicry adapted to the terrain!")

    # Illusion: disguise as last ally by id order (best-effort stub)
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_switch_in"
            and parts[1] == "disguise_as"
        ):
            continue
        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        allies = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id == getattr(unit, "user_id", None),
                GameUnit.id != getattr(unit, "id", None),
            )
            .order_by(GameUnit.id.asc())
            .all()
        )
        if not allies:
            continue
        last_ally = allies[-1]
        flags = _unit_flags(unit)
        flags["illusion_of"] = getattr(last_ally, "id", None)
        _set_unit_flags(unit, flags, db)
        _log(f"{unit_name}'s Illusion disguised it as {get_name(last_ally, db)}!")

    # Imposter: transform into a random opponent (best-effort)
    for token in effects:
        parts = _token_parts(token)
        if not (
            len(parts) >= 3
            and parts[0] == "on_switch_in"
            and parts[1] == "transform"
            and parts[2] == "opponent"
        ):
            continue
        game_id = getattr(unit, "game_id", None) or getattr(game, "id", None)
        if not game_id:
            continue
        opponents = (
            db.query(GameUnit)
            .filter(
                GameUnit.game_id == game_id,
                GameUnit.user_id != getattr(unit, "user_id", None),
                GameUnit.is_fainted.is_(False),
            )
            .all()
        )
        if not opponents:
            continue
        source = opponents[0]
        source_aid = _get_unit_ability_id(source)
        if source_aid is not None:
            if set_ability:
                set_ability(unit, source_aid, db)
            else:
                flags = _unit_flags(unit)
                flags["ability_id"] = int(source_aid)
                _set_unit_flags(unit, flags, db)
        get_types = helpers.get("get_unit_types")
        if get_types:
            try:
                stypes = list(get_types(source, db) or [])
            except TypeError:
                stypes = list(get_types(source) or [])
            if stypes:
                set_battle_types(unit, [str(t) for t in stypes], db)
        src_stats = getattr(source, "current_stats", None)
        if isinstance(src_stats, dict):
            cur = dict(getattr(unit, "current_stats", None) or {})
            for key in ("attack", "defense", "sp_attack", "sp_defense", "speed"):
                if key in src_stats:
                    cur[key] = src_stats[key]
            unit.current_stats = cur
            db.add(unit)
        flags = _unit_flags(unit)
        flags["imposter_of"] = getattr(source, "id", None)
        _set_unit_flags(unit, flags, db)
        _log(f"{unit_name}'s Imposter transformed it into {get_name(source, db)}!")

    return messages


# ---------------------------------------------------------------------------
# End of turn
# ---------------------------------------------------------------------------


def process_end_of_turn_abilities(
    units: list[GameUnit],
    db: Session,
    *,
    game: Any,
    game_state: Any,
    weather_tiles: list | None,
    current_turn: int,
    helpers: dict | None = None,
) -> list[int]:
    """Process Speed Boost / Shed Skin / Rain Dish / Pickup / Gen4 EOT abilities.

    Returns list of unit ids that were mutated. ``helpers`` may include
    ``apply_stat_change``, ``publish_system_log_event``, ``get_unit_display_name``,
    ``cure_status_effect``.
    """
    helpers = helpers or {}
    mutated: list[int] = []
    apply_stat: Callable | None = helpers.get("apply_stat_change")
    publish: Callable | None = helpers.get("publish_system_log_event")
    get_name: Callable = helpers.get("get_unit_display_name") or (
        lambda u, _db: _unit_display_name(u)
    )
    cure_status: Callable | None = helpers.get("cure_status_effect")

    weather_suppressed = False
    if game is not None and getattr(game, "id", None):
        weather_suppressed = weather_is_suppressed(int(game.id), db)

    cache: dict = {}

    for unit in units or []:
        if unit is None or getattr(unit, "is_fainted", False):
            continue

        effects = get_ability_effects(unit, db, _cache=cache)
        unit_name = get_name(unit, db)
        ability = get_active_ability(unit, db, _cache=cache)
        ability_name = getattr(ability, "name", None) or "ability"
        changed = False

        weather_id = 0 if weather_suppressed else _unit_weather_id(unit, weather_tiles)

        # Forecast / Mimicry / Ice Face type/forme update each turn
        if effects and update_forecast_types(unit, weather_id, db):
            changed = True
        if effects and restore_ice_face_on_hail(unit, weather_id, db):
            changed = True
            if publish and game is not None:
                try:
                    publish(
                        getattr(game, "link", None),
                        f"{unit_name}'s Ice Face was restored!",
                        game_state,
                        db,
                    )
                except Exception:
                    pass
        terrain_tiles = helpers.get("terrain_tiles")
        if effects and terrain_tiles is not None:
            terrain_id = _unit_terrain_id(unit, terrain_tiles, db)
            if update_mimicry_types(unit, terrain_id, db):
                changed = True

        # Perish Body / Perish Song countdown (any perish state)
        states = _normalize_states(getattr(unit, "states", None))
        if states and str(states[0]).lower() == "perish":
            try:
                remaining = int(states[1])
            except (TypeError, ValueError):
                remaining = 0
            if remaining > 0:
                remaining -= 1
                if remaining <= 0:
                    unit.current_hp = 0
                    unit.is_fainted = True
                    unit.states = []
                    db.add(unit)
                    if publish and game is not None:
                        try:
                            publish(
                                getattr(game, "link", None),
                                f"{unit_name} perished!",
                                game_state,
                                db,
                            )
                        except Exception:
                            pass
                    changed = True
                    uid = getattr(unit, "id", None)
                    if isinstance(uid, int):
                        mutated.append(uid)
                    continue
                unit.states = ["perish", remaining]
                db.add(unit)
                if publish and game is not None:
                    try:
                        publish(
                            getattr(game, "link", None),
                            f"{unit_name}'s perish count fell to {remaining}!",
                            game_state,
                            db,
                        )
                    except Exception:
                        pass
                changed = True

        # Decrement Slow Start regardless of other effects
        flags = _unit_flags(unit)
        slow_rem = flags.get("slow_start_remaining")
        try:
            slow_rem_i = int(slow_rem) if slow_rem is not None else 0
        except (TypeError, ValueError):
            slow_rem_i = 0
        if slow_rem_i > 0:
            flags["slow_start_remaining"] = slow_rem_i - 1
            if flags["slow_start_remaining"] <= 0:
                flags.pop("slow_start_remaining", None)
                if publish and game is not None:
                    try:
                        publish(
                            getattr(game, "link", None),
                            f"{unit_name} finally got its act together!",
                            game_state,
                            db,
                        )
                    except Exception:
                        pass
            _set_unit_flags(unit, flags, db)
            changed = True

        if not effects:
            if changed:
                uid = getattr(unit, "id", None)
                if isinstance(uid, int):
                    mutated.append(uid)
            continue

        # Cud Chew: reuse berry queued from earlier eat
        for cud_msg in process_cud_chew_end_of_turn(unit, db):
            if publish and game is not None:
                try:
                    publish(getattr(game, "link", None), cud_msg, game_state, db)
                except Exception:
                    pass
            changed = True

        for token in effects:
            parts = _token_parts(token)

            # on_turn_end:toggle_forme:full_belly_hangry (Hunger Switch)
            if (
                len(parts) >= 3
                and parts[0] == "on_turn_end"
                and parts[1] == "toggle_forme"
            ):
                flags = _unit_flags(unit)
                current = str(flags.get("forme") or "full_belly").lower()
                if "hangry" in current:
                    flags["forme"] = "full_belly"
                else:
                    flags["forme"] = "hangry"
                _set_unit_flags(unit, flags, db)
                if publish and game is not None:
                    try:
                        publish(
                            getattr(game, "link", None),
                            f"{unit_name}'s {ability_name} changed its forme!",
                            game_state,
                            db,
                        )
                    except Exception:
                        pass
                changed = True
                continue

            # on_turn_end:self:raise_stat:speed:1  (Speed Boost)
            if (
                len(parts) >= 5
                and parts[0] == "on_turn_end"
                and parts[1] == "self"
                and parts[2] == "raise_stat"
            ):
                stat = _normalize_stat_name(parts[3])
                try:
                    stages = int(parts[4])
                except (TypeError, ValueError):
                    stages = 1
                if apply_stat:
                    apply_stat(unit, stat, stages, current_turn, db)
                else:
                    boosts = getattr(unit, "stat_boosts", None)
                    if isinstance(boosts, dict):
                        instances = list(boosts.get(stat) or [])
                        instances.append({"magnitude": stages, "expires_turn": 4})
                        boosts = dict(boosts)
                        boosts[stat] = instances
                        unit.stat_boosts = boosts
                        db.add(unit)
                msg = f"{unit_name}'s {ability_name} raised its {stat.replace('_', ' ')}!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # on_turn_end:self:cure_status:30  (Shed Skin)
            if (
                len(parts) >= 4
                and parts[0] == "on_turn_end"
                and parts[1] == "self"
                and parts[2] == "cure_status"
            ):
                if not _has_any_status(unit):
                    continue
                try:
                    chance = int(parts[3]) if len(parts) >= 4 else 30
                except (TypeError, ValueError):
                    chance = 30
                # Hydration-style tokens without chance always cure (handled below)
                if ":" in token and len(parts) == 4:
                    # chance token
                    if random.randint(1, 100) > chance:
                        continue
                if cure_status:
                    cure_status(unit, db)
                else:
                    unit.status_effects = []
                    db.add(unit)
                msg = f"{unit_name}'s {ability_name} cured its status!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # on_weather:rain:on_turn_end:self:heal_fraction:16  (Rain Dish / Ice Body / Dry Skin)
            if (
                len(parts) >= 6
                and parts[0] == "on_weather"
                and parts[2] == "on_turn_end"
                and parts[3] == "self"
                and parts[4] == "heal_fraction"
            ):
                if not weather_id_matches(weather_id, parts[1]):
                    continue
                try:
                    fraction = int(parts[5])
                except (TypeError, ValueError):
                    fraction = 16
                max_hp = _max_hp(unit)
                if max_hp <= 0:
                    continue
                heal = max(1, max_hp // fraction)
                cur = int(unit.current_hp or 0)
                if cur >= max_hp:
                    continue
                unit.current_hp = min(max_hp, cur + heal)
                db.add(unit)
                msg = f"{unit_name}'s {ability_name} restored HP!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # on_weather:sun:on_turn_end:self:damage_fraction:8 (Dry Skin / Solar Power)
            if (
                len(parts) >= 6
                and parts[0] == "on_weather"
                and parts[2] == "on_turn_end"
                and parts[3] == "self"
                and parts[4] == "damage_fraction"
            ):
                if not weather_id_matches(weather_id, parts[1]):
                    continue
                if should_ignore_indirect_damage(unit, db):
                    continue
                try:
                    fraction = int(parts[5])
                except (TypeError, ValueError):
                    fraction = 8
                max_hp = _max_hp(unit)
                if max_hp <= 0:
                    continue
                dmg = max(1, max_hp // fraction)
                new_hp = max(0, int(unit.current_hp or 0) - dmg)
                unit.current_hp = new_hp
                if new_hp <= 0:
                    unit.is_fainted = True
                db.add(unit)
                msg = f"{unit_name} was hurt by its {ability_name}!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # on_weather:rain:on_turn_end:self:cure_status (Hydration)
            if (
                len(parts) >= 5
                and parts[0] == "on_weather"
                and parts[2] == "on_turn_end"
                and parts[3] == "self"
                and parts[4] == "cure_status"
            ):
                if not weather_id_matches(weather_id, parts[1]):
                    continue
                if not _has_any_status(unit):
                    continue
                if cure_status:
                    cure_status(unit, db)
                else:
                    unit.status_effects = []
                    db.add(unit)
                msg = f"{unit_name}'s {ability_name} cured its status!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # on_status:poison:on_turn_end:self:heal_fraction:8 (Poison Heal)
            if (
                len(parts) >= 6
                and parts[0] == "on_status"
                and parts[2] == "on_turn_end"
                and parts[3] == "self"
                and parts[4] == "heal_fraction"
            ):
                status_cond = _normalize_status_name(parts[1])
                active = _active_status(unit)
                if active is None:
                    continue
                poison_family = {"poison", "badly_poisoned"}
                if status_cond in poison_family:
                    if active not in poison_family:
                        continue
                elif status_cond != active:
                    continue
                try:
                    fraction = int(parts[5])
                except (TypeError, ValueError):
                    fraction = 8
                max_hp = _max_hp(unit)
                if max_hp <= 0:
                    continue
                heal = max(1, max_hp // fraction)
                cur = int(unit.current_hp or 0)
                if cur >= max_hp:
                    continue
                unit.current_hp = min(max_hp, cur + heal)
                db.add(unit)
                msg = f"{unit_name}'s {ability_name} restored HP!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # on_turn_end:opponents:if_asleep:damage_fraction:8 (Bad Dreams)
            if (
                len(parts) >= 5
                and parts[0] == "on_turn_end"
                and parts[1] == "opponents"
                and parts[2] == "if_asleep"
                and parts[3] == "damage_fraction"
            ):
                try:
                    fraction = int(parts[4])
                except (TypeError, ValueError):
                    fraction = 8
                game_id = getattr(unit, "game_id", None) or (
                    getattr(game, "id", None) if game is not None else None
                )
                if not game_id:
                    continue
                opponents = (
                    db.query(GameUnit)
                    .filter(
                        GameUnit.game_id == game_id,
                        GameUnit.user_id != getattr(unit, "user_id", None),
                        GameUnit.is_fainted.is_(False),
                    )
                    .all()
                )
                for opp in opponents:
                    if _active_status(opp) != "sleep":
                        continue
                    if should_ignore_indirect_damage(opp, db):
                        continue
                    max_hp = _max_hp(opp)
                    if max_hp <= 0:
                        continue
                    dmg = max(1, max_hp // fraction)
                    new_hp = max(0, int(opp.current_hp or 0) - dmg)
                    opp.current_hp = new_hp
                    if new_hp <= 0:
                        opp.is_fainted = True
                    db.add(opp)
                    opp_name = get_name(opp, db)
                    msg = f"{opp_name} is tormented by {unit_name}'s {ability_name}!"
                    if publish and game is not None:
                        try:
                            publish(getattr(game, "link", None), msg, game_state, db)
                        except Exception:
                            pass
                    changed = True
                continue

            # on_turn_end:self:pickup_consumed_item  (Pickup)
            if (
                len(parts) >= 3
                and parts[0] == "on_turn_end"
                and parts[1] == "self"
                and parts[2] == "pickup_consumed_item"
            ):
                flags = _unit_flags(unit)
                held = flags.get("held_item")
                if held:
                    continue
                if flags.get("consumed_items") or flags.get("pickup_disabled"):
                    continue
                flags["held_item"] = "leftovers"
                _set_unit_flags(unit, flags, db)
                msg = f"{unit_name}'s {ability_name} found Leftovers!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # Harvest: on_turn_end:self:recycle_berry:50
            if (
                len(parts) >= 4
                and parts[0] == "on_turn_end"
                and parts[1] == "self"
                and parts[2] == "recycle_berry"
            ):
                flags = _unit_flags(unit)
                if flags.get("held_item"):
                    continue
                berry = flags.get("consumed_berry") or flags.get("last_consumed_berry")
                if not berry:
                    continue
                try:
                    chance = int(parts[3])
                except (TypeError, ValueError):
                    chance = 50
                if random.randint(1, 100) > chance:
                    continue
                flags["held_item"] = berry
                _set_unit_flags(unit, flags, db)
                msg = f"{unit_name}'s {ability_name} harvested a Berry!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # Harvest sun: on_weather:sun:on_turn_end:self:recycle_berry:100
            if (
                len(parts) >= 6
                and parts[0] == "on_weather"
                and parts[2] == "on_turn_end"
                and parts[3] == "self"
                and parts[4] == "recycle_berry"
            ):
                if not weather_id_matches(weather_id, parts[1]):
                    continue
                flags = _unit_flags(unit)
                if flags.get("held_item"):
                    continue
                berry = flags.get("consumed_berry") or flags.get("last_consumed_berry")
                if not berry:
                    continue
                try:
                    chance = int(parts[5])
                except (TypeError, ValueError):
                    chance = 100
                if random.randint(1, 100) > chance:
                    continue
                flags["held_item"] = berry
                _set_unit_flags(unit, flags, db)
                msg = f"{unit_name}'s {ability_name} harvested a Berry!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # Healer: on_turn_end:allies:cure_status:50
            if (
                len(parts) >= 4
                and parts[0] == "on_turn_end"
                and parts[1] == "allies"
                and parts[2] == "cure_status"
            ):
                try:
                    chance = int(parts[3])
                except (TypeError, ValueError):
                    chance = 50
                game_id = getattr(unit, "game_id", None) or (
                    getattr(game, "id", None) if game is not None else None
                )
                if not game_id:
                    continue
                allies = (
                    db.query(GameUnit)
                    .filter(
                        GameUnit.game_id == game_id,
                        GameUnit.user_id == getattr(unit, "user_id", None),
                        GameUnit.is_fainted.is_(False),
                        GameUnit.id != getattr(unit, "id", None),
                    )
                    .all()
                )
                for ally in allies:
                    if not _has_any_status(ally):
                        continue
                    if random.randint(1, 100) > chance:
                        continue
                    if cure_status:
                        cure_status(ally, db)
                    else:
                        ally.status_effects = []
                        db.add(ally)
                    ally_name = get_name(ally, db)
                    msg = f"{unit_name}'s {ability_name} cured {ally_name}'s status!"
                    if publish and game is not None:
                        try:
                            publish(getattr(game, "link", None), msg, game_state, db)
                        except Exception:
                            pass
                    changed = True
                continue

            # Moody: on_turn_end:self:raise_random_stat:2
            if (
                len(parts) >= 4
                and parts[0] == "on_turn_end"
                and parts[1] == "self"
                and parts[2] == "raise_random_stat"
            ):
                try:
                    stages = int(parts[3])
                except (TypeError, ValueError):
                    stages = 2
                raise_stat = random.choice(list(MOODY_STATS))
                flags = _unit_flags(unit)
                flags["_moody_raised"] = raise_stat
                _set_unit_flags(unit, flags, db)
                if apply_stat:
                    apply_stat(unit, raise_stat, stages, current_turn, db)
                else:
                    boosts = getattr(unit, "stat_boosts", None)
                    if not isinstance(boosts, dict):
                        boosts = {}
                    instances = list(boosts.get(raise_stat) or [])
                    instances.append({"magnitude": stages, "expires_turn": 4})
                    boosts = dict(boosts)
                    boosts[raise_stat] = instances
                    unit.stat_boosts = boosts
                    db.add(unit)
                msg = f"{unit_name}'s {ability_name} sharply raised its {raise_stat.replace('_', ' ')}!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

            # Moody: on_turn_end:self:lower_other_random_stat:1
            if (
                len(parts) >= 4
                and parts[0] == "on_turn_end"
                and parts[1] == "self"
                and parts[2] == "lower_other_random_stat"
            ):
                try:
                    stages = int(parts[3])
                except (TypeError, ValueError):
                    stages = 1
                flags = _unit_flags(unit)
                raised = flags.get("_moody_raised")
                candidates = [s for s in MOODY_STATS if s != raised]
                if not candidates:
                    candidates = list(MOODY_STATS)
                lower_stat = random.choice(candidates)
                flags.pop("_moody_raised", None)
                _set_unit_flags(unit, flags, db)
                if apply_stat:
                    apply_stat(unit, lower_stat, -abs(stages), current_turn, db)
                else:
                    boosts = getattr(unit, "stat_boosts", None)
                    if not isinstance(boosts, dict):
                        boosts = {}
                    instances = list(boosts.get(lower_stat) or [])
                    instances.append({"magnitude": -abs(stages), "expires_turn": 4})
                    boosts = dict(boosts)
                    boosts[lower_stat] = instances
                    unit.stat_boosts = boosts
                    db.add(unit)
                msg = f"{unit_name}'s {ability_name} lowered its {lower_stat.replace('_', ' ')}!"
                if publish and game is not None:
                    try:
                        publish(getattr(game, "link", None), msg, game_state, db)
                    except Exception:
                        pass
                changed = True
                continue

        if changed:
            uid = getattr(unit, "id", None)
            if isinstance(uid, int):
                mutated.append(uid)

    return mutated


# ---------------------------------------------------------------------------
# Gen 6 helpers (auras, parental bond, steal/heal, primal weather, etc.)
# ---------------------------------------------------------------------------


def field_move_type_power_multiplier(game_id: int | None, move_type: str, db: Session) -> float:
    """Dark Aura / Fairy Aura field power; Aura Break inverts boosts."""
    mt = str(move_type or "").lower().strip()
    if not mt or not isinstance(game_id, int):
        return 1.0

    units = (
        db.query(GameUnit)
        .filter(GameUnit.game_id == game_id, GameUnit.is_fainted.is_(False))
        .all()
    )
    cache: dict = {}
    aura_break = False
    boosts: list[float] = []
    for unit in units:
        effects = get_ability_effects(unit, db, _cache=cache)
        for token in effects:
            parts = _token_parts(token)
            if parts and parts[0] in {"reverse_aura_abilities", "aura_break"}:
                aura_break = True
            if (
                len(parts) >= 5
                and parts[0] == "field"
                and parts[1] == "on_move_type"
                and parts[2] == mt
                and parts[3] == "boost_power"
            ):
                try:
                    boosts.append(float(parts[4]))
                except (TypeError, ValueError):
                    pass

    mult = 1.0
    for boost in boosts:
        if aura_break:
            # Invert: 1.33 → ~0.75 (1/boost), also 2-boost for near-1.33
            if boost != 0:
                mult *= (1.0 / boost)
        else:
            mult *= boost
    return mult


def blocks_ball_bomb_move(defender: GameUnit, move: Any, db: Session) -> bool:
    """Bulletproof: block ball/bomb moves."""
    if not ability_has_token(defender, db, "immune_category:ball_bomb", "bulletproof"):
        return False
    return _move_is_ball_bomb(move)


def parental_bond_hit_count(attacker: GameUnit, move: Any, db: Session) -> int | None:
    """Return 2 for Parental Bond on damaging moves, else None."""
    if not ability_has_token(attacker, db, "multi_hit:2", "second_hit_power", "parental_bond"):
        return None
    if _is_status_move(move):
        return None
    try:
        power = int(getattr(move, "power", 0) or 0)
    except (TypeError, ValueError):
        power = 0
    if power <= 0 and _move_category(move) not in {"physical", "special"}:
        return None
    # Don't stack with native multi-hit moves
    effects = getattr(move, "effects", None)
    if isinstance(effects, list):
        for eff in effects:
            parts = [p for p in str(eff or "").lower().split(":") if p]
            if parts and parts[0] == "multi_hit":
                return None
    return 2


def parental_bond_hit_power_mult(hit_index: int) -> float:
    """Second Parental Bond hit deals 25% power."""
    return 0.25 if int(hit_index) >= 1 else 1.0


def process_cheek_pouch(unit: GameUnit, db: Session) -> list[str]:
    """Heal 1/3 max HP when a Berry is eaten (Cheek Pouch)."""
    messages: list[str] = []
    if unit is None or getattr(unit, "is_fainted", False):
        return messages
    if not ability_has_token(unit, db, "on_berry_eat", "cheek_pouch"):
        return messages
    fraction = 3
    for token in get_ability_effects(unit, db):
        parts = _token_parts(token)
        if (
            len(parts) >= 5
            and parts[0] == "on_berry_eat"
            and parts[1] == "self"
            and parts[2] == "heal_fraction"
        ):
            try:
                fraction = int(parts[3])
            except (TypeError, ValueError):
                fraction = 3
            break
    max_hp = _max_hp(unit)
    if max_hp <= 0:
        return messages
    heal = max(1, max_hp // fraction)
    new_hp = min(max_hp, int(unit.current_hp or 0) + heal)
    if new_hp == int(unit.current_hp or 0):
        return messages
    unit.current_hp = new_hp
    db.add(unit)
    messages.append(f"{_unit_display_name(unit)}'s Cheek Pouch restored HP!")
    return messages


def process_magician_steal(
    attacker: GameUnit,
    target: GameUnit,
    damage: int,
    db: Session,
    *,
    helpers: dict | None = None,
) -> list[str]:
    """Magician: steal target's item after dealing damage if attacker has none."""
    messages: list[str] = []
    helpers = helpers or {}
    if damage <= 0 or attacker is None or target is None:
        return messages
    if getattr(attacker, "is_fainted", False) or getattr(target, "is_fainted", False):
        return messages
    if not ability_has_token(attacker, db, "on_damage_dealt:self:steal_item", "magician"):
        return messages
    if blocks_item_removal(target, db):
        return messages

    get_held = helpers.get("get_unit_held_item")
    set_held = helpers.get("set_unit_held_item")
    if get_held:
        atk_item = get_held(attacker)
        tgt_item = get_held(target)
    else:
        atk_item = _unit_flags(attacker).get("held_item")
        tgt_item = _unit_flags(target).get("held_item")
    if atk_item or not tgt_item:
        return messages

    if set_held:
        set_held(attacker, tgt_item, db)
        set_held(target, None, db)
    else:
        aflags = _unit_flags(attacker)
        tflags = _unit_flags(target)
        aflags["held_item"] = tgt_item
        tflags.pop("held_item", None)
        _set_unit_flags(attacker, aflags, db)
        _set_unit_flags(target, tflags, db)
    messages.append(
        f"{_unit_display_name(attacker)} stole {_unit_display_name(target)}'s {tgt_item}!"
    )
    return messages


def process_symbiosis_transfer(
    consumer: GameUnit,
    db: Session,
    *,
    helpers: dict | None = None,
) -> list[str]:
    """Symbiosis: after ally consumes item, give them your held item."""
    messages: list[str] = []
    helpers = helpers or {}
    if consumer is None:
        return messages
    get_held = helpers.get("get_unit_held_item")
    set_held = helpers.get("set_unit_held_item")

    def _get(u: GameUnit):
        if get_held:
            return get_held(u)
        return _unit_flags(u).get("held_item")

    if _get(consumer):
        return messages  # already has an item

    for ally in _living_allies_including_self(consumer, db):
        if getattr(ally, "id", None) == getattr(consumer, "id", None):
            continue
        if not ability_has_token(ally, db, "on_ally_item_consumed", "symbiosis"):
            continue
        item = _get(ally)
        if not item:
            continue
        if set_held:
            set_held(consumer, item, db)
            set_held(ally, None, db)
        else:
            cflags = _unit_flags(consumer)
            aflags = _unit_flags(ally)
            cflags["held_item"] = item
            aflags.pop("held_item", None)
            _set_unit_flags(consumer, cflags, db)
            _set_unit_flags(ally, aflags, db)
        messages.append(
            f"{_unit_display_name(ally)}'s Symbiosis gave its item to {_unit_display_name(consumer)}!"
        )
        break
    return messages


def process_protean(attacker: GameUnit, move_type: str, db: Session) -> bool:
    """Protean: change type to move type once per switch-in. Returns True if changed."""
    if attacker is None or getattr(attacker, "is_fainted", False):
        return False
    mt = str(move_type or "").lower().strip()
    if not mt:
        return False
    if not ability_has_token(
        attacker, db, "on_move_use:self:change_type:move_type", "protean"
    ):
        return False
    flags = _unit_flags(attacker)
    if flags.get("protean_used"):
        return False
    set_battle_types(attacker, [mt], db)
    flags = _unit_flags(attacker)
    flags["protean_used"] = True
    _set_unit_flags(attacker, flags, db)
    return True


def process_stance_change(attacker: GameUnit, move: Any, db: Session) -> str | None:
    """Stance Change: blade on damaging move, shield on King's Shield. Returns forme or None."""
    if not ability_has_token(attacker, db, "on_attack:change_forme", "on_kings_shield", "stance_change"):
        return None
    slug = _move_slug(move).replace("-", "_")
    flags = _unit_flags(attacker)
    if slug in {"kings_shield", "kingsshield"}:
        flags["forme"] = "shield"
        _set_unit_flags(attacker, flags, db)
        return "shield"
    if not _is_status_move(move):
        try:
            power = int(getattr(move, "power", 0) or 0)
        except (TypeError, ValueError):
            power = 0
        if power > 0 or _move_category(move) in {"physical", "special"}:
            flags["forme"] = "blade"
            _set_unit_flags(attacker, flags, db)
            return "blade"
    return None


def move_type_nullified_by_weather(move_type: str, weather_id: int) -> bool:
    """Primordial Sea / Desolate Land weather nullifies opposing elemental moves."""
    mt = str(move_type or "").lower().strip()
    if weather_id == WEATHER_TO_ID.get("heavy_rain") and mt == "fire":
        return True
    if weather_id == WEATHER_TO_ID.get("harsh_sun") and mt == "water":
        return True
    return False


def apply_strong_winds_type_modifier(
    defender: GameUnit,
    type_multiplier: float,
    weather_id: int,
    db: Session,
    *,
    get_types: Callable | None = None,
) -> float:
    """Delta Stream: super-effective vs Flying becomes neutral under strong winds."""
    if weather_id != WEATHER_TO_ID.get("strong_winds"):
        return type_multiplier
    type_fn = get_types or _default_get_unit_types
    types = type_fn(defender, db) if callable(type_fn) else set()
    if "flying" not in {str(t).lower() for t in (types or set())}:
        return type_multiplier
    # Neutralize the SE contribution against Flying (×2 → ×1)
    if type_multiplier >= 2.0:
        return type_multiplier / 2.0
    return type_multiplier


def flying_move_priority_bonus(attacker: GameUnit, move: Any, db: Session) -> int:
    """Gale Wings: +1 priority for Flying moves at full HP. Unused by games priority yet."""
    if attacker is None:
        return 0
    max_hp = _max_hp(attacker)
    if max_hp <= 0 or int(attacker.current_hp or 0) < max_hp:
        return 0
    mt = _move_type(move)
    converted = convert_move_type(attacker, move, db)
    if converted:
        mt = converted
    if mt != "flying":
        return 0
    effects = get_ability_effects(attacker, db)
    for token in effects:
        parts = _token_parts(token)
        if (
            len(parts) >= 5
            and parts[0] == "on_hp_full"
            and parts[1] == "on_move_type"
            and parts[2] == "flying"
            and parts[3] == "priority"
        ):
            try:
                return int(parts[4])
            except (TypeError, ValueError):
                return 1
        if token.lower() == "gale_wings":
            return 1
    return 0


def parse_stat_lowered_reactions(unit: GameUnit, db: Session) -> list[tuple[str, int]]:
    """Parse Defiant/Competitive tokens → list of (stat, stages) to raise."""
    out: list[tuple[str, int]] = []
    for token in get_ability_effects(unit, db):
        parts = _token_parts(token)
        if not (
            len(parts) >= 5
            and parts[0] == "on_stat_lowered_by_opponent"
            and parts[1] == "self"
            and parts[2] == "raise_stat"
        ):
            continue
        stat = _normalize_stat_name(parts[3])
        try:
            stages = int(parts[4])
        except (TypeError, ValueError):
            stages = 2
        out.append((stat, stages))
    return out


# ---------------------------------------------------------------------------
# Convenience: sound / explosion checks used by games wrappers
# ---------------------------------------------------------------------------


def should_block_move_against(
    defender: GameUnit,
    move: Any,
    db: Session,
) -> str | None:
    """Return a reason string if the defender's ability fully blocks the move."""
    if blocks_sound_move(defender, db) and _move_is_sound(move):
        return "soundproof"
    if blocks_ball_bomb_move(defender, move, db):
        return "bulletproof"
    if ability_has_token(defender, db, "immune_category:wind", "wind_rider") and _move_is_wind(move):
        return "wind_rider"
    if ability_has_token(defender, db, "immune_category:status_moves", "good_as_gold") and _is_status_move(move):
        return "good_as_gold"
    if move_is_explosion_like(move):
        game_id = getattr(defender, "game_id", None)
        if isinstance(game_id, int) and blocks_explosion(game_id, db):
            return "damp"
    return None


def should_mirror_status(unit: GameUnit, status: str, db: Session) -> bool:
    """True if Synchronize should copy this status onto the attacker."""
    status_n = _normalize_status_name(status)
    if status_n not in {"burn", "paralysis", "poison", "badly_poisoned"}:
        return False
    return ability_has_token(unit, db, "on_statused:mirror_status", "synchronize")


def unit_traps_opponent(
    trapper: GameUnit,
    victim: GameUnit,
    db: Session,
    *,
    get_types: Callable | None = None,
) -> bool:
    """Arena Trap / Shadow Tag / Magnet Pull adjacency trap check."""
    if trapper is None or victim is None:
        return False
    if getattr(trapper, "is_fainted", False) or getattr(victim, "is_fainted", False):
        return False
    if getattr(trapper, "user_id", None) == getattr(victim, "user_id", None):
        return False
    if _is_ability_suppressed(trapper, db):
        return False

    effects = get_ability_effects(trapper, db)
    if not effects:
        return False

    # Ghost types escape most traps in mainline; keep that rule.
    type_fn = get_types or _default_get_unit_types
    victim_types = type_fn(victim, db) if callable(type_fn) else set()
    if "ghost" in victim_types:
        return False

    for token in effects:
        parts = _token_parts(token)
        if not parts or parts[0] != "trap_opponents":
            continue
        kind = parts[1] if len(parts) > 1 else "all"
        if kind in {"", "all"}:
            return True
        if kind == "grounded":
            # Arena Trap: grounded only (not Flying / Levitate)
            if "flying" in victim_types:
                return False
            if ability_has_token(victim, db, "immune:ground", "levitate"):
                return False
            return True
        if kind == "steel":
            return "steel" in victim_types
    return False


def is_trapped_by_adjacent_opponent(
    unit: GameUnit,
    db: Session,
    *,
    get_types: Callable | None = None,
) -> bool:
    """True if an adjacent opposing unit's ability prevents this unit from fleeing."""
    if unit is None or getattr(unit, "is_fainted", False):
        return False
    # Run Away / Ghost escape
    if ability_has_token(unit, db, "guaranteed_flee", "run_away"):
        return False
    type_fn = get_types or _default_get_unit_types
    if "ghost" in type_fn(unit, db):
        return False

    game_id = getattr(unit, "game_id", None)
    if not isinstance(game_id, int):
        return False
    ux, uy = int(getattr(unit, "current_x", -1) or -1), int(getattr(unit, "current_y", -1) or -1)
    if ux < 0 or uy < 0:
        return False

    opponents = (
        db.query(GameUnit)
        .filter(
            GameUnit.game_id == game_id,
            GameUnit.user_id != getattr(unit, "user_id", None),
            GameUnit.is_fainted.is_(False),
        )
        .all()
    )
    for opp in opponents:
        ox, oy = int(getattr(opp, "current_x", -1) or -1), int(getattr(opp, "current_y", -1) or -1)
        if ox < 0 or oy < 0:
            continue
        if abs(ox - ux) + abs(oy - uy) != 1:
            continue
        if unit_traps_opponent(opp, unit, db, get_types=get_types):
            return True
    return False


# ---------------------------------------------------------------------------
# Gen 7 helpers
# ---------------------------------------------------------------------------


def neuroforce_power_multiplier(attacker: GameUnit, type_multiplier: float, db: Session) -> float:
    """Neuroforce: boost power when dealing super-effective damage."""
    if type_multiplier is None or float(type_multiplier) <= 1.0:
        return 1.0
    effects = get_ability_effects(attacker, db)
    for token in effects:
        parts = _token_parts(token)
        if (
            len(parts) >= 4
            and parts[0] == "on_super_effective_deal"
            and parts[1] == "self"
            and parts[2] == "boost_power"
        ):
            try:
                return float(parts[3])
            except (TypeError, ValueError):
                return 1.25
        if token.lower() == "neuroforce":
            return 1.25
    return 1.0


def move_makes_contact(attacker: GameUnit, move: Any, db: Session) -> bool:
    """Return whether a move makes contact after Long Reach removes the flag."""
    if not bool(getattr(move, "makes_contact", False)):
        return False
    if ability_has_token(attacker, db, "remove_contact_flag", "long_reach"):
        return False
    return True


def guaranteed_crit_vs(attacker: GameUnit, target: GameUnit, db: Session) -> bool:
    """Merciless: guaranteed crit vs poisoned / badly poisoned targets."""
    if attacker is None or target is None:
        return False
    status = _active_status(target)
    if status not in {"poison", "badly_poisoned"}:
        return False
    effects = get_ability_effects(attacker, db)
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 3 and parts[0] == "on_target_status" and parts[2] == "guaranteed_crit":
            wanted = _normalize_status_name(parts[1])
            if wanted == status:
                return True
            if wanted == "poison" and status in {"poison", "badly_poisoned"}:
                return True
            if wanted == "badly_poisoned" and status == "badly_poisoned":
                return True
        if token.lower() == "merciless":
            return True
    return False


def mark_just_switched_in(unit: GameUnit, db: Session) -> None:
    """Flag a unit as freshly switched in (Stakeout)."""
    if unit is None:
        return
    flags = _unit_flags(unit)
    flags["just_switched_in"] = True
    _set_unit_flags(unit, flags, db)


def clear_just_switched_in(unit: GameUnit, db: Session) -> None:
    """Clear Stakeout just-switched-in flag."""
    if unit is None:
        return
    flags = _unit_flags(unit)
    if "just_switched_in" not in flags:
        return
    flags.pop("just_switched_in", None)
    _set_unit_flags(unit, flags, db)


def clear_just_switched_in_for_opponents(
    game_id: int,
    acting_user_id: int,
    db: Session,
) -> None:
    """Clear just_switched_in on the opposing side at end of a player's turn."""
    if not isinstance(game_id, int):
        return
    opponents = (
        db.query(GameUnit)
        .filter(
            GameUnit.game_id == game_id,
            GameUnit.user_id != acting_user_id,
            GameUnit.is_fainted.is_(False),
        )
        .all()
    )
    for opp in opponents:
        clear_just_switched_in(opp, db)


def corrosion_bypasses_type_immunity(
    attacker: GameUnit,
    status: str,
    defender_types: set[str] | list[str] | None,
    db: Session,
) -> bool:
    """True if Corrosion lets poison apply through Steel/Poison type immunity."""
    status_n = _normalize_status_name(status)
    if status_n not in {"poison", "badly_poisoned"}:
        return False
    if attacker is None:
        return False
    types = {str(t).lower() for t in (defender_types or []) if t}
    effects = get_ability_effects(attacker, db)
    allowed: set[str] = set()
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 2 and parts[0] == "can_poison":
            allowed.add(parts[1])
        elif token.lower() == "corrosion":
            allowed.update({"steel", "poison"})
    if not allowed:
        return False
    # Bypass only when the immunity comes from a type Corrosion can poison
    immune_hits = types & {"steel", "poison"}
    if not immune_hits:
        return False
    return immune_hits.issubset(allowed) or bool(allowed & immune_hits)


def can_poison_target(attacker: GameUnit, target: GameUnit, db: Session) -> bool:
    """True if attacker can poison target (Corrosion bypasses Steel/Poison)."""
    if target is None:
        return False
    types = get_battle_types(target, db)
    # Without Corrosion, steel/poison are immune
    if types & {"steel", "poison"}:
        return corrosion_bypasses_type_immunity(attacker, "poison", types, db)
    return True


def apply_disguise(
    defender: GameUnit,
    damage: int,
    db: Session,
) -> tuple[int, list[str]]:
    """Disguise: block first damaging hit, bust forme, return 1/8 max HP chip."""
    return process_disguise(defender, damage, db)


def process_disguise(
    defender: GameUnit,
    damage: int,
    db: Session,
) -> tuple[int, list[str]]:
    """Disguise helper. Returns (final_damage, messages)."""
    messages: list[str] = []
    if damage <= 0 or defender is None or getattr(defender, "is_fainted", False):
        return damage, messages
    flags = _unit_flags(defender)
    if flags.get("disguise_busted") or flags.get("forme") == "busted":
        return damage, messages
    if not ability_has_token(
        defender, db, "on_first_hit:block_damage", "change_forme:busted", "disguise"
    ):
        return damage, messages

    fraction = 8
    for token in get_ability_effects(defender, db):
        parts = _token_parts(token)
        if (
            len(parts) >= 4
            and parts[0] == "on_disguise_break"
            and parts[1] == "self"
            and parts[2] == "damage_fraction"
        ):
            try:
                fraction = int(parts[3])
            except (TypeError, ValueError):
                fraction = 8
            break

    max_hp = _max_hp(defender)
    chip = max(1, max_hp // fraction) if max_hp > 0 else 0
    flags["disguise_busted"] = True
    flags["forme"] = "busted"
    _set_unit_flags(defender, flags, db)
    name = _unit_display_name(defender)
    ability = get_active_ability(defender, db)
    ability_name = getattr(ability, "name", None) or "Disguise"
    messages.append(f"{name}'s {ability_name} was busted!")
    return chip, messages


def process_innards_out(
    fainted: GameUnit,
    attacker: GameUnit,
    *,
    hp_lost: int,
    db: Session,
) -> list[str]:
    """Innards Out: deal HP lost to the attacker when fainted by move damage."""
    messages: list[str] = []
    if fainted is None or attacker is None:
        return messages
    if getattr(attacker, "is_fainted", False):
        return messages
    if hp_lost <= 0:
        return messages
    if not ability_has_token(
        fainted, db, "on_faint_from_move:attacker:damage_equal_to_hp_lost", "innards_out"
    ):
        return messages
    if should_ignore_indirect_damage(attacker, db):
        return messages

    dmg = int(hp_lost)
    new_hp = max(0, int(attacker.current_hp or 0) - dmg)
    attacker.current_hp = new_hp
    if new_hp <= 0:
        attacker.is_fainted = True
    db.add(attacker)
    name = _unit_display_name(fainted)
    atk_name = _unit_display_name(attacker)
    messages.append(f"{atk_name} was hurt by {name}'s Innards Out!")
    return messages


def process_any_faint(
    fainted: GameUnit,
    living_units: list[GameUnit],
    db: Session,
    current_turn: int,
    helpers: dict | None = None,
) -> list[str]:
    """Soul-Heart: living units raise SpA when any other unit faints."""
    helpers = helpers or {}
    apply_stat: Callable | None = helpers.get("apply_stat_change")
    messages: list[str] = []
    if fainted is None:
        return messages

    cache: dict = {}
    for unit in living_units or []:
        if unit is None or getattr(unit, "is_fainted", False):
            continue
        if getattr(unit, "id", None) == getattr(fainted, "id", None):
            continue
        if int(getattr(unit, "current_hp", 0) or 0) <= 0:
            continue
        effects = get_ability_effects(unit, db, _cache=cache)
        for token in effects:
            parts = _token_parts(token)
            if not (
                len(parts) >= 5
                and parts[0] == "on_any_faint"
                and parts[1] == "self"
                and parts[2] == "raise_stat"
            ):
                continue
            stat = _normalize_stat_name(parts[3])
            try:
                stages = int(parts[4])
            except (TypeError, ValueError):
                stages = 1
            if apply_stat:
                try:
                    apply_stat(unit, stat, stages, current_turn, db)
                except TypeError:
                    apply_stat(unit, stat, stages, current_turn, db)
            else:
                boosts = getattr(unit, "stat_boosts", None)
                if not isinstance(boosts, dict):
                    boosts = {}
                instances = list(boosts.get(stat) or [])
                instances.append({"magnitude": stages, "expires_turn": 4})
                boosts = dict(boosts)
                boosts[stat] = instances
                unit.stat_boosts = boosts
                db.add(unit)
            ability = get_active_ability(unit, db, _cache=cache)
            ability_name = getattr(ability, "name", None) or "Soul-Heart"
            messages.append(
                f"{_unit_display_name(unit)}'s {ability_name} raised its {stat.replace('_', ' ')}!"
            )
    return messages


def process_receiver_on_ally_faint(
    fainted: GameUnit,
    living_allies: list[GameUnit],
    db: Session,
    helpers: dict | None = None,
) -> list[str]:
    """Receiver / Power of Alchemy: copy a fainted ally's ability."""
    helpers = helpers or {}
    set_ability: Callable | None = helpers.get("set_unit_ability_id")
    messages: list[str] = []
    if fainted is None:
        return messages
    source_id = _get_unit_ability_id(fainted)
    if source_id is None:
        return messages

    cache: dict = {}
    for unit in living_allies or []:
        if unit is None or getattr(unit, "is_fainted", False):
            continue
        if getattr(unit, "id", None) == getattr(fainted, "id", None):
            continue
        if getattr(unit, "user_id", None) != getattr(fainted, "user_id", None):
            continue
        if not ability_has_token(
            unit, db, "on_ally_faint:self:copy_ability", "receiver", "power_of_alchemy", _cache=cache
        ):
            continue
        if set_ability:
            set_ability(unit, source_id, db)
        else:
            flags = _unit_flags(unit)
            flags["ability_id"] = int(source_id)
            _set_unit_flags(unit, flags, db)
        copied = db.query(Ability).filter(Ability.id == source_id).first()
        copied_name = getattr(copied, "name", None) or "ability"
        ability = get_active_ability(unit, db)
        # Ability already overwritten; use slug-friendly name from prior
        messages.append(
            f"{_unit_display_name(unit)} received {copied_name}!"
        )
        del ability
    return messages


def ensure_comatose_sleep(unit: GameUnit, db: Session) -> bool:
    """Apply permanent sleep for Comatose. Returns True if applied/confirmed."""
    if unit is None or getattr(unit, "is_fainted", False):
        return False
    if not ability_has_token(unit, db, "permanent_status:sleep", "can_act_while_asleep", "comatose"):
        return False
    status = _active_status(unit)
    if status == "sleep":
        return True
    # Force sleep with a very long duration; can_act_while_asleep unlocks moves.
    unit.status_effects = ["sleep", 999]
    db.add(unit)
    return True


def can_act_while_asleep(unit: GameUnit, db: Session) -> bool:
    """Comatose: unit keeps can_move while asleep."""
    return ability_has_token(unit, db, "can_act_while_asleep", "comatose")


def blocks_priority_against(defender_side_unit: GameUnit, db: Session) -> bool:
    """Queenly Majesty / Dazzling: self or living ally blocks priority moves.

    Games currently has no priority sort; expose this for callers/tests.
    """
    if defender_side_unit is None:
        return False
    for unit in _living_allies_including_self(defender_side_unit, db):
        for token in get_ability_effects(unit, db):
            parts = _token_parts(token)
            if (
                len(parts) >= 3
                and parts[0] == "self_and_allies"
                and parts[1] == "immune_category"
                and parts[2] == "priority"
            ):
                return True
            if token.lower() in {"queenly_majesty", "dazzling"}:
                return True
    return False


def healing_move_priority_bonus(attacker: GameUnit, move: Any, db: Session) -> int:
    """Triage: +3 priority for healing moves (heal/drain). Stub like Gale Wings."""
    if attacker is None or move is None:
        return 0
    if not _is_healing_move(move):
        return 0
    effects = get_ability_effects(attacker, db)
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 2 and parts[0] == "priority_healing":
            try:
                return int(parts[1])
            except (TypeError, ValueError):
                return 3
        if token.lower() == "triage":
            return 3
    return 0


def _is_healing_move(move: Any) -> bool:
    effects = getattr(move, "effects", None) or []
    for eff in effects:
        token = str(eff or "").lower()
        parts = [p for p in token.split(":") if p]
        if not parts:
            continue
        if "heal" in parts or "drain" in parts:
            return True
        if parts[0] in {"heal", "drain"} or (len(parts) >= 2 and parts[1] in {"heal", "drain"}):
            return True
    # Soft fallbacks by slug
    slug = _move_slug(move)
    heal_slugs = {
        "recover",
        "soft_boiled",
        "softboiled",
        "roost",
        "moonlight",
        "morning_sun",
        "synthesis",
        "slack_off",
        "heal_order",
        "milk_drink",
        "shore_up",
        "drain_punch",
        "giga_drain",
        "mega_drain",
        "absorb",
        "leech_life",
        "horn_leech",
        "parabolic_charge",
        "draining_kiss",
        "oblivion_wing",
        "strength_sap",
    }
    return slug in heal_slugs


def process_emergency_exit_or_wimp_out(
    unit: GameUnit,
    *,
    before_hp: int,
    db: Session,
) -> list[str]:
    """Emergency Exit / Wimp Out: flag wants_switch_out when HP crosses ≤50%."""
    messages: list[str] = []
    if unit is None or getattr(unit, "is_fainted", False):
        return messages
    if not ability_has_token(unit, db, "on_hp_below:50:force_switch_out", "emergency_exit", "wimp_out"):
        return messages
    max_hp = _max_hp(unit)
    if max_hp <= 0:
        return messages
    after_hp = int(unit.current_hp or 0)
    threshold = max_hp * 0.5
    if before_hp > threshold and after_hp <= threshold and after_hp > 0:
        flags = _unit_flags(unit)
        flags["wants_switch_out"] = True
        _set_unit_flags(unit, flags, db)
        unit.can_move = False
        db.add(unit)
        ability = get_active_ability(unit, db)
        ability_name = getattr(ability, "name", None) or "ability"
        messages.append(f"{_unit_display_name(unit)} wants to switch out with {ability_name}!")
    return messages


def update_hp_threshold_formes(unit: GameUnit, db: Session) -> bool:
    """Schooling / Shields Down / Power Construct forme flags from HP thresholds."""
    if unit is None:
        return False
    effects = get_ability_effects(unit, db)
    if not effects:
        return False
    hp_pct = _hp_percent(unit)
    flags = _unit_flags(unit)
    changed = False
    # Prefer above tokens first so dual schooling tokens resolve cleanly
    above: list[tuple[float, str]] = []
    below: list[tuple[float, str]] = []
    for token in effects:
        parts = _token_parts(token)
        if len(parts) >= 4 and parts[0] == "on_hp_above" and parts[2] == "change_forme":
            try:
                above.append((float(parts[1]), parts[3]))
            except (TypeError, ValueError):
                pass
        if len(parts) >= 4 and parts[0] == "on_hp_below" and parts[2] == "change_forme":
            try:
                below.append((float(parts[1]), parts[3]))
            except (TypeError, ValueError):
                pass
    new_forme = flags.get("forme")
    for threshold, forme in above:
        if hp_pct > threshold:
            new_forme = forme
    for threshold, forme in below:
        if hp_pct <= threshold:
            new_forme = forme
    if new_forme != flags.get("forme"):
        if new_forme:
            flags["forme"] = new_forme
        else:
            flags.pop("forme", None)
        _set_unit_flags(unit, flags, db)
        changed = True
    return changed


def is_dance_move(move: Any) -> bool:
    """True if the move is a known dance move for Dancer."""
    if move is None:
        return False
    slug = _move_slug(move)
    if slug in DANCE_MOVE_SLUGS:
        return True
    name = str(getattr(move, "name", "") or "").lower().replace(" ", "_").replace("-", "_")
    return name in DANCE_MOVE_SLUGS


def process_dancer_copy(
    move: Any,
    move_user: GameUnit,
    living_units: list[GameUnit],
    db: Session,
    current_turn: int,
    helpers: dict | None = None,
) -> list[str]:
    """Best-effort Dancer: copy raise_stat effects from a dance move onto Dancer units."""
    helpers = helpers or {}
    apply_stat: Callable | None = helpers.get("apply_stat_change")
    messages: list[str] = []
    if not is_dance_move(move) or move_user is None:
        return messages

    raise_effects: list[tuple[str, int]] = []
    for eff in getattr(move, "effects", None) or []:
        parts = _token_parts(str(eff))
        if len(parts) >= 4 and parts[0] == "self" and parts[1] == "raise_stat":
            raise_effects.append((_normalize_stat_name(parts[2]), int(parts[3]) if parts[3].lstrip("-").isdigit() else 1))
        elif len(parts) >= 4 and parts[1] == "raise_stat":
            # recipient:raise_stat:stat:N
            try:
                stages = int(parts[3])
            except (TypeError, ValueError):
                stages = 1
            raise_effects.append((_normalize_stat_name(parts[2]), stages))

    if not raise_effects:
        return messages

    cache: dict = {}
    for unit in living_units or []:
        if unit is None or getattr(unit, "is_fainted", False):
            continue
        if getattr(unit, "id", None) == getattr(move_user, "id", None):
            continue
        if not ability_has_token(unit, db, "on_dance_move_used:copy_immediately", "dancer", _cache=cache):
            continue
        for stat, stages in raise_effects:
            if apply_stat:
                try:
                    apply_stat(unit, stat, stages, current_turn, db)
                except TypeError:
                    apply_stat(unit, stat, stages, current_turn, db)
            else:
                boosts = getattr(unit, "stat_boosts", None)
                if not isinstance(boosts, dict):
                    boosts = {}
                instances = list(boosts.get(stat) or [])
                instances.append({"magnitude": stages, "expires_turn": 4})
                boosts = dict(boosts)
                boosts[stat] = instances
                unit.stat_boosts = boosts
                db.add(unit)
        messages.append(f"{_unit_display_name(unit)} copied the dance with Dancer!")
    return messages


# ---------------------------------------------------------------------------
# Gen 8 helpers
# ---------------------------------------------------------------------------


def process_ice_face(
    defender: GameUnit,
    damage: int,
    *,
    is_physical: bool,
    db: Session,
) -> tuple[int, list[str]]:
    """Ice Face: block one physical hit, change to Noice forme. Returns (damage, msgs)."""
    messages: list[str] = []
    if damage <= 0 or defender is None or getattr(defender, "is_fainted", False):
        return damage, messages
    if not is_physical:
        return damage, messages
    flags = _unit_flags(defender)
    if flags.get("ice_face_broken") or flags.get("forme") == "noice":
        return damage, messages
    if not ability_has_token(
        defender, db, "on_physical_hit:block_and_change_forme", "ice_face"
    ):
        return damage, messages

    flags["ice_face_broken"] = True
    flags["forme"] = "noice"
    _set_unit_flags(defender, flags, db)
    name = _unit_display_name(defender)
    ability = get_active_ability(defender, db)
    ability_name = getattr(ability, "name", None) or "Ice Face"
    messages.append(f"{name}'s {ability_name} blocked the hit!")
    return 0, messages


def apply_ice_face(
    defender: GameUnit,
    damage: int,
    *,
    is_physical: bool,
    db: Session,
) -> tuple[int, list[str]]:
    return process_ice_face(defender, damage, is_physical=is_physical, db=db)


def berry_effect_multiplier(unit: GameUnit, db: Session) -> float:
    """Ripen: double berry effects when the ability is active."""
    if ability_has_token(unit, db, "double_berry_effects", "ripen"):
        return 2.0
    return 1.0


def locks_first_selected_move(unit: GameUnit, db: Session) -> bool:
    """Gorilla Tactics: Choice-style lock to first selected move."""
    return ability_has_token(unit, db, "lock_move:first_selected", "gorilla_tactics")


def enforce_gorilla_tactics_lock(
    unit: GameUnit,
    move_id: int,
    db: Session,
) -> int | None:
    """Record/return locked move id for Gorilla Tactics. None if unlocked/ok."""
    if not locks_first_selected_move(unit, db):
        return None
    flags = _unit_flags(unit)
    locked = flags.get("locked_move_id")
    if locked is None:
        flags["locked_move_id"] = int(move_id)
        _set_unit_flags(unit, flags, db)
        return None
    try:
        locked_i = int(locked)
    except (TypeError, ValueError):
        flags["locked_move_id"] = int(move_id)
        _set_unit_flags(unit, flags, db)
        return None
    if locked_i != int(move_id):
        return locked_i
    return None


def contact_bypasses_protect(attacker: GameUnit, db: Session) -> bool:
    """Unseen Fist: contact moves bypass Protect (when Protect exists)."""
    return ability_has_token(attacker, db, "contact_bypass_protect", "unseen_fist")


def quick_draw_goes_first(unit: GameUnit, db: Session) -> bool:
    """Quick Draw: 30% chance to go first at same priority (caller must roll/order)."""
    for token in get_ability_effects(unit, db):
        parts = _token_parts(token)
        if (
            len(parts) >= 3
            and parts[0] == "on_same_priority"
            and parts[1] == "go_first"
        ):
            try:
                chance = int(parts[2])
            except (TypeError, ValueError):
                chance = 30
            return random.randint(1, 100) <= chance
        if token.lower() == "quick_draw":
            return random.randint(1, 100) <= 30
    return False


def process_gulp_missile_spit(
    defender: GameUnit,
    attacker: GameUnit,
    damage: int,
    db: Session,
) -> list[str]:
    """Gulp Missile stub: if prey flag set, spit at attacker for 1/4 max HP."""
    messages: list[str] = []
    if damage <= 0 or defender is None or attacker is None:
        return messages
    flags = _unit_flags(defender)
    prey = flags.get("gulp_prey")
    if not prey:
        return messages
    if not ability_has_token(defender, db, "on_damage_taken:spit_prey", "gulp_missile"):
        return messages
    max_hp = _max_hp(attacker)
    dmg = max(1, max_hp // 4) if max_hp > 0 else 0
    if dmg > 0 and not should_ignore_indirect_damage(attacker, db):
        new_hp = max(0, int(attacker.current_hp or 0) - dmg)
        attacker.current_hp = new_hp
        if new_hp <= 0:
            attacker.is_fainted = True
        db.add(attacker)
    flags.pop("gulp_prey", None)
    _set_unit_flags(defender, flags, db)
    messages.append(
        f"{_unit_display_name(defender)} spat its prey at {_unit_display_name(attacker)}!"
    )
    return messages


def maybe_catch_gulp_prey(unit: GameUnit, move: Any, db: Session) -> bool:
    """Gulp Missile: Surf/Dive sets prey flag (forme stub)."""
    if not ability_has_token(unit, db, "on_surf_or_dive:catch_prey", "gulp_missile"):
        return False
    slug = _move_slug(move)
    if slug not in {"surf", "dive"}:
        return False
    flags = _unit_flags(unit)
    flags["gulp_prey"] = "gulping" if _hp_percent(unit) >= 50 else "gorging"
    flags["forme"] = flags["gulp_prey"]
    _set_unit_flags(unit, flags, db)
    return True


# ---------------------------------------------------------------------------
# Gen 9 helpers
# ---------------------------------------------------------------------------


def _highest_stat_for_drive(unit: GameUnit) -> str:
    """Pick highest among Atk/Def/SpA/SpD/Spe for Protosynthesis / Quark Drive."""
    stats = getattr(unit, "current_stats", None) or {}
    best = "attack"
    best_val = -1
    for stat in ("attack", "defense", "sp_attack", "sp_defense", "speed"):
        try:
            val = int(stats.get(stat, 0) or 0)
        except (TypeError, ValueError):
            val = 0
        if val > best_val:
            best_val = val
            best = stat
    return best


def _protosynthesis_or_quark_boost(
    unit: GameUnit,
    db: Session,
    *,
    weather_id: int = 0,
    terrain_id: int = 0,
) -> tuple[str, float] | None:
    """Return (stat, mult) when Protosynthesis / Quark Drive is active."""
    effects = get_ability_effects(unit, db)
    if not effects:
        return None
    flags = _unit_flags(unit)
    activated = bool(flags.get("booster_energy_active") or flags.get("drive_boost_active"))

    for token in effects:
        parts = _token_parts(token)
        # on_weather:sun:boost_highest_stat:1.3
        if (
            len(parts) >= 4
            and parts[0] == "on_weather"
            and parts[2] == "boost_highest_stat"
        ):
            if weather_id_matches(weather_id, parts[1]) or activated:
                try:
                    mult = float(parts[3])
                except (TypeError, ValueError):
                    mult = 1.3
                return _highest_stat_for_drive(unit), mult
        # on_terrain:electric:boost_highest_stat:1.3
        if (
            len(parts) >= 4
            and parts[0] == "on_terrain"
            and parts[2] == "boost_highest_stat"
        ):
            expected = TERRAIN_TO_ID.get(parts[1])
            if (expected is not None and terrain_id == expected) or activated:
                try:
                    mult = float(parts[3])
                except (TypeError, ValueError):
                    mult = 1.3
                return _highest_stat_for_drive(unit), mult
        # on_held_item:booster_energy:boost_highest_stat:1.3
        if (
            len(parts) >= 5
            and parts[0] == "on_held_item"
            and parts[1] == "booster_energy"
            and parts[2] == "boost_highest_stat"
        ):
            held = flags.get("held_item")
            held_s = str(held or "").lower()
            if "booster" in held_s or activated:
                try:
                    mult = float(parts[3])
                except (TypeError, ValueError):
                    mult = 1.3
                return _highest_stat_for_drive(unit), mult
    return None


def activate_booster_energy(unit: GameUnit, db: Session) -> bool:
    """Consume Booster Energy and activate Protosynthesis/Quark Drive flag."""
    if not ability_has_token(
        unit, db, "on_held_item:booster_energy", "protosynthesis", "quark_drive"
    ):
        return False
    flags = _unit_flags(unit)
    held = str(flags.get("held_item") or "").lower()
    if "booster" not in held:
        return False
    flags.pop("held_item", None)
    flags["booster_energy_active"] = True
    flags["drive_boost_active"] = True
    _set_unit_flags(unit, flags, db)
    return True


def tera_shell_type_multiplier(
    defender: GameUnit,
    type_multiplier: float,
    db: Session,
    *,
    damaging: bool = True,
) -> float:
    """Tera Shell: at full HP, treat damaging moves as not very effective."""
    if not damaging:
        return type_multiplier
    if not ability_has_token(
        defender, db, "on_hp_full:all_damaging_moves:not_very_effective", "tera_shell"
    ):
        return type_multiplier
    max_hp = _max_hp(defender)
    if max_hp <= 0 or int(defender.current_hp or 0) < max_hp:
        return type_multiplier
    return min(float(type_multiplier), 0.5)


def process_toxic_chain(
    attacker: GameUnit,
    target: GameUnit,
    *,
    damage: int,
    db: Session,
    helpers: dict | None = None,
) -> list[str]:
    """Toxic Chain: chance to badly poison on dealing damage."""
    helpers = helpers or {}
    messages: list[str] = []
    if damage <= 0 or attacker is None or target is None:
        return messages
    if getattr(target, "is_fainted", False):
        return messages
    apply_status = helpers.get("apply_status_effect")
    for token in get_ability_effects(attacker, db):
        parts = _token_parts(token)
        if not (
            len(parts) >= 5
            and parts[0] == "on_damage_dealt"
            and parts[1] == "target"
            and parts[2] == "status"
        ):
            continue
        status_n = _normalize_status_name(parts[3])
        try:
            chance = int(parts[4])
        except (TypeError, ValueError):
            chance = 30
        if random.randint(1, 100) > chance:
            continue
        if not can_apply_status(target, status_n, db):
            continue
        if _has_any_status(target):
            continue
        applied = False
        if apply_status:
            try:
                applied = bool(apply_status(target, status_n, db, source=attacker))
            except TypeError:
                applied = bool(apply_status(target, status_n, db))
        else:
            target.status_effects = [status_n, 9999, 1] if status_n == "badly_poisoned" else [status_n, 7]
            db.add(target)
            applied = True
        if applied:
            messages.append(
                f"{_unit_display_name(attacker)}'s Toxic Chain poisoned {_unit_display_name(target)}!"
            )
    return messages


def copies_opponent_stat_boosts(unit: GameUnit, db: Session) -> bool:
    """Opportunist: copy opponent's positive stat boosts."""
    return ability_has_token(unit, db, "on_opponent_stat_boost:copy_stat_boosts", "opportunist")


def process_poison_puppeteer(
    source: GameUnit,
    target: GameUnit,
    status: str,
    db: Session,
    helpers: dict | None = None,
) -> list[str]:
    """Poison Puppeteer: also confuse when this unit poisons a target."""
    helpers = helpers or {}
    messages: list[str] = []
    status_n = _normalize_status_name(status)
    if status_n not in {"poison", "badly_poisoned"}:
        return messages
    if source is None or target is None:
        return messages
    if not ability_has_token(source, db, "on_poison_dealt:also:apply_state:confusion", "poison_puppeteer"):
        return messages
    if not can_apply_state(target, "confusion", db):
        return messages
    apply_state = helpers.get("apply_state_effect")
    applied = False
    if apply_state:
        try:
            applied = bool(apply_state(target, "confusion", db))
        except TypeError:
            applied = False
    if not applied:
        states = _normalize_states(getattr(target, "states", None))
        if not (states and int(states[1]) > 0):
            target.states = ["confusion", random.randint(2, 5)]
            db.add(target)
            applied = True
    if applied:
        messages.append(
            f"{_unit_display_name(target)} became confused from {_unit_display_name(source)}'s Poison Puppeteer!"
        )
    return messages


def process_cud_chew_on_berry_eat(unit: GameUnit, db: Session) -> bool:
    """Cud Chew: queue last berry for reuse next turn."""
    if not ability_has_token(unit, db, "on_berry_eat:reuse_next_turn", "cud_chew"):
        return False
    flags = _unit_flags(unit)
    berry = flags.get("last_consumed_berry") or flags.get("consumed_berry")
    if not berry:
        return False
    flags["cud_chew_berry"] = berry
    flags["cud_chew_pending"] = True
    _set_unit_flags(unit, flags, db)
    return True


def process_cud_chew_end_of_turn(unit: GameUnit, db: Session) -> list[str]:
    """Reuse queued berry at end of turn (flag clear; actual berry effects are stubbed)."""
    messages: list[str] = []
    flags = _unit_flags(unit)
    if not flags.get("cud_chew_pending"):
        return messages
    berry = flags.pop("cud_chew_berry", None)
    flags.pop("cud_chew_pending", None)
    _set_unit_flags(unit, flags, db)
    if berry:
        messages.append(
            f"{_unit_display_name(unit)} chewed its {berry} again with Cud Chew!"
        )
    return messages


def status_moves_ignore_target_ability(attacker: GameUnit, move: Any, db: Session) -> bool:
    """Mycelium Might: status moves ignore the target's ability."""
    if not _is_status_move(move):
        return False
    return ability_has_token(
        attacker, db, "status_moves:ignore_target_ability", "mycelium_might"
    )


def immune_to_forced_switch(unit: GameUnit, db: Session) -> bool:
    """Guard Dog / Suction Cups: cannot be forced out."""
    return ability_has_token(unit, db, "immune_forced_switch", "guard_dog", "suction_cups")


def electric_move_charge_multiplier(attacker: GameUnit, move_type: str, db: Session) -> float:
    """If unit has Charge state, next Electric move deals 2x and clears Charge."""
    if str(move_type or "").lower() != "electric":
        return 1.0
    states = _normalize_states(getattr(attacker, "states", None))
    if not (states and str(states[0]).lower() == "charge" and int(states[1]) > 0):
        return 1.0
    attacker.states = []
    db.add(attacker)
    return 2.0


def process_wind_rider_on_tailwind(unit: GameUnit, db: Session, current_turn: int, helpers: dict | None = None) -> list[str]:
    """Wind Rider: raise Attack when Tailwind is applied to its side."""
    helpers = helpers or {}
    messages: list[str] = []
    if not ability_has_token(unit, db, "on_tailwind:self:raise_stat", "wind_rider"):
        return messages
    apply_stat = helpers.get("apply_stat_change")
    for token in get_ability_effects(unit, db):
        parts = _token_parts(token)
        if not (
            len(parts) >= 5
            and parts[0] == "on_tailwind"
            and parts[1] == "self"
            and parts[2] == "raise_stat"
        ):
            continue
        stat = _normalize_stat_name(parts[3])
        try:
            stages = int(parts[4])
        except (TypeError, ValueError):
            stages = 1
        if apply_stat:
            try:
                apply_stat(unit, stat, stages, current_turn, db)
            except TypeError:
                apply_stat(unit, stat, stages, current_turn, db)
        messages.append(
            f"{_unit_display_name(unit)}'s Wind Rider raised its {stat.replace('_', ' ')}!"
        )
    return messages
