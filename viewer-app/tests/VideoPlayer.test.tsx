import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VideoPlayer } from "../src/components/VideoPlayer";

describe("VideoPlayer", () => {
  it("shows a waiting message when there is no stream", () => {
    render(<VideoPlayer stream={null} />);
    expect(screen.getByText(/waiting for host/i)).toBeInTheDocument();
  });

  it("renders a video element bound to the stream when present", () => {
    const fakeStream = {} as MediaStream;
    const { container } = render(<VideoPlayer stream={fakeStream} />);
    expect(container.querySelector("video")).not.toBeNull();
  });
});
