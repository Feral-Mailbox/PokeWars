// main.test.tsx
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "@/App";

describe("Main entry point", () => {
  it("renders App without crashing", () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>
    );
  });
});

