import { useEffect, type RefObject } from "react";

const LONG_PRESS_MS = 500;
const DRAG_THRESHOLD_PX = 20;

interface UseInputControlOptions {
  videoRef: RefObject<HTMLVideoElement | null>;
  channel: RTCDataChannel | null;
}

type Button = "left" | "right";

export function useInputControl({ videoRef, channel }: UseInputControlOptions): void {
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    function send(message: Record<string, unknown>) {
      if (channel?.readyState === "open") {
        channel.send(JSON.stringify(message));
      }
    }

    function toNormalized(clientX: number, clientY: number): { x: number; y: number } {
      const rect = video!.getBoundingClientRect();
      return {
        x: (clientX - rect.left) / rect.width,
        y: (clientY - rect.top) / rect.height,
      };
    }

    let longPressTimer: ReturnType<typeof setTimeout> | null = null;
    let downAt: { x: number; y: number; clientX: number; clientY: number } | null = null;
    let activeButton: Button | null = null;

    function handlePointerDown(event: PointerEvent) {
      event.preventDefault();
      // Without capture, releasing the pointer outside the video's bounds
      // (e.g. dragging off the edge) never fires pointerup on this element,
      // leaving the mouse button stuck "down" on the host forever. Optional
      // chaining because jsdom's test environment doesn't implement this.
      video!.setPointerCapture?.(event.pointerId);
      const { x, y } = toNormalized(event.clientX, event.clientY);
      downAt = { x, y, clientX: event.clientX, clientY: event.clientY };
      activeButton = null;
      longPressTimer = setTimeout(() => {
        if (!downAt) return;
        activeButton = "right";
        send({ type: "pointer-down", x: downAt.x, y: downAt.y, button: "right" });
      }, LONG_PRESS_MS);
    }

    function handlePointerMove(event: PointerEvent) {
      if (!downAt) return;
      const { x, y } = toNormalized(event.clientX, event.clientY);

      if (activeButton === null) {
        const dx = event.clientX - downAt.clientX;
        const dy = event.clientY - downAt.clientY;
        if (Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;

        if (longPressTimer) clearTimeout(longPressTimer);
        activeButton = "left";
        send({ type: "pointer-down", x: downAt.x, y: downAt.y, button: "left" });
      }

      send({ type: "pointer-move", x, y });
    }

    function handlePointerUp(event: PointerEvent) {
      video!.releasePointerCapture?.(event.pointerId);
      if (longPressTimer) clearTimeout(longPressTimer);
      if (!downAt) return;
      const { x, y } = toNormalized(event.clientX, event.clientY);

      if (activeButton === null) {
        // Never moved past the drag threshold or the long-press timer: a
        // plain tap. Send a synthetic down+up pair at the same spot.
        send({ type: "pointer-down", x: downAt.x, y: downAt.y, button: "left" });
        send({ type: "pointer-up", x: downAt.x, y: downAt.y, button: "left" });
      } else {
        send({ type: "pointer-up", x, y, button: activeButton });
      }

      downAt = null;
      activeButton = null;
    }

    function handleWheel(event: WheelEvent) {
      event.preventDefault();
      send({ type: "wheel", deltaX: event.deltaX, deltaY: event.deltaY });
    }

    function handleKeyDown(event: KeyboardEvent) {
      send({ type: "key-down", key: event.key });
    }

    function handleKeyUp(event: KeyboardEvent) {
      send({ type: "key-up", key: event.key });
    }

    video.addEventListener("pointerdown", handlePointerDown);
    video.addEventListener("pointermove", handlePointerMove);
    video.addEventListener("pointerup", handlePointerUp);
    video.addEventListener("wheel", handleWheel);
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      if (longPressTimer) clearTimeout(longPressTimer);
      video.removeEventListener("pointerdown", handlePointerDown);
      video.removeEventListener("pointermove", handlePointerMove);
      video.removeEventListener("pointerup", handlePointerUp);
      video.removeEventListener("wheel", handleWheel);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [videoRef, channel]);
}
