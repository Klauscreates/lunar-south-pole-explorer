/** Screen-space pan at the current focus depth. No terrain/science coordinates change. */
export function panDistance(dx: number, dy: number, depth: number, fovy: number, height: number) {
  if (![dx,dy,depth,fovy,height].every(Number.isFinite) || depth <= 0 || height <= 0 || fovy <= 0 || fovy >= Math.PI) return null;
  const scale = 2 * depth * Math.tan(fovy / 2) / height;
  // Reject discontinuous pointer jumps rather than flinging the camera away.
  if (Math.abs(dx) > height || Math.abs(dy) > height) return null;
  return {right:-dx*scale, up:dy*scale};
}

export function installTouchNavigation(canvas: HTMLElement, controls: {
  interrupt: () => void;
  rotate: (enabled: boolean) => void; pan: (dx: number, dy: number) => void;
  look: (dx: number, dy: number) => void;
}) {
  const touches = new Map<number,{x:number;y:number}>();
  const down = (event: PointerEvent) => {
    controls.interrupt();
    controls.rotate(event.pointerType !== 'touch');
    if (event.pointerType !== 'touch') return;
    touches.set(event.pointerId,{x:event.clientX,y:event.clientY});
    canvas.setPointerCapture(event.pointerId);
  };
  const move = (event: PointerEvent) => {
    const previous=touches.get(event.pointerId);
    if (!previous) return;
    touches.set(event.pointerId,{x:event.clientX,y:event.clientY});
    // Two-finger centroid motion turns the viewing basis; finger separation
    // still drives Cesium's native pinch zoom. No on-screen mode is needed.
    if (touches.size === 1) {
      const dx=event.clientX-previous.x, dy=event.clientY-previous.y;
      controls.pan(dx,dy);
    } else if (touches.size === 2) {
      controls.look((event.clientX-previous.x)/2,(event.clientY-previous.y)/2);
    }
  };
  const end = (event: PointerEvent) => { touches.delete(event.pointerId); };
  canvas.addEventListener('pointerdown',down,{capture:true});
  canvas.addEventListener('pointermove',move,{capture:true});
  canvas.addEventListener('pointerup',end);
  canvas.addEventListener('pointercancel',end);
  canvas.addEventListener('lostpointercapture',end);
  return () => {
    canvas.removeEventListener('pointerdown',down,true);
    canvas.removeEventListener('pointermove',move,true);
    canvas.removeEventListener('pointerup',end);
    canvas.removeEventListener('pointercancel',end);
    canvas.removeEventListener('lostpointercapture',end);
    touches.clear();
  };
}
