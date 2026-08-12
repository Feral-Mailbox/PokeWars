export type GuideSection = {
  id: string;
  title: string;
  intro?: string;
  items: GuideItem[];
};

export type GuideItem = {
  title: string;
  body: string;
};

export const HOW_TO_PLAY: GuideSection = {
  id: 'how-to-play',
  title: 'How to play',
  intro:
    'PokéTactics is a browser-based tactical RPG. Create or join a match, build a team during preparation, then take turns moving units and using moves on a grid.',
  items: [
    {
      title: 'Account & login',
      body: 'Register from the navbar, then log in. Sessions last about 24 hours. HTTPS is required for cookies to work.',
    },
    {
      title: 'Create or join a match',
      body: 'Use Create Game to pick a mode, map, player count, and turn timer. Share the game link with opponents, or browse open games on Join Game.',
    },
    {
      title: 'Lobby',
      body: 'Wait until all player slots are filled. Each player marks Ready after placing at least one unit during preparation (or when the lobby allows it). The host starts the match.',
    },
    {
      title: 'Preparation',
      body: 'Spend starting cash to buy units and place them on your spawn zone. Remove units to refund cash. When your lineup is set, click Ready.',
    },
    {
      title: 'Your turn',
      body: 'Click one of your units to open its menu. Move within highlighted tiles, select a move, target valid tiles or enemies, then Execute. Use Wait to end that unit’s actions. Click End Turn when finished — the turn timer auto-advances if time runs out.',
    },
    {
      title: 'Chat & reports',
      body: 'Use in-game chat for coordination. System messages and move logs appear in the chat panel. Use Report bug on a game page if something breaks.',
    },
  ],
};

export const GAME_MODES: GuideSection = {
  id: 'game-modes',
  title: 'Game modes',
  items: [
    {
      title: 'Conquest',
      body: 'Eliminate enemy forces. During preparation, place units only on highlighted tiles in your spawn zone.',
    },
    {
      title: 'War',
      body: 'Capture objectives and outlast opponents. Uses cash-per-turn and unit limits in addition to starting cash.',
    },
    {
      title: 'Capture the Flag',
      body: 'Claim every banner on the map. Flags have 10 HP and jails have 20 HP; capture and unlock use the same damage as War Poké Balls (based on the acting unit’s current HP over max HP). Defeated units are sent to the victor’s jail. Stand on a jail and deplete its HP to free everyone held there — they return to the tiles they started the match on with a three-turn omniboost.',
    },
  ],
};

export const RULE_CHANGES: GuideSection = {
  id: 'rule-changes',
  title: 'Changes from standard Pokémon battles',
  intro:
    'Several mechanics are adapted for grid-based tactical play. These differ from main-series Pokémon turn order and field rules.',
  items: [
    {
      title: '“Priority” moves raise Speed instead',
      body: 'Moves that would normally have priority (Quick Attack, Mach Punch, Aqua Jet, Shadow Sneak, Ice Shard, Bullet Punch, and similar) apply a Speed boost when used — typically +1 stage, sometimes +2 on stronger moves. Turn order within a round is not decided by a separate priority bracket.',
    },
    {
      title: 'Weather on the map',
      body: 'Weather is tracked per tile on the board. Icons appear on affected tiles (sun, rain, sandstorm, hail). Rain boosts Water moves and weakens Fire; harsh sunlight boosts Fire and weakens Water. Sandstorm and hail can chip non-immune types each round.',
    },
    {
      title: 'Terrain on the map',
      body: 'Terrain (Electric, Psychic, Grassy, Misty) is placed on tiles and lasts several turns. It can change move type (e.g. Nature Power / terrain-based modifiers), power specific moves when conditions match, and gate certain effects. Some moves require the target to stand on active terrain.',
    },
    {
      title: 'Screen effects (Reflect, Light Screen, Aurora Veil)',
      body: 'Screens, as well as Safeguard and Tailwind, no longer are side-wide states, as units must be close to the user to benefit from them.',
    },
    {
      title: 'Field hazards',
      body: 'Spikes, Toxic Spikes, Stealth Rock, and Sticky Web can cover tiles. Hazard icons appear on the top-right of affected tiles. Layer limits apply (e.g. up to three layers of Spikes).',
    },
    {
      title: 'Gravity',
      body: 'Gravity field effects on a tile can modify move power and grounding-related interactions for units on that tile.',
    },
    {
      title: 'Grid movement & pathfinding',
      body: 'Units move on orthogonal paths with terrain costs. Ghost types pathfind through other units. Ice tiles can cause sliding after entry unless the unit ignores ice (Ice or Flying type, or Levitate).',
    },
  ],
};

export const TILE_EFFECTS: GuideSection = {
  id: 'tile-effects',
  title: 'Map tiles & type interactions',
  intro:
    'Maps can mark special tiles that restrict movement or alter combat. Type and ability interactions below mirror the game’s movement and defense rules.',
  items: [
    {
      title: 'Impassable tiles',
      body: 'No unit can enter or stand on impassable tiles, regardless of type or ability.',
    },
    {
      title: 'Water tiles',
      body: 'Most units cannot enter water. Water-type, Flying-type, and Levitate units can move through and stand on water tiles.',
    },
    {
      title: 'Sky tiles',
      body: 'Sky tiles are only passable by Flying-type and Levitate units. Grounded units cannot enter or stand on them.',
    },
    {
      title: 'Rock tiles',
      body: 'Most units cannot cross rock. Flying-type, Rock-type, and Levitate units can.',
    },
    {
      title: 'Tall grass tiles',
      body: 'Defenders on grass get extra bulk and evasion: +10% defense/sp. def for most types, +20% for Grass types. Bug types on grass gain 20% dodge (others 10%). Flying types and Levitate do not receive grass cover bonuses.',
    },
    {
      title: 'Stump tiles',
      body: 'Stumps cost 2 movement per step for all units. Grounded defenders on a stump gain +20% defense and sp. def (Flying types and Levitate do not). Grounded Grass-type units on a stump heal 1/8 max HP at the end of each round.',
    },
    {
      title: 'Sand tiles',
      body: 'Sand costs extra movement (2 per step) unless the unit is Ground-type, Flying-type, or has Levitate.',
    },
    {
      title: 'Ice tiles',
      body: 'Entering ice from a non-ice tile can slide the unit in the direction of movement until it hits a non-ice tile, boundary, blocker, or invalid terrain. Ice-type, Flying-type, and Levitate units do not slide.',
    },
    {
      title: 'Ledges',
      body: 'Ledges are one-way for most units — you can only cross from the direction the ledge faces. Flying-type and Levitate units can move onto and stop on ledges freely.',
    },
    {
      title: 'Ghost types',
      body: 'Ghost-type units can pathfind through allied and enemy units when calculating movement.',
    },
    {
      title: 'Levitate (ability)',
      body: 'When implemented on a unit, Levitate grants the same terrain exemptions as Flying for water, sky, rock, ledges, sand slow, and ice slide.',
    },
  ],
};

export const TYPE_CHART_NOTES: GuideSection = {
  id: 'type-chart',
  title: 'Type matchups in combat',
  intro:
    'Damage uses a standard Pokémon-style type chart. A move deals extra damage to types it is super effective against, reduced damage to resisted types, and no damage to immune types.',
  items: [
    {
      title: 'Super effective examples',
      body: 'Fire → Grass, Ice, Bug, Steel. Water → Fire, Ground, Rock. Electric → Water, Flying. Grass → Water, Ground, Rock. Fighting → Normal, Ice, Rock, Dark, Steel.',
    },
    {
      title: 'Not very effective examples',
      body: 'Fire → Fire, Water, Rock, Dragon. Grass → Fire, Grass, Poison, Flying, Bug, Dragon, Steel. Fighting → Poison, Flying, Psychic, Bug, Fairy.',
    },
    {
      title: 'Immunities',
      body: 'Normal cannot hit Ghost. Fighting and Ground cannot hit Flying. Electric cannot hit Ground. Ghost cannot hit Normal. Psychic cannot hit Dark. Dragon cannot hit Fairy.',
    },
    {
      title: 'STAB',
      body: 'Moves matching one of the user’s types deal increased damage (same-type attack bonus), as in main-series Pokémon.',
    },
    {
      title: 'Status immunities by type',
      body: 'Electric types cannot be paralyzed. Poison and Steel types cannot be poisoned. Fire types cannot be burned. Ice types cannot be frozen.',
    },
  ],
};

export type CreditPerson = {
  name: string;
  url?: string;
};

export type CreditsGroup = {
  title: string;
  /** Plain note when there are no people to list (e.g. testers). */
  note?: string;
  people?: CreditPerson[];
};

export type GuideCredits = {
  id: string;
  title: string;
  intro?: string;
  groups: CreditsGroup[];
};

/** Portrait + sprite artists credited in unit seeds (excludes Anonymous placeholders). */
export const POKEMON_SPRITE_CREDITS: CreditPerson[] = [
  { name: '0palite', url: 'https://zeropalart.tumblr.com/' },
  { name: 'A_Lettuce' },
  { name: 'AlexGroeger' },
  { name: 'baronessfaron' },
  { name: 'Blanky' },
  { name: 'C_Pariah' },
  { name: 'Caitemis', url: 'https://caitemis-art.tumblr.com/' },
  { name: 'CamusZekeSirius' },
  { name: 'chikorene' },
  { name: 'CHUNSOFT', url: 'https://www.spike-chunsoft.com/' },
  { name: 'cosmosully', url: 'https://twitter.com/cosmosully' },
  { name: 'Deeshura', url: 'https://github.com/Deeshura' },
  { name: 'Dejais' },
  { name: 'Deleca7755' },
  { name: 'dmDash' },
  { name: 'Emboarger' },
  { name: 'Emmuffin', url: 'https://twitter.com/Ernmuffin' },
  { name: 'estelstarlight' },
  { name: 'Fable' },
  { name: 'Fearless-Quit' },
  { name: 'felis_licht', url: 'https://www.deviantart.com/felis-licht' },
  { name: 'Frostdrop1' },
  { name: 'Garbage', url: 'https://twitter.com/Just_Tr4sh' },
  { name: 'Ginnie' },
  { name: 'gromchurch', url: 'https://twitter.com/poongis2' },
  { name: 'Gust', url: 'https://twitter.com/Estelaris__' },
  { name: 'jackolanternjackalope', url: 'https://www.instagram.com/jackolanternjackalope/' },
  { name: 'JemDragons' },
  { name: 'JFain' },
  { name: 'Jhony-Rex', url: 'https://www.deviantart.com/jhony-rex' },
  { name: 'Magu' },
  { name: 'Mojo' },
  { name: 'MonochromeKirby' },
  { name: 'Mooncaller' },
  { name: 'mucrush', url: 'https://www.deviantart.com/mucrush' },
  { name: 'Murpi', url: 'https://bsky.app/profile/murpia57.bsky.social' },
  { name: 'NeonCityRain', url: 'https://neoncityrain.tumblr.com/' },
  { name: 'NeroIntruder', url: 'https://twitter.com/NeroIntruder' },
  { name: 'Noivern', url: 'https://twitter.com/notarealnoivern' },
  { name: 'NOLASMOR' },
  { name: 'Noo' },
  { name: 'Novie' },
  { name: 'PhillipsYoung', url: 'https://twitter.com/PhilliYoung196' },
  { name: 'powercristal', url: 'https://www.deviantart.com/powercristal' },
  { name: 'Reimu_needs_$$$' },
  { name: 'RoyalRust' },
  { name: 'Sceptile' },
  { name: 'ShyStarryRain' },
  { name: 'silverfox88', url: 'https://twitter.com/realsilverfox88' },
  { name: 'skygummi', url: 'https://twitter.com/skygummi' },
  { name: 'Sloulja', url: 'https://twitter.com/OlSoulja' },
  { name: 'Smalusion', url: 'https://twitter.com/Smalusion' },
  {
    name: 'Spikey-Valentine',
    url: 'https://twitter.com/spikeyvalentine?s=21&t=KmiqQo0hvuT6bxZFEGAKbA',
  },
  { name: 'Tainted#3886' },
  { name: 'TawnySoup', url: 'https://linktr.ee/tawnysoup' },
  { name: 'Top_Kec' },
  { name: 'Uni', url: 'https://github.com/ArianaCastro01' },
  { name: 'Yynnyal' },
];

export const GUIDE_CREDITS: GuideCredits = {
  id: 'credits',
  title: 'Credits',
  intro: 'People and communities who made PokéTactics possible.',
  groups: [
    {
      title: 'Developers',
      people: [{ name: 'Organdroid', url: 'https://github.com/ryganzk' }],
    },
    {
      title: 'Testers',
      note: 'None yet.',
    },
    {
      title: 'Tileset spriters',
      people: [{ name: 'Ekat', url: 'https://x.com/Ekat_99' }],
    },
    {
      title: 'Pokémon spriters',
      people: POKEMON_SPRITE_CREDITS,
    },
  ],
};

export const GUIDE_SECTIONS = [
  HOW_TO_PLAY,
  GAME_MODES,
  RULE_CHANGES,
  TILE_EFFECTS,
  TYPE_CHART_NOTES,
];

/** Content sections plus credits, for the guide table of contents. */
export const GUIDE_NAV_SECTIONS = [
  ...GUIDE_SECTIONS.map(({ id, title }) => ({ id, title })),
  { id: GUIDE_CREDITS.id, title: GUIDE_CREDITS.title },
];
