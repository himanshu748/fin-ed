'use client';

import { useEffect, useRef, useState } from 'react';
import { Menu, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

const NAV_ITEMS = [
  { href: '#how-it-works', label: 'How it works' },
  { href: '#topics', label: 'Topics' },
  { href: '#why-the-loss', label: 'Why the loss' },
  { href: '#sources', label: 'Sources' },
] as const;

interface SiteNavProps {
  connectLabel: string;
  isConnecting: boolean;
  onConnect: () => void;
}

function LedgerMark() {
  return (
    <svg
      aria-hidden="true"
      className="size-8 shrink-0"
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect x="3.5" y="3.5" width="25" height="25" rx="5.5" fill="#EAF1FD" stroke="#174EA6" />
      <path
        d="M10 9.5V22.5M14 9.5H23M14 14H21M14 18.5H23M14 23H19"
        stroke="#174EA6"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path
        d="M8 9.5H10M8 14H10M8 18.5H10M8 23H10"
        stroke="#1F6B4F"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function SiteNav({ connectLabel, isConnecting, onConnect }: SiteNavProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [hasScrolled, setHasScrolled] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleScroll = () => setHasScrolled(window.scrollY > 12);
    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    const firstItem = menuRef.current?.querySelector<HTMLElement>('a, button');
    firstItem?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
        menuButtonRef.current?.focus();
        return;
      }

      if (event.key !== 'Tab') return;
      const focusableItems = Array.from(
        menuRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])') ?? []
      );
      const firstItem = focusableItems.at(0);
      const lastItem = focusableItems.at(-1);

      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem?.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem?.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  const closeMenu = () => {
    setIsOpen(false);
    window.requestAnimationFrame(() => menuButtonRef.current?.focus());
  };
  const connect = () => {
    closeMenu();
    onConnect();
  };

  return (
    <header
      className={cn(
        'sticky top-0 z-50 border-b border-transparent bg-[rgb(246_242_232/0.9)] backdrop-blur-md transition-colors duration-200 ease-out',
        (hasScrolled || isOpen) && 'border-[var(--ledger-rule)]'
      )}
    >
      <nav
        className="section-shell flex min-h-18 items-center justify-between gap-4"
        aria-label="Main navigation"
      >
        <a
          href="#top"
          className="flex min-h-11 items-center gap-2 text-[var(--ledger-ink)] no-underline"
          aria-label="FinEd Saathi home"
        >
          <LedgerMark />
          <span className="font-display text-[1.05rem] font-bold tracking-[-0.025em]">
            FinEd Saathi
          </span>
        </a>

        <div className="hidden items-center gap-6 lg:flex">
          <span className="font-data text-[0.68rem] tracking-[0.08em] text-[var(--muted-ink)] uppercase">
            Financial Services · Murf Falcon 2
          </span>
          {NAV_ITEMS.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="flex min-h-10 items-center text-sm font-semibold text-[var(--muted-ink)] transition-colors duration-200 ease-out hover:text-[var(--ledger-blue)]"
            >
              {item.label}
            </a>
          ))}
          <Button type="button" disabled={isConnecting} onClick={onConnect} className="min-w-48">
            {connectLabel}
          </Button>
        </div>

        <button
          ref={menuButtonRef}
          type="button"
          aria-controls="mobile-menu"
          aria-expanded={isOpen}
          aria-label={isOpen ? 'Close navigation' : 'Open navigation'}
          onClick={() => (isOpen ? closeMenu() : setIsOpen(true))}
          className="grid size-11 place-items-center rounded-[10px] border border-[var(--ledger-rule)] bg-[var(--surface)] text-[var(--ledger-ink)] transition-colors duration-200 ease-out hover:border-[var(--ledger-blue)] hover:text-[var(--ledger-blue)] lg:hidden"
        >
          {isOpen ? (
            <X aria-hidden="true" className="size-5" />
          ) : (
            <Menu aria-hidden="true" className="size-5" />
          )}
        </button>
      </nav>

      {isOpen && (
        <div
          id="mobile-menu"
          ref={menuRef}
          role="dialog"
          aria-modal="true"
          aria-label="Site navigation"
          className="section-shell border-t border-[var(--soft-rule)] py-4 lg:hidden"
        >
          <p className="font-data mb-3 text-[0.68rem] tracking-[0.08em] text-[var(--muted-ink)] uppercase">
            Financial Services · Murf Falcon 2
          </p>
          <div className="grid gap-1">
            {NAV_ITEMS.map((item) => (
              <a
                key={item.href}
                href={item.href}
                onClick={closeMenu}
                className="flex min-h-11 items-center rounded-[10px] px-3 font-semibold text-[var(--ledger-ink)] transition-colors duration-200 ease-out hover:bg-[var(--blue-wash)] hover:text-[var(--ledger-blue)]"
              >
                {item.label}
              </a>
            ))}
            <Button
              type="button"
              disabled={isConnecting}
              onClick={connect}
              className="mt-2 min-w-48"
            >
              {connectLabel}
            </Button>
          </div>
        </div>
      )}
    </header>
  );
}
