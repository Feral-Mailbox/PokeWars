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
    expect(screen.getByText(/Priority.*raise Speed/i)).toBeInTheDocument();
    expect(screen.getByText(/Water-type, Flying-type, and Levitate/i)).toBeInTheDocument();
  });
});
