import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoPlayer } from "../src/components/VideoPlayer";

class FakeDataChannel extends EventTarget {
  readyState: RTCDataChannelState;

  constructor(readyState: RTCDataChannelState) {
    super();
    this.readyState = readyState;
  }

  open() {
    this.readyState = "open";
    this.dispatchEvent(new Event("open"));
  }

  close() {
    this.readyState = "closed";
    this.dispatchEvent(new Event("close"));
  }
}

describe("VideoPlayer", () => {
  it("shows a waiting message when there is no stream", () => {
    render(<VideoPlayer stream={null} inputChannel={null} />);
    expect(screen.getByText(/waiting for host/i)).toBeInTheDocument();
  });

  it("renders a video element bound to the stream when present", () => {
    const fakeStream = {} as MediaStream;
    const { container } = render(<VideoPlayer stream={fakeStream} inputChannel={null} />);
    expect(container.querySelector("video")).not.toBeNull();
  });

  it("shows the connecting status and updates to active once the channel opens", async () => {
    const fakeStream = {} as MediaStream;
    const channel = new FakeDataChannel("connecting");

    render(<VideoPlayer stream={fakeStream} inputChannel={channel as unknown as RTCDataChannel} />);

    expect(screen.getByText(/input connecting/i)).toBeInTheDocument();

    channel.open();

    await waitFor(() => {
      expect(screen.getByText(/input active/i)).toBeInTheDocument();
    });
  });

  it("shows the active status immediately when the channel is already open at mount", () => {
    const fakeStream = {} as MediaStream;
    const channel = new FakeDataChannel("open");

    render(<VideoPlayer stream={fakeStream} inputChannel={channel as unknown as RTCDataChannel} />);

    expect(screen.getByText(/input active/i)).toBeInTheDocument();
  });

  describe("click mode toggle", () => {
    it("defaults to left-click mode", () => {
      const fakeStream = {} as MediaStream;
      render(<VideoPlayer stream={fakeStream} inputChannel={null} />);

      expect(screen.getByRole("button", { name: /left.?click/i })).toBeInTheDocument();
    });

    it("switches to right-click mode when clicked, and back to left on a second click", async () => {
      const user = userEvent.setup();
      const fakeStream = {} as MediaStream;
      render(<VideoPlayer stream={fakeStream} inputChannel={null} />);

      await user.click(screen.getByRole("button", { name: /left.?click/i }));
      expect(screen.getByRole("button", { name: /right.?click/i })).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /right.?click/i }));
      expect(screen.getByRole("button", { name: /left.?click/i })).toBeInTheDocument();
    });
  });

  describe("fullscreen toggle", () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("requests fullscreen on the wrapper when clicked", async () => {
      const user = userEvent.setup();
      const fakeStream = {} as MediaStream;
      const requestFullscreen = vi.fn().mockResolvedValue(undefined);
      // jsdom doesn't implement the Fullscreen API at all.
      HTMLElement.prototype.requestFullscreen = requestFullscreen;

      render(<VideoPlayer stream={fakeStream} inputChannel={null} />);
      await user.click(screen.getByRole("button", { name: /fullscreen/i }));

      expect(requestFullscreen).toHaveBeenCalledTimes(1);
    });

    it("exits fullscreen instead when already fullscreen", async () => {
      const user = userEvent.setup();
      const fakeStream = {} as MediaStream;
      const exitFullscreen = vi.fn().mockResolvedValue(undefined);
      HTMLElement.prototype.requestFullscreen = vi.fn().mockResolvedValue(undefined);
      document.exitFullscreen = exitFullscreen;
      Object.defineProperty(document, "fullscreenElement", {
        value: document.createElement("div"),
        configurable: true,
      });

      render(<VideoPlayer stream={fakeStream} inputChannel={null} />);
      await user.click(screen.getByRole("button", { name: /fullscreen/i }));

      expect(exitFullscreen).toHaveBeenCalledTimes(1);

      Object.defineProperty(document, "fullscreenElement", { value: null, configurable: true });
    });
  });
});
