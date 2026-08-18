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

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("useInputControl", () => {
  it("sends a left click (down immediately followed by up) on a quick tap", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - assigning a ref's current for the test
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(channel.send).toHaveBeenCalledTimes(2);
    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "pointer-down",
      x: 0.5,
      y: 0.5,
      button: "left",
    });
    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "pointer-up",
      x: 0.5,
      y: 0.5,
      button: "left",
    });
  });

  it("sends a right click after the long-press threshold elapses", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    vi.advanceTimersByTime(500);

    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "pointer-down",
      x: 0.5,
      y: 0.5,
      button: "right",
    });

    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "pointer-up",
      x: 0.5,
      y: 0.5,
      button: "right",
    });
  });

  it("starts a left-button drag once movement exceeds the threshold before the long-press fires", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointermove", 130, 50));

    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "pointer-down",
      x: 0.5,
      y: 0.5,
      button: "left",
    });
    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "pointer-move",
      x: 0.65,
      y: 0.5,
    });

    // The long-press timer must have been cancelled by the drag — advancing
    // past the threshold must NOT also fire a right-click pointer-down.
    vi.advanceTimersByTime(500);
    expect(channel.send).toHaveBeenCalledTimes(2);
  });

  it("drops events silently when the channel is not open", () => {
    const video = setupVideo();
    const channel = fakeChannel("connecting");
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("relays wheel deltas", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(
      new WheelEvent("wheel", { deltaX: 10, deltaY: 20, bubbles: true })
    );

    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "wheel",
      deltaX: 10,
      deltaY: 20,
    });
  });

  it("relays keydown and keyup key values", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    window.dispatchEvent(new KeyboardEvent("keyup", { key: "a" }));

    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "key-down",
      key: "a",
    });
    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "key-up",
      key: "a",
    });
  });

  it("releases a held left-button drag with a synthetic pointer-up on unmount", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    const { unmount } = renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointermove", 130, 50));

    expect(channel.send).toHaveBeenCalledTimes(2);

    unmount();

    expect(channel.send).toHaveBeenCalledTimes(3);
    expect(JSON.parse((channel.send as any).mock.calls[2][0])).toEqual({
      type: "pointer-up",
      x: 0.5,
      y: 0.5,
      button: "left",
    });
  });

  it("releases a held right-button long-press with a synthetic pointer-up on unmount", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    const { unmount } = renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    vi.advanceTimersByTime(500);

    expect(channel.send).toHaveBeenCalledTimes(1);

    unmount();

    expect(channel.send).toHaveBeenCalledTimes(2);
    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "pointer-up",
      x: 0.5,
      y: 0.5,
      button: "right",
    });
  });

  it("does not send anything extra on unmount when no button is held", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    const { unmount } = renderHook(() => useInputControl({ videoRef, channel }));

    // A completed tap: down then up, no button left "held".
    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(channel.send).toHaveBeenCalledTimes(2);

    unmount();

    expect(channel.send).toHaveBeenCalledTimes(2);
  });

  it("maps coordinates through object-fit: contain letterboxing", () => {
    // 200x200 square element showing a 1920x1080 video: scale = min(200/1920,
    // 200/1080) = 0.1042, displayed picture is 200x112.5, vertically centered
    // with ~43.75px of letterbox padding on top and bottom.
    const video = setupVideo(
      { width: 200, height: 200, right: 200, bottom: 200 },
      { videoWidth: 1920, videoHeight: 1080 }
    );
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    // Exact center of the element is also the exact center of the picture.
    video.dispatchEvent(pointerEvent("pointerdown", 100, 100));
    video.dispatchEvent(pointerEvent("pointerup", 100, 100));

    expect(channel.send).toHaveBeenCalledTimes(2);
    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "pointer-down",
      x: 0.5,
      y: 0.5,
      button: "left",
    });

    (channel.send as any).mockClear();

    // A click in the top letterbox padding (y=10, well above the picture's
    // top edge at ~43.75px) must be dropped entirely — no gesture starts.
    video.dispatchEvent(pointerEvent("pointerdown", 100, 10));
    video.dispatchEvent(pointerEvent("pointerup", 100, 10));

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("ignores a second pointer while a gesture is already active", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    // First finger: long-press fires a right-click pointer-down.
    video.dispatchEvent(pointerEvent("pointerdown", 100, 50, 1));
    vi.advanceTimersByTime(500);
    expect(channel.send).toHaveBeenCalledTimes(1);

    // Second finger touches down mid-gesture: must be ignored entirely.
    video.dispatchEvent(pointerEvent("pointerdown", 150, 80, 2));
    video.dispatchEvent(pointerEvent("pointermove", 150, 80, 2));
    video.dispatchEvent(pointerEvent("pointerup", 150, 80, 2));
    expect(channel.send).toHaveBeenCalledTimes(1);

    // First finger lifts: releases the right button held from finger 1,
    // not a fresh left click.
    video.dispatchEvent(pointerEvent("pointerup", 100, 50, 1));
    expect(channel.send).toHaveBeenCalledTimes(2);
    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "pointer-up",
      x: 0.5,
      y: 0.5,
      button: "right",
    });
  });

  it("releases a held button on pointercancel", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50, 1));
    video.dispatchEvent(pointerEvent("pointermove", 130, 50, 1));
    expect(channel.send).toHaveBeenCalledTimes(2);

    video.dispatchEvent(pointerEvent("pointercancel", 130, 50, 1));

    expect(channel.send).toHaveBeenCalledTimes(3);
    expect(JSON.parse((channel.send as any).mock.calls[2][0])).toEqual({
      type: "pointer-up",
      x: 0.5,
      y: 0.5,
      button: "left",
    });

    // A subsequent pointerup for the now-cancelled pointer must not send
    // anything else (the gesture already ended).
    video.dispatchEvent(pointerEvent("pointerup", 130, 50, 1));
    expect(channel.send).toHaveBeenCalledTimes(3);
  });

  it("releases held modifier keys on window blur", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Shift" }));
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Control" }));
    expect(channel.send).toHaveBeenCalledTimes(2);

    window.dispatchEvent(new Event("blur"));

    expect(channel.send).toHaveBeenCalledTimes(4);
    const keys = [2, 3].map(
      (i) => JSON.parse((channel.send as any).mock.calls[i][0]).key
    );
    expect(keys.sort()).toEqual(["Control", "Shift"]);
    expect(JSON.parse((channel.send as any).mock.calls[2][0]).type).toBe("key-up");
    expect(JSON.parse((channel.send as any).mock.calls[3][0]).type).toBe("key-up");

    // Keys already released before blur must not be sent again.
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

    const { unmount } = renderHook(() => useInputControl({ videoRef, channel }));

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Alt" }));
    expect(channel.send).toHaveBeenCalledTimes(1);

    unmount();

    expect(channel.send).toHaveBeenCalledTimes(2);
    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "key-up",
      key: "Alt",
    });
  });
});
