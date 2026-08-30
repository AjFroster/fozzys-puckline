import { useEffect, useState } from "react";
import type {
  Index,
  Metrics,
  RatingHistory,
  Ratings,
  SeasonTrack,
  Slate,
  Teams,
} from "../types/contract";

/**
 * Everything is a static JSON file on the same origin, written by the nightly
 * Python job. There is no API to call and nothing to authenticate.
 */
const BASE = "/data/v1";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${BASE}/${path}`, { signal });
  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? "No data published for that date yet."
        : `Could not load data (${response.status}).`,
    );
  }
  return (await response.json()) as T;
}

/** Fetch one published document. `path` of null means "nothing to load yet". */
export function useJson<T>(path: string | null): Loaded<T> {
  const [state, setState] = useState<Loaded<T>>({ data: null, error: null, loading: true });

  useEffect(() => {
    if (path === null) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    const controller = new AbortController();
    setState({ data: null, error: null, loading: true });

    getJson<T>(path, controller.signal)
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const message = cause instanceof Error ? cause.message : "Something went wrong.";
        setState({ data: null, error: message, loading: false });
      });

    return () => controller.abort();
  }, [path]);

  return state;
}

export const useIndex = () => useJson<Index>("index.json");
export const useTeams = () => useJson<Teams>("teams.json");
export const useMetrics = () => useJson<Metrics>("metrics.json");
export const useTrack = () => useJson<SeasonTrack>("track.json");
export const useRatings = () => useJson<Ratings>("ratings/current.json");
export const useRatingHistory = () => useJson<RatingHistory>("ratings/history.json");
export const useSlate = (date: string | null) =>
  useJson<Slate>(date === null ? "latest.json" : `slate/${date}.json`);
