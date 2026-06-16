export type PlacedUnitState = {
  id: number;
  game_id: number;
  unit_id: number;
  user_id: number;
  unit: any;
  /** Current map position (updates when the unit moves). */
  tile: [number, number];
  /** Turn-start anchor for movement range; synced from starting_x/y. */
  start_tile: [number, number];
  level: number;
  current_hp: number;
  current_stats: Record<string, number>;
  stat_boosts: Record<string, unknown>;
  status_effects: unknown;
  states: unknown;
  is_fainted: boolean;
  can_move: boolean;
  move_pp: number[];
  held_item: string | null;
  held_item_slug: string | null;
  ability: string | null;
  ability_id: number | null;
};

export type ActiveUnitView = PlacedUnitState & {
  instanceId: number;
};

export function mapPlacedUnitFromBackend(backendUnit: any): PlacedUnitState {
  const currentX = Number(backendUnit?.current_x ?? backendUnit?.starting_x ?? 0);
  const currentY = Number(backendUnit?.current_y ?? backendUnit?.starting_y ?? 0);
  const startX = Number(backendUnit?.starting_x ?? currentX);
  const startY = Number(backendUnit?.starting_y ?? currentY);

  return {
    id: Number(backendUnit.id),
    game_id: Number(backendUnit.game_id),
    unit_id: Number(backendUnit.unit_id),
    user_id: Number(backendUnit.user_id),
    unit: backendUnit.unit,
    tile: [currentX, currentY],
    start_tile: [startX, startY],
    level: Number(backendUnit.level ?? 50),
    current_hp: Number(backendUnit.current_hp ?? 0),
    current_stats: backendUnit.current_stats ?? {},
    stat_boosts: backendUnit.stat_boosts ?? {},
    status_effects: backendUnit.status_effects ?? [],
    states: backendUnit.states ?? [],
    is_fainted: Boolean(backendUnit.is_fainted),
    can_move: backendUnit.can_move !== false,
    move_pp: Array.isArray(backendUnit.move_pp) ? backendUnit.move_pp.map(Number) : [],
    held_item: backendUnit.held_item ?? null,
    held_item_slug: backendUnit.held_item_slug ?? null,
    ability: backendUnit.ability ?? null,
    ability_id:
      backendUnit.ability_id != null
        ? Number(backendUnit.ability_id)
        : null,
  };
}

export function toActiveUnitView(placed: PlacedUnitState): ActiveUnitView {
  return {
    ...placed,
    instanceId: placed.id,
  };
}
