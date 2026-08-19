import { useEffect, type RefObject } from "react";

export type PrimaryButton = "left" | "right";

interface UseInputControlOptions {
  videoRef: RefObject<HTMLVideoElement | null>;
  channel: RTCDataChannel | null;
  // Which mouse button single-finger press/drag/release simulates. A mode
  // toggle in the UI switches this, rather than trying to infer intent
  // from touch timing/finger count — that used to make two fingers double
  // as both scroll AND a held/discrete right click, which was ambiguous to
  // use and to reason about. Two fingers are now scroll only.
  primaryButton: PrimaryButton;
}

type Point = { x: number; y: number };
type TrackedTouch = { clientX: number; clientY: number };

export function useInputControl({ videoRef, channel, primaryButton }: UseInputControlOptions): void {
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
    function toNormalized(clientX: number, clientY: number): Point | null {
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

    // Single finger: press = primaryButton down, move = drag, release =
    // primaryButton up. This mirrors a real mouse button directly, including
    // holding it in place with no movement needed — there is no separate
    // "hold" gesture, pressing and not lifting simply keeps the button down.
    let primaryPointerId: number | null = null;
    let primaryLastPoint: Point | null = null;
    let primaryLastClientX = 0;
    let primaryLastClientY = 0;
    // The button this specific gesture is using — captured at pointer-down
    // from the current primaryButton, so a mode switch mid-gesture (rare,
    // but the button could in principle change between down and up) can't
    // send a down with one button and an up with another.
    let primaryButtonHeld: PrimaryButton | null = null;

    // Two fingers: always a scroll, from the very first movement. There is
    // no click/hold sub-state here anymore — right-click now comes from the
    // primaryButton mode instead, so a second gesture vocabulary for it on
    // two fingers would just be redundant and ambiguous with scrolling.
    const twoFingerTouches = new Map<number, TrackedTouch>();
    let twoFingerActive = false;
    let scrollLastMidpoint: Point | null = null;

    const pressedKeys = new Set<string>();

    function releasePrimary() {
      if (primaryPointerId === null) return;
      const point = primaryLastPoint;
      const button = primaryButtonHeld;
      primaryPointerId = null;
      primaryLastPoint = null;
      primaryButtonHeld = null;
      if (point && button) send({ type: "pointer-up", x: point.x, y: point.y, button });
    }

    function releaseHeldKeys() {
      for (const key of pressedKeys) {
        send({ type: "key-up", key });
      }
      pressedKeys.clear();
    }

    function midpoint(a: TrackedTouch, b: TrackedTouch) {
      return { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 };
    }

    function releaseTwoFingerGesture() {
      twoFingerTouches.clear();
      twoFingerActive = false;
      scrollLastMidpoint = null;
    }

    function handlePointerDown(event: PointerEvent) {
      // A two-finger scroll already tracks two touches; ignore a third
      // finger entirely rather than clobbering it.
      if (twoFingerActive) return;

      if (primaryPointerId !== null && event.pointerId !== primaryPointerId) {
        // A second finger joined while the first was held: cancel that
        // single-finger hold (compensating pointer-up) and start a
        // two-finger scroll instead.
        const firstTouch: TrackedTouch = {
          clientX: primaryLastClientX,
          clientY: primaryLastClientY,
        };
        const firstPointerId = primaryPointerId;
        releasePrimary();

        const secondTouch: TrackedTouch = { clientX: event.clientX, clientY: event.clientY };
        twoFingerTouches.set(firstPointerId, firstTouch);
        twoFingerTouches.set(event.pointerId, secondTouch);
        twoFingerActive = true;
        scrollLastMidpoint = midpoint(firstTouch, secondTouch);
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
      primaryPointerId = event.pointerId;
      primaryLastPoint = point;
      primaryLastClientX = event.clientX;
      primaryLastClientY = event.clientY;
      primaryButtonHeld = primaryButton;
      send({ type: "pointer-down", x: point.x, y: point.y, button: primaryButton });
    }

    function handlePointerMove(event: PointerEvent) {
      if (twoFingerActive) {
        if (!twoFingerTouches.has(event.pointerId)) return;
        twoFingerTouches.set(event.pointerId, { clientX: event.clientX, clientY: event.clientY });
        if (twoFingerTouches.size < 2) return;
        const [a, b] = Array.from(twoFingerTouches.values());

        const mid = midpoint(a, b);
        if (scrollLastMidpoint) {
          // "Natural" scrolling: content follows the fingers, so moving the
          // fingers up (midpoint Y decreases) scrolls the same way a
          // positive-deltaY mouse wheel tick would.
          send({
            type: "wheel",
            deltaX: -(mid.x - scrollLastMidpoint.x),
            deltaY: -(mid.y - scrollLastMidpoint.y),
          });
        }
        scrollLastMidpoint = mid;
        return;
      }

      if (primaryPointerId === null || event.pointerId !== primaryPointerId) return;
      primaryLastClientX = event.clientX;
      primaryLastClientY = event.clientY;
      const point = toNormalized(event.clientX, event.clientY);
      // Outside the displayed picture (letterbox bars): nothing meaningful
      // to report at this instant, but the gesture itself stays alive and
      // the last known-good position is kept for the eventual release.
      if (point) {
        primaryLastPoint = point;
        send({ type: "pointer-move", x: point.x, y: point.y });
      }
    }

    function handlePointerUp(event: PointerEvent) {
      if (twoFingerActive) {
        if (!twoFingerTouches.has(event.pointerId)) return;
        releaseTwoFingerGesture();
        return;
      }

      if (primaryPointerId === null || event.pointerId !== primaryPointerId) return;
      video!.releasePointerCapture?.(event.pointerId);
      const point = toNormalized(event.clientX, event.clientY);
      if (point) primaryLastPoint = point;
      releasePrimary();
    }

    function handlePointerCancel(event: PointerEvent) {
      // The browser/OS interrupted the gesture (edge swipe, notification
      // pull-down, pointer capture loss) so pointerup will never fire.
      if (twoFingerActive) {
        if (twoFingerTouches.has(event.pointerId)) releaseTwoFingerGesture();
        return;
      }
      if (primaryPointerId === null || event.pointerId !== primaryPointerId) return;
      releasePrimary();
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
      // listeners won't fire for keys released while unfocused, and a held
      // button would otherwise stay "down" on the host indefinitely.
      releasePrimary();
      releaseTwoFingerGesture();
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
      // If a button is currently "held" from the host's perspective,
      // tearing down without releasing it would leave it stuck down forever.
      // Send a compensating pointer-up at the last known position first.
      releasePrimary();
      releaseTwoFingerGesture();
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
  }, [videoRef, channel, primaryButton]);
}
