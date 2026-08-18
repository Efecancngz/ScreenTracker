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

    // The video element is styled with `object-fit: contain`, so the actual
    // displayed picture is a centered sub-rectangle of the element's box
    // (letterboxed/pillarboxed whenever the video's aspect ratio doesn't
    // match the element's). Compute that sub-rectangle from the video's
    // intrinsic size and map into it, rather than dividing by the element's
    // full bounding box. Points that land in the letterbox bars are outside
    // the picture entirely and have no corresponding host-screen location,
    // so they're reported as unusable (null) rather than clamped to an edge.
    function toNormalized(clientX: number, clientY: number): { x: number; y: number } | null {
      const rect = video!.getBoundingClientRect();
      const vw = video!.videoWidth;
      const vh = video!.videoHeight;
      if (!vw || !vh || !rect.width || !rect.height) return null;

      const scale = Math.min(rect.width / vw, rect.height / vh);
      const dispW = vw * scale;
      const dispH = vh * scale;
      const offX = (rect.width - dispW) / 2;
      const offY = (rect.height - dispH) / 2;

      const x = (clientX - rect.left - offX) / dispW;
      const y = (clientY - rect.top - offY) / dispH;
      if (x < 0 || x > 1 || y < 0 || y > 1) return null;
      return { x, y };
    }

    let longPressTimer: ReturnType<typeof setTimeout> | null = null;
    let downAt: { x: number; y: number; clientX: number; clientY: number } | null = null;
    let activeButton: Button | null = null;
    // The pointerId of the gesture currently in progress. While a gesture is
    // active, pointerdown/move/up/cancel events from any other pointerId
    // (e.g. a second finger touching down mid-gesture) are ignored so they
    // can't clobber the first gesture's state and strand a held button.
    let activePointerId: number | null = null;
    const pressedKeys = new Set<string>();

    // Shared compensating release used any time a gesture ends abnormally
    // (component teardown, browser-interrupted pointer sequence) so a
    // mouse button never stays "held" on the host forever.
    function releaseHeldButton() {
      if (longPressTimer) {
        clearTimeout(longPressTimer);
        longPressTimer = null;
      }
      if (activeButton !== null && downAt) {
        send({ type: "pointer-up", x: downAt.x, y: downAt.y, button: activeButton });
      }
      downAt = null;
      activeButton = null;
      activePointerId = null;
    }

    function releaseHeldKeys() {
      for (const key of pressedKeys) {
        send({ type: "key-up", key });
      }
      pressedKeys.clear();
    }

    function handlePointerDown(event: PointerEvent) {
      if (downAt !== null) {
        // A gesture is already in progress (from a different pointer);
        // ignore this second pointer entirely rather than clobbering it.
        return;
      }
      const point = toNormalized(event.clientX, event.clientY);
      if (!point) return; // touched down in the letterbox padding, outside the picture

      event.preventDefault();
      // Without capture, releasing the pointer outside the video's bounds
      // (e.g. dragging off the edge) never fires pointerup on this element,
      // leaving the mouse button stuck "down" on the host forever. Optional
      // chaining because jsdom's test environment doesn't implement this.
      video!.setPointerCapture?.(event.pointerId);
      activePointerId = event.pointerId;
      downAt = { x: point.x, y: point.y, clientX: event.clientX, clientY: event.clientY };
      activeButton = null;
      longPressTimer = setTimeout(() => {
        if (!downAt) return;
        activeButton = "right";
        send({ type: "pointer-down", x: downAt.x, y: downAt.y, button: "right" });
      }, LONG_PRESS_MS);
    }

    function handlePointerMove(event: PointerEvent) {
      if (!downAt || event.pointerId !== activePointerId) return;
      const point = toNormalized(event.clientX, event.clientY);

      if (activeButton === null) {
        const dx = event.clientX - downAt.clientX;
        const dy = event.clientY - downAt.clientY;
        if (Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;

        if (longPressTimer) clearTimeout(longPressTimer);
        activeButton = "left";
        send({ type: "pointer-down", x: downAt.x, y: downAt.y, button: "left" });
      }

      // Outside the displayed picture (letterbox bars): nothing meaningful
      // to report at this instant, but the gesture itself stays alive.
      if (point) {
        send({ type: "pointer-move", x: point.x, y: point.y });
      }
    }

    function handlePointerUp(event: PointerEvent) {
      if (event.pointerId !== activePointerId) return;
      video!.releasePointerCapture?.(event.pointerId);
      if (longPressTimer) {
        clearTimeout(longPressTimer);
        longPressTimer = null;
      }
      if (!downAt) return;
      const point = toNormalized(event.clientX, event.clientY);

      if (activeButton === null) {
        // Never moved past the drag threshold or the long-press timer: a
        // plain tap. Send a synthetic down+up pair at the same spot.
        send({ type: "pointer-down", x: downAt.x, y: downAt.y, button: "left" });
        send({ type: "pointer-up", x: downAt.x, y: downAt.y, button: "left" });
      } else {
        // Prefer the release point, but fall back to the last known-good
        // (down) position if the pointer lifted inside the letterbox bars —
        // a held button must always be released, never silently dropped.
        const releasePoint = point ?? downAt;
        send({ type: "pointer-up", x: releasePoint.x, y: releasePoint.y, button: activeButton });
      }

      downAt = null;
      activeButton = null;
      activePointerId = null;
    }

    function handlePointerCancel(event: PointerEvent) {
      if (event.pointerId !== activePointerId) return;
      // The browser/OS interrupted the gesture (edge swipe, notification
      // pull-down, pointer capture loss) so pointerup will never fire.
      // Release any held button exactly as unmount-cleanup does.
      releaseHeldButton();
    }

    function handleWheel(event: WheelEvent) {
      event.preventDefault();
      send({ type: "wheel", deltaX: event.deltaX, deltaY: event.deltaY });
    }

    function handleKeyDown(event: KeyboardEvent) {
      pressedKeys.add(event.key);
      send({ type: "key-down", key: event.key });
    }

    function handleKeyUp(event: KeyboardEvent) {
      pressedKeys.delete(event.key);
      send({ type: "key-up", key: event.key });
    }

    function handleBlur() {
      // The page lost focus (tab switch, minimize, etc.) — window keyup
      // listeners won't fire for keys released while unfocused, so any
      // held modifier would otherwise stay "down" on the host indefinitely.
      releaseHeldKeys();
    }

    video.addEventListener("pointerdown", handlePointerDown);
    video.addEventListener("pointermove", handlePointerMove);
    video.addEventListener("pointerup", handlePointerUp);
    video.addEventListener("pointercancel", handlePointerCancel);
    video.addEventListener("wheel", handleWheel);
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", handleBlur);

    return () => {
      // If a button is currently "held" from the host's perspective (mid-drag
      // past the threshold, or a long-press that already fired a right-click
      // pointer-down), tearing down without releasing it would leave the
      // host's mouse button stuck down forever. Send a compensating
      // pointer-up at the last known position before removing listeners.
      releaseHeldButton();
      releaseHeldKeys();
      video.removeEventListener("pointerdown", handlePointerDown);
      video.removeEventListener("pointermove", handlePointerMove);
      video.removeEventListener("pointerup", handlePointerUp);
      video.removeEventListener("pointercancel", handlePointerCancel);
      video.removeEventListener("wheel", handleWheel);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", handleBlur);
    };
  }, [videoRef, channel]);
}
