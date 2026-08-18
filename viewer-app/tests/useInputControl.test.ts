import { renderHook } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useInputControl } from "../src/hooks/useInputControl";

function setupVideo(rect: Partial<DOMRect> = {}) {
  const video = document.createElement("video");
  document.body.appendChild(video);
  vi.spyOn(video, "getBoundingClientRect").mockReturnValue({
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
  } as DOMRect);
  return video;
}

function fakeChannel(readyState: RTCDataChannelState = "open") {
  return { readyState, send: vi.fn() } as unknown as RTCDataChannel;
}

function pointerEvent(type: string, clientX: number, clientY: number) {
  return new PointerEvent(type, { clientX, clientY, bubbles: true });
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
});
