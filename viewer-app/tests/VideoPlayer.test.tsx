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

  send = vi.fn();

  receive(payload: unknown) {
    this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(payload) }));
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

  it("mutes the video element so Chrome's autoplay policy doesn't block playback", () => {
    // Confirmed live: an unmuted <video autoPlay> got a live, correctly
    // dimensioned MediaStream (readyState 4) but stayed paused at
    // currentTime 0 -- Chrome's autoplay policy silently rejected it
    // (NotAllowedError: "play() failed because the user didn't interact
    // with the document first"). The host's capture track never carries
    // audio, so muting costs nothing and makes autoplay always allowed.
    const fakeStream = {} as MediaStream;
    const { container } = render(<VideoPlayer stream={fakeStream} inputChannel={null} />);
    expect(container.querySelector("video")).toHaveProperty("muted", true);
  });

  it("explicitly calls play() when a stream is attached, instead of relying on the autoPlay attribute alone", () => {
    // Confirmed live: even after muting fixed the NotAllowedError, the
    // native autoPlay attribute still didn't start playback on its own --
    // srcObject is assigned programmatically in a useEffect after mount,
    // and browsers don't reliably re-run the autoplay algorithm for a
    // MediaStream attached that way. Calling .play() explicitly once the
    // stream is set is the documented, reliable way to start a
    // programmatically-attached stream.
    const play = vi.fn().mockResolvedValue(undefined);
    HTMLMediaElement.prototype.play = play;
    const fakeStream = {} as MediaStream;

    render(<VideoPlayer stream={fakeStream} inputChannel={null} />);

    expect(play).toHaveBeenCalledTimes(1);
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

  describe("monitor selector", () => {
    it("shows no selector when there is only one monitor", () => {
      const fakeStream = {} as MediaStream;
      const channel = new FakeDataChannel("open");
      render(<VideoPlayer stream={fakeStream} inputChannel={channel as unknown as RTCDataChannel} />);

      channel.receive({
        type: "monitor-list",
        monitors: [{ index: 1, width: 1920, height: 1080, left: 0, top: 0 }],
      });

      expect(screen.queryByRole("button", { name: /monitor 1/i })).not.toBeInTheDocument();
    });

    it("shows one button per monitor when there are two or more", async () => {
      const fakeStream = {} as MediaStream;
      const channel = new FakeDataChannel("open");
      render(<VideoPlayer stream={fakeStream} inputChannel={channel as unknown as RTCDataChannel} />);

      channel.receive({
        type: "monitor-list",
        monitors: [
          { index: 1, width: 1920, height: 1080, left: 0, top: 0 },
          { index: 2, width: 1280, height: 720, left: 1920, top: 0 },
        ],
      });

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /monitor 1/i })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /monitor 2/i })).toBeInTheDocument();
      });
    });

    it("sends select-monitor and marks the tapped button active", async () => {
      const user = userEvent.setup();
      const fakeStream = {} as MediaStream;
      const channel = new FakeDataChannel("open");
      render(<VideoPlayer stream={fakeStream} inputChannel={channel as unknown as RTCDataChannel} />);

      channel.receive({
        type: "monitor-list",
        monitors: [
          { index: 1, width: 1920, height: 1080, left: 0, top: 0 },
          { index: 2, width: 1280, height: 720, left: 1920, top: 0 },
        ],
      });

      const monitor2Button = await screen.findByRole("button", { name: /monitor 2/i });
      await user.click(monitor2Button);

      expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "select-monitor", index: 2 }));
      expect(monitor2Button).toHaveAttribute("aria-pressed", "true");
    });
  });
});
