import { useEffect, useMemo, useState } from 'react';
import { type AgentState } from '@livekit/components-react';

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => setPrefersReducedMotion(mediaQuery.matches);
    updatePreference();
    mediaQuery.addEventListener('change', updatePreference);
    return () => mediaQuery.removeEventListener('change', updatePreference);
  }, []);

  return prefersReducedMotion;
}

export function useAgentAudioVisualizerBarAnimator(
  state: AgentState | undefined,
  columns: number,
  _interval: number
): number[] {
  const prefersReducedMotion = usePrefersReducedMotion();
  void _interval;

  return useMemo(() => {
    if (state !== 'speaking' || prefersReducedMotion) return [];
    return Array.from({ length: columns }, (_, index) => index);
  }, [columns, prefersReducedMotion, state]);
}
