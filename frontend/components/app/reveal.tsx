'use client';

import { type ComponentProps, useEffect, useRef } from 'react';
import { useReducedMotion } from 'motion/react';
import { cn } from '@/lib/shadcn/utils';

interface RevealProps extends Omit<ComponentProps<'div'>, 'ref'> {
  delay?: number;
}

export function Reveal({ className, delay = 0, children, ...props }: RevealProps) {
  const shouldReduceMotion = useReducedMotion();
  const nodeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = nodeRef.current;
    if (shouldReduceMotion || !node || typeof IntersectionObserver === 'undefined') return;

    let animation: Animation | undefined;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        animation = node.animate(
          [
            { opacity: 0, transform: 'translateY(18px)' },
            { opacity: 1, transform: 'translateY(0)' },
          ],
          {
            duration: 220,
            delay: delay * 1000,
            easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
            fill: 'both',
          }
        );
        observer.disconnect();
      },
      { threshold: 0.14 }
    );
    observer.observe(node);

    return () => {
      observer.disconnect();
      animation?.cancel();
    };
  }, [delay, shouldReduceMotion]);

  return (
    <div ref={nodeRef} className={cn(className)} {...props}>
      {children}
    </div>
  );
}
