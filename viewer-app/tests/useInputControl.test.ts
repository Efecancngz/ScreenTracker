import { renderHook } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useInputControl } from "../src/hooks/useInputControl";

function setupVideo(
  rect: Partial<DOMRect> = {},
  videoSize: { videoWidth?: number; videoHeight?: number } = {}
) {
  const video = document.createElement("video");
  document.body.appendChild(video);
  const resolvedRect = {
    left: 0,
    top: 0,
    width: 200,
    height: 100,
    right: 200,
    bottom: 100,
    x: 0,
    y: 0,
    toJSON: () => ({}),
    ...rect,
  } as DOMRect;
  vi.spyOn(video, "getBoundingClientRect").mockReturnValue(resolvedRect);
  // jsdom's video elements report videoWidth/videoHeight as 0 by default
  // (no real media loaded). Default them to match the element's box 1:1 so
  // existing tests, which assume no letterboxing, keep their prior
  // behavior; tests that care about object-fit: contain letterboxing pass
  // an explicit intrinsic size that differs from the element's aspect ratio.
  Object.defineProperty(video, "videoWidth", {
    value: videoSize.videoWidth ?? resolvedRect.width,
    configurable: true,
  });
  Object.defineProperty(video, "videoHeight", {
    value: videoSize.videoHeight ?? resolvedRect.height,
    configurable: true,
  });
  return video;
}

function fakeChannel(readyState: RTCDataChannelState = "open") {
  return { readyState, send: vi.fn() } as unknown as RTCDataChannel;
}

function pointerEvent(type: string, clientX: number, clientY: number, pointerId = 1) {
  return new PointerEvent(type, { clientX, clientY, pointerId, bubbles: true });
}

function sentMessages(channel: RTCDataChannel) {
  return (channel.send as any).mock.calls.map((call: any[]) => JSON.parse(call[0]));
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

function setUp(
  rect?: Partial<DOMRect>,
  videoSize?: { videoWidth?: number; videoHeight?: number },
  primaryButton: "left" | "right" = "left"
) {
  const video = setupVideo(rect, videoSize);
  const channel = fakeChannel();
  const videoRef = createRef<HTMLVideoElement>();
  // @ts-expect-error - assigning a ref's current for the test
  videoRef.current = video;
  const view = renderHook(
    ({ primaryButton }) => useInputControl({ videoRef, channel, primaryButton }),
    { initialProps: { primaryButton } }
  );
  return { video, channel, rerender: view.rerender };
}

describe("useInputControl", () => {
  it("sends left-down immediately on touch and left-up on release (a tap) in left mode", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "left" },
      { type: "pointer-up", x: 0.5, y: 0.5, button: "left" },
    ]);
  });

  it("sends right-down/up on tap when in right mode", () => {
    const { video, channel } = setUp(undefined, undefined, "right");

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "right" },
      { type: "pointer-up", x: 0.5, y: 0.5, button: "right" },
    ]);
  });

  it("switching mode between gestures changes which button the next tap uses", () => {
    const { video, channel, rerender } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));
    (channel.send as any).mockClear();

    rerender({ primaryButton: "right" });

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "right" },
      { type: "pointer-up", x: 0.5, y: 0.5, button: "right" },
    ]);
  });

  it("keeps the primary button held while the finger stays down without moving", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    vi.advanceTimersByTime(5000); // holding for a while must not do anything on its own
    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "left" },
    ]);

    video.dispatchEvent(pointerEvent("pointerup", 100, 50));
    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "left" },
      { type: "pointer-up", x: 0.5, y: 0.5, button: "left" },
    ]);
  });

  it("sends pointer-move while dragging with the button held", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointermove", 130, 50));

    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "left" },
      { type: "pointer-move", x: 0.65, y: 0.5 },
    ]);
  });

  it("drops events silently when the channel is not open", () => {
    const video = setupVideo();
    const channel = fakeChannel("connecting");
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;
    renderHook(() => useInputControl({ videoRef, channel, primaryButton: "left" }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("relays wheel deltas from a real mouse wheel", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(new WheelEvent("wheel", { deltaX: 10, deltaY: 20, bubbles: true }));

    expect(sentMessages(channel)).toEqual([{ type: "wheel", deltaX: 10, deltaY: 20 }]);
  });

  it("relays keydown and keyup key values", () => {
    const { channel } = setUp();

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    window.dispatchEvent(new KeyboardEvent("keyup", { key: "a" }));

    expect(sentMessages(channel)).toEqual([
      { type: "key-down", key: "a" },
      { type: "key-up", key: "a" },
    ]);
  });

  it("releases a held primary button with a synthetic pointer-up on unmount", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;
    const { unmount } = renderHook(() => useInputControl({ videoRef, channel, primaryButton: "left" }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    expect(sentMessages(channel)).toHaveLength(1);

    unmount();

    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "left" },
      { type: "pointer-up", x: 0.5, y: 0.5, button: "left" },
    ]);
  });

  it("does not send anything extra on unmount when no button is held", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;
    const { unmount } = renderHook(() => useInputControl({ videoRef, channel, primaryButton: "left" }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));
    expect(sentMessages(channel)).toHaveLength(2);

    unmount();

    expect(sentMessages(channel)).toHaveLength(2);
  });

  it("maps coordinates through object-fit: contain letterboxing", () => {
    // 200x200 square element showing a 1920x1080 video: scale = min(200/1920,
    // 200/1080) = 0.1042, displayed picture is 200x112.5, vertically centered
    // with ~43.75px of letterbox padding on top and bottom.
    const { video, channel } = setUp(
      { width: 200, height: 200, right: 200, bottom: 200 },
      { videoWidth: 1920, videoHeight: 1080 }
    );

    // Exact center of the element is also the exact center of the picture.
    video.dispatchEvent(pointerEvent("pointerdown", 100, 100));
    video.dispatchEvent(pointerEvent("pointerup", 100, 100));

    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "left" },
      { type: "pointer-up", x: 0.5, y: 0.5, button: "left" },
    ]);

    (channel.send as any).mockClear();

    // A touch in the top letterbox padding (y=10, well above the picture's
    // top edge at ~43.75px) must be dropped entirely — no gesture starts.
    video.dispatchEvent(pointerEvent("pointerdown", 100, 10));
    video.dispatchEvent(pointerEvent("pointerup", 100, 10));

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("releases the held primary button with a compensating pointer-up when a second finger joins", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50, 1));
    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "left" },
    ]);

    video.dispatchEvent(pointerEvent("pointerdown", 150, 60, 2));

    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "left" },
      { type: "pointer-up", x: 0.5, y: 0.5, button: "left" },
    ]);
  });

  it("two fingers always scroll from the first movement -- no click, no hold timer", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 100, 60, 1));
    video.dispatchEvent(pointerEvent("pointerdown", 100, 40, 2));
    (channel.send as any).mockClear(); // discard the cancelled single-finger down/up

    // Holding still (even past what used to be the hold-promotion threshold)
    // must never send a click of any kind now.
    vi.advanceTimersByTime(2000);
    expect(channel.send).not.toHaveBeenCalled();

    // Both fingers move up by 30px each -> midpoint moves by 30px (mid 50 -> mid 20).
    video.dispatchEvent(pointerEvent("pointermove", 100, 30, 1));
    video.dispatchEvent(pointerEvent("pointermove", 100, 10, 2));

    const messages = sentMessages(channel);
    expect(messages.length).toBeGreaterThan(0);
    expect(messages.every((m: any) => m.type === "wheel")).toBe(true);

    // Lifting a finger ends the scroll gesture without sending anything else.
    (channel.send as any).mockClear();
    video.dispatchEvent(pointerEvent("pointerup", 100, 30, 1));
    video.dispatchEvent(pointerEvent("pointerup", 100, 10, 2));
    expect(channel.send).not.toHaveBeenCalled();
  });

  it("a quick two-finger tap sends only wheel deltas (if any movement) and never a click", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 80, 50, 1));
    video.dispatchEvent(pointerEvent("pointerdown", 120, 50, 2));
    (channel.send as any).mockClear();

    video.dispatchEvent(pointerEvent("pointerup", 80, 50, 1));

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("ignores a third finger during a two-finger scroll gesture", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 80, 50, 1));
    video.dispatchEvent(pointerEvent("pointerdown", 120, 50, 2));
    (channel.send as any).mockClear();

    video.dispatchEvent(pointerEvent("pointerdown", 100, 90, 3));
    video.dispatchEvent(pointerEvent("pointermove", 100, 95, 3));
    video.dispatchEvent(pointerEvent("pointerup", 100, 95, 3));

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("releases a held primary button on pointercancel", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50, 1));
    video.dispatchEvent(pointerEvent("pointercancel", 100, 50, 1));

    expect(sentMessages(channel)).toEqual([
      { type: "pointer-down", x: 0.5, y: 0.5, button: "left" },
      { type: "pointer-up", x: 0.5, y: 0.5, button: "left" },
    ]);

    // A subsequent pointerup for the now-cancelled pointer must not send
    // anything else (the gesture already ended).
    (channel.send as any).mockClear();
    video.dispatchEvent(pointerEvent("pointerup", 100, 50, 1));
    expect(channel.send).not.toHaveBeenCalled();
  });

  it("ending a two-finger scroll via pointercancel sends nothing further", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 80, 50, 1));
    video.dispatchEvent(pointerEvent("pointerdown", 120, 50, 2));
    (channel.send as any).mockClear();

    video.dispatchEvent(pointerEvent("pointercancel", 80, 50, 1));

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("releases a held primary button and held keys on window blur", () => {
    const { video, channel } = setUp();

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Shift" }));
    (channel.send as any).mockClear();

    window.dispatchEvent(new Event("blur"));

    const messages = sentMessages(channel);
    expect(messages).toContainEqual({ type: "pointer-up", x: 0.5, y: 0.5, button: "left" });
    expect(messages).toContainEqual({ type: "key-up", key: "Shift" });

    // Already released before blur must not be sent again.
    (channel.send as any).mockClear();
    window.dispatchEvent(new Event("blur"));
    expect(channel.send).not.toHaveBeenCalled();
  });

  it("releases held keys on unmount", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;
    const { unmount } = renderHook(() => useInputControl({ videoRef, channel, primaryButton: "left" }));

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Alt" }));
    expect(sentMessages(channel)).toEqual([{ type: "key-down", key: "Alt" }]);

    unmount();

    expect(sentMessages(channel)).toEqual([
      { type: "key-down", key: "Alt" },
      { type: "key-up", key: "Alt" },
    ]);
  });
});
