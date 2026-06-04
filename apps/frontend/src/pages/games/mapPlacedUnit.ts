export type PlacedUnitState = {
  id: number;
  game_id: number;
  unit_id: number;
  user_id: number;
  unit: any;
  tile: [number, number];
  level: number;
  current_hp: number;
  current_stats: Record<string, number>;
  stat_boosts: Record<string, unknown>;
  status_effects: unknown;
  states: unknown;
  is_fainted: boolean;
  can_move: boolean;
  move_pp: number[];
};

export type ActiveUnitView = PlacedUnitState & {
  instanceId: number;
};

export function mapPlacedUnitFromBackend(backendUnit: any): PlacedUnitState {
  const currentX = Number(backendUnit?.current_x ?? backendUnit?.starting_x ?? 0);
  const currentY = Number(backendUnit?.current_y ?? backendUnit?.starting_y ?? 0);

  return {
    id: Number(backendUnit.id),
    game_id: Number(backendUnit.game_id),
    unit_id: Number(backendUnit.unit_id),
    user_id: Number(backendUnit.user_id),
    unit: backendUnit.unit,
    tile: [currentX, currentY],
    level: Number(backendUnit.level ?? 50),
    current_hp: Number(backendUnit.current_hp ?? 0),
    current_stats: backendUnit.current_stats ?? {},
    stat_boosts: backendUnit.stat_boosts ?? {},
    status_effects: backendUnit.status_effects ?? [],
    states: backendUnit.states ?? [],
    is_fainted: Boolean(backendUnit.is_fainted),
    can_move: backendUnit.can_move !== false,
    move_pp: Array.isArray(backendUnit.move_pp) ? backendUnit.move_pp.map(Number) : [],
  };
}

export function toActiveUnitView(placed: PlacedUnitState): ActiveUnitView {
  return {
    ...placed,
    instanceId: placed.id,
  };
}
