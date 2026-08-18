import { useEffect, type RefObject } from "react";

// How far a finger has to move from where it touched down before a
// two-finger gesture is treated as a scroll instead of a right-click hold.
const TWO_FINGER_MOVE_THRESHOLD_PX = 20;
// How long two fingers have to stay down without moving before the gesture
// is promoted to a held right button (mirrors a real mouse's right button:
// press, hold, release — not a discrete click fired only at release time).
const TWO_FINGER_HOLD_MS = 400;

interface UseInputControlOptions {
  videoRef: RefObject<HTMLVideoElement | null>;
  channel: RTCDataChannel | null;
}

type Point = { x: number; y: number };
type TrackedTouch = { startX: number; startY: number; clientX: number; clientY: number };

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

    // Single finger: press = left button down, move = drag, release = left
    // button up. This mirrors a real mouse button directly, including
    // holding it in place with no movement needed — there is no separate
    // "hold" gesture, pressing and not lifting simply keeps the button down.
    let primaryPointerId: number | null = null;
    let primaryLastPoint: Point | null = null;
    let primaryLastClientX = 0;
    let primaryLastClientY = 0;

    // Two fingers: held in place past TWO_FINGER_HOLD_MS with no scroll-worthy
    // movement -> promoted to a held right button (mirrors the single-finger
    // left button, including drag-while-held). Movement past the threshold
    // before that timer fires -> a scroll instead. A quick release before
    // either happens still resolves as a discrete right click, the same way
    // a fast press-release of a real mouse button is still a click.
    const twoFingerTouches = new Map<number, TrackedTouch>();
    let twoFingerMode: "pending" | "scroll" | "right-hold" | null = null;
    let twoFingerHoldTimer: ReturnType<typeof setTimeout> | null = null;
    let scrollLastMidpoint: Point | null = null;
    let rightHoldPoint: Point | null = null;

    const pressedKeys = new Set<string>();

    function releasePrimary() {
      if (primaryPointerId === null) return;
      const point = primaryLastPoint;
      primaryPointerId = null;
      primaryLastPoint = null;
      if (point) send({ type: "pointer-up", x: point.x, y: point.y, button: "left" });
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
      if (twoFingerHoldTimer) {
        clearTimeout(twoFingerHoldTimer);
        twoFingerHoldTimer = null;
      }
      if (twoFingerMode === "right-hold" && rightHoldPoint) {
        send({ type: "pointer-up", x: rightHoldPoint.x, y: rightHoldPoint.y, button: "right" });
      }
      twoFingerTouches.clear();
      twoFingerMode = null;
      scrollLastMidpoint = null;
      rightHoldPoint = null;
    }

    function promoteToRightHold() {
      twoFingerHoldTimer = null;
      if (twoFingerMode !== "pending") return;
      const [a, b] = Array.from(twoFingerTouches.values());
      const mid = midpoint(a, b);
      const point = toNormalized(mid.x, mid.y);
      twoFingerMode = "right-hold";
      if (point) {
        rightHoldPoint = point;
        send({ type: "pointer-down", x: point.x, y: point.y, button: "right" });
      }
    }

    function handlePointerDown(event: PointerEvent) {
      // A two-finger gesture (pending/scroll/right-hold) already tracks two
      // touches; ignore a third finger entirely rather than clobbering it.
      if (twoFingerMode) return;

      if (primaryPointerId !== null && event.pointerId !== primaryPointerId) {
        // A second finger joined while the first was held: cancel that
        // single-finger hold (compensating pointer-up) and start tracking a
        // two-finger gesture instead. Which one it becomes — a held right
        // button or a scroll — isn't decided until it resolves (see below).
        const firstTouch: TrackedTouch = {
          startX: primaryLastClientX,
          startY: primaryLastClientY,
          clientX: primaryLastClientX,
          clientY: primaryLastClientY,
        };
        const firstPointerId = primaryPointerId;
        releasePrimary();

        twoFingerTouches.set(firstPointerId, firstTouch);
        twoFingerTouches.set(event.pointerId, {
          startX: event.clientX,
          startY: event.clientY,
          clientX: event.clientX,
          clientY: event.clientY,
        });
        twoFingerMode = "pending";
        twoFingerHoldTimer = setTimeout(promoteToRightHold, TWO_FINGER_HOLD_MS);
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
      send({ type: "pointer-down", x: point.x, y: point.y, button: "left" });
    }

    function handlePointerMove(event: PointerEvent) {
      if (twoFingerMode) {
        if (!twoFingerTouches.has(event.pointerId)) return;
        twoFingerTouches.set(event.pointerId, {
          ...twoFingerTouches.get(event.pointerId)!,
          clientX: event.clientX,
          clientY: event.clientY,
        });
        if (twoFingerTouches.size < 2) return;
        const [a, b] = Array.from(twoFingerTouches.values());

        if (twoFingerMode === "pending") {
          const moved =
            Math.hypot(a.clientX - a.startX, a.clientY - a.startY) > TWO_FINGER_MOVE_THRESHOLD_PX ||
            Math.hypot(b.clientX - b.startX, b.clientY - b.startY) > TWO_FINGER_MOVE_THRESHOLD_PX;
          if (!moved) return;
          if (twoFingerHoldTimer) {
            clearTimeout(twoFingerHoldTimer);
            twoFingerHoldTimer = null;
          }
          twoFingerMode = "scroll";
          scrollLastMidpoint = { x: (a.startX + b.startX) / 2, y: (a.startY + b.startY) / 2 };
        }

        if (twoFingerMode === "right-hold") {
          const holdMid = midpoint(a, b);
          const point = toNormalized(holdMid.x, holdMid.y);
          if (point) {
            rightHoldPoint = point;
            send({ type: "pointer-move", x: point.x, y: point.y });
          }
          return;
        }

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
      if (twoFingerMode) {
        if (!twoFingerTouches.has(event.pointerId)) return;
        if (twoFingerMode === "pending") {
          // Released before the hold threshold or any scroll-worthy
          // movement: a fast press-release is still a click, same as a
          // real mouse button.
          const [a, b] = Array.from(twoFingerTouches.values());
          const tapMid = midpoint(a, b);
          const point = toNormalized(tapMid.x, tapMid.y);
          if (point) {
            send({ type: "pointer-down", x: point.x, y: point.y, button: "right" });
            send({ type: "pointer-up", x: point.x, y: point.y, button: "right" });
          }
        }
        // No-ops for "pending"/"scroll"; sends the release for "right-hold".
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
      if (twoFingerMode) {
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
  }, [videoRef, channel]);
}
