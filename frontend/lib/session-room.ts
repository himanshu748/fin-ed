import { Room } from 'livekit-client';

const SESSION_ROOM_PROPERTY = '__finedLiveKitSessionRoom';

type SessionWindow = Window & {
  [SESSION_ROOM_PROPERTY]?: Room;
};

export function getPersistentSessionRoom(): Room {
  if (typeof window === 'undefined') return new Room();

  const sessionWindow = window as SessionWindow;
  sessionWindow[SESSION_ROOM_PROPERTY] ??= new Room();
  return sessionWindow[SESSION_ROOM_PROPERTY];
}
