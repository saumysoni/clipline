// A stand-in for @twick/live-player (vite.config.js aliases it here): Twick's timeline only needs the player's shared
// state (current time, seek time, playing or not). Pit Crew's own <video> plays the Short, so Twick's player (its
// canvas renderer and everything under it, ~4 MB) isn't bundled. Same names and behaviour as LivePlayerProvider.
import React, { createContext, useContext, useState } from "react";

export const PLAYER_STATE = { REFRESH: "Refresh", PLAYING: "Playing", PAUSED: "Paused" };
const Ctx = createContext(undefined);

export function LivePlayerProvider({ children }) {
  const [playerState, setPlayerState] = useState(PLAYER_STATE.PAUSED);
  const [seekTime, setSeekTime] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [playerVolume, setPlayerVolume] = useState(1);
  return <Ctx.Provider value={{
    seekTime, playerState, currentTime, playerVolume, getCurrentTime: () => currentTime, setSeekTime,
    setPlayerState: (s) => { if (s === PLAYER_STATE.PAUSED) setSeekTime(currentTime); setPlayerState(s); },
    setCurrentTime, setPlayerVolume,
  }}>{children}</Ctx.Provider>;
}

export function useLivePlayerContext() {
  const c = useContext(Ctx);
  if (c === undefined) throw new Error("useLivePlayerContext must be used within a LivePlayerProvider");
  return c;
}

export function LivePlayer() { return null; }  // never shown: the editor has its own player
