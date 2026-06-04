export type ActiveUnitState = {
  name: string;
  turnsRemaining: number;
};

/** Backend uses a large turn count for effects without a meaningful round timer. */
export const PERMANENT_STATE_TURN_COUNT = 9999;

const STATE_LABELS: Record<string, string> = {
  confusion: "Confusion",
  flinch: "Flinch",
  reflect: "Reflect",
  light_screen: "Light Screen",
  aurora_veil: "Aurora Veil",
  safeguard: "Safeguard",
  tailwind: "Tailwind",
  aqua_ring: "Aqua Ring",
  destiny_bond: "Destiny Bond",
  ingrain: "Ingrain",
  laser_focus: "Laser Focus",
  encore: "Encore",
  heal_block: "Heal Block",
  cursed: "Cursed",
  nightmare: "Nightmare",
  immobilized: "Immobilized",
  salt_cure: "Salt Cure",
  taunt: "Taunt",
  torment: "Torment",
  telekinesis: "Telekinesis",
  tar_shot: "Tar Shot",
  gastro_acid: "Gastro Acid",
  foresight: "Foresight",
  mind_reader: "Mind Reader",
  power_trick: "Power Trick",
  embargo: "Embargo",
  drowsy: "Drowsy",
};

const STATE_EFFECTS: Record<string, string> = {
  confusion: "May hurt itself when acting",
  flinch: "Cannot act this turn",
  reflect: "Reduces physical damage taken",
  light_screen: "Reduces special damage taken",
  aurora_veil: "Reduces physical and special damage taken",
  safeguard: "Protects from status conditions",
  tailwind: "Raises team Speed",
  aqua_ring: "Restores HP each turn",
  destiny_bond: "Faints the attacker if this unit faints",
  ingrain: "Restores HP each turn but cannot move",
  laser_focus: "Next attack is a critical hit",
  encore: "Can only use the encored move",
  heal_block: "Cannot be healed",
  cursed: "Loses HP each turn",
  nightmare: "Loses HP while asleep",
  immobilized: "Cannot move",
  salt_cure: "Takes damage each turn",
  taunt: "Can only use attacking moves",
  torment: "Cannot use the same move twice in a row",
  telekinesis: "Moves always hit except OHKO moves",
  tar_shot: "Takes extra damage from Fire-type moves",
  gastro_acid: "Ability is suppressed",
  foresight: "Normal and Fighting moves can hit Ghost types",
  mind_reader: "Psychic moves can hit Dark types",
  power_trick: "Attack and Defense are swapped",
  embargo: "Cannot use held item",
  drowsy: "Will fall asleep after two rounds",
};

function formatStateName(name: string): string {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function getActiveUnitState(raw: unknown): ActiveUnitState | null {
  if (raw == null) return null;

  if (Array.isArray(raw) && raw.length >= 2) {
    const name = String(raw[0] ?? "").trim().toLowerCase();
    const turnsRemaining = Number(raw[1]);
    if (!name || !Number.isFinite(turnsRemaining) || turnsRemaining <= 0) return null;
    return { name, turnsRemaining: Math.trunc(turnsRemaining) };
  }

  if (typeof raw === "string" && raw.trim()) {
    return { name: raw.trim().toLowerCase(), turnsRemaining: 1 };
  }

  return null;
}

export function getStateLabel(name: string): string {
  return STATE_LABELS[name] ?? formatStateName(name);
}

export function getStateEffect(name: string): string {
  return STATE_EFFECTS[name] ?? formatStateName(name);
}

export type StateTooltipContent = {
  name: string;
  description: string;
  roundsLine?: string;
};

export function formatStateTooltipContent(state: ActiveUnitState): StateTooltipContent {
  const content: StateTooltipContent = {
    name: getStateLabel(state.name),
    description: getStateEffect(state.name),
  };

  if (stateShowsRoundCount(state)) {
    content.roundsLine = `${state.turnsRemaining} round${state.turnsRemaining === 1 ? "" : "s"} left`;
  }

  return content;
}

export function stateShowsRoundCount(state: ActiveUnitState): boolean {
  if (state.name === "confusion") return false;
  if (state.turnsRemaining >= PERMANENT_STATE_TURN_COUNT) return false;
  return true;
}

