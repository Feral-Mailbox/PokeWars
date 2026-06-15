import { FormEvent, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../state/auth';
import {
  GAME_NOT_FOUND_MESSAGE,
  INVALID_GAME_LINK_MESSAGE,
  gameExists,
  parseGameLink,
} from '../utils/gameLink';

const GAME_MODES = [
  {
    name: 'Conquest',
    goal: 'Capture objectives and outlast opponents.',
  },
  {
    name: 'War',
    goal: 'Eliminate enemy forces.',
  },
  {
    name: 'Capture the Flag',
    goal: 'Bring the flag to your base.',
  },
] as const;

const ALPHA_TEST_FOCUS = [
  'Creating and joining games',
  'Unit placement during preparation',
  'Movement, combat, and turn flow',
  'Real-time updates without refresh',
  'In-game chat',
];

function AlphaBadge() {
  return (
    <span className="inline-block rounded-full border border-yellow-500/60 bg-yellow-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-yellow-300">
      Early Alpha
    </span>
  );
}

function GameModeCards() {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {GAME_MODES.map((mode) => (
        <div
          key={mode.name}
          className="rounded-lg border border-gray-700 bg-gray-800/80 p-4 text-left"
        >
          <h3 className="font-semibold text-white">{mode.name}</h3>
          <p className="mt-1 text-sm text-gray-400">{mode.goal}</p>
        </div>
      ))}
    </div>
  );
}

function Toast({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="fixed top-4 left-1/2 z-50 -translate-x-1/2 transform rounded bg-red-600 px-4 py-2 text-white shadow-lg"
    >
      {message}
    </div>
  );
}

function LoggedOutHome({ onLogin, onRegister }: { onLogin: () => void; onRegister: () => void }) {
  return (
    <div className="mx-auto max-w-3xl px-4 text-left">
      <AlphaBadge />

      <h1 className="mt-4 text-4xl font-bold text-white">PokéTactics</h1>
      <p className="mt-3 max-w-2xl text-lg text-gray-300">
        Tactical battles on a grid — Advance Wars meets Pokémon-style combat.
      </p>

      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <button
          type="button"
          onClick={onLogin}
          className="rounded bg-indigo-600 px-6 py-3 font-semibold text-white hover:bg-indigo-700"
        >
          Log in
        </button>
        <button
          type="button"
          onClick={onRegister}
          className="rounded border border-gray-600 px-6 py-3 font-semibold text-white hover:border-gray-500 hover:bg-gray-800"
        >
          Create account
        </button>
      </div>
      <p className="mt-2 text-sm text-gray-500">Use the form in the top-right navbar.</p>

      <section className="mt-10">
        <h2 className="text-lg font-semibold text-white">How to play</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-gray-300">
          <li>Create an account and log in.</li>
          <li>Create a game or join with a link from your opponent.</li>
          <li>Place units, take turns, and win by mode rules.</li>
        </ol>
      </section>

      <section className="mt-10">
        <h2 className="mb-3 text-lg font-semibold text-white">Game modes</h2>
        <GameModeCards />
      </section>

      <p className="mt-10 text-sm text-gray-500">
        Alpha build — abilities and replay viewer are not in the UI yet. HTTPS is required to stay
        logged in. Read the full{' '}
        <Link to="/guide" className="text-indigo-400 hover:text-indigo-300">
          game guide
        </Link>
        .
      </p>
    </div>
  );
}

function LoggedInHome({
  username,
  onToast,
}: {
  username: string;
  onToast: (message: string) => void;
}) {
  const navigate = useNavigate();
  const [gameLinkInput, setGameLinkInput] = useState('');
  const [checkingLink, setCheckingLink] = useState(false);

  const handlePasteLink = async (event: FormEvent) => {
    event.preventDefault();
    const slug = parseGameLink(gameLinkInput);
    if (!slug) {
      onToast(INVALID_GAME_LINK_MESSAGE);
      return;
    }

    setCheckingLink(true);
    try {
      const exists = await gameExists(slug);
      if (!exists) {
        onToast(GAME_NOT_FOUND_MESSAGE);
        return;
      }
      navigate(`/games/${slug}`);
    } finally {
      setCheckingLink(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-4 text-left">
      <AlphaBadge />

      <h1 className="mt-4 text-3xl font-bold text-white">Welcome back, {username}</h1>
      <p className="mt-2 text-gray-300">Ready for your next match?</p>

      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        <Link
          to="/games/create"
          className="rounded bg-green-600 px-6 py-4 text-center font-semibold text-white hover:bg-green-700"
        >
          Create Game
        </Link>
        <Link
          to="/games/join"
          className="rounded bg-indigo-600 px-6 py-4 text-center font-semibold text-white hover:bg-indigo-700"
        >
          Join Game
        </Link>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Link
          to="/games/in-progress"
          className="rounded border border-gray-600 px-4 py-3 text-center font-medium text-white hover:border-gray-500 hover:bg-gray-800"
        >
          In-Progress Games
        </Link>
        <Link
          to="/games/completed"
          className="rounded border border-gray-600 px-4 py-3 text-center font-medium text-white hover:border-gray-500 hover:bg-gray-800"
        >
          Completed Games
        </Link>
      </div>

      <form onSubmit={handlePasteLink} className="mt-8 rounded-lg border border-gray-700 bg-gray-800/80 p-4">
        <label htmlFor="game-link" className="block text-sm font-medium text-gray-200">
          Have a game link?
        </label>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <input
            id="game-link"
            type="text"
            value={gameLinkInput}
            onChange={(e) => setGameLinkInput(e.target.value)}
            placeholder="Paste link or game ID"
            disabled={checkingLink}
            className="flex-1 rounded border border-gray-600 bg-gray-900 px-3 py-2 text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={checkingLink}
            className="rounded bg-gray-700 px-4 py-2 font-medium text-white hover:bg-gray-600 disabled:opacity-60"
          >
            {checkingLink ? 'Checking...' : 'Go'}
          </button>
        </div>
      </form>

      <section className="mt-10">
        <h2 className="text-lg font-semibold text-white">What we&apos;re testing</h2>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-gray-300">
          {ALPHA_TEST_FOCUS.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="mt-10">
        <h2 className="mb-3 text-lg font-semibold text-white">Game modes</h2>
        <GameModeCards />
      </section>

      <p className="mt-10 text-sm text-gray-500">
        Report bugs through the channel your host provides. Cosmetic polish and missing animations
        are expected in this build. See the{' '}
        <Link to="/guide" className="text-indigo-400 hover:text-indigo-300">
          game guide
        </Link>{' '}
        for rules and mechanics.
      </p>
    </div>
  );
}

const Homepage = () => {
  const { user, loading, requestAuthPrompt } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  useEffect(() => {
    const message = (location.state as { toastMessage?: string } | null)?.toastMessage;
    if (!message) return;
    setToastMessage(message);
    navigate('.', { replace: true, state: null });
  }, [location.state, navigate]);

  useEffect(() => {
    if (!toastMessage) return;
    const timeout = setTimeout(() => setToastMessage(null), 3000);
    return () => clearTimeout(timeout);
  }, [toastMessage]);

  if (loading) {
    return (
      <div className="pt-24 px-4 text-center text-gray-400">
        Loading...
      </div>
    );
  }

  return (
    <div className="pt-20 pb-12">
      {toastMessage && <Toast message={toastMessage} />}
      {user ? (
        <LoggedInHome username={user.username} onToast={setToastMessage} />
      ) : (
        <LoggedOutHome
          onLogin={() => requestAuthPrompt('login')}
          onRegister={() => requestAuthPrompt('register')}
        />
      )}
    </div>
  );
};

export default Homepage;
