import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import GameGuide from '@/pages/GameGuide';

describe('GameGuide', () => {
  it('renders major guide sections', () => {
    render(
      <MemoryRouter>
        <GameGuide />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: /PokéTactics/i, level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /How to play/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Game modes/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Changes from standard Pokémon battles/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Map tiles & type interactions/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Type matchups in combat/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Credits/i })).toBeInTheDocument();
    expect(screen.getByText(/Priority.*raise Speed/i)).toBeInTheDocument();
    expect(screen.getByText(/Water-type, Flying-type, and Levitate/i)).toBeInTheDocument();
    expect(screen.getByText(/None yet/i)).toBeInTheDocument();

    const organdroid = screen.getByRole('link', { name: 'Organdroid' });
    expect(organdroid).toHaveAttribute('href', 'https://github.com/ryganzk');
    expect(organdroid).toHaveAttribute('target', '_blank');

    const ekat = screen.getByRole('link', { name: 'Ekat' });
    expect(ekat).toHaveAttribute('href', 'https://x.com/Ekat_99');

    const chunsoft = screen.getByRole('link', { name: 'CHUNSOFT' });
    expect(chunsoft).toHaveAttribute('href', 'https://www.spike-chunsoft.com/');

    expect(screen.getByText('A_Lettuce')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'A_Lettuce' })).not.toBeInTheDocument();
    expect(
      screen.getByText(/If a contributor.s socials have not been properly credited/i),
    ).toBeInTheDocument();
    expect(screen.getByText('@ganzker')).toBeInTheDocument();
  });
});
