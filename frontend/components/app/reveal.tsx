'use client';

import { type ComponentProps, useRef } from 'react';
import { useGsapReveal } from '@/hooks/use-gsap-reveal';
import { cn } from '@/lib/shadcn/utils';

interface RevealProps extends Omit<ComponentProps<'div'>, 'ref'> {
  delay?: number;
}

export function Reveal({ className, delay = 0, children, ...props }: RevealProps) {
  const nodeRef = useRef<HTMLDivElement>(null);

  useGsapReveal(nodeRef, { delay, once: true, start: 'top 86%', y: 18 });

  return (
    <div ref={nodeRef} className={cn(className)} {...props}>
      {children}
    </div>
  );
}
