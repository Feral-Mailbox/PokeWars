import {
  GUIDE_CREDITS,
  GUIDE_NAV_SECTIONS,
  GUIDE_SECTIONS,
  type CreditPerson,
  type GuideCredits,
} from '../content/gameGuide';

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

function CreditName({ person }: { person: CreditPerson }) {
  if (!person.url) {
    return <span>{person.name}</span>;
  }
  return (
    <a
      href={person.url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-sky-300 underline decoration-sky-300/40 underline-offset-2 hover:text-sky-200 hover:decoration-sky-200"
    >
      {person.name}
    </a>
  );
}

function CreditsBlock({ credits }: { credits: GuideCredits }) {
  return (
    <section id={credits.id} className="scroll-mt-24 border-b border-gray-800 pb-10 last:border-b-0">
      <h2 className="text-2xl font-bold text-white">{credits.title}</h2>
      {credits.intro && <p className="mt-3 text-gray-300">{credits.intro}</p>}
      <div className="mt-6 space-y-4">
        {credits.groups.map((group) => (
          <article
            key={group.title}
            className="rounded-lg border border-gray-700 bg-gray-800/70 p-4 text-left"
          >
            <h3 className="font-semibold text-white">{group.title}</h3>
            {group.note && (
              <p className="mt-2 text-sm leading-relaxed text-gray-300">{group.note}</p>
            )}
            {group.people && group.people.length > 0 && (
              <ul className="mt-2 space-y-1 text-sm leading-relaxed text-gray-300">
                {group.people.map((person) => (
                  <li key={person.name}>
                    <CreditName person={person} />
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))}
      </div>
      <p className="mt-6 text-sm leading-relaxed text-gray-400">
        If a contributor&apos;s socials have not been properly credited, DM me on Discord{' '}
        <span className="font-medium text-gray-200">@ganzker</span> so I can add the proper link.
      </p>
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
          {GUIDE_NAV_SECTIONS.map((section) => (
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
        <CreditsBlock credits={GUIDE_CREDITS} />
      </div>
    </div>
  );
}
