import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SessionJoinForm } from "../src/components/SessionJoinForm";

describe("SessionJoinForm", () => {
  it("calls onJoin with the assembled code once all six digits are entered", async () => {
    const handleJoin = vi.fn();
    render(<SessionJoinForm onJoin={handleJoin} />);

    const code = "X7K2M9";
    for (let i = 0; i < code.length; i++) {
      await userEvent.type(screen.getByLabelText(`Digit ${i + 1} of 6`), code[i]);
    }
    await userEvent.click(screen.getByRole("button", { name: "Connect →" }));

    expect(handleJoin).toHaveBeenCalledWith(code);
  });

  it("disables the connect button until all six digits are filled", () => {
    render(<SessionJoinForm onJoin={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Connect →" })).toBeDisabled();
  });

  it("auto-advances focus to the next digit as you type", async () => {
    render(<SessionJoinForm onJoin={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Digit 1 of 6"), "X");
    expect(screen.getByLabelText("Digit 2 of 6")).toHaveFocus();
  });
});
