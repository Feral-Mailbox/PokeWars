import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "@/App";

describe("App Routing", () => {
  it("renders home route", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByText(/Welcome! Please login to continue/i)).toBeInTheDocument();
  });

  it("renders create game route", () => {
    render(
      <MemoryRouter initialEntries={["/games/create"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByText(/Create Game/i)).toBeInTheDocument();
  });

  it("renders 404 for unknown route", () => {
    render(
      <MemoryRouter initialEntries={["/unknown"]}>
        <App />
      </MemoryRouter>
    );
    expect(screen.getByText(/Not Found/i)).toBeInTheDocument();
  });
});
