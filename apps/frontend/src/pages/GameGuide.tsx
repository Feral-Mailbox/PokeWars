import { GUIDE_SECTIONS } from '../content/gameGuide';

function GuideBlock({
  id,
  title,
  intro,
  items,
}: {
  id: string;
  title: string;
  intro?: string;
  items: { title: string; body: string }[];
}) {
  return (
    <section id={id} className="scroll-mt-24 border-b border-gray-800 pb-10 last:border-b-0">
      <h2 className="text-2xl font-bold text-white">{title}</h2>
      {intro && <p className="mt-3 text-gray-300">{intro}</p>}
      <div className="mt-6 space-y-4">
        {items.map((item) => (
          <article
            key={item.title}
            className="rounded-lg border border-gray-700 bg-gray-800/70 p-4 text-left"
          >
            <h3 className="font-semibold text-white">{item.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-gray-300">{item.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export default function GameGuide() {
  return (
    <div className="mx-auto max-w-3xl px-4 pt-20 pb-16 text-left">
      <header className="mb-10">
        <p className="text-sm font-semibold uppercase tracking-wide text-yellow-300">Game guide</p>
        <h1 className="mt-2 text-4xl font-bold text-white">PokéTactics</h1>
        <p className="mt-3 text-lg text-gray-300">
          Rules, modes, and mechanics for the alpha build. Some features (abilities on units, replay
          viewer) are still in progress.
        </p>
      </header>

      <nav
        aria-label="Guide sections"
        className="mb-10 rounded-lg border border-gray-700 bg-gray-900/80 p-4"
      >
        <p className="mb-3 text-sm font-medium text-gray-200">On this page</p>
        <ul className="flex flex-wrap gap-2">
          {GUIDE_SECTIONS.map((section) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                className="inline-block rounded border border-gray-600 px-3 py-1 text-sm text-gray-200 hover:border-gray-500 hover:bg-gray-800"
              >
                {section.title}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="space-y-10">
        {GUIDE_SECTIONS.map((section) => (
          <GuideBlock key={section.id} {...section} />
        ))}
      </div>
    </div>
  );
}
