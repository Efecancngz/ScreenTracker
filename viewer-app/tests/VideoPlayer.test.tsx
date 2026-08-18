import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
});
