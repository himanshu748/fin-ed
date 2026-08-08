import Image from 'next/image';

const voiceStatus = ['Nikhil · India voice', 'Murf Falcon 2', 'Practice only'] as const;

export function HeroMarketLedger() {
  return (
    <figure
      data-gsap-reveal
      className="relative overflow-hidden rounded-[12px] border border-[var(--ledger-rule)] bg-[var(--surface)] p-2 shadow-[0_18px_50px_rgb(21_35_59/0.10)] sm:p-3"
    >
      <Image
        src="/images/fin-ed-voice-ledger-v1.png"
        width={1568}
        height={1003}
        priority
        sizes="(min-width: 1024px) 470px, (min-width: 640px) 70vw, calc(100vw - 48px)"
        alt="Voice-led learning ledger for Indian market concepts and paper practice"
        className="h-auto w-full rounded-[8px] object-cover"
      />
      <figcaption className="absolute inset-x-4 bottom-4 flex flex-wrap gap-2 sm:inset-x-5 sm:bottom-5">
        {voiceStatus.map((status) => (
          <span
            key={status}
            className="font-data rounded-[8px] border border-[var(--ledger-rule)] bg-[rgb(255_252_245/0.94)] px-2.5 py-2 text-[0.66rem] font-medium tracking-[0.04em] text-[var(--ledger-ink)] shadow-sm backdrop-blur-sm"
          >
            {status}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
