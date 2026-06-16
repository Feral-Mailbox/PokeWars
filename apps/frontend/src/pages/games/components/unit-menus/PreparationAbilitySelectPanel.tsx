export type PreparationAbilityOption = {
  id: number;
  name: string;
  isHidden: boolean;
  cost: number;
};

export const HIDDEN_ABILITY_COST = 250;

type PreparationAbilitySelectPanelProps = {
  abilities: PreparationAbilityOption[];
  cash: number;
  currentAbilityId: number | null;
  onSelectAbility: (abilityId: number) => void;
};

export default function PreparationAbilitySelectPanel({
  abilities,
  cash,
  currentAbilityId,
  onSelectAbility,
}: PreparationAbilitySelectPanelProps) {
  const currentIsHidden =
    currentAbilityId != null &&
    abilities.some(
      (ability) => ability.id === currentAbilityId && ability.isHidden
    );

  const canAffordAbility = (ability: PreparationAbilityOption) => {
    if (ability.isHidden && !currentIsHidden) {
      return cash >= ability.cost;
    }
    return true;
  };

  return (
    <div className="mt-2 rounded border border-gray-600 bg-gray-900/80 p-3">
      <ul className="max-h-48 space-y-1 overflow-y-auto text-sm">
        {abilities.length === 0 && (
          <li className="rounded border border-dashed border-gray-600 px-2 py-2 text-gray-400">
            This unit has no abilities to choose from.
          </li>
        )}
        {abilities.map((ability) => {
          const affordable = canAffordAbility(ability);
          const isEquipped = ability.id === currentAbilityId;

          return (
            <li key={ability.id}>
              <button
                type="button"
                disabled={!affordable}
                onClick={() => onSelectAbility(ability.id)}
                className={`flex w-full items-center justify-between rounded px-2 py-1 text-left ${
                  isEquipped
                    ? "bg-yellow-700/40 hover:bg-yellow-700/60"
                    : affordable
                      ? "hover:bg-gray-700"
                      : "cursor-not-allowed opacity-50"
                }`}
              >
                <span className="font-medium">{ability.name}</span>
                {ability.isHidden ? (
                  <span className="text-green-400">${ability.cost}</span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
