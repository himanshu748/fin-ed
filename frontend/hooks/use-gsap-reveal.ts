'use client';

import { type RefObject, useEffect } from 'react';
import { gsap } from 'gsap';

export interface GsapRevealOptions {
  selector?: string;
  y?: number;
  stagger?: number;
  start?: string;
  once?: boolean;
  delay?: number;
}

function observerMargin(start: string): string {
  const viewportStart = /^top\s+(\d+(?:\.\d+)?)%$/.exec(start.trim());
  if (!viewportStart) return start;

  const viewportPercent = Math.min(100, Math.max(0, Number(viewportStart[1])));
  return `0px 0px -${100 - viewportPercent}% 0px`;
}

export function useGsapReveal(
  scopeRef: RefObject<HTMLElement | null>,
  options: GsapRevealOptions = {}
): void {
  const { selector, y = 18, stagger = 0.08, start = 'top 86%', once = true, delay = 0 } = options;

  useEffect(() => {
    const scope = scopeRef.current;
    if (!scope) return;

    const media = gsap.matchMedia();
    let observer: IntersectionObserver | undefined;
    let timeline: gsap.core.Timeline | undefined;

    const context = gsap.context(() => {
      media.add(
        {
          allowMotion: '(prefers-reduced-motion: no-preference)',
          reduceMotion: '(prefers-reduced-motion: reduce)',
        },
        (mediaContext) => {
          const targets = selector ? gsap.utils.toArray<HTMLElement>(selector, scope) : [scope];
          const shouldReduceMotion = mediaContext.conditions?.reduceMotion;

          observer?.disconnect();
          timeline?.kill();

          if (shouldReduceMotion) {
            gsap.set(targets, { autoAlpha: 1, y: 0 });
            return;
          }

          timeline = gsap.timeline({ paused: true }).fromTo(
            targets,
            { autoAlpha: 0, y },
            {
              autoAlpha: 1,
              y: 0,
              duration: 0.55,
              delay,
              ease: 'power2.out',
              stagger,
              clearProps: 'transform,opacity,visibility',
            }
          );

          if (typeof IntersectionObserver === 'undefined') {
            timeline.play(0);
            return;
          }

          observer = new IntersectionObserver(
            ([entry]) => {
              if (entry?.isIntersecting) {
                timeline?.play();
                if (once) observer?.disconnect();
              } else if (!once) {
                timeline?.reverse();
              }
            },
            { rootMargin: observerMargin(start), threshold: 0.01 }
          );
          observer.observe(scope);

          return () => {
            observer?.disconnect();
            timeline?.kill();
          };
        }
      );
    }, scope);

    return () => {
      observer?.disconnect();
      timeline?.kill();
      media.revert();
      context.revert();
    };
  }, [delay, once, scopeRef, selector, stagger, start, y]);
}
