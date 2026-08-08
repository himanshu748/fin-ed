'use client';

import { useEffect, useRef, useState } from 'react';
import { animate } from 'animejs';
import { useReducedMotion } from 'motion/react';

export interface AnimatedNumberOptions {
  duration?: number;
  ease?: string;
  from?: number;
}

export function useAnimatedNumber(value: number, options: AnimatedNumberOptions = {}): number {
  const { duration = 500, ease = 'out(3)', from } = options;
  const shouldReduceMotion = useReducedMotion();
  const displayedValueRef = useRef(from ?? value);
  const animationRef = useRef<ReturnType<typeof animate> | null>(null);
  const [displayedValue, setDisplayedValue] = useState(from ?? value);

  useEffect(() => {
    animationRef.current?.cancel();

    if (shouldReduceMotion) {
      displayedValueRef.current = value;
      setDisplayedValue(value);
      animationRef.current = null;
      return;
    }

    const animatedState = { value: displayedValueRef.current };
    const animation = animate(animatedState, {
      value,
      duration,
      ease,
      onUpdate: () => {
        displayedValueRef.current = animatedState.value;
        setDisplayedValue(animatedState.value);
      },
      onComplete: () => {
        displayedValueRef.current = value;
        setDisplayedValue(value);
      },
    });
    animationRef.current = animation;

    return () => {
      animation.cancel();
      if (animationRef.current === animation) animationRef.current = null;
    };
  }, [duration, ease, shouldReduceMotion, value]);

  return shouldReduceMotion ? value : displayedValue;
}
